# Phase 5 Design Document: Gold Layer Architecture & Analytical Marts

This document defines the **MATCHPOINT Gold Layer** (`schema: gold`) built with **dbt** on **PostgreSQL 16**, aligned with **Data Contract v3.0.0**, **ADR-001 through ADR-012**, **ADR-018**, **ADR-019**, **ADR-047**, and **ADR-050**.

---

## 1. Design Principles & Consumers

The Gold Layer serves two downstream consumers without duplicating business rules already implemented in Silver:

1. **Application Backend & Matching (`FastAPI`, owned by Mahmoud):**
   - Consumes `fct_opportunities`, `fct_opportunity_sources`, and canonical bridge tables (`bridge_opportunity_skills`, `bridge_opportunity_categories`, `bridge_opportunity_work_modes`, `bridge_opportunity_employment_types`) using stable canonical `opportunity_id` UUIDs while preserving all original source URLs (`all_source_urls`, `fct_opportunity_sources`).
2. **Analytics & Visualization (`ClickHouse` loaded by Andrew → `Power BI` built by Ramadan):**
   - Consumes conformed star-schema dimensions, facts, bridges, and pre-aggregated analytical marts (`mart_*`).
   - Enforces the core counting rule (`data_contract.md §7.4`, `pending_tasks.md §10`): **unique opportunity KPIs are always counted at the canonical `opportunity_id` grain**, never double-counting duplicate cross-source listings.

---

## 2. Lineage & Dependency Boundaries

```text
Silver Layer (schema: silver)                           Gold Layer (schema: gold, materialized: table)
──────────────────────────────────────────────          ──────────────────────────────────────────────
silver_opportunities ─────────────────────────┬───────► gold.fct_opportunities          (PK: opportunity_id)
silver_opportunity_sources ───────────────────┼───────► gold.fct_opportunity_sources    (PK: source_listing_id)
silver_source_listings ───────────────────────┘         gold.dim_sources                (PK: source_name)
silver_organizations ─────────────────────────┬───────► gold.dim_organizations          (PK: organization_key)
silver_locations ─────────────────────────────┼───────► gold.dim_locations              (PK: location_key)
silver_skills ────────────────────────────────┼───────► gold.dim_skills                 (PK: skill_key)
silver_categories ────────────────────────────┘         gold.dim_categories             (PK: category_key)

silver_opportunity_sources + silver_listing_skills ───► gold.bridge_opportunity_skills
silver_opportunity_sources + silver_listing_categories► gold.bridge_opportunity_categories
silver_opportunities (work_modes JSONB) ──────────────► gold.bridge_opportunity_work_modes
silver_opportunities (employment_types JSONB) ────────► gold.bridge_opportunity_employment_types

stg_bronze__collection_runs + stg_bronze__invalid_records* ► gold.fct_collection_runs   (PK: run_id)

bounded calendar spine (2020-01-01 .. CURRENT_DATE+5y) ┐
UNION observed dates from gold.fct_opportunities       ├─► gold.dim_dates               (PK: date_key)
UNION observed dates from gold.fct_collection_runs     ┘
  (outlier dates included via UNION without expanding GENERATE_SERIES)

Gold Dimensions + Facts + Bridges ────────────────────► gold.mart_opportunities_by_source
                                                        gold.mart_opportunities_by_category
                                                        gold.mart_opportunities_by_location
                                                        gold.mart_opportunities_by_work_mode
                                                        gold.mart_opportunities_by_employment_type
                                                        gold.mart_skill_demand
                                                        gold.mart_opportunity_lifecycle_trends
```

> **\*Explicitly Justified Staging Dependency (`fct_collection_runs`):** All opportunity, entity, skill, category, and source attribution Gold models read exclusively from **Silver models** (`silver_*`) and the shared `supported_sources` seed. Only `fct_collection_runs` reads from `stg_bronze__collection_runs` and `stg_bronze__invalid_records` (staging views in the `silver` schema) because Silver intentionally models accepted opportunities rather than run-level ingestion telemetry and rejected records (`ADR-009`, `ADR-046`). Gold never queries `bronze.*` directly via `source()`.

---

## 3. Gold Models Inventory, Indexing & Materialization Strategy

