# MATCHPOINT Opportunity Lifecycle Requirements Specification

**Governance Reference:** `ADR-018`, `ADR-022`, `ADR-043`, `ADR-047`, `ADR-050`, Data Contract `v3.0.0`  
**Current Implementation Reviewed:**
- Source-level derivation: `dbt/models/intermediate/int_listings_cleaned.sql` (lines 198–234)
- Canonical synthesis: `dbt/models/silver/silver_opportunities.sql` (lines 280–286, 448–453)
- Historical preservation: `bronze.source_listing_history` → `silver.silver_listing_history` → `silver.silver_opportunity_history`
- Gold consumption: `gold.fct_opportunities` (`effective_status`, `primary_effective_status`, `primary_observed_status`, `observed_effective_statuses`, `lifecycle_evaluated_at`, `is_active`, `is_expired`, `is_closed`, `is_unknown_status`)

> **Strict Baseline Rule:** This document specifies lifecycle requirements, analyzes current behavior, and documents proposed future SQL enhancements **without silently modifying accepted Phase 1–5 SQL models**.

---

## 1. Current Verified Lifecycle Behavior (Phase 3–5 Baseline)

### 1.1 Source-Listing Level (`int_listings_cleaned.sql`)
For each accepted `source_listing_id`:
1. **Explicit `closed` / `expired` precedence:** If Bronze `observed_status IN ('closed', 'expired')`, `effective_status = observed_status` (`effective_status_reason = 'observed_source_status'`).
2. **Exact deadline expiration:** If `observed_status NOT IN ('closed', 'expired')` and `deadline IS NOT NULL` and `deadline_precision = 'exact'` and `deadline < CURRENT_TIMESTAMP`, then `effective_status = 'expired'` (`exact_deadline_passed`).
3. **Conservative `date_only` deadline expiration:** If `deadline_precision = 'date_only'` and `((DATE_TRUNC('day', deadline AT TIME ZONE 'UTC') + INTERVAL '36 hours') AT TIME ZONE 'UTC') < CURRENT_TIMESTAMP`, then `effective_status = 'expired'` (`date_only_deadline_passed_conservative`) — i.e., UTC midnight + 24h day end + 12h timezone safety buffer.
4. **Uncertain deadlines never auto-expire:** `relative`, `unknown`, or `NULL` deadlines retain `observed_status`.
5. **No promotion of `unknown`:** A future deadline NEVER promotes `observed_status = 'unknown'` to `'active'`.
6. **No absence-based closure:** Absence from a bounded collection run NEVER sets `closed` or `expired` (`ADR-022`, `ADR-047`).
7. **Evaluation timestamp:** `lifecycle_evaluated_at = CURRENT_TIMESTAMP` records exact UTC evaluation time.

### 1.2 Canonical Opportunity Level (`silver_opportunities.sql`)
When multiple sources merge into one canonical `opportunity_id`, `silver_opportunities` currently applies conservative precedence across all merged members:
```sql
CASE
    WHEN BOOL_OR(effective_status = 'closed') THEN 'closed'
    WHEN BOOL_OR(effective_status = 'expired') THEN 'expired'
    WHEN BOOL_OR(effective_status = 'active') THEN 'active'
    ELSE 'unknown'
END AS effective_status
```
Meanwhile, `primary_effective_status`, `primary_observed_status`, `observed_effective_statuses`, and `conflicting_attributes` (`'effective_status'`) preserve full transparency when merged sources disagree.

---

## 2. Reopened Opportunities Requirements (`ADR-047`)

### 2.1 Single-Source Reopening (Already Supported by Current Baseline)
When a previously `closed` or `expired` opportunity is reopened on its source platform (e.g., an employer extends the deadline to a future date and switches status back to `active`):
1. **Bronze Ingestion (`Mahmoud`):**
   - Retains the **exact same** `source_listing_id` and `(source_name, source_identity_key)` (`ADR-042`, `ADR-047`).
   - Because `status` and/or `deadline` changed, `content_hash` changes → Bronze increments `content_version` (e.g., `v1 [active] → v2 [closed] → v3 [active]`) and appends a new immutable snapshot row in `bronze.source_listing_history` (`ADR-043`).
   - Note: `A → B → A` reopening (returning to the exact original `content_hash`) is explicitly supported by `bronze.source_listing_history`'s `UNIQUE (source_listing_id, content_version)` constraint!
