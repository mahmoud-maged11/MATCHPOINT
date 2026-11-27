# Downstream Handoff Contract — Mahmoud (FastAPI Backend & Bronze Ingestion Alignment)

**Owner (Consumer / Upstream Ingestion):** Mahmoud (`scrapers/storage/postgres.py`, `backend/`)  
**Owner (Warehouse):** Momen (`dbt/`, PostgreSQL `silver` & `gold` schemas)  
**Contract Version:** Data Contract `v3.0.0` (ADR-050)  
**Current External Component Status:** Verified read-only — `scrapers/storage/postgres.py` is 0 bytes and `backend/` contains `.gitkeep` only (`origin/feature/backend` at `0912a49`).

---

## Part A — FastAPI Read-Only Consumption Contract (`gold.*`)

### 1. Approved Gold Tables for Backend API Consumption
FastAPI should read **exclusively** from the `gold` schema (never query `bronze.*`, `silver.int_*`, or raw staging views in user-facing APIs):

| Gold Table | Primary API Use Case | Key Indexes Available in PostgreSQL |
|---|---|---|
| `gold.fct_opportunities` | Opportunity feed/search, opportunity detail endpoint, matching/skill-gap input | `UNIQUE (opportunity_id)`, `(effective_status, opportunity_type)`, `(organization_key)`, `(location_key)`, `(primary_source_name)`, `(published_date_key)` |
| `gold.fct_opportunity_sources` | Full multi-source attribution links & match audit on detail page | `UNIQUE (source_listing_id)`, `(opportunity_id)`, `(source_name)` |
| `gold.bridge_opportunity_skills` | Skill-based filtering & explainable skill-gap computation | `UNIQUE (opportunity_skill_id)`, `(opportunity_id)`, `(skill_key)` |
| `gold.bridge_opportunity_categories` | Category-based filtering | `UNIQUE (opportunity_category_id)`, `(opportunity_id)`, `(category_key)` |
| `gold.bridge_opportunity_work_modes` | Multi-value `work_mode` filter (`on_site`, `remote`, `hybrid`) | `UNIQUE (opportunity_work_mode_id)`, `(opportunity_id)`, `(work_mode)` |
| `gold.bridge_opportunity_employment_types` | Multi-value `employment_type` filter (`full_time`, `part_time`, etc.) | `UNIQUE (opportunity_employment_type_id)`, `(opportunity_id)`, `(employment_type)` |
| `gold.dim_sources` | Source filter dropdown & platform display metadata | `UNIQUE (source_name)` |
| `gold.dim_organizations` | Organization autocomplete (`WHERE has_canonical_opportunities = TRUE`) | `UNIQUE (organization_key)`, `(has_canonical_opportunities)` |
| `gold.dim_locations` | Location filter dropdown (`WHERE has_canonical_opportunities = TRUE`) | `UNIQUE (location_key)`, `(has_canonical_opportunities)` |
| `gold.dim_skills` | Skill picker for user profiles & search filters | `UNIQUE (skill_key)` |
| `gold.dim_categories` | Category picker for search filters | `UNIQUE (category_key)` |

### 2. Read-Only Access & Data Ownership Boundaries
- **Database Role:** Provision a dedicated read-only PostgreSQL role (e.g., `matchpoint_api_ro`) granted `USAGE ON SCHEMA gold` and `SELECT ON ALL TABLES IN SCHEMA gold` (plus `ALTER DEFAULT PRIVILEGES` so full-refresh dbt table swaps remain readable).
- **Ownership Boundary:**
  - **Momen (`dbt`):** Owns schemas `silver` and `gold` (all opportunity catalog tables). FastAPI MUST NEVER `INSERT`, `UPDATE`, or `DELETE` rows in `bronze`, `silver`, or `gold`.
  - **Mahmoud (`FastAPI`):** Owns application-domain tables (users, auth, profiles, user skills, saved opportunities, application tracking, recommendation logs) in a separate application schema (e.g., `app`).
  - **Reference Warning for Saved Opportunities / Bookmarks:** Because `silver_opportunities` is currently stateless, a late-arriving higher-authority source that merges with an earlier lower-authority singleton can update the canonical `opportunity_id` (`phase4_deduplication_design.md §5`). **Recommendation:** Store `(opportunity_id, primary_source_listing_id)` when a user saves an opportunity so FastAPI can still resolve a saved item via `fct_opportunity_sources.source_listing_id` if its canonical anchor ever upgrades!

### 3. Expected Canonical API Response Shape (Mapping from `gold.fct_opportunities`)
Recommended JSON structure for `GET /api/v1/opportunities/{opportunity_id}`:

