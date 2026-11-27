# MATCHPOINT Gold Layer Data Dictionary

**Data Contract Version:** `3.0.0` (Approved under `ADR-050`)  
**Target Schema:** `gold` (PostgreSQL 16; all 20 models materialized as `table`)  
**Scope:** Complete reference for all **20 Gold models** (6 Dimensions, 7 Facts & Bridges, 7 Analytical Marts) and **33 PostgreSQL indexes**.  
**Source of Truth:** Derived directly from the SQL models under `dbt/models/gold/` and schema tests in `dbt/models/gold/gold_schema.yml`.

---

## Global Conventions & Counting Rules

1. **Canonical Opportunity Counting (`data_contract.md §7.4`):** Unique opportunity KPIs MUST always be counted at the canonical `opportunity_id` grain (`gold.fct_opportunities`). Never sum source listings (`fct_opportunity_sources`) to count unique opportunities.
2. **Timestamp Timezone:** All `TIMESTAMPTZ` columns store UTC timestamps; `date_key` integers use UTC calendar dates formatted as `YYYYMMDD`.
3. **Preserved `NULL` vs Confirmed Empty `[]` Arrays:** `fct_opportunities` preserves the distinction between missing (`NULL`) and confirmed empty (`[]`) JSONB arrays. Canonical bridges emit **0 rows** for both `NULL` and `[]`. Specific marts (`mart_opportunities_by_location`, `mart_opportunities_by_work_mode`, `mart_opportunities_by_employment_type`) surface an explicit `'unreported'` bucket strictly for aggregation reconciliation without altering underlying `NULL`/`[]` values.
4. **No Cross-Currency or Cross-Period Salary Aggregation:** Never average `salary_min`, `salary_max`, or `salary_midpoint` across rows with different `currency` or `salary_period` values.
5. **Candidate Skills Disclaimer (`ADR-007`):** Skill tags carry `is_candidate_skill = TRUE` until taxonomy curation is finalized. Categories remain strictly separate from skills.
6. **Applicant Eligibility (`data_contract.md §5.11–5.12`):** `is_online_location_label = TRUE` or an Egyptian location does NOT guarantee Egyptian applicant eligibility; inspect `applicant_eligibility_raw` without fabricating boolean eligibility flags.

---

## Part 1 — Dimensions (6 Models)

### 1.1 `gold.dim_sources`
- **Table Type:** Dimension (`table`)
- **Purpose & Business Meaning:** Conformed dimension of all eight approved MATCHPOINT data sources (`wuzzuf`, `forasna`, `egyincs`, `itida`, `nti`, `bayt`, `devpost`, `un_volunteers`) sourced from the single shared authority seed `supported_sources.csv`. Guaranteed to contain all 8 rows even when Bronze is empty.
- **Grain:** 1 row per approved `source_name` (always 8 rows).
- **Primary Key:** `source_name`
- **Alternate Unique Key:** `source_authority_rank`
- **PostgreSQL Indexes (2):** `UNIQUE (source_name)`, `UNIQUE (source_authority_rank)`
- **Relationships:** Referenced by `fct_opportunities.primary_source_name`, `fct_opportunity_sources.source_name`, `fct_collection_runs.source_name`, and `mart_opportunities_by_source.source_name`.

| Column | PostgreSQL Type | Nullable | Role | Description & Business Rule |
|---|---|---|---|---|
| `source_name` | `TEXT` | No | PK | Canonical source CLI identifier (`wuzzuf`, `forasna`, `egyincs`, `itida`, `nti`, `bayt`, `devpost`, `un_volunteers`). |
| `source_display_name` | `TEXT` | No | Attribute | Human-readable platform display name from `supported_sources.csv`. |
| `source_authority_rank` | `INTEGER` | No | Unique Attr | Deterministic authority priority `1..8` (`itida=1`, `nti=2`, `un_volunteers=3`, `devpost=4`, `wuzzuf=5`, `forasna=6`, `bayt=7`, `egyincs=8`), consistent with Phase 4 deduplication (`assert_source_authority_rank_consistent`). |
| `collection_approach` | `TEXT` | No | Attribute | Approved collection mechanism (`api`, `html_json_ld`, `wordpress_rest_api`, `sharepoint_html`, etc.). |
| `source_listing_count` | `BIGINT` | No | Measure (Additive) | Total accepted source listings in `fct_opportunity_sources` from this source (`0` if none). |
| `canonical_participating_count` | `BIGINT` | No | Measure (**Non-Additive**) | Distinct canonical `opportunity_id`s with at least one listing from this source. Do NOT sum across sources (multi-source opportunities count under each participating source). |
| `canonical_primary_count` | `BIGINT` | No | Measure (**Additive**) | Canonical opportunities where this source is `is_primary_source = TRUE`. Summing across all 8 rows equals `COUNT(*) FROM gold.fct_opportunities`. |
| `total_collection_runs` | `BIGINT` | No | Measure (Additive) | Total runs recorded in `fct_collection_runs` for this source. |
| `completed_collection_runs` | `BIGINT` | No | Measure (Additive) | Runs with `run_status = 'completed'`. |
| `earliest_seen_at` | `TIMESTAMPTZ` | Yes | Lineage | `MIN(first_seen_at)` across accepted listings for this source (`NULL` if 0 listings). |
| `latest_seen_at` | `TIMESTAMPTZ` | Yes | Lineage | `MAX(last_seen_at)` across accepted listings for this source (`NULL` if 0 listings). |
| `latest_run_started_at` | `TIMESTAMPTZ` | Yes | Lineage | `MAX(started_at)` from `fct_collection_runs` (`NULL` if 0 runs). |

- **Known Limitations:** `latest_seen_at` indicates collection recency only, never source publication time or absence-based closure (`ADR-022`, `ADR-047`).

---

### 1.2 `gold.dim_organizations`
- **Table Type:** Dimension (`table`)
- **Purpose & Business Meaning:** Conformed catalog of standardized organizations observed across accepted opportunities, mapped using explicit aliases (`organization_aliases.csv`) without fuzzy matching.
- **Grain:** 1 row per unique standardized `organization_key`.
- **Primary Key:** `organization_key`
- **PostgreSQL Indexes (2):** `UNIQUE (organization_key)`, `(has_canonical_opportunities)`
- **Relationships:** Referenced by `fct_opportunities.organization_key` (nullable FK).

| Column | PostgreSQL Type | Nullable | Role | Description & Business Rule |
|---|---|---|---|---|
| `organization_key` | `TEXT` | No | PK | Deterministic SHA-256 surrogate key over `('org', LOWER(organization_standardized))`. |
| `organization_name` | `TEXT` | No | Attribute | Standardized organization display name (canonical alias if mapped, else cleaned raw name). |
| `is_alias_mapped` | `BOOLEAN` | No | Flag | `TRUE` if mapped via explicit `organization_aliases.csv`. |
| `observed_raw_names` | `JSONB` | No | Audit Array | Distinct raw organization strings observed in Bronze that resolved to this key. |
| `source_listing_count` | `BIGINT` | No | Measure (Raw) | Number of source listings in Silver referencing this organization. |
| `canonical_opportunity_count` | `BIGINT` | No | Measure (Additive) | Number of canonical opportunities in `fct_opportunities` where this is the primary `organization_key`. |
| `active_opportunity_count` | `BIGINT` | No | Measure (Additive) | Subset of `canonical_opportunity_count` where `is_active = TRUE`. |
| `has_canonical_opportunities` | `BOOLEAN` | No | Flag | `TRUE` when `canonical_opportunity_count > 0`. |

