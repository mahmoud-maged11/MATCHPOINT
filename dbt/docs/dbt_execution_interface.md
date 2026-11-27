# Standard dbt Execution Interface (Local, Airflow, Docker & CI/CD)

## Current Warehouse Validation

The latest warehouse technical review was completed on
2026-11-27.

Current acceptance baseline:

- 44 dbt models.
- 483 passing dbt data tests.
- 41 baseline listings and 33 canonical opportunities.
- 52 expanded listings and 44 canonical opportunities.
- All 52 expanded source mappings preserved.
- Silver mapping idempotency passed.
- All 20 Gold snapshot comparisons passed.
- All eight supported sources represented.

Earlier results of 461 tests, 32 baseline opportunities
and 43 expanded opportunities are historical unless
explicitly identified otherwise.

See `dbt/docs/warehouse_review_2026_11_27.md` from the
repository root for the complete technical review,
current acceptance results and remaining limitations.

Synthetic acceptance does not establish real-data ingestion
or production readiness.

**Project:** `matchpoint`
**Project Version:** `1.0.0`
**Target Warehouse:** PostgreSQL 16
**Physical Schemas:** `bronze`, `silver`, `gold`
**Required Migrations:** `database/migrations/001..007`

**Reviewed Runtime:**

- Python 3.12.10
- dbt-core 1.12.7
- dbt-postgres 1.11.0

The standard execution entry point is `dbt/run_dbt.py`.

---

## 1. Runtime & Dependency Requirements

| Requirement | Specification | Reference |
|---|---|---|
| Python | 3.12.x in a dedicated virtual environment | `dbt/README.md` |
| dbt Core | `1.12.7` | `dbt/requirements.txt` |
| PostgreSQL Adapter | `1.11.0` | `dbt/requirements.txt` |
| Database | PostgreSQL 16.x | `docker-compose.yml` |
| External dbt Hub Packages | None required | `dbt/macros/` |

Keep the dbt Python environment separate from the scraper environment.

Direct dbt dependencies are pinned. A complete transitive dependency
lock is not currently maintained.

Upgrade dependencies only after compatibility and regression testing.

### Windows Installation

Run from the repository root:

```powershell
py -3.12 -m venv "$env:USERPROFILE\venvs\matchpoint-dbt"

$dbtPython = Join-Path $env:USERPROFILE "venvs\matchpoint-dbt\Scripts\python.exe"

& $dbtPython -m pip install -r dbt/requirements.txt

if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed."
}

& $dbtPython -m pip check

if ($LASTEXITCODE -ne 0) {
    throw "Dependency validation failed."
}
```

### Linux Installation

```bash
python3.12 -m venv "$HOME/venvs/matchpoint-dbt"

DBT_PYTHON="$HOME/venvs/matchpoint-dbt/bin/python"

"$DBT_PYTHON" -m pip install --no-cache-dir -r dbt/requirements.txt &&
"$DBT_PYTHON" -m pip check
```

Linux, Docker, and Airflow execution examples are integration
templates pending environment-specific validation.

---

## 2. Environment Variables & Profile Configuration

Never commit `dbt/profiles.yml` or `.env`.

Derive the local profile from `dbt/profiles.yml.example`.

Inject credentials through environment variables or an approved
secret-management mechanism.

| Variable | Required | Default | Description |
|---|---|---|---|
| `POSTGRES_PASSWORD` | Yes | None | PostgreSQL password injected at runtime. |
| `POSTGRES_HOST` | No | `localhost` | Database hostname. Use `postgres` inside the Compose network. |
| `POSTGRES_PORT` | No | `5432` | PostgreSQL port. |
| `POSTGRES_USER` | No | `matchpoint` | Database role used by dbt. |
| `POSTGRES_DB` | No | `matchpoint` | Database for the dev target. |
| `POSTGRES_TEST_DB` | No | `matchpoint_test` | Database for the test target. |
| `DBT_TARGET` | No | `dev` | Active profile target. |
| `DBT_SCHEMA` | No | `silver` | Fallback schema. |
| `DBT_THREADS` | No | `4` | Parallel dbt worker threads. |
| `MATCHPOINT_DBT_JIT` | No | `off` | Runner-managed PostgreSQL JIT mode. Accepts `on` or `off`. |
| `PGOPTIONS` | No | None | Additional PostgreSQL connection options. |

