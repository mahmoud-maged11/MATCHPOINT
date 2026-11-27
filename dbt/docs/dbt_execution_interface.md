# Standard dbt Execution Interface (Local, Airflow, Docker & CI/CD)

**Project:** `matchpoint` (`dbt/dbt_project.yml`, `version: 1.0.0`)  
**Target Warehouse:** PostgreSQL 16 (`bronze`, `silver`, `gold` schemas created by `database/migrations/001..007`)  
**Verified Runtime:** Python `3.12.13`, `dbt-core 1.9.11`, `dbt-postgres 1.9.1`

---

## 1. Runtime & Dependency Requirements

| Requirement | Specification | Reference |
|---|---|---|
| **Python** | `3.12.x` (recommended; matches repository `README.md`) | `README.md` |
| **dbt Packages** | `dbt-core>=1.8.0,<1.10.0` and `dbt-postgres>=1.8.0,<1.10.0` | `dbt/requirements.txt` |
| **Database** | PostgreSQL `16.x` with `database/migrations/001..007` applied | `docker-compose.yml` |
| **External dbt Hub Packages** | None required (100% native PostgreSQL 16 SQL & custom macros) | `dbt/macros/` |

### Dependency Installation
```bash
python -m venv .venv
# Linux / Docker:
./.venv/bin/python -m pip install --no-cache-dir -r dbt/requirements.txt
# Windows PowerShell:
.\.venv\Scripts\python.exe -m pip install -r dbt/requirements.txt
```

---

## 2. Environment Variables & Profile Configuration

Never commit `dbt/profiles.yml` or `.env` (both excluded via `.gitignore`). Always derive `profiles.yml` from `dbt/profiles.yml.example`:

| Variable | Required | Default | Description |
|---|---|---|---|
| `POSTGRES_PASSWORD` | **Yes** | *(none)* | PostgreSQL password (must be injected at runtime via env/secret). |
| `POSTGRES_HOST` | No | `localhost` | Use `localhost` on host machine; use `postgres` inside Docker network `matchpoint_network`. |
| `POSTGRES_PORT` | No | `5432` | PostgreSQL port (cast with `as_number`). |
| `POSTGRES_USER` | No | `matchpoint` | PostgreSQL role with read access to `bronze` and DDL/write access to `silver` and `gold`. |
| `POSTGRES_DB` | No | `matchpoint` | Database name for `dev` target. |
| `POSTGRES_TEST_DB` | No | `matchpoint_test` | Isolated database name for `test` target. |
| `DBT_TARGET` | No | `dev` | Active dbt target (`dev` or `test`; add `prod` output in deployment profile when provisioning prod). |
| `DBT_SCHEMA` | No | `silver` | Fallback schema (all models explicitly declare `+schema: silver` or `+schema: gold` via `generate_schema_name.sql`). |
| `DBT_THREADS` | No | `4` | Parallel worker threads (cast with `as_number`). |

### Environment Separation Rules
- **`dev` target (`POSTGRES_DB=matchpoint`):** Local developer & integrated Docker Compose warehouse database.
- **`test` target (`POSTGRES_TEST_DB=matchpoint_test`):** Strictly isolated test database for synthetic fixtures (`dbt/integration_tests/`), empty-Bronze tests, and CI runs. All synthetic SQL loaders abort unless `current_database() ILIKE '%test%'`.
- **`prod` target (future deployment):** Dedicated production database with least-privilege dbt runner role (read-only on `bronze`, write on `silver`/`gold`) and separate read-only API/analytics consumer roles.

---

## 3. Canonical Command Sequence & Execution Order

Always run commands with working directory `dbt/` (or pass `--project-dir dbt --profiles-dir dbt`):

| Step | Command | Purpose | Required in Scheduled Runs? |
|---|---|---|---|
| **1. Connectivity** | `dbt debug --profiles-dir . --target <target>` | Validates profile, env vars, and PostgreSQL 16 connectivity | On startup / CI / troubleshooting |
| **2. Static Validation** | `dbt parse --profiles-dir . --target <target>` | Validates Jinja, YAML schemas, refs, and DAG without touching DB | **Yes in CI** (no DB required if using dummy env var or parse-only) |
| **3. Load Seeds** | `dbt seed --profiles-dir . --target <target>` | Loads all 5 lookup & authority CSV seeds into `silver.*` | **Yes** (before `dbt run`) |
| **4. Build Warehouse** | `dbt run --profiles-dir . --target <target>` | Materializes all 44 models (4 staging views, 6 int views, 14 Silver tables, 20 Gold tables + 33 indexes) | **Yes** |
| **5. Quality Gate** | `dbt test --profiles-dir . --target <target>` | Runs all 461 tests (443 generic + 18 singular); **mandatory gate before ClickHouse load** | **Yes** |
| **6. Source Freshness** | `dbt source freshness --profiles-dir . --target <target>` | Checks Bronze observation recency (`warn: 24h`, `error: 72h`, provisional) | Optional monitoring task |
| **7. Docs Catalog** | `dbt docs generate --profiles-dir . --target <target>` | Generates `target/catalog.json` & `target/manifest.json` | Optional / release artifact |

---

## 4. Exit Codes, Logging & Failure Handling

