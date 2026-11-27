# MATCHPOINT Data Warehouse (dbt)

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

This directory contains the dbt project for the **MATCHPOINT** Data Warehouse running on **PostgreSQL 16**, aligned with **Data Contract v3.0.0** and **ADR-041 through ADR-050**.

> **Current Milestone Status (Phase 5):** The dbt project foundation, Bronze source definitions, explicit lookup & generic-portal seeds, Bronze staging views, intermediate cleaning/lifecycle/deduplication models, Silver source-level and canonical opportunity models, Gold analytical dimensions/facts/bridges/marts, and dbt data quality tests are implemented and synthetic-runtime validated on an isolated PostgreSQL 16.16 test database (`matchpoint_test`). Persistent Python ingestion into Bronze (owned by Mahmoud) and downstream Airflow/ClickHouse/Power BI/Backend integration remain pending.

---

## Architecture & Bronze-to-Silver Flow

```text
Approved Physical Bronze Schema (database/migrations/001..007)
  ├── bronze.collection_runs
  ├── bronze.source_listings
  ├── bronze.source_listing_history
  ├── bronze.ingestion_observations
  ├── bronze.invalid_records
  └── bronze.source_checkpoints
         │
         ▼  dbt {{ source('bronze', '...') }}
  models/staging/      ──► schema: silver (views, Phase 3)
         │
         ▼
  models/intermediate/ ──► schema: silver (views, Phase 3–4)
         │
         ▼
  models/silver/       ──► schema: silver (full-refresh tables, Phase 3–4)
         │
         ▼
  models/gold/         ──► schema: gold   (tables, Phase 5)
```

### Key Boundaries

- The three physical schemas (`bronze`, `silver`, `gold`) and all six Bronze tables are created and owned by SQL migrations in `database/migrations/`. dbt **reads** from `bronze` and **never** recreates or modifies physical Bronze tables.
- Persistent Python ingestion into Bronze (`scrapers/storage/postgres.py`) is owned by Mahmoud and remains pending. Configuring dbt sources does not imply that live ingestion is complete.
- Collection timestamps (`started_at`, `last_seen_at`, `processed_at`) represent pipeline observation/processing times only — they **never** establish source publication time or absence-based listing closure (`ADR-022`, `ADR-047`).

---

## Directory Structure

```text
dbt/
├── dbt_project.yml              # Project config, paths, vars, and layer materialization defaults
├── profiles.yml.example         # Safe PostgreSQL 16 profile template (env-var driven)
├── requirements.txt             # Pinned dbt-core and dbt-postgres versions
├── run_dbt.py                    # Standard dbt execution runner
├── README.md                    # This documentation
├── docs/
│   ├── phase4_deduplication_design.md # Phase 4 deduplication design & runtime validation record
│   └── phase5_gold_design.md          # Phase 5 Gold star-schema & analytical marts design
├── integration_tests/           # Synthetic Bronze loaders, Phase 4/5 verifiers & idempotency checks
├── macros/
│   ├── generate_schema_name.sql # Maps custom schemas directly to `silver` and `gold`
│   ├── normalize_text.sql       # Non-destructive Arabic/English text cleaning helpers
│   ├── normalize_url.sql        # Symmetric URL normalization (host+path lower, query preserved)
│   ├── deterministic_key.sql    # Native PostgreSQL SHA-256 deterministic key helper
│   └── deterministic_uuid.sql   # Native PostgreSQL SHA-256 deterministic UUID helper
├── models/
│   ├── sources/
│   │   └── bronze_sources.yml   # Definitions for all 6 Bronze tables (96 columns)
│   ├── staging/                 # 4 Bronze staging views + staging_schema.yml
│   ├── intermediate/            # 6 cleaning, lifecycle & deduplication views + schema
│   ├── silver/                  # 14 Silver tables (source-level + canonical) + schema + README
│   └── gold/                    # 20 Gold tables (6 dims, 7 facts/bridges, 7 marts) + gold_schema.yml
├── seeds/                       # 5 explicit lookup, portal & source-authority CSVs + schema
├── snapshots/                   # Reserved for SCD snapshots if required later
└── tests/                       # 18 custom singular dbt SQL data quality tests
```

---

## Setup & PostgreSQL Configuration

### 1. Prerequisites

- **PostgreSQL 16** running locally (for example via `docker compose up -d postgres` from the repository root) with migrations `database/migrations/001` through `007` applied.
- **Python 3.12** (recommended in the root `README.md` for `dbt-postgres` compatibility).