### Environment Separation

#### Development

- Target: `dev`.
- Default database: `matchpoint`.
- Used for integrated local development.
- Synthetic fixture scripts must never execute against this database.

#### Testing

- Target: `test`.
- Default database: `matchpoint_test`.
- Independent review database: `matchpoint_dbt_review_test`.
- Apply all seven Bronze migrations before running dbt.
- Verify the actual database connection before executing fixtures.
- Synthetic fixture scripts require explicit session authorization.

The mutating integration scripts require both:

1. An explicitly allowed test database name.
2. An exact match between `current_database()` and the session
   setting `matchpoint.expected_test_database`.

Allowed database names:

- `matchpoint_test`
- `matchpoint_dbt_review_test`

Example session authorization:

```bash
export PGOPTIONS="-c matchpoint.expected_test_database=matchpoint_test"
```

This setting is required for the protected integration SQL scripts,
not for ordinary dbt model execution.

The authorization guard is an accidental-execution safeguard,
not a substitute for database permissions.

#### Production

Production deployment is pending.

A future production profile must use:

- A dedicated database.
- A least-privilege dbt execution role.
- Read-only access to Bronze.
- Required DDL and write access to Silver and Gold.
- Separate read-only API and analytics roles.
- Runtime secret injection.

Production credentials and permissions must be provisioned
and validated before deployment.

---

## 3. Standard Execution Runner

Use `dbt/run_dbt.py` for local development and automated execution.

The runner:

- Locates dbt in the current Python environment.
- Sets its working directory to the dbt project directory.
- Disables PostgreSQL JIT by default.
- Preserves existing PostgreSQL connection options.
- Passes command-line arguments to dbt.
- Propagates the dbt process exit code.
- Does not change PostgreSQL server-wide configuration.

### JIT Configuration

Default:

```text
MATCHPOINT_DBT_JIT=off
```

Controlled benchmarking:

```text
MATCHPOINT_DBT_JIT=on
```

The runner appends the selected JIT setting to `PGOPTIONS`
in the child process environment.

The parent environment remains unchanged.

The current PostgreSQL profile does not configure `search_path`.
Introducing adapter-level connection options may affect
`PGOPTIONS` behavior and requires compatibility testing.

### Performance Evidence

Independent query-plan measurements on the 52-listing synthetic
review dataset identified JIT compilation as the dominant overhead
for the recursive deduplication query.

| Configuration | Planning + Execution |
|---|---:|
| JIT enabled | 11685.087 ms |
| JIT disabled | 57.305 ms |

These measurements are query-specific and dataset-specific.

They do not establish production-scale performance.

---

## 4. Canonical Execution Sequence

Run the runner from the repository root using the dedicated
dbt Python environment.

The runner changes its working directory to `dbt/`.

Consequently, `--profiles-dir .` refers to the dbt directory.
Absolute profile paths are recommended for orchestration.

| Step | dbt Arguments | Purpose |
|---|---|---|
| 1 | `debug --profiles-dir . --target <target>` | Verify connectivity and configuration. |
| 2 | `parse --profiles-dir . --target <target> --warn-error` | Validate project configuration. |
| 3 | `seed --profiles-dir . --target <target>` | Load five lookup seeds. |
| 4 | `run --profiles-dir . --target <target>` | Build all 44 warehouse models. |
| 5 | `test --profiles-dir . --target <target> --warn-error` | Execute the complete 483-test quality gate. |
| 6 | `source freshness --profiles-dir . --target <target>` | Optional Bronze freshness monitoring. |
| 7 | `docs generate --profiles-dir . --target <target>` | Generate documentation artifacts. |

### Scheduled Execution

The required warehouse sequence is:

```text
Successful Bronze Persistence
    |
    v
dbt seed
    |
    v
dbt run
    |
    v
dbt test
    |
    v
Successful Quality Gate
    |
    v
ClickHouse Extraction and Loading
```

The warehouse currently contains:

- 4 staging views.
- 6 intermediate views.
- 14 Silver tables.
- 20 Gold tables.
- 5 lookup seeds.
- 443 generic data tests.
- 18 singular data tests.

Silver and Gold table models are rebuilt during normal dbt runs.

Incremental model materialization is not implemented.

### Source Freshness

Current freshness thresholds are provisional:

- Warning: 24 hours.
- Error: 72 hours.

Freshness monitoring becomes operationally meaningful after
persistent Bronze ingestion is available.

It must not be interpreted as proof that every source is fresh.

---

## 5. Execution Safety & Concurrency

The entire warehouse build is not a single atomic transaction.

A failed run may leave some models refreshed while other models
retain previous data.

Therefore:

- Do not overlap warehouse builds against the same target database.
- Serialize seed, run, test, and downstream extraction.
- Prevent downstream publication after any failed warehouse stage.
- Preserve the last successfully published ClickHouse dataset
  until a replacement dataset passes its quality gate.
- Coordinate Bronze persistence and warehouse transformation
  to avoid inconsistent source snapshots.
- Do not expose partially rebuilt warehouse data as a successful release.

### Airflow Concurrency Requirements

The orchestration implementation must provide:

- `max_active_runs=1` for the warehouse DAG.
- A target-specific Airflow pool or equivalent serialization mechanism.
- Protection against overlapping builds initiated by different DAGs.
- Coordination with manual and external warehouse executions.
- No concurrent downstream extraction during a warehouse rebuild.

A single-slot pool on individual tasks is not sufficient to guarantee
exclusive ownership of an entire multi-task warehouse sequence.

The complete build, quality gate, and extraction sequence must be
coordinated as one protected workflow.

These controls are implementation requirements.

They are not currently enforced by `run_dbt.py`.

---

## 6. Exit Codes & Failure Handling

| Exit Code | Interpretation | Required Action |
|---|---|---|
| `0` | Command completed successfully. | Continue to the next required stage. |
| `1` | dbt reported a handled failure. | Halt downstream processing and inspect diagnostics. |
| `2` | Runtime, configuration, invocation, or runner validation failure. | Halt and classify the underlying error. |
| `130` | Runner interrupted by the operator. | Halt downstream processing. |
| Other non-zero | Unexpected process failure. | Halt and investigate. |

Every non-zero exit code must block downstream publication.

Exit codes alone are not sufficient to determine whether a failure
is transient or permanent.

### Retry Policy

Retry only confirmed transient failures, such as:

- Temporary database unavailability.
- Temporary network interruption.
- Recoverable infrastructure failures.

Allow at most two retries after the initial attempt, with backoff.

Do not automatically retry:

- Invalid credentials.
- Invalid profile configuration.
- Missing environment variables.
- Invalid SQL or YAML.
- Failed data-quality assertions.
- Unsupported runtime configuration.

A retry must preserve the warehouse execution safety requirements.

If a model build fails, rerun the required warehouse sequence
after resolving the failure before publishing downstream data.

---

## 7. Logging & Execution Evidence

Standard dbt artifacts:

- `dbt/target/run_results.json`
- `dbt/target/manifest.json`
- `dbt/logs/dbt.log`

Optional artifacts:

- `dbt/target/catalog.json`
- `dbt/target/sources.json`

These generated artifacts are excluded from Git.

The orchestrator must archive relevant artifacts after each stage
because subsequent dbt commands may overwrite them.

Recommended evidence metadata:

- Workflow run identifier.
- Target database.
- Git commit SHA.
- dbt Core and adapter versions.
- Execution start and finish timestamps.
- Stage name and exit code.
- Model and test execution results.
- Error classification.

Do not include passwords or connection secrets in logs.

Use `--no-use-colors` for automated execution.

Structured logging with `--log-format json` may be enabled
when supported by the orchestration logging pipeline.

Use `--warn-error` for static validation and the quality gate.

Do not use `--fail-fast` for the complete scheduled quality gate
when all failing data tests need to be reported.

---

## 8. Local Execution Example

### Windows PowerShell

Run from the repository root.

The isolated database must already exist with all seven
Bronze migrations applied.

Supply `POSTGRES_PASSWORD` securely before execution.

