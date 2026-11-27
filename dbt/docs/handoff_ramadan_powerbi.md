# Downstream Handoff Contract — Ramadan (Power BI & Analytics)

**Owner (Consumer):** Ramadan (`analytics/`, Power BI dashboards)  
**Owner (Producer):** Momen (`dbt/`, `gold.*` models; delivered via Andrew's ClickHouse `matchpoint_analytics`)  
**Contract Version:** Data Contract `v3.0.0` (ADR-050)  
**Current External Component Status:** Verified read-only — `analytics/` contains `.gitkeep` only (`origin/feature/analytics` at `0912a49`). This contract defines the exact star schema, KPI formulas, additivity rules, and anti-double-counting rules for Power BI.

---

## 1. Recommended Tables & Marts for Power BI

Power BI can consume Gold datasets either through the **Star Schema** (for interactive cross-filtering across dimensions) or directly through **Pre-Aggregated Marts** (for fast executive cards and standalone charts):

### A. Interactive Star Schema (Recommended Primary Power BI Semantic Model)
- **Core Fact:** `fct_opportunities` (1 row = 1 unique canonical opportunity)
- **Operational Fact:** `fct_collection_runs` (1 row = 1 collection run)
- **Source Audit Fact:** `fct_opportunity_sources` (1 row = 1 source listing; use ONLY for source-overlap/attribution pages, never for grand-total unique opportunities!)
- **Conformed Dimensions:** `dim_sources`, `dim_organizations`, `dim_locations`, `dim_skills`, `dim_categories`, `dim_dates`
- **Canonical Bridges:** `bridge_opportunity_skills`, `bridge_opportunity_categories`, `bridge_opportunity_work_modes`, `bridge_opportunity_employment_types`

### B. Pre-Aggregated Analytical Marts (Standalone Page / Fast Visual Sources)
- `mart_opportunities_by_source` — Source comparison & quality scorecard
- `mart_opportunities_by_location` — Geographic breakdown (includes explicit `'unreported'`)
- `mart_opportunities_by_category` — Category breakdown
- `mart_opportunities_by_work_mode` — Work mode breakdown by opportunity type
- `mart_opportunities_by_employment_type` — Employment type breakdown by opportunity type
- `mart_skill_demand` — Top demanded candidate skills
- `mart_opportunity_lifecycle_trends` — Reliable publication trend over time

---

## 2. Recommended Power BI Star-Schema Relationships

| From (Many / Bridge) | To (One / Dimension) | Cardinality | Cross-Filter Direction | Active / Notes |
|---|---|---|---|---|
| `fct_opportunities[primary_source_name]` | `dim_sources[source_name]` | Many-to-One | Single | **Active** |
| `fct_opportunities[organization_key]` | `dim_organizations[organization_key]` | Many-to-One | Single | **Active** (nullable FK; blank = undisclosed org) |
| `fct_opportunities[location_key]` | `dim_locations[location_key]` | Many-to-One | Single | **Active** (nullable FK; blank = unreported location) |
| `fct_opportunities[published_date_key]` | `dim_dates[date_key]` | Many-to-One | Single | **Active** (primary date axis for publication trends) |
| `fct_opportunities[deadline_date_key]` | `dim_dates[date_key]` | Many-to-One | Single | **Inactive** (activate via `USERELATIONSHIP` on deadline visuals) |
| `fct_opportunities[first_seen_date_key]` | `dim_dates[date_key]` | Many-to-One | Single | **Inactive** (use ONLY for pipeline observation visuals, never publication trends) |
| `fct_collection_runs[source_name]` | `dim_sources[source_name]` | Many-to-One | Single | **Active** |
| `fct_collection_runs[started_date_key]` | `dim_dates[date_key]` | Many-to-One | Single | **Active** (or inactive if sharing `dim_dates` with `fct_opportunities`) |
| `bridge_opportunity_skills[opportunity_id]` | `fct_opportunities[opportunity_id]` | Many-to-One | **Both** *(or via DAX `TREATAS`)* | Required so selecting a `dim_skills` row filters `fct_opportunities` |
| `bridge_opportunity_skills[skill_key]` | `dim_skills[skill_key]` | Many-to-One | Single | **Active** |
| `bridge_opportunity_categories[opportunity_id]` | `fct_opportunities[opportunity_id]` | Many-to-One | **Both** *(or via DAX `TREATAS`)* | Filters `fct_opportunities` by category |
| `bridge_opportunity_categories[category_key]` | `dim_categories[category_key]` | Many-to-One | Single | **Active** |
| `bridge_opportunity_work_modes[opportunity_id]` | `fct_opportunities[opportunity_id]` | Many-to-One | **Both** | Filters `fct_opportunities` by work mode |
| `bridge_opportunity_employment_types[opportunity_id]` | `fct_opportunities[opportunity_id]` | Many-to-One | **Both** | Filters `fct_opportunities` by employment type |

> **Important Modeling Note:** Keep `fct_opportunity_sources` disconnected or single-directional from `fct_opportunities[opportunity_id]` and ALWAYS compute unique opportunity counts with `DISTINCTCOUNT(fct_opportunities[opportunity_id])` so bidirectional bridge filters never inflate row counts.

---

## 3. Official KPI Definitions & Formulas (100% SQL-Aligned)

| KPI Name | Source Table | Exact Formula (SQL / DAX Equivalent) | Additivity |
|---|---|---|---|
| **Total Unique Opportunities** | `fct_opportunities` | `COUNT(DISTINCT opportunity_id)` / `DISTINCTCOUNT(fct_opportunities[opportunity_id])` | **Strictly Additive** (by primary source, type, status, location) |
| **Active Opportunities** | `fct_opportunities` | `COUNT(DISTINCT opportunity_id) FILTER (WHERE is_active)` | **Strictly Additive** |
| **Expired / Closed / Unknown Opportunities** | `fct_opportunities` | `COUNT(DISTINCT opportunity_id) FILTER (WHERE is_expired / is_closed / is_unknown_status)` | **Strictly Additive** (sum of all 4 statuses == Total Unique Opportunities) |
| **Multi-Source Opportunities** | `fct_opportunities` | `COUNT(DISTINCT opportunity_id) FILTER (WHERE is_multi_source)` | **Strictly Additive** |
| **Deduplication Compression Ratio** | `fct_opportunity_sources` & `fct_opportunities` | `1 - (DISTINCTCOUNT(fct_opportunities[opportunity_id]) / COUNTROWS(fct_opportunity_sources))` | Ratio (**Non-Additive** — recompute from numerator & denominator) |
| **Primary Canonical Opportunities (by Source)** | `mart_opportunities_by_source` | `SUM(primary_canonical_opportunities)` | **Strictly Additive** across all 8 sources (`SUM == Total Unique Opportunities`) |
| **Source Contributed Opportunities** | `mart_opportunities_by_source` | `canonical_opportunities_contributed` (per source row only) | **NON-ADDITIVE** across sources — NEVER display a grand-total sum! |
| **Disclosed Salary Share** | `fct_opportunities` | `DIVIDE(COUNTROWS(FILTER(fct_opportunities, has_disclosed_salary)), COUNTROWS(fct_opportunities))` | Ratio (**Non-Additive**) |
| **Median / Average Disclosed Salary** | `fct_opportunities` | **MUST** filter to a **single `currency` AND single `salary_period`** (e.g., `currency = "EGP" && salary_period = "monthly"`) and use `salary_midpoint` (only non-null when both `salary_min` & `salary_max` exist) | Semi-additive — NEVER average across mixed currencies or periods |
| **Skill Demand Count** | `mart_skill_demand` / `bridge_opportunity_skills` | `canonical_opportunity_count` (`DISTINCTCOUNT(bridge_opportunity_skills[opportunity_id])`) | **NON-ADDITIVE** across skills |
| **Skill Demand Share** | `mart_skill_demand` | `share_of_opportunities_with_skills` (denominator = opportunities disclosing `>= 1` skill) | **NON-ADDITIVE** (sums > 100%) |
| **Run Invalid Record Rate** | `fct_collection_runs` | `DIVIDE(SUM(records_invalid), SUM(records_received))` (excluding rows where `has_invalid_counter_anomaly = TRUE`) | Ratio (**Non-Additive** — never average `invalid_record_rate` column!) |

---

## 4. Additive vs Non-Additive Rules (Quick Reference Matrix)

| Table / Metric Group | Additive Across Rows? | Safe to Show Table "Total" Row in Power BI? |
|---|---|---|
| `fct_opportunities` counts by `opportunity_type` or `effective_status` | **YES** | **YES** |
| `mart_opportunities_by_source`: `primary_canonical_opportunities`, `primary_{active,expired,closed,unknown}_opportunities`, `total_source_listings` | **YES** | **YES** (equals `fct_opportunities` totals) |
| `mart_opportunities_by_source`: `canonical_opportunities_contributed`, `{active,expired,closed,unknown}_contributed_opportunities` | **NO** | **NO** — turn OFF Total row or override with `DISTINCTCOUNT(fct_opportunities[opportunity_id])` |
| `mart_opportunities_by_location`: all count columns (including `'unreported'`) | **YES** | **YES** (equals `fct_opportunities` totals) |
| `mart_opportunities_by_work_mode`: `opportunities_with_work_mode_count` | **NO** (within an `opportunity_type`) | **NO** — one opportunity can be both `hybrid` and `remote` |
| `mart_opportunities_by_employment_type`: `opportunities_with_employment_type_count` | **NO** (within an `opportunity_type`) | **NO** — one opportunity can be both `part_time` and `freelance` |
| `mart_opportunities_by_category`: `canonical_opportunity_count` | **NO** | **NO** — one opportunity can belong to multiple categories |
| `mart_skill_demand`: `canonical_opportunity_count`, `share_of_opportunities_with_skills` | **NO** | **NO** — one opportunity lists multiple skills |
| `mart_opportunity_lifecycle_trends`: all count columns | **YES** *(for reliable-date subset only)* | **YES** (equals `fct_opportunities` where `published_date_key IS NOT NULL`) |

---

## 5. Date Filtering, NULL / Unreported Handling & Guardrails

1. **Date Filtering & Outlier Protection (`dim_dates`):**
   - Always apply a visual/page filter **`dim_dates[is_within_standard_calendar_range] = TRUE`** on time-series charts so anomalous source dates (such as `1970-01-01`, `2099-12-31`, `9999-12-31`) do not stretch chart axes across 8,000 years.
   - Surface a small data-quality badge/card showing `COUNTROWS(FILTER(fct_opportunities, ISBLANK(published_date_key)))` alongside publication trend charts so stakeholders see how many opportunities had missing/relative publication dates and were intentionally excluded (`ADR-006`).
   - Use `dim_dates[is_egypt_weekend]` (`Friday` & `Saturday`) when analyzing weekday vs weekend posting patterns in Egypt.
2. **Handling `NULL` and `'unreported'` Buckets:**
   - **Location:** `mart_opportunities_by_location` already includes an explicit `'Unreported'` row (`is_unreported_location = TRUE`) so charts add up to 100% of opportunities. In the Star Schema, opportunities with `location_key IS NULL` appear under `(Blank)` unless labeled `'Unreported'` in a calculated display column.
   - **Work Modes & Employment Types:** `mart_opportunities_by_work_mode` and `mart_opportunities_by_employment_type` map both `NULL` (missing) and `[]` (confirmed empty) to `'unreported'` without altering Silver/Gold `NULL` semantics.
   - **Secondary Organizations & Locations:** In `dim_organizations` and `dim_locations`, filter slicers by **`has_canonical_opportunities = TRUE`** so secondary names observed only on non-primary merged listings (`canonical_opportunity_count = 0`) do not clutter dropdowns.
3. **Anti-Double-Counting Guardrails (Mandatory Checklist for Ramadan):**
   - NEVER sum `mart_opportunities_by_work_mode` and `mart_opportunities_by_employment_type` together or cross-join their bridges.
   - NEVER sum `canonical_opportunities_contributed` across sources — use `primary_canonical_opportunities` for additive breakdowns and `canonical_opportunities_contributed` strictly for "Platform Reach / Coverage" per-platform bars.
   - NEVER display `is_online_location_label = TRUE` as "Egypt Eligible" — show `applicant_eligibility_raw` transparently (`data_contract.md §5.11–5.12`).
   - Label skill visuals as **"Candidate Skills (ADR-007)"** until skill taxonomy curation is finalized.
