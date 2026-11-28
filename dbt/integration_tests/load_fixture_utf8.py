"""Load authorized MATCHPOINT integration fixtures using UTF-8 bytes."""

import argparse
import hashlib
import json
import os
import subprocess

from datetime import datetime
from pathlib import Path


CONTAINER = "matchpoint_postgres"

DATABASE = "matchpoint_date_contract_utf8_test"

USER = "matchpoint"

FIXTURE_ROOT = Path(__file__).resolve().parent

PROJECT_ROOT = FIXTURE_ROOT.parent.parent

MIGRATIONS_ROOT = PROJECT_ROOT / "database" / "migrations"

ALLOWED_FIXTURES = {
    "phase4": "load_phase4_synthetic_bronze.sql",
    "phase5-edge": "load_phase5_edge_cases_synthetic.sql",
    "phase5-enrichment":
        "load_phase5_gold_skills_categories_enrichment.sql",
}


def require(condition, message):

    if not condition:
        raise RuntimeError(message)

    print("PASS:", message, flush=True)


def sha256(raw):

    return hashlib.sha256(raw).hexdigest()


def psql_command(read_only):

    options = (
        "-c timezone=UTC "
        "-c datestyle=ISO,YMD "
        "-c default_transaction_read_only="
        + ("on" if read_only else "off")
    )

    return [
        "docker", "exec", "-i",
        "-e", "PGCLIENTENCODING=UTF8",
        "-e", "PGOPTIONS=" + options,
        CONTAINER,
        "psql",
        "-X",
        "-v", "ON_ERROR_STOP=1",
        "-U", USER,
        "-d", DATABASE,
    ]