```powershell
$dbtPython = Join-Path $env:USERPROFILE "venvs/matchpoint-dbt/Scripts/python.exe"

$env:POSTGRES_HOST = "127.0.0.1"
$env:POSTGRES_PORT = "5432"
$env:POSTGRES_USER = "matchpoint"
$env:POSTGRES_TEST_DB = "matchpoint_test"
$env:DBT_TARGET = "test"
$env:MATCHPOINT_DBT_JIT = "off"

if ([string]::IsNullOrWhiteSpace($env:POSTGRES_PASSWORD)) {
    throw "POSTGRES_PASSWORD is required."
}

if (-not (Test-Path "dbt/profiles.yml")) {
    Copy-Item dbt/profiles.yml.example dbt/profiles.yml
}

$commands = @("debug", "parse", "seed", "run", "test")

foreach ($command in $commands) {

    $dbtArgs = @(
        $command,
        "--profiles-dir", ".",
        "--target", "test",
        "--no-use-colors"
    )

    if ($command -in @("parse", "test")) {
        $dbtArgs += "--warn-error"
    }

    & $dbtPython "dbt/run_dbt.py" @dbtArgs

    if ($LASTEXITCODE -ne 0) {
        throw "dbt stage failed: $command"
    }
}
```

---

## 9. Docker Execution Template

For deployment, build a dedicated image with the pinned dbt
dependencies installed during image creation.

Do not install dependencies on every scheduled warehouse run.

Example Dockerfile template:

```dockerfile
FROM python:3.12-slim

WORKDIR /opt/matchpoint

COPY dbt/requirements.txt /tmp/dbt-requirements.txt

RUN python -m pip install --no-cache-dir \
    -r /tmp/dbt-requirements.txt \
    && python -m pip check

COPY dbt/ /opt/matchpoint/dbt/

ENTRYPOINT ["python", "/opt/matchpoint/dbt/run_dbt.py"]
```

The Docker build context must exclude:

- `.env`
- Local `profiles.yml`
- Generated dbt artifacts.
- Logs and caches.
- Virtual environments.

Mount or provision the runtime profile separately.

Inject credentials at runtime.

Use the actual Docker Compose network name rather than
assuming a fixed generated network name.

The container must connect to PostgreSQL using the service
hostname and internal database port.

This Dockerfile is a proposed integration template.
It is not an implemented or validated deployment artifact.

---

## 10. Airflow Execution Interface

The following example defines the required task interface
for the Airflow integration owner.

It assumes:

- A dedicated dbt Python environment.
- The repository dbt project mounted at `/opt/airflow/dbt`.
- A runtime profile directory at `/opt/airflow/dbt_profiles`.
- A configured Airflow PostgreSQL connection.
- A target-specific execution pool.

```python
DBT_PYTHON = "/opt/venvs/matchpoint-dbt/bin/python"

DBT_RUNNER = "/opt/airflow/dbt/run_dbt.py"

DBT_PROFILES = "/opt/airflow/dbt_profiles"

DBT_ENV = {
    "POSTGRES_HOST": "{{ conn.matchpoint_postgres.host }}",
    "POSTGRES_PORT": "{{ conn.matchpoint_postgres.port or 5432 }}",
    "POSTGRES_USER": "{{ conn.matchpoint_postgres.login }}",
    "POSTGRES_DB": "{{ conn.matchpoint_postgres.schema }}",
    "POSTGRES_PASSWORD": "{{ conn.matchpoint_postgres.password }}",
    "DBT_TARGET": "dev",
    "DBT_THREADS": "4",
    "MATCHPOINT_DBT_JIT": "off",
}


def build_dbt_command(command, strict=False):

    strict_flag = " --warn-error" if strict else ""

    return (
        f"{DBT_PYTHON} {DBT_RUNNER} {command}"
        f" --profiles-dir {DBT_PROFILES}"
        " --target dev"
        " --no-use-colors"
        f"{strict_flag}"
    )


dbt_seed = BashOperator(
    task_id="dbt_seed",
    bash_command=build_dbt_command("seed"),
    env=DBT_ENV,
    append_env=True,
    pool="matchpoint_warehouse",
    retries=0,
    skip_on_exit_code=None,
)

dbt_run = BashOperator(
    task_id="dbt_run",
    bash_command=build_dbt_command("run"),
    env=DBT_ENV,
    append_env=True,
    pool="matchpoint_warehouse",
    retries=0,
    skip_on_exit_code=None,
)

dbt_test = BashOperator(
    task_id="dbt_test",
    bash_command=build_dbt_command("test", strict=True),
    env=DBT_ENV,
    append_env=True,
    pool="matchpoint_warehouse",
    retries=0,
    skip_on_exit_code=None,
)

dbt_seed >> dbt_run >> dbt_test
```