2. **Silver & Gold Transformation (`Momen`):**
   - On the next `dbt run`, `int_listings_cleaned` sees `observed_status = 'active'` and the extended future (or `NULL`) deadline → `effective_status` transitions cleanly back to `'active'`.
   - `silver_opportunity_history` preserves all three historical snapshots (`v1`, `v2`, `v3`) linked to the same canonical `opportunity_id`.

### 2.2 Multi-Source Reopening Edge Case (Identified Gap — Proposed Future Enhancement)
- **Scenario:** Opportunity X exists on both `wuzzuf` (primary, `rank=5`, `last_seen_at = Day 10`, reopened to `active` with new future deadline) and `egyincs` (secondary aggregator, `rank=8`, `last_seen_at = Day 5`, still showing old `closed` or old expired deadline because Egyincs has not re-crawled yet).
- **Current Baseline Behavior:** Because `silver_opportunities.sql` uses unconditional `BOOL_OR(effective_status = 'closed')` / `BOOL_OR(effective_status = 'expired')` across all cluster members, the stale secondary listing (`egyincs`) will keep the canonical `effective_status = 'closed'` or `'expired'` even though the newer, higher-authority primary listing (`wuzzuf`) explicitly reopened it! `conflicting_attributes` flags `'effective_status'` transparently, so the conflict is visible, not hidden.
- **Proposed Future SQL Enhancement (Documented ONLY — Requires Explicit Team Approval Before Modifying Accepted Phase 4 SQL):**
  - **Option A (Recency + Authority Precedence for Reopening):** If the primary source listing has `effective_status = 'active'` AND its `last_seen_at` is strictly newer than every `closed`/`expired` secondary listing (e.g., by `>= 24 hours`) AND has a valid future deadline (or explicit active re-observation), allow primary `'active'` to take precedence while retaining `'effective_status'` in `conflicting_attributes`.
  - **Option B (Status Quo + Secondary Revalidation):** Keep current conservative `closed > expired > active > unknown` rule until live multi-source reopening frequency is observed, and rely on scheduled secondary-source revalidation to refresh stale mirrors.
  - **Impact if Option A is later adopted:** Affects ONLY `silver_opportunities.sql` (lines 280–286) and requires a new singular test verifying recency-aware multi-source reopening. **Decision pending team review after live multi-source data arrives.**

---

## 3. `effective_status` Freshness & Time-Dependent Recomputation

Because `gold.fct_opportunities` is materialized as a physical **`table`** (not a live view), `effective_status` reflects the state at `lifecycle_evaluated_at` (`CURRENT_TIMESTAMP` of the last `dbt run`):
- **Freshness SLA Requirement:**
  - **Minimum scheduled cadence:** Airflow MUST execute `dbt run` + `dbt test` at least **twice daily** (`00:15 UTC` and `12:15 UTC`), and immediately after every scheduled collection batch completes.
  - **Rationale:**
    - `00:15 UTC` catches `exact` deadlines that expired at end-of-day UTC and transitions `date_only` deadlines whose `+36h` window elapsed at `12:00 UTC` the prior day.
    - `12:15 UTC` catches `date_only` deadlines that crossed their `12:00 UTC` (`+36h`) conservative expiration boundary (`DATE_TRUNC('day', deadline) + INTERVAL '36 hours'`).
  - **Max Acceptable Staleness for `lifecycle_evaluated_at`:** `<= 12 hours` in normal operation; alert via Airflow monitoring if `NOW() - MAX(lifecycle_evaluated_at) > INTERVAL '24 hours'`.
- **No Artificial Bronze Versions:** Passage of time alone (when a deadline passes and `dbt run` transitions `effective_status` from `active` to `expired`) MUST NEVER mutate `bronze.source_listings` or create a new `bronze.source_listing_history` row (`ADR-047`).

---

## 4. Source Revalidation Schedules & Stale Opportunity Handling

| Source Category | Sources | Recommended Collection / Revalidation Cadence | Stale Opportunity Handling Policy |
|---|---|---|---|
| **High-Churn Job Boards** | `wuzzuf`, `forasna`, `bayt` | Bounded new-listings run every **6–12 hours**; targeted revalidation of `active` listings without reliable deadlines (`deadline IS NULL`) older than **14 days** (`last_seen_at`) | Never mark `closed` from search-page absence; only explicit HTTP 404/410 or explicit "Position Closed / Expired" page evidence updates Bronze `status = 'closed'`. |
| **Aggregators & Community** | `egyincs` | Every **12–24 hours** (separate `jobs` and `lp_course` scopes) | Revalidate listings whose `last_seen_at` > 14 days if application availability is uncertain (`B-010`). |
| **Training, Hackathons & Volunteering** | `itida`, `nti`, `devpost`, `un_volunteers` | Daily (**24 hours**) | Rely on reliable `deadline` (`exact`/`date_only`) for automatic expiration; retain historical program/event archives with explicit `expired`/`closed`/`unknown` status so historical records are never shown as currently open (`pending_tasks.md:379`). |

