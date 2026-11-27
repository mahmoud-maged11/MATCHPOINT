# Phase 7 — Live Integration & End-to-End Acceptance Plan

**Pipeline Scope:** `Source Scrapers → PostgreSQL Bronze → dbt Silver → Deduplication → Gold → Airflow → ClickHouse → Power BI / FastAPI`  
**Contract Baseline:** Data Contract `v3.0.0` (`ADR-050`)  
**Inspection Date:** `2026-11-27` (verified read-only across `feature/data-warehouse` and all remote feature branches)

---

## 1. Verified Current State of All Pipeline Components (Honest Separation)

| Pipeline Stage | Directory / Artifact | Owner | Verified Repository State | Integration Status |
|---|---|---|---|---|
| **1. Source Scrapers & Validation** | `scrapers/sources/`, `scrapers/models.py`, `scrapers/utils/` | Mahmoud | 8/8 adapters implemented; 665 Python unit tests passing (as of `2026-11-25`) | **Implemented (In-Memory / JSON)** |
| **2. Bronze Physical Schema** | `database/migrations/001..007`, `tests/sql/` | Momen / Mahmoud | 3 schemas, 6 Bronze tables (96 columns), 23 SQL checks passing (`f7216a9`) | **Verified** |
| **3. Persistent Bronze Ingestion** | `scrapers/storage/postgres.py` | **Mahmoud** | **0 bytes (empty file)**; `origin/feature/data-collection` at `ee3b029` | **BLOCKED (External — `B-006`)** |
| **4. dbt Silver, Dedup & Gold** | `dbt/` (44 models, 5 seeds, 461 tests, 33 Gold indexes) | **Momen** | Complete; 97 approved files staged for M1 commit; synthetic runtime verified on PostgreSQL 16.16 (`matchpoint_test`) | **Verified (Synthetic Only)** |
| **5. Airflow Orchestration** | `airflow/dags/` | **Andrew** | `.gitkeep` only (`origin/feature/orchestration` at `0912a49`) | **BLOCKED (External)** |
| **6. ClickHouse Analytical Store** | `clickhouse/` | **Andrew** | `.gitkeep` only (ClickHouse 25.8 container defined in `docker-compose.yml`, DDL/loaders not yet implemented) | **BLOCKED (External)** |
| **7. Power BI Dashboards** | `analytics/` | **Ramadan** | `.gitkeep` only (`origin/feature/analytics` at `0912a49`) | **BLOCKED (External)** |
| **8. FastAPI Backend** | `backend/` | **Mahmoud** | `.gitkeep` only (`origin/feature/backend` at `0912a49`) | **BLOCKED (External)** |
| **9. React Frontend** | `frontend/` | **Abdel Rahman** | `.gitkeep` only (`origin/feature/frontend` at `0912a49`) | **BLOCKED (External)** |

> **Clear Distinction:** All warehouse results reported to date (44 models, 461 dbt tests, 10 Phase 4 scenarios, 6 Gold baseline checks, 11 edge-case scenarios, 20-model Gold idempotency) were executed on **controlled synthetic fixtures in `matchpoint_test`**. **Zero live end-to-end integration claims are made** until the blocked external components above are delivered and executed against real records.

---

## 2. Stage-by-Stage Live Integration Procedures (Ready to Execute Immediately Upon Delivery)

### 2.1 Live Bronze Integration (Unblocked Once Mahmoud Delivers `scrapers/storage/postgres.py`)
1. **Schema & Constraint Compatibility Review:** Verify `scrapers/storage/postgres.py` writes cleanly to `bronze.collection_runs`, `bronze.source_listings`, `bronze.source_listing_history`, `bronze.ingestion_observations`, and `bronze.invalid_records` without violating any migration `002..007` check or unique constraint.
2. **40-Record Handover Sample (5 per Source × 8 Sources):**
   - Load the agreed 40-record validated handover sample through `scrapers/storage/postgres.py` into an isolated live-test database (e.g., `matchpoint_test` freshly migrated).
   - Verify all 8 sources appear in `bronze.source_listings` (`COUNT(*) = 5` per source, total `40`) and `bronze.collection_runs` has non-negative consistent counters (`records_invalid` vs `bronze.invalid_records` confirmed with Mahmoud).