### Integration Requirements

The example is not a complete Airflow DAG.

The Airflow integration owner must:

- Select the correct operator imports for the installed Airflow version.
- Configure the required Airflow connection and execution pool.
- Validate secret masking.
- Implement workflow-level concurrency protection.
- Archive execution evidence after each stage.
- Implement failure classification and conditional retries.
- Connect successful Bronze persistence to the warehouse workflow.
- Connect successful dbt testing to ClickHouse loading.
- Validate the runner in the Linux execution environment.

The example deliberately disables unconditional task retries.

Transient-error retry behavior must be implemented separately.

---

## 11. CI/CD Execution Template

CI must use an ephemeral PostgreSQL 16 database.

The migration connection and dbt test profile must refer
to the same isolated database.

Recommended GitHub Actions steps:

```yaml
- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: "3.12"

- name: Install dbt dependencies
  shell: bash
  run: |
    set -euo pipefail
    python -m pip install -r dbt/requirements.txt
    python -m pip check

- name: Validate isolated warehouse
  shell: bash
  env:
    POSTGRES_HOST: 127.0.0.1
    POSTGRES_PORT: "5432"
    POSTGRES_USER: matchpoint
    POSTGRES_TEST_DB: matchpoint_test
    POSTGRES_PASSWORD: ${{ secrets.CI_POSTGRES_PASSWORD }}
    DBT_TARGET: test
    MATCHPOINT_DBT_JIT: "off"
  run: |
    set -euo pipefail

    export PGHOST="$POSTGRES_HOST"
    export PGPORT="$POSTGRES_PORT"
    export PGUSER="$POSTGRES_USER"
    export PGDATABASE="$POSTGRES_TEST_DB"
    export PGPASSWORD="$POSTGRES_PASSWORD"

    actual_db="$(psql -X -v ON_ERROR_STOP=1 \
      -tAc 'SELECT current_database();')"

    if [ "$actual_db" != "matchpoint_test" ]; then
      echo "Unexpected CI database."
      exit 1
    fi

    for migration in database/migrations/*.sql; do
      psql -X -v ON_ERROR_STOP=1 -f "$migration"
    done

    cp dbt/profiles.yml.example dbt/profiles.yml

    python dbt/run_dbt.py debug \
      --profiles-dir . --target test --no-use-colors

    python dbt/run_dbt.py parse \
      --profiles-dir . --target test \
      --warn-error --no-use-colors

    python dbt/run_dbt.py seed \
      --profiles-dir . --target test --no-use-colors

    python dbt/run_dbt.py run \
      --profiles-dir . --target test --no-use-colors

    python dbt/run_dbt.py test \
      --profiles-dir . --target test \
      --warn-error --no-use-colors
```

This template assumes that the PostgreSQL service container,
database, role, password, and PostgreSQL client have already
been provisioned.

CI must also archive relevant execution artifacts.

Synthetic integration testing should be implemented as
a separate protected stage using the documented fixture sequence.

CI/CD implementation and execution validation remain pending.

---

## 12. Independent Review Status

The independent warehouse review used:

- Python 3.12.10.
- dbt-core 1.12.7.
- dbt-postgres 1.11.0.
- PostgreSQL 16.
- Isolated database `matchpoint_dbt_review_test`.

Verified review improvements include:

- Exact direct dependency pinning.
- Supported generic test argument syntax.
- Protected synthetic fixture execution.
- NULL-safe integration assertions.
- Duplicate-sensitive idempotency comparisons.
- Protected snapshot creation.
- Gold snapshot schema comparison.
- Process-scoped PostgreSQL JIT configuration.
- Eight successful runner functional checks.

The expanded synthetic dataset contains:

- 52 Bronze source listings.
- 43 canonical opportunities.
- All eight supported sources.

The original implementation validation results remain
historical evidence and must not be overwritten.

### Remaining Acceptance Requirements

- Persistent Python Bronze ingestion.
- Real collected data integration.
- Same-run retry and observation idempotency validation.
- Lifecycle refresh validation.
- Production-scale performance testing.
- Linux and Docker runner validation.
- Airflow orchestration and concurrency protection.
- ClickHouse loading and publication validation.
- CI/CD implementation.
- Production role and permission provisioning.

Synthetic warehouse validation does not establish
production readiness or complete end-to-end acceptance.