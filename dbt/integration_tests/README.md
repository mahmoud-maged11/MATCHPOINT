# Phase 4 & Phase 5 Synthetic Integration Test Suite (`dbt/integration_tests/`)

This directory holds executable SQL fixtures, verification scripts, and idempotency checks that validate the **actual Phase 4 Silver deduplication models** and **Phase 5 Gold dimensions, facts, bridges, and analytical marts** end-to-end against synthetic Bronze records on an **isolated PostgreSQL 16 test database** (such as `matchpoint_test`).

> These files live outside `dbt/tests/` intentionally so dbt's singular test runner (`test-paths: ["tests"]`) does not try to execute DDL/DML fixture scripts as `SELECT` assertions. All mutating scripts enforce a `current_database() NOT ILIKE '%test%'` safety guard.

---

## Script Inventory & Responsibilities

### Phase 4 — Cross-Source Deduplication & Canonical Identity
| Script / Test | Purpose & Scenarios Verified |
|---|---|
| `load_phase4_synthetic_bronze.sql` | Loads 41 baseline synthetic source listings, 9 collection runs, and 2 Bronze history rows (`collection_scope = 'synthetic_phase4'`) covering all Phase 4 positive, negative, transitive, and conflict scenarios. |
| `verify_phase4_synthetic_results.sql` | Asserts all 10 Phase 4 verification groups (`PASS S1`–`PASS S10`) against materialized `silver.silver_opportunity_sources`, `silver.silver_opportunities`, and `silver.silver_opportunity_history`: Tier 1A direct Wuzzuf URL, case-sensitive ITIDA SharePoint paths, Tier 1B shared external URL with query params, Tier 2 composite English/Arabic Cairo match, same-source direct & transitive prevention, ambiguous same-source composite guard, generic portal exclusions (root + non-root paths), 4-source transitive chain + anchor authority stability, ADR-019 salary scale equivalence vs real `salary_period`/`employment_types` conflicts, false-positive prevention, and Bronze history preservation. Also re-run after Phase 5 edge-case loading as a regression check. |
| `verify_phase4_idempotency.sql` | Compares a Run 1 snapshot (`silver._tmp_phase4_run1_snapshot`) against Run 2 `silver.silver_opportunity_sources` on `(opportunity_id, source_listing_id, is_primary_source, match_method, canonical_anchor_key)` and asserts 0 diffs, then drops the temporary snapshot table. |
| `dbt/tests/assert_dedup_positive_and_negative_cases.sql` | Runs automatically inside `dbt test`; validates URL normalization macro, generic portal seed exclusions, ADR-019 salary conflict normalization, deterministic UUID stability, and `WITH RECURSIVE ... UNION` convergence on a 10-edge (11-node) chain. |

### Phase 5 — Gold Layer, Edge Cases & Full 20-Model Idempotency
| Script | Purpose & Scenarios Verified |
|---|---|
| `load_phase5_gold_skills_categories_enrichment.sql` | Enriches selected Phase 4 baseline listings with overlapping/aliased skills (`Python` vs `py`, `Power BI` vs `PowerBI`), categories (`Data Engineering`), and 1 persisted `bronze.invalid_records` row so canonical bridge deduplication and run telemetry can be verified without altering Phase 4's 41→32 merge topology. |
| `verify_phase5_gold_results.sql` | Runs immediately after the Phase 4 baseline + enrichment `dbt run` to verify 6 Gold baseline invariants (`PASS G1`–`PASS G6`): all 8 sources represented in `dim_sources` & `mart_opportunities_by_source`, 41→32 canonical parity, skill alias & canonical bridge deduplication (`Python` 4 raw → 3 canonical; `Power BI` 2 raw → 1 canonical), category bridge deduplication, consistency of location / work-mode / employment-type / primary-source lifecycle / publication-trend marts, and invalid-record telemetry in `fct_collection_runs`. |
| `load_phase5_edge_cases_synthetic.sql` | Appends 11 isolated edge-case listings (`collection_scope = 'synthetic_phase5_edge'`, UUIDs `2001`–`2011`) and 3 edge-case collection runs on top of the 41 baseline listings (total: 52 listings → 43 canonical opportunities) without disturbing any baseline canonical IDs. Covers outlier dates (`1970-01-01`, `2099-12-31`, `9999-12-31`), past `exact` & `date_only` deadlines, explicitly `closed` status with future deadline, `relative` publication/deadline precision, `NULL` location, confirmed empty `[]` JSONB arrays, `devpost` (hackathon) and `un_volunteers` (volunteering) sources, one-sided salary (`salary_min` only) combined with multiple `work_modes` and multiple `employment_types`, and a collection-run counter anomaly (`records_invalid > records_received`). |
| `verify_phase5_edge_cases.sql` | Runs after `load_phase5_edge_cases_synthetic.sql` + `dbt run` to assert all 11 edge-case outcomes (`PASS EC1`–`PASS EC11`): bounded `dim_dates` row count (`< 5000`) with outlier FK resolution and `is_within_standard_calendar_range = FALSE`, deadline expiration transitions, `closed` preservation, `relative` date nulling & trend exclusion, explicit `'unreported'` location bucket reconciling 100% to `fct_opportunities`, 0 bridge rows for `[]` arrays, `devpost`/`un_volunteers` counts, `salary_midpoint IS NULL` with `has_disclosed_salary = TRUE`, zero Cartesian multiplication across `mart_opportunities_by_work_mode` & `mart_opportunities_by_employment_type`, and anomaly flagging in `fct_collection_runs`. |
| `snapshot_phase5_gold_run1.sql` | Snapshots **all 20 Gold models** (6 dimensions, 7 facts/bridges, 7 analytical marts) into temporary `gold._tmp_run1_*` tables after Run 1, immediately prior to executing Run 2. |
| `verify_phase5_gold_idempotency.sql` | Performs symmetric two-way `EXCEPT` comparison between Run 1 (`gold._tmp_run1_*`) and Run 2 (`gold.*`) across **all 20 Gold models** and every column except the explicitly documented per-run wall-clock evaluation timestamp `lifecycle_evaluated_at` (on `fct_opportunities` only), asserts 0 row-count or content diffs across all 20 models, and drops all temporary snapshot tables. |