- **Known Limitations & Warnings:** Secondary organizations observed only on non-primary merged listings are retained for Silver lineage parity with `canonical_opportunity_count = 0` and `has_canonical_opportunities = FALSE`. Filter `WHERE has_canonical_opportunities = TRUE` for active-employer dropdowns. Hidden/undisclosed employers (`organization IS NULL` in Bronze) do not appear in this dimension.

---

### 1.3 `gold.dim_locations`
- **Table Type:** Dimension (`table`)
- **Purpose & Business Meaning:** Conformed catalog of standardized opportunity locations (city, governorate, country, ISO country code, online label flag) mapped via `location_mappings.csv`. Strictly separated from organization headquarters, `work_modes`, and applicant geographic eligibility.
- **Grain:** 1 row per unique `location_key`.
- **Primary Key:** `location_key`
- **PostgreSQL Indexes (2):** `UNIQUE (location_key)`, `(has_canonical_opportunities)`
- **Relationships:** Referenced by `fct_opportunities.location_key` (nullable FK) and `mart_opportunities_by_location.location_key` (where `NOT is_unreported_location`).

| Column | PostgreSQL Type | Nullable | Role | Description & Business Rule |
|---|---|---|---|---|
| `location_key` | `TEXT` | No | PK | Deterministic SHA-256 key (`loc_std` tuple when standardized, else `loc_raw` normalized string). |
| `location_display` | `TEXT` | No | Attribute | Clean human-readable label (e.g., `Cairo, Egypt`, `Online`, or cleaned raw string). |
| `standardized_city` | `TEXT` | Yes | Attribute | Standardized city name when matched in `location_mappings.csv`. |
| `standardized_governorate` | `TEXT` | Yes | Attribute | Standardized governorate/region name when matched. |
| `standardized_country` | `TEXT` | Yes | Attribute | Standardized country name when matched. |
| `country_code` | `TEXT` | Yes | Attribute | ISO-2 country code (e.g., `EG`) when matched. |
| `is_online_location_label` | `BOOLEAN` | No | Flag | `TRUE` if the raw location string represents online/virtual delivery (e.g., `"Online"`, `"Remote"`). Separate from `work_modes`. |
| `is_standardized_mapping` | `BOOLEAN` | No | Flag | `TRUE` when resolved through `location_mappings.csv`. |
| `observed_raw_locations` | `JSONB` | No | Audit Array | Distinct raw location strings from Bronze mapped to this key. |
| `source_listing_count` | `BIGINT` | No | Measure (Raw) | Raw source listings referencing this location. |
| `canonical_opportunity_count` | `BIGINT` | No | Measure (Additive) | Canonical opportunities in `fct_opportunities` assigned to this `location_key`. |
| `active_opportunity_count` | `BIGINT` | No | Measure (Additive) | Active canonical opportunities (`is_active = TRUE`) at this location. |
| `has_canonical_opportunities` | `BOOLEAN` | No | Flag | `TRUE` when `canonical_opportunity_count > 0`. |

- **Known Limitations & Warnings:** Secondary-only locations from non-primary merged listings remain with `has_canonical_opportunities = FALSE`. Opportunities with `location_key IS NULL` are NOT rows in `dim_locations`; they are surfaced explicitly via `mart_opportunities_by_location` (`location_key = 'unreported'`).

---

### 1.4 `gold.dim_skills`
- **Table Type:** Dimension (`table`)
- **Purpose & Business Meaning:** Conformed catalog of standardized candidate skills (`ADR-007`) consolidated via `skill_aliases.csv`, with deduplicated canonical opportunity counts.
- **Grain:** 1 row per unique `skill_key`.
- **Primary Key:** `skill_key`
- **PostgreSQL Indexes (1):** `UNIQUE (skill_key)`
- **Relationships:** Referenced by `bridge_opportunity_skills.skill_key` and `mart_skill_demand.skill_key`.

| Column | PostgreSQL Type | Nullable | Role | Description & Business Rule |
|---|---|---|---|---|
| `skill_key` | `TEXT` | No | PK | Deterministic SHA-256 key over standardized skill name. |
| `skill_name` | `TEXT` | No | Attribute | Standardized skill display name (e.g., `Python`, `Power BI`). |
| `skill_group` | `TEXT` | Yes | Attribute | High-level skill category from `skill_aliases.csv` (`NULL` for unmapped skills). |
| `is_alias_mapped` | `BOOLEAN` | No | Flag | `TRUE` if mapped via `skill_aliases.csv`. |
| `is_candidate_skill` | `BOOLEAN` | No | Flag | Preserves `ADR-007` candidate-skill classification (`TRUE`). |
| `observed_raw_skills` | `JSONB` | No | Audit Array | Distinct raw skill strings from Bronze consolidated into this key. |
| `source_listing_count` | `BIGINT` | No | Measure (Raw) | Raw source listings mentioning this skill (may include cross-source duplicates). |
| `canonical_opportunity_count` | `BIGINT` | No | Measure (**Non-Additive**) | Deduplicated canonical opportunities requiring this skill (`COUNT(DISTINCT opportunity_id)` via `bridge_opportunity_skills`). Do NOT sum across skills. |
| `active_opportunity_count` | `BIGINT` | No | Measure (**Non-Additive**) | Active canonical opportunities requiring this skill. |

---

### 1.5 `gold.dim_categories`
- **Table Type:** Dimension (`table`)
- **Purpose & Business Meaning:** Conformed catalog of opportunity categories kept strictly separate from `dim_skills` (`ADR-007`).
- **Grain:** 1 row per unique `category_key`.
- **Primary Key:** `category_key`
- **PostgreSQL Indexes (1):** `UNIQUE (category_key)`
- **Relationships:** Referenced by `bridge_opportunity_categories.category_key` and `mart_opportunities_by_category.category_key`.

| Column | PostgreSQL Type | Nullable | Role | Description & Business Rule |
|---|---|---|---|---|
| `category_key` | `TEXT` | No | PK | Deterministic SHA-256 key over normalized category name. |
| `category_name` | `TEXT` | No | Attribute | Cleaned canonical category display name. |
| `observed_raw_categories` | `JSONB` | No | Audit Array | Distinct raw category labels observed in Bronze. |
| `source_listing_count` | `BIGINT` | No | Measure (Raw) | Raw source listings tagged with this category. |
| `canonical_opportunity_count` | `BIGINT` | No | Measure (**Non-Additive**) | Deduplicated canonical opportunities in this category. Do NOT sum across categories (multi-category opportunities appear in each). |
| `active_opportunity_count` | `BIGINT` | No | Measure (**Non-Additive**) | Active canonical opportunities in this category. |