def query_json(query):

    result = subprocess.run(
        psql_command(read_only=True)
        + ["-q", "-A", "-t", "-c", query],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if result.returncode != 0:

        raise RuntimeError(
            result.stderr.decode(
                "utf-8", errors="replace"
            )
        )

    return json.loads(
        result.stdout.decode("utf-8", errors="strict")
    )


def database_state():

    return query_json("""
        SELECT JSONB_BUILD_OBJECT(
            'database', CURRENT_DATABASE(),
            'server_encoding',
                CURRENT_SETTING('server_encoding'),
            'client_encoding',
                CURRENT_SETTING('client_encoding'),
            'read_only',
                CURRENT_SETTING('transaction_read_only'),
            'listings',
                (SELECT COUNT(*) FROM bronze.source_listings),
            'registry',
                (
                    SELECT JSONB_AGG(
                        TO_JSONB(m) ORDER BY version
                    )
                    FROM public.schema_migrations m
                )
        )
    """)


def expected_migrations():

    expected = []

    for path in sorted(MIGRATIONS_ROOT.glob("*.sql")):

        text = path.read_bytes().decode("utf-8-sig")

        normalized = (
            text.replace("\r\n", "\n")
                .replace("\r", "\n")
        )

        version = int(path.name.split("_", 1)[0])

        expected.append({
            "version": version,
            "migration_name": path.name,
            "checksum": sha256(
                normalized.encode("utf-8")
            ),
        })

    require(
        [item["version"] for item in expected]
        == list(range(1, 10)),
        "Expected migration versions 001 through 009",
    )

    return expected


def verify_database(state):

    require(
        state["database"] == DATABASE,
        "Authorized fixture database",
    )

    require(
        state["server_encoding"] == "UTF8"
        and state["client_encoding"] == "UTF8",
        "UTF-8 server and client encoding",
    )

    require(
        state["read_only"] == "on",
        "Read-only preflight connection",
    )

    registry = [
        {
            "version": row["version"],
            "migration_name": row["migration_name"],
            "checksum": row["checksum"],
        }
        for row in state["registry"]
    ]

    require(
        registry == expected_migrations(),
        "Migration names and checksums verified",
    )


def verify_unicode_transport():

    probe = "\u0627\u0644\u0642\u0627\u0647\u0631\u0629"

    expected = probe.encode("utf-8").hex()

    sql = (
        "SELECT ENCODE(CONVERT_TO('"
        + probe
        + "', 'UTF8'), 'hex');\n"
    ).encode("utf-8")

    result = subprocess.run(
        psql_command(read_only=True)
        + ["-q", "-A", "-t"],
        input=sql,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    require(
        result.returncode == 0,
        "Unicode transport probe executed",
    )

    require(
        result.stdout.decode("ascii").strip() == expected,
        "Arabic UTF-8 byte-for-byte roundtrip",
    )


def verify_phase4():

    result = query_json("""
        SELECT JSONB_BUILD_OBJECT(
            'listing_count',
                (SELECT COUNT(*) FROM bronze.source_listings),
            'history_count',
                (SELECT COUNT(*) FROM bronze.source_listing_history),
            'collection_run_count',
                (SELECT COUNT(*) FROM bronze.collection_runs),
            'arabic_locations',
                (
                    SELECT JSONB_OBJECT_AGG(
                        source_listing_id::TEXT,
                        ENCODE(CONVERT_TO(location, 'UTF8'), 'hex')
                    )
                    FROM bronze.source_listings
                    WHERE source_listing_id IN (
                        '22222222-2222-4222-8222-000000000402',
                        '22222222-2222-4222-8222-000000000804'
                    )
                )
        )
    """)

    expected_hex = "d8a7d984d982d8a7d987d8b1d8a9"

    require(
        result["listing_count"] == 41,
        "41 expected Phase 4 listings",
    )

    require(
        result["history_count"] == 2,
        "Two expected history records",
    )

    require(
        result["collection_run_count"] == 9,
        "Nine expected collection runs",
    )

    require(
        result["arabic_locations"] == {
            "22222222-2222-4222-8222-000000000402":
                expected_hex,
            "22222222-2222-4222-8222-000000000804":
                expected_hex,
        },
        "Both Arabic locations preserved byte-for-byte",
    )

    return result


def main():

    import sys as _execution_guard_sys
    if any(
        arg.startswith('--')
        and len(arg) > 2
        and '--execute'.startswith(arg)
        for arg in _execution_guard_sys.argv[1:]
    ):
        raise RuntimeError(
            'Legacy execution disabled; use the atomic loader'
        )

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "fixture",
        choices=sorted(ALLOWED_FIXTURES),
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute fixture after successful preflight",
    )

    args = parser.parse_args()

    path = FIXTURE_ROOT / ALLOWED_FIXTURES[args.fixture]

    raw = path.read_bytes()

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

    require(
        DATABASE in text,
        "Fixture explicitly authorizes target database",
    )

    print("Fixture:", path.name)
    print("SHA256:", sha256(raw))
    print("Bytes:", len(raw))

    # Phase 5 requires separate stage-specific state gates.
    # Keep it disabled until those contracts are validated.

    if args.fixture != "phase4":

        raise RuntimeError(
            "Phase 5 execution is not enabled yet"
        )

    before = database_state()

    verify_database(before)

    require(
        before["listings"] == 0,
        "Phase 4 requires an empty listing table",
    )

    expected_tables = {
        "collection_runs",
        "ingestion_observations",
        "invalid_records",
        "source_checkpoints",
        "source_listing_history",
        "source_listings",
    }

    actual_tables = query_json("""
        SELECT COALESCE(
            JSONB_AGG(tablename ORDER BY tablename),
            '[]'::JSONB
        )
        FROM pg_tables
        WHERE schemaname = 'bronze'
    """)

    actual_set = set(actual_tables)

    require(
        actual_set == expected_tables,
        (
            "Exact Bronze schema contract; "
            f"missing={sorted(expected_tables - actual_set)}; "
            f"unexpected={sorted(actual_set - expected_tables)}"
        ),
    )

    table_counts = {}

    for table in actual_tables:

        require(
            table in expected_tables,
            f"Authorized Bronze table: {table}",
        )

        table_counts[table] = query_json(
            f'SELECT TO_JSONB(COUNT(*)) FROM bronze."{table}"'
        )

    print(
        "Bronze counts:",
        json.dumps(table_counts, sort_keys=True),
    )

    require(
        all(count == 0 for count in table_counts.values()),
        "All six Bronze tables are empty",
    )

    verify_unicode_transport()

    if not args.execute:

        print("PASS: Preflight completed; no fixture executed")
        return

    artifact = (
        Path(os.environ["LOCALAPPDATA"])
        / "MATCHPOINT"
        / "Validation"
        / (
            "utf8_fixture_"
            + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        )
    )

    artifact.mkdir(parents=True, exist_ok=False)

    def save(name, value):

        (artifact / name).write_text(
            json.dumps(
                value,
                indent=2,
                ensure_ascii=False,
                default=str,
            ),
            encoding="utf-8",
        )

    save("preflight.json", before)

    save("fixture_metadata.json", {
        "database": DATABASE,
        "fixture": path.name,
        "sha256": sha256(raw),
        "bytes": len(raw),
    })

    # Session-level guard required by existing fixtures.
    prefix = (
        "SET matchpoint.expected_test_database = '"
        + DATABASE
        + "';\n"
    ).encode("ascii")

    require(
        path.read_bytes() == raw,
        "Fixture unchanged since preflight",
    )

    print("Artifact directory:", artifact)

    result = subprocess.run(
        psql_command(read_only=False),
        input=prefix + raw + b"\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    (artifact / "psql_stdout.log").write_bytes(
        result.stdout
    )

    (artifact / "psql_stderr.log").write_bytes(
        result.stderr
    )

    save("execution_result.json", {
        "exit_code": result.returncode,
    })

    print(
        result.stdout.decode(
            "utf-8", errors="replace"
        )
    )

    if result.stderr:

        print(
            result.stderr.decode(
                "utf-8", errors="replace"
            )
        )

    after = database_state()

    save("post_execution_state.json", after)

    require(
        after["registry"] == before["registry"],
        "Migration registry unchanged",
    )

    require(
        result.returncode == 0,
        "Fixture SQL execution successful",
    )

    verified = verify_phase4()

    save("phase4_verification.json", verified)

    require(
        path.read_bytes() == raw,
        "Original fixture file unchanged",
    )

    print("PASS: UTF-8 Phase 4 fixture loading completed")


if __name__ == "__main__":
    main()