All **20 Gold models** (6 Dimensions, 7 Facts/Bridges, 7 Analytical Marts) materialize as **`table`** in the `gold` schema (`dbt_project.yml`: `gold: {+schema: gold, +materialized: table}`):
- **Rationale:** Downstream consumers (FastAPI APIs, ClickHouse extract jobs, Power BI DirectQuery/Import) require fast indexed table reads without re-evaluating recursive Silver deduplication views at query time. Full-refresh tables also align with Silver's stateless materialization and guarantee deterministic idempotency on every `dbt run`.
- **PostgreSQL Indexes (33 total across 13 Dimensions, Facts, and Bridges):** Every Dimension and Fact/Bridge declares explicit dbt `config(indexes=[...])` (15 unique PK/alternate-key indexes + 18 non-unique join/filter indexes; the 7 small pre-aggregated marts intentionally omit extra indexes).
  - **Query-Plan (`EXPLAIN`) Validation Limitation:** Synthetic runtime verification on `matchpoint_test` confirmed all 33 index definitions via `pg_indexes` and ran representative `EXPLAIN` checks with `SET enable_seqscan = off`. Setting `enable_seqscan = off` proves **index eligibility and predicate compatibility only** — it does **not** prove that the default PostgreSQL cost-based planner (`enable_seqscan = on`) will select those indexes over sequential scans. Production-scale query-plan validation under realistic data volumes and normal planner settings remains pending live data ingestion.

### 3.1 Dimensions (`dbt/models/gold/dimensions/`)
| Model | Primary Key | Source Dependencies | Responsibility |
|---|---|---|---|
| `dim_sources` | `source_name` | `supported_sources` (seed), `silver_opportunity_sources`, `silver_opportunities`, `fct_collection_runs` | Conformed dimension of all 8 approved Data Contract v3.0.0 sources derived from the single authoritative `supported_sources` seed (shared with Phase 4 `int_listing_match_features`) with authority rank, collection approach, and listing/canonical counts. |
| `dim_organizations` | `organization_key` | `silver_organizations`, `silver_opportunities` | Conformed organizations with canonical opportunity counts, active counts, and `has_canonical_opportunities` boolean flag (secondary organizations from non-primary merged listings remain present for Silver lineage parity with `has_canonical_opportunities = FALSE`). |
| `dim_locations` | `location_key` | `silver_locations`, `silver_opportunities` | Conformed opportunity locations (city/governorate/country/online flag; kept separate from org HQ and applicant eligibility) with `has_canonical_opportunities` boolean flag. |
| `dim_skills` | `skill_key` | `silver_skills`, `bridge_opportunity_skills`, `fct_opportunities` | Conformed candidate skills (`ADR-007`) with deduplicated canonical opportunity counts. |
| `dim_categories` | `category_key` | `silver_categories`, `bridge_opportunity_categories`, `fct_opportunities` | Conformed opportunity categories kept strictly separate from skills (`ADR-007`). |
| `dim_dates` | `date_key` (`INTEGER YYYYMMDD`) | `fct_opportunities`, `fct_collection_runs` | Bounded UTC calendar spine (`2020-01-01` through `CURRENT_DATE + 5 years`) unioned with all genuinely observed fact dates outside that window (`is_within_standard_calendar_range = FALSE`) to guarantee 100% FK resolvability without generating millions of rows for outlier dates (e.g. `1970-01-01`, `9999-12-31`). |

### 3.2 Facts & Canonical Bridges (`dbt/models/gold/facts/`)
| Model | Primary Key | Grain | Responsibility |
|---|---|---|---|
| `fct_opportunities` | `opportunity_id` | 1 row per canonical opportunity | Core business fact table linking to `dim_organizations`, `dim_locations`, `dim_sources`, and `dim_dates`; provides lifecycle boolean flags, disclosed salary/experience bounds, conflict flags, and preserved JSONB arrays + `all_source_urls`. Defines 6 PostgreSQL indexes: `opportunity_id` (unique PK), `(effective_status, opportunity_type)`, `organization_key`, `location_key`, `primary_source_name`, and `published_date_key`. |
| `fct_opportunity_sources` | `source_listing_id` | 1 row per accepted source listing | Source attribution & deduplication audit fact linking every `source_listing_id` to `fct_opportunities.opportunity_id` and `dim_sources.source_name` with `match_method`, `match_evidence`, and `is_primary_source`. |
| `bridge_opportunity_skills` | `opportunity_skill_id` | 1 row per unique `(opportunity_id, skill_key)` | Canonical skill bridge deduplicated across merged sources with explicit provenance precedence (`explicit_source_tag` over `extracted`) and `BOOL_AND(is_candidate_skill)`. |
| `bridge_opportunity_categories` | `opportunity_category_id` | 1 row per unique `(opportunity_id, category_key)` | Canonical category bridge deduplicated across merged sources. |
| `bridge_opportunity_work_modes` | `opportunity_work_mode_id` | 1 row per unique `(opportunity_id, work_mode)` | Canonical work-mode bridge expanded from `silver_opportunities.work_modes` (respecting `unknown` exclusivity; 0 rows for NULL or confirmed empty `[]`). |
| `bridge_opportunity_employment_types` | `opportunity_employment_type_id` | 1 row per unique `(opportunity_id, employment_type)` | Canonical employment-type bridge expanded from `silver_opportunities.employment_types` (respecting `unknown` exclusivity; 0 rows for NULL or confirmed empty `[]`). |
| `fct_collection_runs` | `run_id` | 1 row per collection run | Operational & data quality telemetry fact joining `stg_bronze__collection_runs` with persisted `stg_bronze__invalid_records` counts, exposing `persisted_vs_reported_invalid_diff`, `has_invalid_counter_anomaly`, and bounded `invalid_record_rate` (`[0, 1]` or `NULL` on counter anomaly). |