---

### 1.6 `gold.dim_dates`
- **Table Type:** Dimension (`table`)
- **Purpose & Business Meaning:** Bounded UTC calendar dimension (`2020-01-01` through `CURRENT_DATE + 5 years`) unioned via set-deduplicating `UNION` with all genuinely observed dates from `fct_opportunities` and `fct_collection_runs`. Protects against extreme outlier dates (e.g., `1970-01-01`, `2099-12-31`, `9999-12-31`) generating millions of rows while guaranteeing 100% FK resolvability.
- **Grain:** 1 row per UTC `calendar_date` (`date_key`).
- **Primary Key:** `date_key` (`INTEGER YYYYMMDD`)
- **Alternate Unique Key:** `calendar_date` (`DATE`)
- **PostgreSQL Indexes (2):** `UNIQUE (date_key)`, `UNIQUE (calendar_date)`
- **Relationships:** Referenced by `fct_opportunities` (`published_date_key`, `deadline_date_key`, `first_seen_date_key`, `last_seen_date_key`), `fct_collection_runs.started_date_key`, and `mart_opportunity_lifecycle_trends.published_date_key`.

| Column | PostgreSQL Type | Nullable | Role | Description & Business Rule |
|---|---|---|---|---|
| `date_key` | `INTEGER` | No | PK | Surrogate integer key formatted `YYYYMMDD` (UTC). |
| `calendar_date` | `DATE` | No | Unique Attr | Calendar date (UTC). |
| `year` | `INTEGER` | No | Attribute | Calendar year (`EXTRACT(YEAR)`). |
| `quarter` | `INTEGER` | No | Attribute | Quarter `1..4`. |
| `month` | `INTEGER` | No | Attribute | Month `1..12`. |
| `month_name` | `TEXT` | No | Attribute | Trimmed English month name (`January`..`December`). |
| `week_of_year` | `INTEGER` | No | Attribute | ISO week of year (`1..53`). |
| `day_of_month` | `INTEGER` | No | Attribute | Day of month (`1..31`). |
| `iso_day_of_week` | `INTEGER` | No | Attribute | ISO day of week (`1`=Monday .. `7`=Sunday). |
| `day_name` | `TEXT` | No | Attribute | Trimmed English weekday name. |
| `is_egypt_weekend` | `BOOLEAN` | No | Flag | `TRUE` for Friday (`5`) and Saturday (`6`). |
| `is_within_standard_calendar_range` | `BOOLEAN` | No | Flag | `TRUE` when `calendar_date BETWEEN '2020-01-01' AND CURRENT_DATE + 5 years`; `FALSE` for observed outlier dates preserved via `UNION`. |

- **Known Limitations & Warnings:** Power BI time-intelligence functions (`DATESYTD`, `SAMEPERIODLASTYEAR`) require a contiguous date range; filter `is_within_standard_calendar_range = TRUE` on trend charts so outlier dates like `1970-01-01` or `9999-12-31` do not distort axis scaling.

---

## Part 2 — Facts & Canonical Bridges (7 Models)

### 2.1 `gold.fct_opportunities`
- **Table Type:** Core Fact Table (`table`)
- **Purpose & Business Meaning:** Authoritative canonical opportunity fact table (one row per unique real-world opportunity after cross-source deduplication). Primary data source for FastAPI opportunity search/detail APIs, ClickHouse star schema, and Power BI grand-total KPIs.
- **Grain:** 1 row per canonical `opportunity_id`.
- **Primary Key:** `opportunity_id` (`UUID`)
- **Foreign Keys:**
  - `primary_source_listing_id` → `fct_opportunity_sources.source_listing_id` (NOT NULL, UNIQUE)
  - `primary_source_name` → `dim_sources.source_name` (NOT NULL)
  - `organization_key` → `dim_organizations.organization_key` (nullable)
  - `location_key` → `dim_locations.location_key` (nullable)
  - `published_date_key` → `dim_dates.date_key` (nullable; populated ONLY for `exact`/`date_only` precision)
  - `deadline_date_key` → `dim_dates.date_key` (nullable; populated ONLY when `is_deadline_reliable = TRUE`)
  - `first_seen_date_key` → `dim_dates.date_key` (NOT NULL)
  - `last_seen_date_key` → `dim_dates.date_key` (NOT NULL)
- **PostgreSQL Indexes (6):** `UNIQUE (opportunity_id)`, `(effective_status, opportunity_type)`, `(organization_key)`, `(location_key)`, `(primary_source_name)`, `(published_date_key)`