3. **Run Full Warehouse Pipeline on Real Records:**
   - Execute `dbt seed` → `dbt run` → `dbt test` (all 44 models, 461 tests).
   - Inspect live deduplication outputs (`silver_opportunity_sources`, `silver_opportunities`) for:
     - Expected cross-source merges vs false positives/false negatives.
     - Conflict transparency (`has_source_attribute_conflicts`, `conflicting_attributes`).
     - Real-world unmapped organizations (`dim_organizations WHERE NOT is_alias_mapped`), unmapped locations (`dim_locations WHERE NOT is_standardized_mapping`), and unmapped skills (`dim_skills WHERE NOT is_alias_mapped`) to calibrate `organization_aliases.csv`, `location_mappings.csv`, `skill_aliases.csv`, and `generic_application_portals.csv`.
4. **Live Re-Run Idempotency & Reopening Verification (`LC-6`):**
   - Re-ingest the exact same 40-record sample (testing Bronze idempotency: `0` duplicate listings, `0` spurious `content_version` increments) and execute dbt Run 2 (`verify_phase4_idempotency.sql` + `verify_phase5_gold_idempotency.sql` → `0 diffs`).
   - Test at least one `active → closed → active` reopened listing cycle verifying `content_version` progression and 3 preserved rows in `silver_opportunity_history`.
5. **Production-Scale Query-Plan Verification (Normal Planner Settings — `enable_seqscan = on`):**
   - Once realistic multi-thousand-row live Bronze volume is loaded, run `ANALYZE` and execute `EXPLAIN (ANALYZE, BUFFERS)` with **default planner settings (`enable_seqscan = on`)** on:
     - `SELECT * FROM gold.fct_opportunities WHERE effective_status = 'active' AND opportunity_type = 'job' ORDER BY published_at DESC NULLS LAST LIMIT 50;`
     - `SELECT fo.opportunity_id, fo.title FROM gold.fct_opportunities fo WHERE fo.effective_status = 'active' AND EXISTS (SELECT 1 FROM gold.bridge_opportunity_skills bs WHERE bs.opportunity_id = fo.opportunity_id AND bs.skill_key = $1);`
     - `SELECT * FROM gold.fct_opportunity_sources WHERE opportunity_id = $1;`
   - Tune or add composite/partial indexes (e.g., partial index on `has_canonical_opportunities WHERE has_canonical_opportunities = TRUE`, or composite `(skill_key, opportunity_id)` on bridges) ONLY based on actual live `EXPLAIN (ANALYZE, BUFFERS)` evidence.

### 2.2 Airflow & ClickHouse Integration (Unblocked Once Andrew Delivers `airflow/dags/` & `clickhouse/`)
1. Verify Airflow invokes dbt strictly via `dbt/docs/dbt_execution_interface.md` (`dbt seed >> dbt run >> dbt test`).
2. Verify ClickHouse loading task is gated on `dbt test` exit code `0` and performs atomic table replacement (never append-only inserts).
3. Verify ClickHouse handles outlier dates (`9999-12-31`) without `Date`/`Date32` overflow (`dbt/docs/handoff_andrew_airflow_clickhouse.md §5`).
4. Run cross-engine parity check:
   - Exact row count match across all loaded Gold tables between PostgreSQL `gold.*` and ClickHouse `matchpoint_analytics.*`.
   - Exact aggregate match on `COUNT(*) FROM fct_opportunities`, `SUM(primary_canonical_opportunities) FROM mart_opportunities_by_source`, and `SUM(canonical_opportunity_count) FROM mart_opportunities_by_location`.