### 3.3 Analytical Marts (`dbt/models/gold/marts/`)
| Model | Grain | Additivity & Analytical Questions Answered |
|---|---|---|
| `mart_opportunities_by_source` | `source_name` (all 8 sources) | **Strictly Additive:** `primary_canonical_opportunities` and `primary_{active,expired,closed,unknown}_opportunities` (sum across all 8 sources = `fct_opportunities`). **Non-Additive:** `canonical_opportunities_contributed` and `{active,expired,closed,unknown}_contributed_opportunities` (multi-source opportunities count under each contributing source). |
| `mart_opportunities_by_category` | `category_key` | **Non-Additive across categories** (multi-category opportunities appear in each category). Canonical opportunities by category and lifecycle status. |
| `mart_opportunities_by_location` | `location_key` (incl. `'unreported'`) | **Strictly Additive across all rows** (sum = `fct_opportunities`). Includes an explicit `'unreported'` bucket (`is_unreported_location = TRUE`) whenever opportunities have `location_key IS NULL`. |
| `mart_opportunities_by_work_mode` | `(opportunity_type, work_mode)` | **Non-Additive across `work_mode` within an `opportunity_type`** (ADR-002 multi-value work modes). Replaces the former Cartesian arrangement mart to prevent artificial cross-product multiplication. `'unreported'` covers `NULL` or confirmed empty `[]`. |
| `mart_opportunities_by_employment_type` | `(opportunity_type, employment_type)` | **Non-Additive across `employment_type` within an `opportunity_type`** (ADR-001 multi-value employment types). Replaces the former Cartesian arrangement mart to prevent artificial cross-product multiplication. `'unreported'` covers `NULL` or confirmed empty `[]`. |
| `mart_skill_demand` | `skill_key` | **Non-Additive across skills.** Most demanded candidate skills ranked by canonical opportunity count, active count, and share of opportunities with disclosed skills. |
| `mart_opportunity_lifecycle_trends` | `(published_date, opportunity_type, effective_status)` | **Strictly Additive for reliable-date subset.** Publication trends strictly restricted to reliable `exact`/`date_only` publication dates (`published_at IS NOT NULL AND published_at_precision IN ('exact', 'date_only')`). |

---

## 4. Assumptions, Non-Invented Metrics & Unresolved Questions

1. **No cross-currency or cross-period salary aggregation:** Gold deliberately avoids computing global average salaries across mixed currencies (`EGP`, `USD`, etc.) and mixed periods (`hourly`, `monthly`, `yearly`). `fct_opportunities` exposes `salary_midpoint` only within a single opportunity when both `salary_min` and `salary_max` are present.
2. **No fabricated applicant eligibility:** `applicant_eligibility_raw` is passed through from Silver without converting `'unverified'` or online delivery into a boolean `is_egypt_eligible` flag (`data_contract.md §5.11–5.12`).
3. **No fabricated publication trends:** `mart_opportunity_lifecycle_trends` excludes rows with missing or `relative`/`unknown` publication precision rather than substituting `collected_at` (`ADR-006`).
4. **Candidate skills disclaimer:** `mart_skill_demand` and `dim_skills` preserve `is_candidate_skill = TRUE` (`ADR-007`) until downstream skill taxonomy validation is finalized.
5. **Unresolved downstream interface details (to coordinate with Andrew, Ramadan, and Mahmoud):**
   - Exact ClickHouse `MergeTree` table DDL and incremental sync cadence (Andrew).
   - Whether Power BI requires additional currency-normalized salary bands once live salary volume is ingested (Ramadan).
   - Exact user-profile and recommendation scoring tables once FastAPI backend development starts (Mahmoud).
