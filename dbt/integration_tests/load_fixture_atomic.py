"""Atomic Phase 4 fixture loader for isolated acceptance testing."""

import argparse
import hashlib
import json
import os
import sys

from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(ROOT))

from scrapers.storage.postgres import (
    PostgresSettings,
    PostgresStorage,
)

from scrapers.storage.migration_runner import (
    discover_migrations,
)


TARGET = "matchpoint_date_contract_utf8_test"

FIXTURE = (
    ROOT
    / "dbt"
    / "integration_tests"
    / "load_phase4_synthetic_bronze.sql"
)

FIXTURE_SHA256 = (
    "9b142e59f6fde7ead374c92338133caef"
    "831a9d8457c9c1881e351f99874d103"
)

EXPECTED_TABLES = (
    "collection_runs",
    "ingestion_observations",
    "invalid_records",
    "source_checkpoints",
    "source_listing_history",
    "source_listings",
)

EMPTY_COUNTS = {
    table: 0
    for table in EXPECTED_TABLES
}

PHASE4_COUNTS = {
    "collection_runs": 9,
    "ingestion_observations": 0,
    "invalid_records": 0,
    "source_checkpoints": 0,
    "source_listing_history": 2,
    "source_listings": 41,
}

ARABIC_IDS = (
    "22222222-2222-4222-8222-000000000402",
    "22222222-2222-4222-8222-000000000804",
)

ARABIC_HEX = "d8a7d984d982d8a7d987d8b1d8a9"

ADVISORY_LOCK = 710004


class RehearsalRollback(Exception):
    pass


class ForcedValidationFailure(Exception):
    pass


def require(condition, message):

    if not condition:
        raise RuntimeError(message)

    print("PASS:", message, flush=True)


def fixture_body():

    raw = FIXTURE.read_bytes()

    actual_hash = hashlib.sha256(raw).hexdigest()

    require(
        actual_hash == FIXTURE_SHA256,
        "Exact reviewed Phase 4 fixture checksum",
    )

    require(
        not raw.startswith(b"\xef\xbb\xbf"),
        "Fixture has no UTF-8 BOM",
    )

    text = raw.decode("utf-8", errors="strict")

    require(
        text.encode("utf-8") == raw,
        "Strict UTF-8 byte preservation",
    )

    require(
        "\ufffd" not in text,
        "No Unicode replacement characters",
    )

    lines = text.splitlines(keepends=True)

    meaningful = [
        index
        for index, line in enumerate(lines)
        if line.strip()
        and not line.lstrip().startswith("--")
    ]

    require(
        len(meaningful) >= 3,
        "Nonempty fixture body",
    )

    first = meaningful[0]
    last = meaningful[-1]

    require(
        lines[first].strip().upper() == "BEGIN;",
        "Expected outer BEGIN",
    )

    require(
        lines[last].strip().upper() == "COMMIT;",
        "Expected outer COMMIT",
    )

    lines[first] = "\n"
    lines[last] = "\n"

    body = "".join(lines)

    require(
        TARGET in body,
        "Fixture authorizes target database",
    )

    return body


def identity(conn, expected_read_only):

    row = conn.execute("""
        SELECT
            CURRENT_DATABASE() AS database_name,
            CURRENT_USER AS database_user,
            CURRENT_SETTING('server_encoding') AS server_encoding,
            CURRENT_SETTING('client_encoding') AS client_encoding,
            CURRENT_SETTING('transaction_read_only') AS read_only,
            (
                SELECT oid::TEXT
                FROM pg_database
                WHERE datname = CURRENT_DATABASE()
            ) AS database_oid,
            (
                SELECT system_identifier::TEXT
                FROM pg_control_system()
            ) AS system_identifier
    """).fetchone()

    require(
        row["database_name"] == TARGET,
        "Authorized database identity",
    )

    require(
        row["database_user"] == "matchpoint",
        "Authorized database user",
    )

    require(
        row["server_encoding"] == "UTF8"
        and row["client_encoding"] == "UTF8",
        "Server and client use UTF-8",
    )

    require(
        row["read_only"] == expected_read_only,
        f"Expected transaction read-only={expected_read_only}",
    )

    return dict(row)