### 2. Install dbt Dependencies

Use a dedicated Python 3.12 virtual environment,
separate from the scraper runtime.

Validated versions:

- `dbt-core==1.12.7`
- `dbt-postgres==1.11.0`

From the repository root:

```powershell
py -3.12 -m venv "$env:USERPROFILE\venvs\matchpoint-dbt"
$dbtPython = Join-Path $env:USERPROFILE "venvs\matchpoint-dbt\Scripts\python.exe"
& $dbtPython -m pip install -r dbt/requirements.txt
& $dbtPython -m pip check
```

### 3. Configure `profiles.yml` (No Hardcoded Secrets)

Copy the example profile to `dbt/profiles.yml` (already ignored by `.gitignore`) or `~/.dbt/profiles.yml`:

```powershell
Copy-Item dbt/profiles.yml.example dbt/profiles.yml
```

Never commit `dbt/profiles.yml` or `.env` to Git.

### 4. Required Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `POSTGRES_PASSWORD` | **Yes** | *(none)* | PostgreSQL password (must be supplied via environment; never hardcoded). |
| `POSTGRES_HOST` | No | `localhost` | Database hostname. Use `localhost` when running dbt on the host machine, or `postgres` when running inside the Docker Compose network. |
| `POSTGRES_PORT` | No | `5432` | PostgreSQL port (cast with `as_number` in `profiles.yml`). |
| `POSTGRES_USER` | No | `matchpoint` | PostgreSQL username. |
| `POSTGRES_DB` | No | `matchpoint` | Primary database name for the `dev` target. |
| `POSTGRES_TEST_DB` | No | `matchpoint_test` | Isolated database name for the `test` target. |
| `DBT_TARGET` | No | `dev` | Active dbt target (`dev` or `test`). |
| `DBT_SCHEMA` | No | `silver` | Fallback schema when a model does not declare `+schema`. |
| `DBT_THREADS` | No | `4` | Number of parallel dbt threads (cast with `as_number`). |
| `MATCHPOINT_DBT_JIT` | No | `off` | JIT mode for runner connections; accepts `on` or `off`. |

Example in Windows PowerShell (current session only):

```powershell
$env:POSTGRES_HOST = "localhost"
$env:POSTGRES_PORT = "5432"
$env:POSTGRES_USER = "matchpoint"
$env:POSTGRES_DB = "matchpoint"
$env:POSTGRES_PASSWORD = "<your-local-password>"
```

---

## Schema Naming Behavior

By default, dbt concatenates `target.schema` with a model's custom schema (producing unintended schemas such as `public_silver` or `silver_gold`).

`dbt/macros/generate_schema_name.sql` overrides that default:

- When a model defines `+schema: silver` (`staging/`, `intermediate/`, `silver/`), dbt targets `silver`.
- When a model defines `+schema: gold` (`gold/`), dbt targets `gold`.
- When no custom schema is specified, dbt falls back to `target.schema` (`silver` by default).

All models stay strictly within the approved schemas created by `database/migrations/001_create_schemas.sql`.

---

## Bronze Sources (`dbt/models/sources/bronze_sources.yml`)

All six physical Bronze tables (96 columns total) are declared under the `bronze` source and referenced in downstream SQL via `{{ source('bronze', '<table_name>') }}`:

| Source Table | Columns | Primary Key | Foreign Keys | Freshness Check (`loaded_at_field`) |
|---|---:|---|---|---|
| `bronze.collection_runs` | 18 | `run_id` | — | `started_at` (warn: 24h, error: 72h; provisional) |
| `bronze.source_listings` | 42 | `source_listing_id` | `last_collection_run_id → collection_runs(run_id)` | `last_seen_at` (warn: 24h, error: 72h; provisional) |
| `bronze.source_listing_history` | 10 | `history_id` | `source_listing_id → source_listings`, `collection_run_id → collection_runs` | Intentionally omitted (append-only on new/changed content per ADR-043) |
| `bronze.ingestion_observations` | 6 | `(source_listing_id, collection_run_id)` | `source_listing_id → source_listings`, `collection_run_id → collection_runs` | `processed_at` (warn: 24h, error: 72h; provisional) |
| `bronze.invalid_records` | 12 | `invalid_record_id` | `collection_run_id → collection_runs` | Intentionally omitted (zero rows is healthy; `observed_at` is nullable) |
| `bronze.source_checkpoints` | 8 | `checkpoint_id` | `last_successful_run_id → collection_runs` | Intentionally omitted (incremental collection deferred per ADR-048) |