| Column | PostgreSQL Type | Nullable | Role | Description & Business Rule |
|---|---|---|---|---|
| `opportunity_id` | `UUID` | No | PK | Deterministic canonical UUID (`SHA256('matchpoint:canonical_opportunity:v1|' || canonical_anchor_key)`). |
| `primary_source_listing_id` | `UUID` | No | FK (Unique) | Winning primary source listing UUID from `silver_opportunity_sources`. |
| `primary_source_name` | `TEXT` | No | FK | Source name of the winning primary listing. |
| `primary_source_url` | `TEXT` | No | Attribute | Original public listing URL of the primary source. |
| `organization_key` | `TEXT` | Yes | FK | Standardized organization key (`NULL` when organization is hidden/missing). |
| `location_key` | `TEXT` | Yes | FK | Standardized opportunity location key (`NULL` when location is missing). |
| `published_date_key` | `INTEGER` | Yes | FK | UTC `YYYYMMDD` key ONLY when `published_at IS NOT NULL AND published_at_precision IN ('exact', 'date_only')`, else `NULL` (`ADR-006`). |
| `deadline_date_key` | `INTEGER` | Yes | FK | UTC `YYYYMMDD` key ONLY when `deadline IS NOT NULL AND is_deadline_reliable = TRUE`, else `NULL`. |
| `first_seen_date_key` | `INTEGER` | No | FK | UTC `YYYYMMDD` of earliest observation across all merged sources. |
| `last_seen_date_key` | `INTEGER` | No | FK | UTC `YYYYMMDD` of latest observation across all merged sources. |
| `title` | `TEXT` | No | Attribute | Cleaned opportunity title from primary source (Arabic & English preserved). |
| `organization` | `TEXT` | Yes | Attribute | Standardized organization display name (correlated with `organization_key`). |
| `description` | `TEXT` | Yes | Attribute | Cleaned description text (highest-priority non-null fallback across merged sources). |
| `opportunity_type` | `TEXT` | No | Attribute | Enum: `job`, `internship`, `graduate_program`, `training`, `scholarship`, `competition`, `hackathon`, `freelance`, `volunteering`, `event`. |
| `location_display` | `TEXT` | Yes | Attribute | Human-readable opportunity location label. |
| `standardized_city` | `TEXT` | Yes | Attribute | Standardized city (from correlated location bundle). |
| `standardized_governorate` | `TEXT` | Yes | Attribute | Standardized governorate. |
| `standardized_country` | `TEXT` | Yes | Attribute | Standardized country. |
| `country_code` | `TEXT` | Yes | Attribute | ISO-2 country code. |
| `is_online_location_label` | `BOOLEAN` | No | Flag | `TRUE` if location label indicates online delivery. |
| `applicant_eligibility_raw` | `TEXT` | Yes | Attribute | Raw geographic eligibility signal preserved from source `raw_payload` (e.g., `'unverified'`). |
| `experience_level` | `TEXT` | Yes | Attribute | Standardized level (`entry_level`, `junior`, `mid_level`, `senior`, `lead`, `manager`, `executive`, `unknown`). |
| `experience_level_raw` | `TEXT` | Yes | Attribute | Original source experience label. |
| `experience_years_min` | `NUMERIC` | Yes | Measure | Non-negative minimum experience years (`<= experience_years_max`). |
| `experience_years_max` | `NUMERIC` | Yes | Measure | Non-negative maximum experience years. |
| `education_level` | `TEXT` | Yes | Attribute | Cleaned education requirement text. |
| `requirements` | `TEXT` | Yes | Attribute | Cleaned free-text qualifications and requirements. |
| `salary_min` | `NUMERIC` | Yes | Measure | Disclosed minimum salary (from correlated salary bundle; never mixed across sources). |
| `salary_max` | `NUMERIC` | Yes | Measure | Disclosed maximum salary. |
| `salary_midpoint` | `NUMERIC` | Yes | Measure | `ROUND((salary_min + salary_max) / 2.0, 2)` ONLY when **both** `salary_min` and `salary_max` are non-null, else `NULL`. Never average across mixed currencies/periods. |
| `currency` | `TEXT` | Yes | Attribute | Uppercase 3-letter ISO 4217 currency code (e.g., `EGP`, `USD`). |
| `salary_period` | `TEXT` | Yes | Attribute | `hourly`, `daily`, `weekly`, `monthly`, `yearly`, `project`, `unknown`. |
| `published_at` | `TIMESTAMPTZ` | Yes | Date | UTC publication timestamp from highest-precision correlated bundle. |
| `published_at_raw` | `TEXT` | Yes | Attribute | Original publication date label. |
| `published_at_precision` | `TEXT` | Yes | Attribute | `exact`, `date_only`, `relative`, `unknown`. |
| `deadline` | `TIMESTAMPTZ` | Yes | Date | UTC deadline timestamp from highest-precision correlated bundle. |
| `deadline_raw` | `TEXT` | Yes | Attribute | Original deadline text. |
| `deadline_precision` | `TEXT` | Yes | Attribute | `exact`, `date_only`, `relative`, `unknown`. |
| `is_deadline_reliable` | `BOOLEAN` | No | Flag | `TRUE` iff `deadline IS NOT NULL AND deadline_precision IN ('exact', 'date_only')`. |
| `effective_status` | `TEXT` | No | Attribute | Conservative canonical lifecycle status (`closed` > `expired` > `active` > `unknown`, `ADR-047`). |
| `primary_effective_status` | `TEXT` | No | Attribute | Effective status of the primary source listing alone. |
| `primary_observed_status` | `TEXT` | No | Attribute | Raw Bronze `status` of the primary source listing prior to deadline expiration evaluation. |
| `observed_effective_statuses` | `JSONB` | No | Audit Array | All distinct `effective_status` values observed across merged member listings. |
| `lifecycle_evaluated_at` | `TIMESTAMPTZ` | No | Metadata | UTC wall-clock timestamp when dbt evaluated deadline expiration for this run. *(Intentionally changes on each dbt run.)* |
| `is_active` | `BOOLEAN` | No | Flag | `effective_status = 'active'`. Exactly one of the 4 status flags is `TRUE`. |
| `is_expired` | `BOOLEAN` | No | Flag | `effective_status = 'expired'`. |
| `is_closed` | `BOOLEAN` | No | Flag | `effective_status = 'closed'`. |
| `is_unknown_status` | `BOOLEAN` | No | Flag | `effective_status = 'unknown'`. |
| `has_disclosed_salary` | `BOOLEAN` | No | Flag | `salary_min IS NOT NULL OR salary_max IS NOT NULL`. |
| `is_multi_source` | `BOOLEAN` | No | Flag | `source_count > 1`. |
| `source_count` | `BIGINT` | No | Measure | Count of merged distinct-source listings backing this canonical opportunity (`>= 1`). |
| `source_names` | `JSONB` | No | Array | Sorted distinct `source_name` array for all participating sources. |
| `all_source_urls` | `JSONB` | No | Array | Ordered JSONB array of `{source_name, source_listing_id, source_url, is_primary_source, match_method, effective_status}` preserving 100% source attribution. |
| `match_methods_present` | `JSONB` | No | Array | Distinct deduplication match methods present in this cluster. |
| `has_source_attribute_conflicts` | `BOOLEAN` | No | Flag | `TRUE` if merged sources disagree on any tracked attribute. |
| `conflicting_attributes` | `JSONB` | No | Audit Array | JSONB array of conflicting field names among `title`, `organization`, `opportunity_type`, `location`, `effective_status`, `salary`, `employment_types`, `deadline`. |
| `work_modes` | `JSONB` | Yes | Array | Merged standardized work modes respecting `'unknown'` exclusivity (`NULL` vs `[]` preserved). |
| `employment_types` | `JSONB` | Yes | Array | Merged standardized employment types respecting `'unknown'` exclusivity (`NULL` vs `[]` preserved). |
| `categories` | `JSONB` | Yes | Array | Merged normalized category names (`NULL` vs `[]` preserved). |
| `required_skills` | `JSONB` | Yes | Array | Merged standardized candidate skill names (`NULL` vs `[]` preserved). |
| `first_seen_at` | `TIMESTAMPTZ` | No | Lineage | `MIN(first_seen_at)` across merged sources. |
| `last_seen_at` | `TIMESTAMPTZ` | No | Lineage | `MAX(last_seen_at)` across merged sources. |
| `latest_collected_at` | `TIMESTAMPTZ` | No | Lineage | `MAX(collected_at)` across merged sources. |

- **Known Limitations:** Stateless dbt materialization means a late-arriving higher-authority source that merges with an older lower-authority singleton will shift `opportunity_id` to the higher-authority anchor (`phase4_deduplication_design.md §5`).

---

### 2.2 `gold.fct_opportunity_sources`
- **Table Type:** Fact / Attribution Audit Table (`table`)
- **Purpose & Business Meaning:** Full source-to-canonical attribution mapping preserving every accepted Bronze source listing, its original public URL, deduplication match method, JSONB match evidence, and primary-source flag.
- **Grain:** 1 row per accepted `source_listing_id` (1-to-1 parity with `silver.silver_opportunity_sources`).
- **Primary Key:** `source_listing_id` (`UUID`)
- **Foreign Keys:** `opportunity_id` → `fct_opportunities.opportunity_id` (NOT NULL); `source_name` → `dim_sources.source_name` (NOT NULL)
- **PostgreSQL Indexes (3):** `UNIQUE (source_listing_id)`, `(opportunity_id)`, `(source_name)`