def registry(conn):

    rows = conn.execute("""
        SELECT
            version,
            migration_name,
            checksum,
            applied_at,
            execution_time_ms
        FROM public.schema_migrations
        ORDER BY version
    """).fetchall()

    return [dict(row) for row in rows]


def verify_registry(conn):

    migrations = discover_migrations()

    require(
        [m.version for m in migrations]
        == list(range(1, 10)),
        "Nine production migrations discovered",
    )

    expected = [
        (m.version, m.name, m.checksum)
        for m in migrations
    ]

    actual_rows = registry(conn)

    actual = [
        (
            row["version"],
            row["migration_name"],
            row["checksum"],
        )
        for row in actual_rows
    ]

    require(
        actual == expected,
        "Production migration registry matches files",
    )

    return actual_rows


def table_counts(conn):

    rows = conn.execute("""
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'bronze'
        ORDER BY tablename
    """).fetchall()

    actual = tuple(
        row["tablename"]
        for row in rows
    )

    require(
        actual == EXPECTED_TABLES,
        (
            "Exact Bronze schema contract; "
            f"actual={actual}"
        ),
    )

    counts = {}

    for table in EXPECTED_TABLES:

        counts[table] = conn.execute(
            f'SELECT COUNT(*) AS n FROM bronze."{table}"'
        ).fetchone()["n"]

    print(
        "Bronze counts:",
        json.dumps(counts, sort_keys=True),
        flush=True,
    )

    return counts


def fingerprints(conn):

    result = {}

    for table in EXPECTED_TABLES:

        row = conn.execute(f"""
            SELECT ENCODE(
                SHA256(
                    CONVERT_TO(
                        COALESCE(
                            STRING_AGG(
                                row_hash,
                                ''
                                ORDER BY row_hash
                            ),
                            ''
                        ),
                        'UTF8'
                    )
                ),
                'hex'
            ) AS fingerprint
            FROM (
                SELECT ENCODE(
                    SHA256(
                        CONVERT_TO(
                            TO_JSONB(t)::TEXT,
                            'UTF8'
                        )
                    ),
                    'hex'
                ) AS row_hash
                FROM bronze."{table}" t
            ) hashes
        """).fetchone()

        result[table] = row["fingerprint"]

    return result


def snapshot(conn):

    return {
        "counts": table_counts(conn),
        "fingerprints": fingerprints(conn),
        "registry": verify_registry(conn),
    }


def acquire_locks(conn):

    conn.execute("SET LOCAL lock_timeout = '10s'")

    conn.execute(
        "SET LOCAL statement_timeout = '120s'"
    )

    conn.execute("SET LOCAL timezone = 'UTC'")

    conn.execute("SET LOCAL datestyle = 'ISO, YMD'")

    conn.execute(
        "SELECT pg_advisory_xact_lock(%s)",
        (ADVISORY_LOCK,),
    )

    conn.execute("""
        LOCK TABLE public.schema_migrations
        IN SHARE MODE
    """)

    for table in EXPECTED_TABLES:

        conn.execute(
            f'LOCK TABLE bronze."{table}" '
            'IN SHARE ROW EXCLUSIVE MODE'
        )

    print(
        "PASS: Transaction-level advisory and table locks acquired",
        flush=True,
    )