### 2.3 Power BI & FastAPI Integration (Unblocked Once Ramadan & Mahmoud Deliver `analytics/` & `backend/`)
1. **Power BI Verification (`Ramadan`):**
   - Confirm dashboard grand-total opportunity cards match `COUNT(*) FROM gold.fct_opportunities` (zero double-counting).
   - Confirm non-additive marts (`work_mode`, `employment_type`, `skill_demand`, `category`, `*_contributed_*`) do NOT display misleading additive grand totals.
   - Confirm `dim_dates[is_within_standard_calendar_range] = TRUE` is applied on trend visuals and `'Unreported'` location bucket reconciles totals.
   - Confirm salary visuals never average across mixed `currency` or `salary_period`.
2. **FastAPI Verification (`Mahmoud`):**
   - Confirm read-only consumption strictly from `gold.*` (no direct queries to `bronze.*` or `silver.int_*`).
   - Confirm opportunity detail responses expose all original links in `all_source_urls`, preserve `applicant_eligibility_raw`, and handle empty Bronze (`200` with `[]`) cleanly.
   - Confirm multi-value filtering uses bridge `EXISTS` checks without multiplying pagination totals.

---

## 3. Master End-to-End Acceptance Matrix (9 Mandatory Criteria)

| # | Acceptance Dimension | Verification Query / Evidence Required | Synthetic Baseline Status | Live E2E Status |
|---|---|---|---|---|
| 1 | **Data Completeness** | All 8 sources present in `bronze.source_listings`, `gold.dim_sources`, and `gold.mart_opportunities_by_source` | **PASS** (52 synthetic listings across 8 sources) | **Blocked (Mahmoud `B-006`)** |
| 2 | **Data Quality** | `dbt test` passes `461/461` (`0` errors, `0` warnings) on live Bronze | **PASS** (461/461 on 0, 41, and 52 rows) | **Blocked (Mahmoud `B-006`)** |
| 3 | **Canonical Opportunity Consistency** | 1-to-1 parity `silver_opportunities == fct_opportunities`; `same_source_violations = 0` | **PASS** (`assert_gold_canonical_opportunity_parity`) | **Blocked (Mahmoud `B-006`)** |
| 4 | **Source Traceability** | Every accepted Bronze `source_listing_id` present in `fct_opportunity_sources` and `fct_opportunities.all_source_urls`; history preserved | **PASS** (`assert_silver_source_attribution_complete`) | **Blocked (Mahmoud `B-006`)** |
| 5 | **No Double Counting** | `assert_gold_no_double_counting_in_marts` passes + Power BI cards match `fct_opportunities` | **PASS** (10 SQL mart invariants + EC10) | **Blocked (Andrew + Ramadan)** |
| 6 | **Lifecycle Consistency** | `exact`/`date_only` expiration, `closed` precedence, `relative` guard, reopened opportunity (`LC-6`), scheduled `dbt run` freshness (`LC-8`) | **PASS** (EC3–EC6; `LC-6` & `LC-8` pending live) | **Blocked (Mahmoud + Andrew)** |
| 7 | **Data Freshness** | `dbt source freshness` monitored; `NOW() - MAX(lifecycle_evaluated_at) <= 12h` via Airflow schedule | **Documented** (provisional 24h/72h) | **Blocked (Andrew)** |
| 8 | **Failure Handling** | Intentional `dbt test` failure halts Airflow ClickHouse load; partial scraper failure isolates without corrupting Bronze | **Documented** (`dbt_execution_interface.md`) | **Blocked (Mahmoud + Andrew)** |
| 9 | **Reproducibility & Idempotency** | Fresh `migrations 001..007` + `dbt seed/run/test` twice → `0 diffs` across Phase 4 & all 20 Gold models | **PASS** (0 diffs across 20/20 Gold models) | **Blocked (Full Team E2E)** |