| Exit Code | Meaning | Required Automated Action (Airflow / CI) |
|---|---|---|
| `0` | All invoked models/seeds/tests succeeded | Proceed to next stage (e.g., ClickHouse load) |
| `1` | One or more models failed SQL execution OR one or more `dbt test` assertions failed | **HALT downstream ClickHouse load**; inspect `dbt/target/run_results.json` and `dbt/logs/dbt.log`; alert Data Engineering owner |
| `2` | Unhandled runtime/config/connection error (missing `POSTGRES_PASSWORD`, invalid YAML, DB unreachable) | Retry up to 2× for transient connection errors (`Airflow`); fail fast in CI |

### Logging & Diagnostics
- Machine-readable execution artifacts are written to `dbt/target/run_results.json` (excluded from Git via `.gitignore`).
- Detailed SQL and timing logs are written to `dbt/logs/dbt.log` (excluded from Git).
- For automated pipelines (Airflow / CI), pass `--no-use-colors` and `--log-format json` (or default text) to keep orchestrator logs clean.
- Use `--fail-fast` during CI smoke runs if rapid failure feedback is preferred; omit `--fail-fast` in scheduled production `dbt test` so **all** failing data-quality checks are reported together.

---

## 5. Reproducible Execution Examples

### A. Local Developer (Windows PowerShell — Isolated Test Target)
```powershell
Copy-Item dbt/profiles.yml.example dbt/profiles.yml
$env:POSTGRES_HOST = "127.0.0.1"
$env:POSTGRES_PORT = "5432"
$env:POSTGRES_USER = "matchpoint"
$env:POSTGRES_TEST_DB = "matchpoint_test"
$env:POSTGRES_PASSWORD = "<your-local-password>"

Push-Location dbt
..\.venv\Scripts\dbt.exe debug --profiles-dir . --target test
..\.venv\Scripts\dbt.exe seed  --profiles-dir . --target test
..\.venv\Scripts\dbt.exe run   --profiles-dir . --target test
..\.venv\Scripts\dbt.exe test  --profiles-dir . --target test
Pop-Location
```

### B. Docker Execution (Against `matchpoint_network` in `docker-compose.yml`)
```bash
docker run --rm \
  --network matchpoint_matchpoint_network \
  -v "$(pwd)/dbt:/usr/app/dbt" \
  -w /usr/app/dbt \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_PORT=5432 \
  -e POSTGRES_USER=matchpoint \
  -e POSTGRES_DB=matchpoint \
  -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
  -e DBT_TARGET=dev \
  python:3.12-slim bash -lc "
    pip install --no-cache-dir -q -r requirements.txt &&
    cp profiles.yml.example /tmp/profiles.yml &&
    dbt seed --profiles-dir /tmp --no-use-colors &&
    dbt run  --profiles-dir /tmp --no-use-colors &&
    dbt test --profiles-dir /tmp --no-use-colors
  "
```
*(In production/Airflow, pre-bake `requirements.txt` into an image rather than installing at runtime.)*

### C. Airflow Task Interface (`BashOperator` Pattern for Andrew)
```python
DBT_ENV = {
    "POSTGRES_HOST": "postgres",
    "POSTGRES_PORT": "5432",
    "POSTGRES_USER": "{{ var.value.postgres_user }}",
    "POSTGRES_DB": "{{ var.value.postgres_db }}",
    "POSTGRES_PASSWORD": "{{ conn.matchpoint_postgres.password }}",
    "DBT_TARGET": "dev",
    "DBT_THREADS": "4",
}

dbt_seed = BashOperator(
    task_id="dbt_seed",
    bash_command="cd /opt/airflow/dbt && dbt seed --profiles-dir /opt/airflow/dbt_profiles --no-use-colors",
    env=DBT_ENV,
)
dbt_run = BashOperator(
    task_id="dbt_run",
    bash_command="cd /opt/airflow/dbt && dbt run --profiles-dir /opt/airflow/dbt_profiles --no-use-colors",
    env=DBT_ENV,
)
dbt_test = BashOperator(
    task_id="dbt_test",
    bash_command="cd /opt/airflow/dbt && dbt test --profiles-dir /opt/airflow/dbt_profiles --no-use-colors",
    env=DBT_ENV,
)

dbt_seed >> dbt_run >> dbt_test
```

### D. GitHub Actions CI/CD Pattern (Static Parse + Ephemeral PostgreSQL 16 Smoke Test)
```yaml
# Recommended CI job steps (requires postgres:16 service container)
- name: Apply Bronze migrations 001..007
  run: |
    for f in database/migrations/*.sql; do
      psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"
    done
- name: Install dbt dependencies
  run: pip install -r dbt/requirements.txt
- name: Parse, Seed, Run, and Test on Empty Bronze
  working-directory: dbt
  env:
    POSTGRES_HOST: 127.0.0.1
    POSTGRES_PORT: 5432
    POSTGRES_USER: matchpoint
    POSTGRES_TEST_DB: matchpoint_test
    POSTGRES_PASSWORD: ${{ secrets.CI_POSTGRES_PASSWORD }}
  run: |
    cp profiles.yml.example profiles.yml
    dbt parse --profiles-dir . --target test --no-use-colors
    dbt seed  --profiles-dir . --target test --no-use-colors
    dbt run   --profiles-dir . --target test --no-use-colors
    dbt test  --profiles-dir . --target test --no-use-colors
```