---

## Recommended End-to-End Execution Order

Run against an isolated PostgreSQL 16 test database (`matchpoint_test`) initialized with `database/migrations/001` through `007`:

1. **Empty Bronze Sanity Check (0 rows):**
   - `dbt debug --target test --profiles-dir .`
   - `dbt parse --target test --profiles-dir .`
   - `dbt seed --target test --profiles-dir .` *(loads all 5 seeds including `supported_sources`)*
   - `dbt run --target test --profiles-dir .` *(all 44 models on 0 Bronze rows)*
   - `dbt test --target test --profiles-dir .` *(all 461 dbt tests on 0 Bronze rows)*
2. **Phase 4 Baseline + Phase 5 Gold Baseline (41 listings → 32 canonical opportunities):**
   - Execute `load_phase4_synthetic_bronze.sql`
   - Execute `load_phase5_gold_skills_categories_enrichment.sql`
   - Run `dbt run --target test --profiles-dir .` and `dbt test --target test --profiles-dir .`
   - Execute `verify_phase4_synthetic_results.sql` *(asserts `PASS S1`–`PASS S10`)*
   - Execute `verify_phase5_gold_results.sql` *(asserts `PASS G1`–`PASS G6`)*
   - *(Optional baseline stability check)* Snapshot baseline `silver.silver_opportunity_sources` IDs to confirm zero drift after appending edge cases.
3. **Expanded Phase 5 Edge Cases + Phase 4 Regression (52 listings → 43 canonical opportunities):**
   - Execute `load_phase5_edge_cases_synthetic.sql`
   - Run **Run 1:** `dbt run --target test --profiles-dir .` and `dbt test --target test --profiles-dir .`
   - Re-run `verify_phase4_synthetic_results.sql` *(confirms zero Phase 4 regression)*
   - Execute `verify_phase5_edge_cases.sql` *(asserts `PASS EC1`–`PASS EC11`)*
4. **Full Idempotency Verification (Phase 4 + All 20 Gold Models):**
   - Create `silver._tmp_phase4_run1_snapshot` from `silver.silver_opportunity_sources`
   - Execute `snapshot_phase5_gold_run1.sql` *(snapshots all 20 Gold models)*
   - Run **Run 2:** `dbt run --target test --profiles-dir .` and `dbt test --target test --profiles-dir .`
   - Execute `verify_phase4_idempotency.sql` *(asserts 0 Phase 4 canonical ID/mapping diffs)*
   - Execute `verify_phase5_gold_idempotency.sql` *(asserts 0 diffs across all 20 Gold models)*

---

## Index & Query-Plan (`EXPLAIN`) Validation Note

The 33 PostgreSQL indexes declared across the 13 Gold dimensions, facts, and bridges were verified via `pg_indexes`, and representative `EXPLAIN` plans were checked with `SET enable_seqscan = off`. Using `enable_seqscan = off` confirms **index eligibility and predicate compatibility only**; it does **not** prove that PostgreSQL's default cost-based planner (`enable_seqscan = on`) will prefer index scans over sequential scans. Production-scale query-plan validation under normal planner settings and realistic live volumes remains pending persistent ingestion (`scrapers/storage/postgres.py`).
