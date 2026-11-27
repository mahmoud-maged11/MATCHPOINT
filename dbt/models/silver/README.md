# Silver Layer Documentation (`dbt/models/silver/`)

This directory contains the Phase 3 Silver models that transform Bronze records into clean, standardized, traceable datasets while preserving all original source evidence and attribution.

> **Scope Boundary:** Phase 3 operates at the **source listing grain** (`source_listing_id`). Cross-source deduplication and canonical `opportunity_id` generation (`ADR-003`, `ADR-004`, `ADR-026`) are intentionally deferred to **Phase 4**. Gold analytical marts are deferred to **Phase 5**.

---

## Models Implemented

| Model | Materialization | Primary Key | Purpose |
|---|---|---|---|
| `silver_source_listings` | `table` | `source_listing_id` | 1-to-1 cleaned source listings with standardized org/location keys, preserved JSONB arrays + state flags, and derived `effective_status`. |
| `silver_organizations` | `table` | `organization_key` | Distinct standardized organizations with preserved `observed_raw_names` JSONB array. |
| `silver_locations` | `table` | `location_key` | Distinct standardized opportunity locations (kept separate from org location, work modes, and applicant eligibility). |
| `silver_skills` | `table` | `skill_key` | Distinct normalized candidate skills with `is_alias_mapped` and `is_candidate_skill` flags. |
| `silver_categories` | `table` | `category_key` | Distinct normalized opportunity categories kept separate from `required_skills` (`ADR-007`). |
| `silver_listing_skills` | `table` | `listing_skill_id` | Relational bridge from `silver_source_listings` to `silver_skills` with `skill_source_type = 'explicit_source_tag'`. |
| `silver_listing_categories` | `table` | `listing_category_id` | Relational bridge from `silver_source_listings` to `silver_categories`. |
| `silver_listing_work_modes` | `table` | `listing_work_mode_id` | Relational expansion of populated `work_modes` JSONB arrays. |
| `silver_listing_employment_types` | `table` | `listing_employment_type_id` | Relational expansion of populated `employment_types` JSONB arrays. |
| `silver_listing_history` | `table` | `history_id` | Read-only preservation of Bronze content version snapshots (`ADR-043`) enriched with collection run metadata. |
| `silver_source_traceability` | `table` | `source_listing_id` | Lineage summary connecting each listing to its latest collection run and content history count. |

---

## Cleaning & Normalization Rules

### 1. Text Cleaning (`macros/normalize_text.sql`)
- `clean_text(col)` trims leading/trailing whitespace, collapses repeated internal whitespace (`\s+` → single space), and converts empty strings to `NULL`.
- Preserves both **Arabic** and **English** scripts and original casing (non-destructive).
- `normalize_lookup_key(col)` lowercases whitespace-normalized text strictly for exact seed lookups without altering display values.

### 2. Organizations (`seeds/organization_aliases.csv`)
- Preserves `organization_raw` verbatim.
- Applies exact lookup against `organization_aliases.csv` only for explicitly documented organizations (e.g., `NTI`, `ITIDA`, `ITI`, `UN Volunteers`).
- Unmapped organizations retain their cleaned original name.
- **Never** merges organizations by fuzzy string similarity.

### 3. Locations (`seeds/location_mappings.csv`)
- Preserves `location_raw` verbatim.
- Matches full location string and comma-separated tokens (supporting both ASCII `,` and Arabic `،`) against explicit English and Arabic mappings for Egyptian cities, governorates, country labels, and explicit online labels.
- Keeps **opportunity location** strictly separate from organization headquarters, `work_modes`, and applicant geographic eligibility (`applicant_eligibility_raw` extracted from `raw_payload->>'egypt_eligibility'` only when present).
- Non-Egyptian or unmapped locations (such as international host countries on UN Volunteers online assignments) are retained without fabricating city/country mappings.

### 4. Skills and Categories (`seeds/skill_aliases.csv`)
- Kept strictly separate (`ADR-007`).
- Explicit skill aliases normalize known synonyms (e.g., `JS` → `JavaScript`, `Postgres` → `PostgreSQL`, `PowerBI` → `Power BI`). Unmapped tags remain intact.
- Every skill row carries `skill_source_type = 'explicit_source_tag'` (distinguishing source-supplied tags from any future NLP-extracted skills) and `is_candidate_skill = TRUE`.

### 5. Missing Values & JSONB Arrays (`ADR-011`, Data Contract §5.2)
- Missing attributes remain `NULL`; values are never fabricated.
- Original Bronze JSONB arrays (`work_modes`, `employment_types`, `categories`, `required_skills`) are preserved untouched on `silver_source_listings`.
- Explicit `*_state` indicators distinguish `'missing'` (`NULL`), `'confirmed_empty'` (`[]`), and `'populated'` (`len > 0`).
- Relational bridge tables emit rows only for `'populated'` arrays.

---

## Lifecycle Management (`ADR-018`, `ADR-047`)

`effective_status` is derived conservatively in `int_listings_cleaned`:

1. **Explicit Bronze status precedence:** If `observed_status IN ('closed', 'expired')`, `effective_status = observed_status` (`observed_source_status`).
2. **Exact deadline expiration:** If `observed_status IN ('active', 'unknown')`, `deadline IS NOT NULL`, `deadline_precision = 'exact'`, and `deadline < CURRENT_TIMESTAMP`, then `effective_status = 'expired'` (`exact_deadline_passed`).
3. **Conservative date-only expiration:** If `observed_status IN ('active', 'unknown')`, `deadline IS NOT NULL`, `deadline_precision = 'date_only'`, and `((DATE_TRUNC('day', deadline AT TIME ZONE 'UTC') + INTERVAL '36 hours') AT TIME ZONE 'UTC') < CURRENT_TIMESTAMP` (end of UTC day + conservative 12-hour margin covering unknown source timezones), then `effective_status = 'expired'` (`date_only_deadline_passed_conservative`).
4. **Uncertain or missing deadlines:** When `deadline IS NULL` or `deadline_precision IN ('relative', 'unknown')`, `effective_status` retains `observed_status`.
5. **No promotion of `unknown`:** A future deadline never turns `observed_status = 'unknown'` into `'active'`.
6. **No absence-based closure:** `last_seen_at` or absence from bounded runs never sets `effective_status = 'closed'`.
7. **Bronze immutability:** Time-driven `effective_status` updates never modify `bronze.source_listings` or `bronze.source_listing_history`.

---

## Known Limitations & Dependencies

- **Materialization freshness:** Because `silver_source_listings` is materialized as a `table`, `effective_status` reflects `lifecycle_evaluated_at` (the timestamp of the latest `dbt run`). Scheduled refreshes via Airflow will keep time-dependent statuses current.
- **Persistent Python Ingestion (Dependency):** Live Bronze population (`scrapers/storage/postgres.py`, owned by Mahmoud) remains pending.
- **Seed coverage:** `organization_aliases.csv`, `location_mappings.csv`, and `skill_aliases.csv` contain initial curated explicit mappings and should be expanded iteratively as real ingested samples are audited.
- **Canonical Deduplication:** Intentionally deferred to Phase 4 (`silver_opportunities`, `silver_opportunity_sources`).
