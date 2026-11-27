# Downstream Handoff Contract — Andrew (Airflow & ClickHouse)

**Owner (Consumer):** Andrew (`airflow/dags/`, `clickhouse/`)  
**Owner (Producer):** Momen (`dbt/`, PostgreSQL `silver` & `gold` schemas)  
**Contract Version:** Data Contract `v3.0.0` (ADR-050)  
**Current External Component Status:** Verified read-only — `airflow/dags/` and `clickhouse/` contain `.gitkeep` only (`origin/feature/orchestration` at `0912a49`). This document defines the exact integration contract so Andrew can implement Airflow DAGs and ClickHouse loaders without ambiguity.

---

## 1. End-to-End Orchestration Sequence (Airflow DAG)

Airflow orchestrates the full pipeline in four strictly ordered stages:

```text
[1. Source Scrapers -> PostgreSQL Bronze (Mahmoud)]
          │  (run per source / bounded batch; exit 0 on completed/partial)
          ▼
[2. dbt Seed & Transform (PostgreSQL Bronze -> Silver -> Gold)]
          │  dbt seed  -> dbt run  -> dbt test
          ▼
[3. ClickHouse Analytical Load (PostgreSQL gold.* -> ClickHouse matchpoint_analytics.*)]
          │  Atomic load of Gold tables ONLY after dbt test exits 0
          ▼
[4. Post-Load Parity & Freshness Checks]
             Verify row counts in ClickHouse == PostgreSQL gold.*
```

> **Critical Gate Rule:** NEVER load ClickHouse if `dbt run` or `dbt test` fails (non-zero exit code). `dbt test` enforces canonical uniqueness, referential integrity, no same-source duplicate merges, and zero mart double-counting across 461 checks.

---

## 2. How Airflow Should Trigger dbt

### Required Execution Order Inside the dbt Stage
1. **`dbt seed --profiles-dir . --target <target>`** — Loads/refreshes the 5 authoritative CSV seeds into `silver.*` (`supported_sources`, `organization_aliases`, `location_mappings`, `skill_aliases`, `generic_application_portals`). Safe and fast (~1s); run before `dbt run` whenever seeds may have changed or on every scheduled DAG run.
2. **`dbt run --profiles-dir . --target <target>`** — Builds all **44 dbt models** in DAG order:
   - 4 staging views (`silver.stg_bronze__*`)
   - 6 intermediate views (`silver.int_*`)
   - 14 Silver tables (`silver.silver_*`)
   - 20 Gold tables (`gold.dim_*`, `gold.fct_*`, `gold.bridge_*`, `gold.mart_*`)
3. **`dbt test --profiles-dir . --target <target>`** — Runs all **461 data tests** (443 generic YAML + 18 singular SQL tests).
4. *(Optional monitoring task)* **`dbt source freshness --profiles-dir . --target <target>`** — Monitors `bronze.collection_runs.started_at`, `bronze.source_listings.last_seen_at`, and `bronze.ingestion_observations.processed_at` (`warn: 24h`, `error: 72h`, provisional). Run as a warning/alert task; do NOT treat freshness warnings as closure evidence (`ADR-022`, `ADR-047`).

### Environment Variables & Networking (`docker-compose.yml`)
When Airflow runs inside `matchpoint_network` (`docker-compose.yml`):

| Variable | Required | Docker Network Value | Host Dev Value |
|---|---|---|---|
| `POSTGRES_HOST` | Yes | `postgres` | `localhost` |
| `POSTGRES_PORT` | No | `5432` | `5432` |
| `POSTGRES_USER` | No | `matchpoint` | `matchpoint` |
| `POSTGRES_DB` | No | `matchpoint` | `matchpoint` |
| `POSTGRES_PASSWORD` | **Yes** | *(Airflow Connection / Secret)* | *(env var)* |
| `DBT_TARGET` | No | `dev` *(or `prod` once configured)* | `dev` |
| `DBT_SCHEMA` | No | `silver` | `silver` |
| `DBT_THREADS` | No | `4` | `4` |
| `CLICKHOUSE_HOST` | Yes (loader) | `clickhouse` | `localhost` |
| `CLICKHOUSE_PORT` | No (loader) | `8123` (HTTP) / `9000` (Native) | `8123` / `9000` |
| `CLICKHOUSE_DB` | No (loader) | `matchpoint_analytics` | `matchpoint_analytics` |

- Copy `dbt/profiles.yml.example` to `dbt/profiles.yml` (or mount via container secret/config at `/opt/airflow/dbt/profiles.yml` and pass `--profiles-dir`). **Never hardcode credentials or commit `profiles.yml`.**

