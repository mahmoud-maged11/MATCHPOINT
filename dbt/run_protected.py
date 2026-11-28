from __future__ import annotations

import os
import sys
import time
import subprocess

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scrapers.storage.concurrency import (
    ConcurrencyManager,
    LockUnavailableError,
    LockConnectionLostError,
)


STAGES = ("seed", "run", "test")


def verify_session(connection):

    ConcurrencyManager.ensure_connection(connection)

    try:

        connection.execute("SELECT 1").fetchone()

    except Exception as error:

        raise LockConnectionLostError(
            "Warehouse protection session lost"
        ) from error



class PublicationBlockedError(RuntimeError):
    pass


def verify_publication_ready(connection):

    rows = connection.execute("""
        SELECT r.run_id, r.source_name
        FROM bronze.collection_runs AS r
        WHERE r.status = 'running'
          AND (
              EXISTS (
                  SELECT 1
                  FROM bronze.ingestion_observations AS o
                  WHERE o.collection_run_id = r.run_id
              )
              OR EXISTS (
                  SELECT 1
                  FROM bronze.source_listing_history AS h
                  WHERE h.collection_run_id = r.run_id
              )
              OR EXISTS (
                  SELECT 1
                  FROM bronze.source_listings AS s
                  WHERE s.last_collection_run_id = r.run_id
              )
              OR EXISTS (
                  SELECT 1
                  FROM bronze.invalid_records AS i
                  WHERE i.collection_run_id = r.run_id
              )
          )
        ORDER BY r.run_id
    """).fetchall()

    if rows:
        identities = ", ".join(
            f"{row[1]}:{row[0]}" for row in rows
        )

        raise PublicationBlockedError(
            "Unfinalized persisted runs: " + identities
        )


def execute_protected(manager, runner, *, publication_gate=None):


    with manager.warehouse() as connection:

        verify_session(connection)

        if publication_gate is not None:
            publication_gate(connection)

        for stage in STAGES:

            verify_session(connection)

            exit_code = runner(stage, connection)

            verify_session(connection)

            if exit_code != 0:
                return exit_code

        return 0


def run_stage(stage, connection):

    dbt = ROOT / ".venv312" / "Scripts" / "dbt.exe"

    if not dbt.is_file():
        raise FileNotFoundError(dbt)

    target = os.environ.get(
        "MATCHPOINT_DBT_TARGET",
        "test",
    )

    command = [
        str(dbt),
        stage,
        "--target", target,
        "--profiles-dir", ".",
        "--no-use-colors",
        "--warn-error",
    ]

    print(
        f"Starting protected dbt {stage}",
        flush=True,
    )

    process = subprocess.Popen(
        command,
        cwd=ROOT / "dbt",
        env=os.environ.copy(),
    )

    try:

        while process.poll() is None:

            verify_session(connection)

            time.sleep(0.5)

        return process.returncode

    finally:

        if process.poll() is None:

            process.terminate()

            try:
                process.wait(timeout=10)

            except subprocess.TimeoutExpired:

                process.kill()
                process.wait()


def main():

    import psycopg

    target = os.environ.get(
        "MATCHPOINT_DBT_TARGET",
        "test",
    )

    if target not in ("test", "dev"):
        raise ValueError("Unsupported dbt target")

    database_variable = (
        "POSTGRES_TEST_DB"
        if target == "test"
        else "POSTGRES_DB"
    )

    database = os.environ[database_variable]

    def connect():

        connection = psycopg.connect(
            host=os.environ.get(
                "POSTGRES_HOST", "127.0.0.1"
            ),
            port=int(os.environ.get(
                "POSTGRES_PORT", "5432"
            )),
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            dbname=database,
            autocommit=True,
            connect_timeout=5,
            options="-c statement_timeout=5000",
        )

        try:

            actual = connection.execute(
                "SELECT current_database()"
            ).fetchone()[0]

            if actual != database:
                raise RuntimeError(
                    "Database identity mismatch"
                )

            return connection

        except BaseException:

            connection.close()
            raise

    manager = ConcurrencyManager(
        connect,
        timeout=30,
        poll_interval=0.2,
    )

    try:

        result = execute_protected(
            manager,
            run_stage,
            publication_gate=verify_publication_ready,
        )

    except PublicationBlockedError as error:

        print(str(error), file=sys.stderr)

        return 5

    except LockUnavailableError as error:

        print(str(error), file=sys.stderr)

        return 4

    if result == 0:

        print(
            "PASS: Protected warehouse stages completed"
        )

    return result


if __name__ == "__main__":

    raise SystemExit(main())