### Stale Opportunity Visibility (Proposed Future Analytical Attribute)
- Currently `fct_opportunities` exposes `last_seen_at` and `last_seen_date_key` directly so FastAPI/Power BI can compute observation age (`CURRENT_DATE - last_seen_at::DATE`).
- **Recommendation (no SQL change required now):** Consumers may display a UI indicator (e.g., *"Last verified X days ago"*) when `effective_status = 'active' AND deadline IS NULL AND last_seen_at < NOW() - INTERVAL '30 days'`, without falsely mutating `effective_status` to `'closed'`.

---

## 5. Historical Status vs Current Status Preservation

| Layer / Table | What It Represents | Status Semantics | Immutability |
|---|---|---|---|
| `bronze.source_listings` | Latest accepted observation per source listing | `status` = latest **observed** status from source | Mutable on newer observations |
| `bronze.source_listing_history` | Append-only content-version snapshots (`v1, v2, ...`) | `standardized_payload ->> 'status'` = **historical observed** status at `observed_at` | **Append-only immutable** (`ADR-043`) |
| `silver.silver_listing_history` & `silver.silver_opportunity_history` | Historical version snapshots linked to canonical `opportunity_id` | Historical observed status at each content revision | Rebuilt from immutable Bronze history |
| `gold.fct_opportunities` | **Current** canonical opportunity state as of `lifecycle_evaluated_at` | `effective_status` (current derived status), `primary_observed_status` (latest raw primary status), `observed_effective_statuses` (all current member statuses) | Full-refresh current-state table |

- **Critical Distinction:** `gold.fct_opportunities` is a **current-state (Type 1)** fact table. To audit status transitions over time (e.g., how often opportunities reopen or close early), query `silver.silver_opportunity_history` ordered by `(opportunity_id, source_listing_id, content_version)`. If Power BI later requires historical daily status snapshots (e.g., *"how many opportunities were active on every past day"*), introduce a scheduled **dbt snapshot** in `dbt/snapshots/` (reserved directory already in place) rather than altering `fct_opportunities` grain.

---

## 6. Required Lifecycle Tests & Acceptance Criteria

| Test ID | Scenario | Expected Result | Current Verification Status |
|---|---|---|---|
| **LC-1** | `exact` past deadline (`observed = active`) | `effective_status = 'expired'`, `is_expired = TRUE` | **Verified** (`EC3`, `matchpoint_test`) |
| **LC-2** | `date_only` past deadline (`> +36h UTC`) | `effective_status = 'expired'`, `is_expired = TRUE` | **Verified** (`EC4`, `matchpoint_test`) |
| **LC-3** | Explicit `closed` with future deadline | `effective_status = 'closed'`, `is_closed = TRUE` | **Verified** (`EC5`, `matchpoint_test`) |
| **LC-4** | `relative` past deadline (`observed = active`) | `deadline_date_key IS NULL`, stays `effective_status = 'active'` | **Verified** (`EC6`, `matchpoint_test`) |
| **LC-5** | `unknown` observed status + future deadline | Stays `effective_status = 'unknown'` (never promoted to `active`) | **Verified** (`assert_silver_lifecycle_consistency`) |
| **LC-6** | Single-source reopening (`v1 active → v2 closed → v3 active` with extended deadline) | Same `source_listing_id` & `opportunity_id`, `content_version = 3`, `effective_status = 'active'`, 3 rows in `silver_opportunity_history` | **Pending Live Ingestion Test** (execute in Phase 7 with Mahmoud's `postgres.py`) |
| **LC-7** | Multi-source reopening conflict (primary reopened `active`, stale secondary still `closed`) | Explicit `'effective_status'` entry in `conflicting_attributes`; final precedence rule pending Team Decision (Option A vs B above) | **Decision Pending** |
| **LC-8** | Time-only expiration without new scrape | Scheduled `dbt run` transitions `effective_status` to `expired` with **0 new rows** in `bronze.source_listing_history` | **Pending Airflow Schedule Test** (Phase 7 with Andrew) |