| Column | PostgreSQL Type | Nullable | Role | Description & Business Rule |
|---|---|---|---|---|
| `source_listing_id` | `UUID` | No | PK | Stable Bronze listing UUID (`ADR-042`). |
| `opportunity_id` | `UUID` | No | FK | Canonical opportunity UUID. |
| `source_name` | `TEXT` | No | FK | Originating platform identifier. |
| `source_opportunity_id` | `TEXT` | No | Attribute | Native platform listing identifier. |
| `source_identity_key` | `TEXT` | No | Attribute | Deterministic `'id:' || source_opportunity_id`. |
| `source_url` | `TEXT` | No | Attribute | Original public listing URL (preserved verbatim). |
| `external_application_url_raw` | `TEXT` | Yes | Attribute | External `application_url` extracted from `raw_payload` when present. |
| `canonical_anchor_key` | `TEXT` | No | Audit | `source_name || ':' || source_identity_key` of the cluster's identity anchor. |
| `match_method` | `TEXT` | No | Attribute | Enum: `direct_cross_source_url`, `shared_external_application_url`, `multi_signal_composite`, `singleton`, `singleton_ambiguous_composite`, `singleton_transitive_conflict`. |
| `match_evidence` | `JSONB` | No | Audit | Structured JSONB audit evidence explaining how this listing merged or why it remained a singleton. |
| `is_primary_source` | `BOOLEAN` | No | Flag | `TRUE` for exactly one listing per `opportunity_id`. |
| `source_authority_rank` | `INTEGER` | No | Attribute | Authority rank `1..8` from `supported_sources.csv`. |
| `completeness_score` | `INTEGER` | No | Attribute | Deterministic metadata completeness tie-breaker score. |
| `source_title` | `TEXT` | No | Attribute | Cleaned title as reported by this specific source. |
| `source_organization` | `TEXT` | Yes | Attribute | Standardized organization as reported by this specific source. |
| `source_opportunity_type` | `TEXT` | No | Attribute | Opportunity type as reported by this specific source. |
| `source_location_display` | `TEXT` | Yes | Attribute | Location label as reported by this specific source. |
| `observed_status` | `TEXT` | No | Attribute | Raw Bronze status (`active`, `expired`, `closed`, `unknown`). |
| `effective_status` | `TEXT` | No | Attribute | Source-level effective status after deadline evaluation. |
| `first_seen_at` | `TIMESTAMPTZ` | No | Lineage | Initial observation timestamp for this source listing. |
| `last_seen_at` | `TIMESTAMPTZ` | No | Lineage | Latest observation timestamp for this source listing. |
| `content_hash` | `TEXT` | No | Lineage | Latest 64-char SHA-256 content hash. |
| `content_version` | `INTEGER` | No | Lineage | Current positive content revision number (`>= 1`). |
| `last_collection_run_id` | `UUID` | No | Lineage | Run UUID of the latest accepted observation (links to `fct_collection_runs.run_id`). |

- **Warning:** Do NOT use `COUNT(*)` on this table for unique opportunity KPIs; use `COUNT(DISTINCT opportunity_id)` or `fct_opportunities`.

---

### 2.3 `gold.fct_collection_runs`
- **Table Type:** Operational Telemetry Fact (`table`)
- **Purpose & Business Meaning:** Tracks scraper execution health, throughput, duration, reported run counters, and persisted rejection counts from `stg_bronze__collection_runs` and `stg_bronze__invalid_records`.
- **Grain:** 1 row per collection `run_id`.
- **Primary Key:** `run_id` (`UUID`)
- **Foreign Keys:** `source_name` → `dim_sources.source_name` (NOT NULL); `started_date_key` → `dim_dates.date_key` (NOT NULL)
- **PostgreSQL Indexes (2):** `UNIQUE (run_id)`, `(source_name, started_at)`

| Column | PostgreSQL Type | Nullable | Role | Description & Business Rule |
|---|---|---|---|---|
| `run_id` | `UUID` | No | PK | Unique collection run UUID. |
| `source_name` | `TEXT` | No | FK | Source executed in this run. |
| `collection_scope` | `TEXT` | No | Attribute | Endpoint/scope identifier (e.g., `default`, `jobs`, `lp_course`). |
| `collection_mode` | `TEXT` | No | Attribute | Collection mode (e.g., `api`, `html`). |
| `run_status` | `TEXT` | No | Attribute | Enum: `running`, `completed`, `partial`, `failed`, `aborted`. |
| `started_at` | `TIMESTAMPTZ` | No | Date | UTC run start timestamp. |
| `finished_at` | `TIMESTAMPTZ` | Yes | Date | UTC run completion timestamp (`NULL` while `running`). |
| `started_date_key` | `INTEGER` | No | FK | UTC `YYYYMMDD` of `started_at`. |
| `run_duration_seconds` | `NUMERIC` | Yes | Measure | `ROUND(EXTRACT(EPOCH FROM (finished_at - started_at)), 2)` (`NULL` if unfinished; validated `>= 0`). |
| `records_received` | `INTEGER` | No | Measure (Additive) | Run counter reported by ingestion (`>= 0`). |
| `records_inserted` | `INTEGER` | No | Measure (Additive) | New listings inserted (`>= 0`). |
| `records_updated` | `INTEGER` | No | Measure (Additive) | Existing listings updated with content change (`>= 0`). |
| `records_unchanged` | `INTEGER` | No | Measure (Additive) | Unchanged listings re-observed (`>= 0`). |
| `records_invalid` | `INTEGER` | No | Measure (Additive) | Invalid count reported on `bronze.collection_runs` (`>= 0`). |
| `records_stale` | `INTEGER` | No | Measure (Additive) | Out-of-order stale observations (`>= 0`). |
| `records_conflicted` | `INTEGER` | No | Measure (Additive) | Conflicting retry/timestamp observations (`>= 0`). |
| `persisted_invalid_record_count` | `BIGINT` | No | Measure (Additive) | Actual row count persisted in `bronze.invalid_records` for this `run_id`. |
| `persisted_vs_reported_invalid_diff` | `BIGINT` | No | Audit Measure | `persisted_invalid_record_count - records_invalid`. Tracks divergence until ingestion counter semantics are finalized in `scrapers/storage/postgres.py`. |
| `has_invalid_counter_anomaly` | `BOOLEAN` | No | Flag | `TRUE` when `records_invalid > records_received`. |
| `invalid_record_rate` | `NUMERIC` | Yes | Ratio (**Non-Additive**) | `ROUND(records_invalid / records_received, 4)` bounded `[0, 1]` when `records_received > 0 AND records_invalid <= records_received`, else `NULL`. In Power BI, recompute as `SUM(records_invalid) / SUM(records_received)` rather than averaging ratios. |
| `is_completed` | `BOOLEAN` | No | Flag | `run_status = 'completed'`. |
| `is_failed` | `BOOLEAN` | No | Flag | `run_status IN ('failed', 'aborted')`. |
| `contract_version` | `TEXT` | No | Metadata | Active Data Contract version (`3.0.0`). |
| `hash_version` | `INTEGER` | No | Metadata | Content hash algorithm version (`1`). |
| `error_message` | `TEXT` | Yes | Diagnostics | Run-level error summary if failed/aborted. |