---

## 3. Materialization Behavior (Full Refresh vs Incremental)

All **14 Silver tables** and **20 Gold tables** are currently configured as **stateless full-refresh `table`** materializations (`dbt/dbt_project.yml`):
- Every `dbt run` rebuilds each table atomically inside PostgreSQL (dbt builds a temporary relation, creates all 33 configured indexes on Gold tables, and swaps the table inside a transaction).
- **No `--full-refresh` flag is needed** (all models already rebuild cleanly on every run) and **zero incremental state drift occurs**.
- **Important Implication for ClickHouse:** Because `fct_opportunities.effective_status` and `opportunity_id` (under late-arriving higher-authority merges) can change across runs, ClickHouse loading MUST perform an **atomic full-table replacement** (e.g., load into `<table_name>_staging` and run `EXCHANGE TABLES gold_table AND gold_table_staging`, or `TRUNCATE` + `INSERT` inside a dedicated staging swap) rather than append-only `INSERT`s, to prevent duplicate rows in ClickHouse `MergeTree` tables!

---

## 4. Failure Handling, Retries & Data Freshness

### Recommended Airflow Task Policies
- **dbt tasks (`dbt_seed`, `dbt_run`, `dbt_test`):**
  - `retries=2`, `retry_delay=timedelta(minutes=3)` for transient PostgreSQL connection errors.
  - `execution_timeout=timedelta(minutes=15)` (current synthetic runtime is `< 30s`; adjust once live volume scales).
  - Do **NOT** retry blindly on `dbt test` data-quality failures (exit code `1`): alert the team immediately and halt ClickHouse loading so bad data does not reach Power BI.
- **Scraper failure isolation:** A failure in one scraper (e.g., `bayt` HTTP error) should NOT block other scrapers from persisting to Bronze. Downstream `dbt run` can still refresh `effective_status` for existing Bronze records if configured with `TriggerRule.ALL_DONE` after scraper tasks (provided at least the Bronze database is healthy).
- **Data Freshness & Scheduled Time-Dependent Re-evaluation:**
  - Even on days when no new listings are scraped, run `dbt run` + `dbt test` at least **once every 6–12 hours** (minimum daily after `00:05 UTC` and `12:05 UTC`) so `effective_status` accurately transitions expired `exact` and `date_only` (`+36h` conservative UTC window) deadlines in `gold.fct_opportunities` and updates `lifecycle_evaluated_at`.

### How to Validate a Successful Run
1. `dbt run` returns exit code `0` and `target/run_results.json` shows `44` models with `status == "success"`.
2. `dbt test` returns exit code `0` and `target/run_results.json` shows `461` tests with `status == "pass"`.
3. Post-ClickHouse-load check confirms exact row-count parity for every loaded table:
   - `COUNT(*) FROM clickhouse.fct_opportunities == COUNT(*) FROM postgres.gold.fct_opportunities`
   - `SUM(primary_canonical_opportunities) FROM clickhouse.mart_opportunities_by_source == COUNT(*) FROM clickhouse.fct_opportunities`

---

## 5. ClickHouse Source-to-Target Mapping (`gold.*` → `matchpoint_analytics.*`)

All **20 Gold tables** are eligible for loading into ClickHouse 25.8 (`matchpoint_analytics`). Below is the recommended priority and ClickHouse `MergeTree` ordering key (`ORDER BY`) mapping for Andrew's DDL design:

| Priority | PostgreSQL Source (`gold.*`) | ClickHouse Target (`matchpoint_analytics.*`) | Recommended Engine & `ORDER BY` | Type Conversion Notes |
|---|---|---|---|---|
| **P0 Core** | `gold.fct_opportunities` | `fct_opportunities` | `MergeTree() ORDER BY (effective_status, opportunity_type, opportunity_id)` | `UUID` → `UUID`; `JSONB` arrays → `Array(String)` or `String` (JSON); `NUMERIC` → `Nullable(Decimal(14,2))`; `TIMESTAMPTZ` → `DateTime64(3, 'UTC')` |
| **P0 Core** | `gold.fct_opportunity_sources` | `fct_opportunity_sources` | `MergeTree() ORDER BY (source_name, opportunity_id, source_listing_id)` | `match_evidence` (`JSONB`) → `String` |
| **P0 Core** | `gold.fct_collection_runs` | `fct_collection_runs` | `MergeTree() ORDER BY (source_name, started_at, run_id)` | `invalid_record_rate` → `Nullable(Decimal(6,4))` |
| **P0 Dims** | `gold.dim_sources` | `dim_sources` | `MergeTree() ORDER BY (source_authority_rank, source_name)` | Always 8 rows |
| **P0 Dims** | `gold.dim_organizations` | `dim_organizations` | `MergeTree() ORDER BY (organization_key)` | `observed_raw_names` → `Array(String)` or `String` |
| **P0 Dims** | `gold.dim_locations` | `dim_locations` | `MergeTree() ORDER BY (location_key)` | Preserve nullable city/gov/country as `Nullable(String)` |
| **P0 Dims** | `gold.dim_skills` | `dim_skills` | `MergeTree() ORDER BY (skill_key)` | Candidate skills (`is_candidate_skill`) |
| **P0 Dims** | `gold.dim_categories` | `dim_categories` | `MergeTree() ORDER BY (category_key)` | Separate from skills |
| **P0 Dims** | `gold.dim_dates` | `dim_dates` | `MergeTree() ORDER BY (date_key)` | `date_key` → `UInt32`; `calendar_date` → `Date32` (NOTE: use **`Date32`**, NOT `Date`, to safely support outlier dates `1970-01-01` and `2099-12-31`, or map `9999-12-31` to `String`/`Nullable(Date32)` because ClickHouse `Date32` max is `2299-12-31`!) |
| **P0 Bridges** | `gold.bridge_opportunity_skills` | `bridge_opportunity_skills` | `MergeTree() ORDER BY (skill_key, opportunity_id)` | Deduplicated canonical bridge |
| **P0 Bridges** | `gold.bridge_opportunity_categories` | `bridge_opportunity_categories` | `MergeTree() ORDER BY (category_key, opportunity_id)` | Deduplicated canonical bridge |
| **P0 Bridges** | `gold.bridge_opportunity_work_modes` | `bridge_opportunity_work_modes` | `MergeTree() ORDER BY (work_mode, opportunity_id)` | 0 rows for `NULL`/`[]` |
| **P0 Bridges** | `gold.bridge_opportunity_employment_types` | `bridge_opportunity_employment_types` | `MergeTree() ORDER BY (employment_type, opportunity_id)` | 0 rows for `NULL`/`[]` |
| **P1 Marts** | `gold.mart_opportunities_by_source` | `mart_opportunities_by_source` | `MergeTree() ORDER BY (source_authority_rank, source_name)` | Always 8 rows |
| **P1 Marts** | `gold.mart_opportunities_by_category` | `mart_opportunities_by_category` | `MergeTree() ORDER BY (category_key)` | Non-additive across rows |
| **P1 Marts** | `gold.mart_opportunities_by_location` | `mart_opportunities_by_location` | `MergeTree() ORDER BY (location_key)` | Includes `'unreported'` bucket |
| **P1 Marts** | `gold.mart_opportunities_by_work_mode` | `mart_opportunities_by_work_mode` | `MergeTree() ORDER BY (opportunity_type, work_mode)` | Non-additive across `work_mode` |
| **P1 Marts** | `gold.mart_opportunities_by_employment_type` | `mart_opportunities_by_employment_type` | `MergeTree() ORDER BY (opportunity_type, employment_type)` | Non-additive across `employment_type` |
| **P1 Marts** | `gold.mart_skill_demand` | `mart_skill_demand` | `MergeTree() ORDER BY (canonical_opportunity_count, skill_key)` | Non-additive across skills |
| **P1 Marts** | `gold.mart_opportunity_lifecycle_trends` | `mart_opportunity_lifecycle_trends` | `MergeTree() ORDER BY (published_date_key, opportunity_type, effective_status)` | Reliable `exact`/`date_only` dates only |

> **Critical ClickHouse Date Range Warning for `dim_dates` & `fct_opportunities`:** ClickHouse `Date` supports `1970-01-01..2149-06-06` and `Date32` supports `1900-01-01..2299-12-31`. Because PostgreSQL `gold.dim_dates` preserves extreme outlier dates such as `9999-12-31` (`is_within_standard_calendar_range = FALSE`), Andrew's ClickHouse loader MUST either:
> 1. Store `calendar_date` as `Nullable(Date32)` (nulling dates `> 2299-12-31`) while always keeping `date_key` (`UInt32`, e.g., `99991231`) and `calendar_date_iso` (`String`, e.g., `'9999-12-31'`) intact, **or**
> 2. Store `calendar_date` as `String` in ClickHouse for full PostgreSQL parity.
> Failure to handle `9999-12-31` will cause a ClickHouse `Date`/`Date32` overflow error on anomalous source deadlines.