> Note: `bronze_sources.yml` omits a hardcoded `database:` attribute so dbt automatically binds to the active target's `dbname` (`matchpoint` for `dev`, `matchpoint_test` for `test`).

---

## Validation Commands (Once Environment Is Ready)

Use `dbt/run_dbt.py` as the standard execution entry point.

Run from the repository root using the dedicated Python 3.12 environment.
The runner automatically sets its working directory to `dbt/`.

```powershell
$dbtPython = Join-Path $env:USERPROFILE "venvs/matchpoint-dbt/Scripts/python.exe"

$env:DBT_TARGET = "test"
$env:POSTGRES_TEST_DB = "matchpoint_test"

# Configure database credentials before execution.
# Apply migrations 001..007 to the isolated test database first.

& $dbtPython dbt/run_dbt.py debug --profiles-dir . --target test
& $dbtPython dbt/run_dbt.py parse --profiles-dir . --target test --warn-error
& $dbtPython dbt/run_dbt.py seed --profiles-dir . --target test
& $dbtPython dbt/run_dbt.py run --profiles-dir . --target test
& $dbtPython dbt/run_dbt.py test --profiles-dir . --target test --warn-error
```

Execute commands sequentially and check `$LASTEXITCODE` after each command.
Stop immediately on failure.

Source freshness monitoring is optional until persistent ingestion exists.

### PostgreSQL JIT Configuration

The runner disables PostgreSQL JIT by default for its own connections,
preserves existing PGOPTIONS, and propagates dbt exit codes.

Set `MATCHPOINT_DBT_JIT=on` for controlled benchmarking.

| Configuration | Query planning + execution |
|---|---:|
| JIT enabled | 11685.087 ms |
| JIT disabled | 57.305 ms |

These measurements apply to the recursive deduplication query
on the 52-listing synthetic review dataset only.

PostgreSQL server-wide settings remain unchanged.
Introducing adapter-level connection options, including search_path,
requires compatibility verification.

### Execution Safety

- Use isolated databases for synthetic integration tests.
- Mutating fixture scripts require explicit session authorization.
- Never run synthetic fixtures against development or production data.
- Serialize warehouse builds and downstream extraction per target.
- Halt ClickHouse loading on any warehouse build or quality-gate failure.
- Individual table rebuilds are transactional, but the entire dbt run
  is not a single atomic transaction.

See [integration_tests/README.md](integration_tests/README.md)
for fixture execution and snapshot safety requirements.

See [models/silver/README.md](models/silver/README.md) for Phase 3 Silver rules, [docs/phase4_deduplication_design.md](docs/phase4_deduplication_design.md) for Phase 4 deduplication & runtime validation, and [docs/phase5_gold_design.md](docs/phase5_gold_design.md) for Phase 5 Gold star-schema & analytical marts.

---

## Independent Warehouse Review

Original Phase 4 and Phase 5 validation results remain historical evidence.

The independent review used Python 3.12.10, dbt-core 1.12.7,
dbt-postgres 1.11.0, and PostgreSQL 16.

Review database: `matchpoint_dbt_review_test`.

Review improvements:

- Updated 108 generic test declarations to supported arguments syntax.
- Preserved generic test semantics.
- Added exact database authorization for mutating integration scripts.
- Strengthened NULL-safe assertions and fixture preconditions.
- Added duplicate-sensitive EXCEPT ALL comparisons.
- Protected Silver and Gold snapshot creation.
- Added Gold snapshot schema compatibility checks.
- Introduced process-scoped JIT configuration through run_dbt.py.
- Validated eight runner functional checks.

The expanded synthetic dataset contains 52 source listings
across eight supported sources and 44 canonical opportunities.

Live ingestion, production-scale performance, Linux/Airflow runner
validation, and downstream integration remain pending.

---

## Pending Work

- **Live Ingestion Validation:** Re-run full Bronze → Silver → Gold validation against real collected opportunities once persistent Python ingestion (`scrapers/storage/postgres.py`, owned by Mahmoud) is completed.
- **Proposed ADR Reviews:** Review proposed warehouse ADRs with the team before updating `docs/architecture_decisions.md`.
- **External Component Integration:** Airflow orchestration & ClickHouse loading (Andrew), Power BI dashboards (Ramadan), Backend FastAPI & Matching (Mahmoud), Frontend (Abdel Rahman).