def verify_phase4(conn):

    counts = table_counts(conn)

    require(
        counts == PHASE4_COUNTS,
        "Exact Phase 4 row counts",
    )

    unexpected = conn.execute("""
        SELECT COUNT(*) AS n
        FROM bronze.source_listings l
        LEFT JOIN bronze.collection_runs r
            ON r.run_id = l.last_collection_run_id
        WHERE r.collection_scope
            IS DISTINCT FROM 'synthetic_phase4'
    """).fetchone()["n"]

    require(
        unexpected == 0,
        "All listings belong to Phase 4 collection scope",
    )

    unexpected_runs = conn.execute("""
        SELECT COUNT(*) AS n
        FROM bronze.collection_runs
        WHERE collection_scope
            IS DISTINCT FROM 'synthetic_phase4'
    """).fetchone()["n"]

    require(
        unexpected_runs == 0,
        "All collection runs belong to Phase 4",
    )

    rows = conn.execute("""
        SELECT
            source_listing_id::TEXT AS listing_id,
            location,
            ENCODE(
                CONVERT_TO(location, 'UTF8'),
                'hex'
            ) AS location_hex,
            CHAR_LENGTH(location) AS characters,
            OCTET_LENGTH(location) AS bytes
        FROM bronze.source_listings
        WHERE source_listing_id::TEXT = ANY(%s)
        ORDER BY source_listing_id
    """, (list(ARABIC_IDS),)).fetchall()

    require(
        len(rows) == 2,
        "Both expected Arabic listings exist",
    )

    require(
        {row["listing_id"] for row in rows}
        == set(ARABIC_IDS),
        "Expected Arabic listing identities",
    )

    for row in rows:

        require(
            row["location_hex"] == ARABIC_HEX
            and row["characters"] == 7
            and row["bytes"] == 14,
            (
                "Exact Arabic UTF-8 bytes: "
                + row["listing_id"]
            ),
        )

    suspicious = []

    for table in EXPECTED_TABLES:

        rows = conn.execute(f"""
            SELECT
                field.key AS field_name,
                COUNT(*) AS affected_rows
            FROM bronze."{table}" t
            CROSS JOIN LATERAL
                JSONB_EACH(TO_JSONB(t)) field
            WHERE JSONB_TYPEOF(field.value) = 'string'
              AND (
                  field.value #>> '{{}}'
                      LIKE '%' || CHR(65533) || '%'
                  OR field.value #>> '{{}}'
                      ~ '[?]{{3,}}'
              )
            GROUP BY field.key
        """).fetchall()

        for row in rows:

            suspicious.append({
                "table": table,
                **dict(row),
            })

    require(
        not suspicious,
        f"No suspicious scalar text corruption: {suspicious}",
    )

    precision = conn.execute("""
        SELECT
            published_at_precision AS precision,
            COUNT(*) AS n
        FROM bronze.source_listings
        GROUP BY published_at_precision
    """).fetchall()

    distribution = {
        row["precision"]: row["n"]
        for row in precision
    }

    require(
        distribution == {
            "date_only": 37,
            "exact": 4,
        },
        "Expected publication precision distribution",
    )

    invalid_dates = conn.execute("""
        SELECT COUNT(*) AS n
        FROM bronze.source_listings
        WHERE (
            published_at_precision = 'date_only'
            AND (
                published_at IS NOT NULL
                OR published_at_raw IS NULL
                OR NOT PG_INPUT_IS_VALID(
                    published_at_raw,
                    'date'
                )
            )
        )
        OR (
            published_at_precision = 'exact'
            AND (
                published_at IS NULL
                OR NOT ISFINITE(published_at)
            )
        )
    """).fetchone()["n"]

    require(
        invalid_dates == 0,
        "Phase 4 publication date contract",
    )

    return counts