```json
{
  "opportunity_id": "uuid",
  "title": "string",
  "organization": "string | null",
  "opportunity_type": "job | internship | ...",
  "location": {
    "display": "string | null",
    "city": "string | null",
    "governorate": "string | null",
    "country": "string | null",
    "country_code": "string | null",
    "is_online_location_label": false
  },
  "applicant_eligibility_raw": "string | null",
  "work_modes": ["hybrid"] ,
  "employment_types": ["full_time"],
  "categories": ["Data Engineering"],
  "required_skills": ["Python", "SQL"],
  "experience": {
    "level": "mid_level | null",
    "level_raw": "string | null",
    "years_min": 2,
    "years_max": 5
  },
  "salary": {
    "min": 25000,
    "max": 35000,
    "midpoint": 30000,
    "currency": "EGP",
    "period": "monthly",
    "has_disclosed_salary": true
  },
  "dates": {
    "published_at": "ISO-8601 UTC | null",
    "published_at_raw": "string | null",
    "published_at_precision": "exact | date_only | relative | unknown | null",
    "deadline": "ISO-8601 UTC | null",
    "deadline_raw": "string | null",
    "deadline_precision": "exact | date_only | relative | unknown | null",
    "is_deadline_reliable": true
  },
  "lifecycle": {
    "effective_status": "active | expired | closed | unknown",
    "lifecycle_evaluated_at": "ISO-8601 UTC"
  },
  "sources": {
    "primary_source_name": "wuzzuf",
    "primary_source_url": "https://...",
    "source_count": 2,
    "all_source_urls": [
      {
        "source_name": "wuzzuf",
        "source_listing_id": "uuid",
        "source_url": "https://...",
        "is_primary_source": true,
        "match_method": "direct_cross_source_url",
        "effective_status": "active"
      }
    ],
    "has_source_attribute_conflicts": false,
    "conflicting_attributes": []
  }
}
```

- **Important Semantic Rules for FastAPI / React:**
  - Always expose **all original source URLs** (`all_source_urls`) — never hide secondary source links (`data_contract.md`, `pending_tasks.md §9`).
  - Preserve `null` vs `[]` for `work_modes`, `employment_types`, `categories`, and `required_skills` (`null` = not provided by source; `[]` = explicitly empty).
  - Never display `is_online_location_label = true` as guaranteed Egyptian applicant eligibility; expose `applicant_eligibility_raw` directly.
  - Default search feeds should filter `effective_status = 'active'` (with optional user toggle to include `'unknown'` or historical `'expired'`/`'closed'` records).

### 4. Filtering, Pagination, Freshness & Error Handling
- **Recommended Indexed Filter Pattern:**
  - Base filter: `WHERE fo.effective_status = 'active'` (uses composite index `(effective_status, opportunity_type)` when paired with `opportunity_type`).
  - Multi-value filters (`skills`, `categories`, `work_modes`, `employment_types`): use `EXISTS (SELECT 1 FROM gold.bridge_opportunity_skills bs WHERE bs.opportunity_id = fo.opportunity_id AND bs.skill_key = ANY($1))` rather than `JOIN` + `DISTINCT` so pagination counts are never multiplied!
- **Pagination:** Prefer **keyset pagination** on `(COALESCE(published_at, first_seen_at) DESC, opportunity_id ASC)` for stable deep scrolling (fallback to `LIMIT/OFFSET` with `page_size <= 50` for simple MVP pages).
- **Freshness & Availability During dbt Runs:**
  - dbt replaces Gold tables atomically inside a transaction (`CREATE TABLE __dbt_tmp` → index build → `ALTER TABLE ... RENAME`), so reads never observe half-built tables. Brief `AccessExclusiveLock` swaps take milliseconds; configure FastAPI DB queries with a short statement timeout (`5s`) and retry once on transient lock/relation-swap errors (`SQLSTATE 55P03` / `40P01`).
  - Expose `MAX(lifecycle_evaluated_at)` in a `/health/data-freshness` endpoint so Frontend/monitoring can detect stale warehouse refreshes.
- **Empty-Result Behavior:**
  - When Bronze is empty (initial setup), `gold.fct_opportunities` has `0` rows while `gold.dim_sources` always has `8` rows. List endpoints should return HTTP `200` with `{"items": [], "total": 0}` (not `500` or `404`).
  - Detail lookup for a missing `opportunity_id` returns HTTP `404`.

---

## Part B — Bronze Ingestion Compatibility Checklist (`scrapers/storage/postgres.py`)

Before Phase 7 Live Integration (40-record handover sample + all 8 sources), `scrapers/storage/postgres.py` MUST align with these verified Bronze & dbt expectations:

1. **Migrations Applied:** `database/migrations/001..007` (6 tables, 96 columns).
2. **Exact Constraint Alignment:**
   - `bronze.source_listings.source_identity_key = 'id:' || source_opportunity_id`
   - `first_seen_at <= collected_at AND collected_at = last_seen_at`
   - `hash_version = 1`, `content_hash ~ '^[0-9a-f]{64}$'`, `content_version >= 1`
   - JSONB array columns (`work_modes`, `employment_types`, `categories`, `required_skills`) must be SQL `NULL` when missing or JSONB arrays (`[...]`) when present (never JSON scalars or JSON `null`).
3. **Unresolved Counter Semantics to Confirm (`fct_collection_runs`):**
   - Explicitly define whether `bronze.collection_runs.records_invalid` equals the exact count of rows inserted into `bronze.invalid_records` for that `run_id`, OR counts rejected attempts before deduplication via `(collection_run_id, rejection_hash)`.
   - Confirm `records_invalid <= records_received` (Gold currently flags `records_invalid > records_received` with `has_invalid_counter_anomaly = TRUE` and sets `invalid_record_rate = NULL`).
4. **External Apply URL Retention (`raw_payload`):**
   - Continue preserving verified external `application_url` inside `raw_payload` (as Egyincs currently does) so Phase 4 Tier 1A / Tier 1B cross-source URL matching activates on real records.
5. **Handover Validation Trigger:**
   - Once `scrapers/storage/postgres.py` loads the 40-record handover sample (5 per source × 8 sources) into `matchpoint_test` (or dev DB), notify Momen to execute the Phase 7 Live Integration verification checklist (`dbt/docs/phase7_e2e_acceptance_plan.md`).
