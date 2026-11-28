param(
    [string[]]$TestPaths = @("tests")
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot

Push-Location $root

$variables = @(
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "MATCHPOINT_RUN_INGESTION_TESTS",
    "PGOPTIONS"
)

$previous = @{}

foreach ($name in $variables) {
    $previous[$name] = [Environment]::GetEnvironmentVariable(
        $name, "Process"
    )
}

try {

    $password = docker exec matchpoint_postgres printenv POSTGRES_PASSWORD

    if (
        $LASTEXITCODE -ne 0 -or
        [string]::IsNullOrWhiteSpace($password)
    ) {
        throw "Database credentials unavailable"
    }

    $env:POSTGRES_HOST = "127.0.0.1"
    $env:POSTGRES_PORT = "5432"
    $env:POSTGRES_USER = "matchpoint"
    $env:POSTGRES_PASSWORD = $password
    $env:POSTGRES_DB = "matchpoint_ingestion_test"
    $env:MATCHPOINT_RUN_INGESTION_TESTS = "1"

    Remove-Variable password

    Remove-Item Env:PGOPTIONS -ErrorAction SilentlyContinue

    $python = Join-Path $root ".venv\Scripts\python.exe"

    $validation = @"
import os
import subprocess
import sys
import json

from pathlib import Path
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

TABLES = (
    "source_listings",
    "source_listing_history",
    "ingestion_observations",
    "collection_runs",
    "invalid_records",
    "source_checkpoints",
)

def database_state():

    with psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
        connect_timeout=10,
    ) as conn:

        identity = conn.execute("""
            SELECT
                current_database() AS database,
                current_user AS username,
                current_setting('server_encoding') AS encoding,
                system_identifier::TEXT AS cluster
            FROM pg_control_system()
        """).fetchone()

        assert identity == {
            "database": "matchpoint_ingestion_test",
            "username": "matchpoint",
            "encoding": "UTF8",
            "cluster": "7711828057299574822",
        }, identity

        migrations = conn.execute("""
            SELECT *
            FROM public.schema_migrations
            ORDER BY version
        """).fetchall()

        assert [
            int(row["version"])
            for row in migrations
        ] == list(range(1, 10))

        counts = {
            table: conn.execute(
                f"SELECT COUNT(*) AS n FROM bronze.{table}"
            ).fetchone()["n"]
            for table in TABLES
        }

        return {
            "identity": identity,
            "migrations": migrations,
            "counts": counts,
        }

before = database_state()

assert not any(before["counts"].values()), before["counts"]

print("PASS: Database safety preflight", flush=True)
print("PASS: Empty Bronze baseline", flush=True)

artifact = (
    Path(os.environ["LOCALAPPDATA"])
    / "MATCHPOINT"
    / "Validation"
    / datetime.now(timezone.utc).strftime(
        "integration_%Y%m%d_%H%M%S_%f"
    )
)

artifact.mkdir(parents=True, exist_ok=False)

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

save("before.json", before)

command = [
    sys.executable,
    "-m",
    "pytest",
    *sys.argv[1:],
    "-q",
    "--tb=short",
    "-ra",
    "--junitxml",
    str(artifact / "pytest.xml"),
]

result = subprocess.run(command)

after = database_state()

save("after.json", after)

save(
    "result.json",
    {
        "pytest_exit_code": result.returncode,
        "database_unchanged": before == after,
    },
)

print(f"Artifacts: {artifact}", flush=True)

assert before == after, "Database baseline changed"

print("PASS: Bronze baseline restored")
print("PASS: Migration history unchanged")

if result.returncode != 0:
    raise SystemExit(result.returncode)

subprocess.run(
    ["git", "diff", "--check"],
    check=True,
)

print("PASS: Integration regression validation")
"@

    $validation | & $python - @TestPaths

    if ($LASTEXITCODE -ne 0) {
        throw "Integration validation failed"
    }

}
finally {

    foreach ($name in $variables) {

        [Environment]::SetEnvironmentVariable(
            $name,
            $previous[$name],
            "Process"
        )
    }

    Pop-Location

    Write-Host "PASS: Original environment restored"
}