def main():

    parser = argparse.ArgumentParser()

    modes = parser.add_mutually_exclusive_group(
        required=True
    )

    modes.add_argument(
        "--rehearse",
        action="store_true",
    )

    modes.add_argument(
        "--force-failure",
        action="store_true",
    )

    modes.add_argument(
        "--execute",
        action="store_true",
    )

    args = parser.parse_args()

    mode = (
        "rehearse"
        if args.rehearse
        else "force_failure"
        if args.force_failure
        else "execute"
    )

    artifact = (
        Path(os.environ["LOCALAPPDATA"])
        / "MATCHPOINT"
        / "Validation"
        / "date_precision_20261127_103356_274"
        / (
            "atomic_phase4_"
            + mode
            + "_"
            + datetime.now().strftime(
                "%Y%m%d_%H%M%S_%f"
            )
        )
    )

    artifact.mkdir(
        parents=True,
        exist_ok=False,
    )

    def save(name, data):

        (artifact / name).write_text(
            json.dumps(
                data,
                indent=2,
                default=str,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    print("MODE:", mode)
    print("ARTIFACT DIRECTORY:", artifact)

    body = fixture_body()

    settings = PostgresSettings.from_config(
        host="127.0.0.1",
        database=TARGET,
    )

    storage = PostgresStorage(settings)

    with storage.connect(read_only=True) as conn:

        initial_identity = identity(conn, "on")

        conn.execute("SET LOCAL timezone = 'UTC'")
        conn.execute("SET LOCAL datestyle = 'ISO, YMD'")

        before = snapshot(conn)

        require(
            before["counts"] == EMPTY_COUNTS,
            "Initial Bronze state is empty",
        )

    save("identity.json", initial_identity)
    save("before.json", before)

    loaded = None
    outcome = None

    try:

        with storage.connect(read_only=False) as conn:

            current_identity = identity(conn, "off")

            for key in (
                "database_name",
                "database_user",
                "database_oid",
                "system_identifier",
            ):

                require(
                    current_identity[key]
                    == initial_identity[key],
                    f"Write connection identity agrees: {key}",
                )

            acquire_locks(conn)

            locked_before = snapshot(conn)

            require(
                locked_before == before,
                "Database unchanged after lock acquisition",
            )

            conn.execute(
                """
                SELECT SET_CONFIG(
                    'matchpoint.expected_test_database',
                    %s,
                    TRUE
                )
                """,
                (TARGET,),
            )

            print(
                "Executing reviewed fixture body...",
                flush=True,
            )

            conn.execute(
                body,
                prepare=False,
            )

            require(
                conn.info.transaction_status.name
                == "INTRANS",
                "Fixture remains inside open transaction",
            )

            verify_phase4(conn)

            loaded = snapshot(conn)

            require(
                loaded["registry"] == before["registry"],
                "Migration registry unchanged inside transaction",
            )

            save("loaded_uncommitted.json", loaded)

            if args.force_failure:

                raise ForcedValidationFailure(
                    "Intentional post-load validation failure"
                )

            if args.rehearse:

                raise RehearsalRollback(
                    "Intentional rehearsal rollback"
                )

        outcome = "committed"

    except RehearsalRollback:

        if not args.rehearse:
            raise

        outcome = "rehearsal_rolled_back"

        print("PASS: Rehearsal rollback requested")

    except ForcedValidationFailure:

        if not args.force_failure:
            raise

        outcome = "forced_failure_rolled_back"

        print("PASS: Forced validation failure triggered")

    require(
        loaded is not None,
        "Fixture reached post-load validation",
    )

    with storage.connect(read_only=True) as conn:

        final_identity = identity(conn, "on")

        require(
            final_identity == initial_identity,
            "Final verification uses original database",
        )

        conn.execute("SET LOCAL timezone = 'UTC'")
        conn.execute("SET LOCAL datestyle = 'ISO, YMD'")

        after = snapshot(conn)

        if args.execute:

            require(
                after == loaded,
                "Committed state equals validated state",
            )

            verify_phase4(conn)

        else:

            require(
                after == before,
                "All six Bronze fingerprints and registry restored",
            )

            require(
                after["counts"] == EMPTY_COUNTS,
                "No fixture rows persisted",
            )

    save("after.json", after)

    save(
        "summary.json",
        {
            "mode": mode,
            "database": TARGET,
            "outcome": outcome,
            "validated_loaded_counts": loaded["counts"],
            "final_counts": after["counts"],
            "registry_unchanged":
                before["registry"] == after["registry"],
            "fixture_sha256": FIXTURE_SHA256,
        },
    )

    print("\n========== ATOMIC LOADER SUMMARY ==========")
    print("Outcome:", outcome)
    print("Loaded listings:", loaded["counts"]["source_listings"])
    print("Final listings:", after["counts"]["source_listings"])
    print("ARTIFACT DIRECTORY:", artifact)
    print("PASS: Atomic loader validation completed")


if __name__ == "__main__":
    main()