---

### 2.4 `gold.bridge_opportunity_skills`
- **Table Type:** Bridge Table (`table`)
- **Purpose & Business Meaning:** Many-to-many canonical opportunity-to-skill bridge deduplicated across merged sources so a skill mentioned on two merged platforms counts once per opportunity.
- **Grain:** 1 row per unique `(opportunity_id, skill_key)`.
- **Primary Key:** `opportunity_skill_id` (`TEXT` SHA-256)
- **Foreign Keys:** `opportunity_id` → `fct_opportunities.opportunity_id`; `skill_key` → `dim_skills.skill_key`
- **PostgreSQL Indexes (3):** `UNIQUE (opportunity_skill_id)`, `(opportunity_id)`, `(skill_key)`

| Column | PostgreSQL Type | Nullable | Role | Description & Business Rule |
|---|---|---|---|---|
| `opportunity_skill_id` | `TEXT` | No | PK | Deterministic SHA-256 over `(opportunity_id, skill_key)`. |
| `opportunity_id` | `UUID` | No | FK | Canonical opportunity UUID. |
| `skill_key` | `TEXT` | No | FK | Standardized skill key. |
| `skill_name` | `TEXT` | No | Attribute | Standardized skill name. |
| `skill_group` | `TEXT` | Yes | Attribute | Skill group from `skill_aliases.csv`. |
| `is_alias_mapped` | `BOOLEAN` | No | Flag | `TRUE` if any merged source listing resolved this skill via alias mapping. |
| `skill_source_type` | `TEXT` | No | Attribute | Explicit provenance precedence: `'explicit_source_tag'` if ANY merged source provided an explicit tag, else `'extracted'`. |
| `is_candidate_skill` | `BOOLEAN` | No | Flag | `BOOL_AND(is_candidate_skill)` across supporting listings (`ADR-007`). |
| `supporting_source_count` | `BIGINT` | No | Measure | Count of distinct merged `source_listing_id`s corroborating this skill for this opportunity. |

---

### 2.5 `gold.bridge_opportunity_categories`
- **Table Type:** Bridge Table (`table`)
- **Purpose & Business Meaning:** Many-to-many canonical opportunity-to-category bridge deduplicated across merged sources (strictly separate from skills per `ADR-007`).
- **Grain:** 1 row per unique `(opportunity_id, category_key)`.
- **Primary Key:** `opportunity_category_id` (`TEXT` SHA-256)
- **Foreign Keys:** `opportunity_id` → `fct_opportunities.opportunity_id`; `category_key` → `dim_categories.category_key`
- **PostgreSQL Indexes (3):** `UNIQUE (opportunity_category_id)`, `(opportunity_id)`, `(category_key)`

| Column | PostgreSQL Type | Nullable | Role | Description & Business Rule |
|---|---|---|---|---|
| `opportunity_category_id` | `TEXT` | No | PK | Deterministic SHA-256 over `(opportunity_id, category_key)`. |
| `opportunity_id` | `UUID` | No | FK | Canonical opportunity UUID. |
| `category_key` | `TEXT` | No | FK | Normalized category key. |
| `category_name` | `TEXT` | No | Attribute | Normalized category display name. |
| `supporting_source_count` | `BIGINT` | No | Measure | Count of distinct merged `source_listing_id`s supporting this category. |

---

### 2.6 `gold.bridge_opportunity_work_modes`
- **Table Type:** Bridge Table (`table`)
- **Purpose & Business Meaning:** Canonical opportunity-to-work-mode bridge expanded from `silver_opportunities.work_modes` (`ADR-002`). Emits 0 rows for `NULL` or confirmed empty `[]`; enforces `'unknown'` exclusivity (`assert_gold_bridges_deduplicated_and_valid`).
- **Grain:** 1 row per unique `(opportunity_id, work_mode)`.
- **Primary Key:** `opportunity_work_mode_id` (`TEXT` SHA-256)
- **Foreign Keys:** `opportunity_id` → `fct_opportunities.opportunity_id`
- **PostgreSQL Indexes (3):** `UNIQUE (opportunity_work_mode_id)`, `(opportunity_id)`, `(work_mode)`

| Column | PostgreSQL Type | Nullable | Role | Description & Business Rule |
|---|---|---|---|---|
| `opportunity_work_mode_id` | `TEXT` | No | PK | Deterministic SHA-256 over `(opportunity_id, work_mode)`. |
| `opportunity_id` | `UUID` | No | FK | Canonical opportunity UUID. |
| `work_mode` | `TEXT` | No | Attribute | Standardized enum: `on_site`, `remote`, `hybrid`, `unknown`. |

---

### 2.7 `gold.bridge_opportunity_employment_types`
- **Table Type:** Bridge Table (`table`)
- **Purpose & Business Meaning:** Canonical opportunity-to-employment-type bridge expanded from `silver_opportunities.employment_types` (`ADR-001`). Emits 0 rows for `NULL` or confirmed empty `[]`; enforces `'unknown'` exclusivity.
- **Grain:** 1 row per unique `(opportunity_id, employment_type)`.
- **Primary Key:** `opportunity_employment_type_id` (`TEXT` SHA-256)
- **Foreign Keys:** `opportunity_id` → `fct_opportunities.opportunity_id`
- **PostgreSQL Indexes (3):** `UNIQUE (opportunity_employment_type_id)`, `(opportunity_id)`, `(employment_type)`

| Column | PostgreSQL Type | Nullable | Role | Description & Business Rule |
|---|---|---|---|---|
| `opportunity_employment_type_id` | `TEXT` | No | PK | Deterministic SHA-256 over `(opportunity_id, employment_type)`. |
| `opportunity_id` | `UUID` | No | FK | Canonical opportunity UUID. |
| `employment_type` | `TEXT` | No | Attribute | Standardized enum: `full_time`, `part_time`, `contract`, `temporary`, `freelance`, `unknown`. |

---

## Part 3 — Analytical Marts (7 Models)

> Note: All 7 marts are small pre-aggregated tables materialized as `table` in `gold` with no secondary indexes required on PostgreSQL. Every mart enforces strict additivity rules documented below.

### 3.1 `gold.mart_opportunities_by_source`
- **Table Type:** Analytical Mart (`table`)
- **Purpose:** Platform coverage, cross-source overlap, lifecycle breakdown, and ingestion quality telemetry across all 8 approved sources.
- **Grain:** 1 row per `source_name` (always 8 rows).
- **Primary Key / FK:** `source_name` → `dim_sources.source_name`

