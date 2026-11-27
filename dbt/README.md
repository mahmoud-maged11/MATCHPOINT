# MATCHPOINT Data Warehouse (dbt)

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
  models/silver/       ──► schema: silver (tables/incremental, Phase 3–4)
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
├── requirements.txt             # dbt-core and dbt-postgres version constraints
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

From the repository root (inside your virtual environment):

```powershell
.\.venv\Scripts\python.exe -m pip install -r dbt/requirements.txt
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

Run from inside the `dbt/` directory (using `--profiles-dir .` if `dbt/profiles.yml` is placed locally):

```powershell
cd dbt

# 1. Verify profile, environment variables, and PostgreSQL 16 connectivity
dbt debug --profiles-dir .

# 2. Validate YAML, Jinja macros, and source definitions without executing SQL
dbt parse --profiles-dir .

# 3. Check Bronze source freshness (meaningful once data exists in Bronze)
dbt source freshness --profiles-dir .

# 4. Load explicit alias & location mapping seeds
dbt seed --profiles-dir .

# 5. Run staging, intermediate, and Silver models
dbt run --profiles-dir .

# 6. Run dbt generic and singular data quality tests
dbt test --profiles-dir .

# Optional: run against isolated test database
dbt debug --profiles-dir . --target test
```

See [models/silver/README.md](models/silver/README.md) for Phase 3 Silver rules, [docs/phase4_deduplication_design.md](docs/phase4_deduplication_design.md) for Phase 4 deduplication & runtime validation, and [docs/phase5_gold_design.md](docs/phase5_gold_design.md) for Phase 5 Gold star-schema & analytical marts.

---

## Pending Work

- **Live Ingestion Validation:** Re-run full Bronze → Silver → Gold validation against real collected opportunities once persistent Python ingestion (`scrapers/storage/postgres.py`, owned by Mahmoud) is completed.
- **Proposed ADR Reviews:** Review proposed warehouse ADRs with the team before updating `docs/architecture_decisions.md`.
- **External Component Integration:** Airflow orchestration & ClickHouse loading (Andrew), Power BI dashboards (Ramadan), Backend FastAPI & Matching (Mahmoud), Frontend (Abdel Rahman).