| Column | PostgreSQL Type | Nullable | Additivity Across Sources | Description |
|---|---|---|---|---|
| `source_name` | `TEXT` | No | PK / FK | Source identifier. |
| `source_display_name` | `TEXT` | No | Attribute | Display name. |
| `source_authority_rank` | `INTEGER` | No | Attribute | Authority rank `1..8`. |
| `collection_approach` | `TEXT` | No | Attribute | Collection method. |
| `total_source_listings` | `BIGINT` | No | **Additive** | Total listings (`SUM = COUNT(*) FROM fct_opportunity_sources`). |
| `canonical_opportunities_contributed` | `BIGINT` | No | **NON-ADDITIVE** | Distinct canonical opportunities containing a listing from this source. |
| `primary_canonical_opportunities` | `BIGINT` | No | **STRICTLY ADDITIVE** | Canonical opportunities where this source is primary (`SUM = COUNT(*) FROM fct_opportunities`). |
| `multi_source_listings` | `BIGINT` | No | Additive (Listings) | Listings from this source belonging to a multi-source opportunity (`source_count > 1`). |
| `primary_active_opportunities` | `BIGINT` | No | **STRICTLY ADDITIVE** | Active canonical opportunities where this source is primary. |
| `primary_expired_opportunities` | `BIGINT` | No | **STRICTLY ADDITIVE** | Expired canonical opportunities where this source is primary. |
| `primary_closed_opportunities` | `BIGINT` | No | **STRICTLY ADDITIVE** | Closed canonical opportunities where this source is primary. |
| `primary_unknown_opportunities` | `BIGINT` | No | **STRICTLY ADDITIVE** | Unknown-status canonical opportunities where this source is primary. |
| `active_contributed_opportunities` | `BIGINT` | No | **NON-ADDITIVE** | Active canonical opportunities contributed by this source. |
| `expired_contributed_opportunities` | `BIGINT` | No | **NON-ADDITIVE** | Expired canonical opportunities contributed by this source. |
| `closed_contributed_opportunities` | `BIGINT` | No | **NON-ADDITIVE** | Closed canonical opportunities contributed by this source. |
| `unknown_contributed_opportunities` | `BIGINT` | No | **NON-ADDITIVE** | Unknown-status canonical opportunities contributed by this source. |
| `total_runs` | `BIGINT` | No | Additive | Total collection runs. |
| `completed_runs` | `BIGINT` | No | Additive | Completed collection runs. |
| `failed_runs` | `BIGINT` | No | Additive | Failed/aborted collection runs. |
| `total_records_received` | `BIGINT` | No | Additive | Sum of `records_received`. |
| `total_records_invalid_reported` | `BIGINT` | No | Additive | Sum of reported `records_invalid`. |
| `total_invalid_records_persisted` | `BIGINT` | No | Additive | Sum of persisted rows in `bronze.invalid_records`. |
| `latest_run_started_at` | `TIMESTAMPTZ` | Yes | Metadata | Most recent run start time. |
| `latest_seen_at` | `TIMESTAMPTZ` | Yes | Metadata | Most recent listing observation time. |

---

### 3.2 `gold.mart_opportunities_by_category`
- **Table Type:** Analytical Mart (`table`)
- **Purpose:** Canonical opportunity counts by normalized category and lifecycle status.
- **Grain:** 1 row per `category_key` with at least 1 canonical opportunity.
- **Primary Key / FK:** `category_key` → `dim_categories.category_key`
- **Additivity Warning:** **NON-ADDITIVE across category rows** (one opportunity with 2 categories appears in both rows). Opportunities with `NULL` or `[]` categories are excluded from this mart.

| Column | PostgreSQL Type | Nullable | Description |
|---|---|---|---|
| `category_key` | `TEXT` | No | PK / FK to `dim_categories`. |
| `category_name` | `TEXT` | No | Standardized category name. |
| `canonical_opportunity_count` | `BIGINT` | No | Distinct canonical opportunities tagged with this category (**Non-Additive**). |
| `active_opportunity_count` | `BIGINT` | No | Active subset. |
| `expired_opportunity_count` | `BIGINT` | No | Expired subset. |
| `closed_opportunity_count` | `BIGINT` | No | Closed subset. |
| `unknown_opportunity_count` | `BIGINT` | No | Unknown-status subset. |
| `disclosed_salary_opportunity_count` | `BIGINT` | No | Subset with disclosed salary. |

---

### 3.3 `gold.mart_opportunities_by_location`
- **Table Type:** Analytical Mart (`table`)
- **Purpose:** Canonical opportunity distribution by standardized location, including an explicit `'unreported'` bucket (`location_key = 'unreported'`, `is_unreported_location = TRUE`) whenever opportunities have `location_key IS NULL`.
- **Grain:** 1 row per observed canonical `location_key` plus optional `'unreported'` row.
- **Primary Key:** `location_key` (FK to `dim_locations.location_key` ONLY when `NOT is_unreported_location`).
- **Additivity:** **STRICTLY ADDITIVE across all rows** (`SUM(canonical_opportunity_count) = COUNT(*) FROM gold.fct_opportunities`).

| Column | PostgreSQL Type | Nullable | Description |
|---|---|---|---|
| `location_key` | `TEXT` | No | PK (`'unreported'` for NULL-location bucket; otherwise FK to `dim_locations`). |
| `location_display` | `TEXT` | No | Display label (`'Unreported'` for NULL-location bucket). |
| `standardized_city` | `TEXT` | Yes | Standardized city (`NULL` for unreported/country-only/online). |
| `standardized_governorate` | `TEXT` | Yes | Standardized governorate. |
| `standardized_country` | `TEXT` | Yes | Standardized country. |
| `country_code` | `TEXT` | Yes | ISO-2 country code. |
| `is_online_location_label` | `BOOLEAN` | No | `TRUE` for online location labels; `FALSE` for `'unreported'`. |
| `is_standardized_mapping` | `BOOLEAN` | No | `TRUE` if mapped via `location_mappings.csv`; `FALSE` for `'unreported'`. |
| `is_unreported_location` | `BOOLEAN` | No | `TRUE` exclusively for the `'unreported'` row (`location_key IS NULL` in `fct_opportunities`). |
| `canonical_opportunity_count` | `BIGINT` | No | Canonical opportunities (**Strictly Additive**). |
| `active_opportunity_count` | `BIGINT` | No | Active subset (**Strictly Additive**). |
| `expired_opportunity_count` | `BIGINT` | No | Expired subset (**Strictly Additive**). |
| `closed_opportunity_count` | `BIGINT` | No | Closed subset (**Strictly Additive**). |
| `unknown_opportunity_count` | `BIGINT` | No | Unknown-status subset (**Strictly Additive**). |
| `disclosed_salary_opportunity_count` | `BIGINT` | No | Subset with disclosed salary (**Strictly Additive**). |

---

### 3.4 `gold.mart_opportunities_by_work_mode`
- **Table Type:** Analytical Mart (`table`)
- **Purpose:** Canonical opportunity counts by `opportunity_type` and `work_mode` (separated from `employment_type` to eliminate Cartesian multiplication).
- **Grain:** 1 row per `(opportunity_type, work_mode)`.
- **Primary Key:** `work_mode_bucket_key` (`TEXT` SHA-256)
- **Additivity Warning:** **NON-ADDITIVE across `work_mode` values within an `opportunity_type`** because one opportunity may support multiple work modes (`ADR-002`). `'unreported'` covers opportunities where `work_modes` is `NULL` or confirmed empty `[]`.

| Column | PostgreSQL Type | Nullable | Description |
|---|---|---|---|
| `work_mode_bucket_key` | `TEXT` | No | PK (SHA-256 over `(opportunity_type, work_mode)`). |
| `opportunity_type` | `TEXT` | No | Canonical opportunity type. |
| `work_mode` | `TEXT` | No | `on_site`, `remote`, `hybrid`, `unknown`, or `unreported`. |
| `opportunities_with_work_mode_count` | `BIGINT` | No | Distinct canonical opportunities supporting this work mode (**Non-Additive** across work modes). |
| `active_opportunities_count` | `BIGINT` | No | Active subset. |
| `expired_opportunities_count` | `BIGINT` | No | Expired subset. |
| `closed_opportunities_count` | `BIGINT` | No | Closed subset. |
| `unknown_opportunities_count` | `BIGINT` | No | Unknown-status subset. |
| `disclosed_salary_opportunities_count` | `BIGINT` | No | Subset with disclosed salary. |

---

### 3.5 `gold.mart_opportunities_by_employment_type`
- **Table Type:** Analytical Mart (`table`)
- **Purpose:** Canonical opportunity counts by `opportunity_type` and `employment_type` (separated from `work_mode` to eliminate Cartesian multiplication).
- **Grain:** 1 row per `(opportunity_type, employment_type)`.
- **Primary Key:** `employment_type_bucket_key` (`TEXT` SHA-256)
- **Additivity Warning:** **NON-ADDITIVE across `employment_type` values within an `opportunity_type`** because one opportunity may support multiple employment types (`ADR-001`). `'unreported'` covers `NULL` or confirmed empty `[]`.

| Column | PostgreSQL Type | Nullable | Description |
|---|---|---|---|
| `employment_type_bucket_key` | `TEXT` | No | PK (SHA-256 over `(opportunity_type, employment_type)`). |
| `opportunity_type` | `TEXT` | No | Canonical opportunity type. |
| `employment_type` | `TEXT` | No | `full_time`, `part_time`, `contract`, `temporary`, `freelance`, `unknown`, or `unreported`. |
| `opportunities_with_employment_type_count` | `BIGINT` | No | Distinct canonical opportunities supporting this employment type (**Non-Additive** across employment types). |
| `active_opportunities_count` | `BIGINT` | No | Active subset. |
| `expired_opportunities_count` | `BIGINT` | No | Expired subset. |
| `closed_opportunities_count` | `BIGINT` | No | Closed subset. |
| `unknown_opportunities_count` | `BIGINT` | No | Unknown-status subset. |
| `disclosed_salary_opportunities_count` | `BIGINT` | No | Subset with disclosed salary. |

---

### 3.6 `gold.mart_skill_demand`
- **Table Type:** Analytical Mart (`table`)
- **Purpose:** Ranked market demand for candidate skills (`ADR-007`) based on deduplicated canonical opportunity counts.
- **Grain:** 1 row per `skill_key` present in `bridge_opportunity_skills`.
- **Primary Key / FK:** `skill_key` → `dim_skills.skill_key`
- **Additivity Warning:** **NON-ADDITIVE across skills.** `share_of_opportunities_with_skills` uses opportunities that disclose at least one skill as the denominator (not all opportunities in `fct_opportunities`), so percentages across skills will sum above 100%.

| Column | PostgreSQL Type | Nullable | Description |
|---|---|---|---|
| `skill_key` | `TEXT` | No | PK / FK to `dim_skills`. |
| `skill_name` | `TEXT` | No | Standardized skill name. |
| `skill_group` | `TEXT` | Yes | Skill group. |
| `is_alias_mapped` | `BOOLEAN` | No | Alias-mapping flag. |
| `is_candidate_skill` | `BOOLEAN` | No | Candidate-skill flag (`ADR-007`). |
| `canonical_opportunity_count` | `BIGINT` | No | Distinct canonical opportunities listing this skill (**Non-Additive**). |
| `active_opportunity_count` | `BIGINT` | No | Active subset. |
| `expired_opportunity_count` | `BIGINT` | No | Expired subset. |
| `closed_opportunity_count` | `BIGINT` | No | Closed subset. |
| `unknown_opportunity_count` | `BIGINT` | No | Unknown-status subset. |
| `share_of_opportunities_with_skills` | `NUMERIC` | Yes | `ROUND(canonical_opportunity_count / total_opps_with_skills, 4)` (`NULL` if 0 opportunities disclose skills). |

---

### 3.7 `gold.mart_opportunity_lifecycle_trends`
- **Table Type:** Analytical Mart (`table`)
- **Purpose:** Time-series publication and lifecycle trends strictly restricted to canonical opportunities with **reliable** publication dates (`published_at IS NOT NULL AND published_at_precision IN ('exact', 'date_only')`, per `ADR-006`).
- **Grain:** 1 row per `(published_date_key, opportunity_type, effective_status)`.
- **Primary Key:** `trend_bucket_key` (`TEXT` SHA-256)
- **Foreign Key:** `published_date_key` → `dim_dates.date_key`
- **Additivity:** **STRICTLY ADDITIVE for the reliable-published subset** (`SUM(canonical_opportunity_count) = COUNT(*) FROM fct_opportunities WHERE published_date_key IS NOT NULL`). Opportunities with `NULL`, `relative`, or `unknown` publication precision are intentionally excluded rather than fabricating dates from `collected_at`.

| Column | PostgreSQL Type | Nullable | Description |
|---|---|---|---|
| `trend_bucket_key` | `TEXT` | No | PK (SHA-256 over `(published_date_key, opportunity_type, effective_status)`). |
| `published_date_key` | `INTEGER` | No | FK to `dim_dates.date_key`. |
| `published_date` | `DATE` | No | UTC publication date. |
| `published_year` | `INTEGER` | No | Publication year. |
| `published_month` | `INTEGER` | No | Publication month `1..12`. |
| `opportunity_type` | `TEXT` | No | Canonical opportunity type. |
| `effective_status` | `TEXT` | No | `active`, `expired`, `closed`, or `unknown`. |
| `canonical_opportunity_count` | `BIGINT` | No | Reliable-published canonical opportunities (**Strictly Additive**). |
| `multi_source_opportunity_count` | `BIGINT` | No | Subset backed by `> 1` source (**Strictly Additive**). |
| `disclosed_salary_opportunity_count` | `BIGINT` | No | Subset with disclosed salary (**Strictly Additive**). |
