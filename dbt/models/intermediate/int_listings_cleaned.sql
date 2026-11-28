WITH staged AS (
    SELECT
        source_listing_id,
        source_name,
        source_opportunity_id,
        source_identity_key,
        source_url,

        -- Non-destructive whitespace normalization preserving Arabic and English
        {{ clean_text('title') }} AS title_cleaned,
        title AS title_raw,
        {{ clean_text('organization') }} AS organization_cleaned,
        organization AS organization_raw,
        {{ normalize_lookup_key('organization') }} AS organization_lookup_key,
        {{ clean_text('description') }} AS description_cleaned,
        opportunity_type,

        -- Opportunity location (kept separate from organization location, work_modes, and eligibility)
        {{ clean_text('location') }} AS location_cleaned,
        location AS location_raw,
        {{ normalize_lookup_key('location') }} AS location_lookup_key,

        -- Preserve original Bronze JSONB arrays (NULL vs confirmed empty [])
        work_modes,
        employment_types,
        categories,
        required_skills,

        -- Qualifications and requirements
        experience_level,
        experience_level_raw,
        experience_years_min,
        experience_years_max,
        {{ clean_text('education_level') }} AS education_level_cleaned,
        {{ clean_text('requirements') }} AS requirements_cleaned,

        -- Salary information
        salary_min,
        salary_max,
        UPPER(currency) AS currency,
        salary_period,

        -- Dates and precision
        published_at,
        published_at_raw,
        published_at_precision,
        deadline,
        deadline_raw,
        deadline_precision,

        {{ reliable_calendar_date(
            'published_at',
            'published_at_raw',
            'published_at_precision'
        ) }} AS published_calendar_date,

        {{ reliable_calendar_date(
            'deadline',
            'deadline_raw',
            'deadline_precision'
        ) }} AS deadline_calendar_date,

        -- Observed status preserved from Bronze
        observed_status,
        source_status_raw,

        -- Separate geographic eligibility signal when preserved in raw_payload (e.g. Devpost, UN Volunteers)
        NULLIF(BTRIM(raw_payload ->> 'egypt_eligibility'), '') AS applicant_eligibility_raw,

        -- Bronze lineage and versioning metadata
        collected_at,
        first_seen_at,
        last_seen_at,
        created_at,
        updated_at,
        content_hash,
        hash_version,
        content_version,
        last_collection_run_id,
        raw_payload

    FROM {{ ref('stg_bronze__source_listings') }}
),

{{ resolve_listing_locations('staged', ref('location_mappings')) }}

enriched AS (
    SELECT
        lt.source_listing_id,
        lt.source_name,
        lt.source_opportunity_id,
        lt.source_identity_key,
        lt.source_url,

        lt.title_cleaned AS title,
        lt.title_raw,

        -- Organization standardization via explicit alias seed only (never fuzzy similarity)
        lt.organization_raw,
        COALESCE(oa.canonical_organization_name, lt.organization_cleaned) AS organization_standardized,
        (oa.raw_alias_normalized IS NOT NULL) AS is_organization_alias_mapped,

        lt.description_cleaned AS description,
        lt.opportunity_type,

        -- Use one consistent geographic mapping row.
        -- Unresolved locations retain their original text.
        lt.location_raw,
        lt.location_cleaned,

        lr.standardized_city,
        lr.standardized_governorate,
        lr.standardized_country,
        lr.country_code,

        COALESCE(
            lr.is_online_location_label,
            FALSE
        ) AS is_online_location_label,

        (
            lr.source_listing_id IS NOT NULL
        ) AS is_location_standardized,

        lt.applicant_eligibility_raw,

        -- Original JSONB arrays + explicit state flags (missing vs confirmed_empty vs populated)
        lt.work_modes,
        CASE
            WHEN lt.work_modes IS NULL THEN 'missing'
            WHEN JSONB_ARRAY_LENGTH(lt.work_modes) = 0 THEN 'confirmed_empty'
            ELSE 'populated'
        END AS work_modes_state,

        lt.employment_types,
        CASE
            WHEN lt.employment_types IS NULL THEN 'missing'
            WHEN JSONB_ARRAY_LENGTH(lt.employment_types) = 0 THEN 'confirmed_empty'
            ELSE 'populated'
        END AS employment_types_state,

        lt.categories,
        CASE
            WHEN lt.categories IS NULL THEN 'missing'
            WHEN JSONB_ARRAY_LENGTH(lt.categories) = 0 THEN 'confirmed_empty'
            ELSE 'populated'
        END AS categories_state,

        lt.required_skills,
        CASE
            WHEN lt.required_skills IS NULL THEN 'missing'
            WHEN JSONB_ARRAY_LENGTH(lt.required_skills) = 0 THEN 'confirmed_empty'
            ELSE 'populated'
        END AS required_skills_state,

        -- Qualifications and salary
        lt.experience_level,
        lt.experience_level_raw,
        lt.experience_years_min,
        lt.experience_years_max,
        lt.education_level_cleaned AS education_level,
        lt.requirements_cleaned AS requirements,
        lt.salary_min,
        lt.salary_max,
        lt.currency,
        lt.salary_period,

        -- Dates and precision
        lt.published_at,
        lt.published_at_raw,
        lt.published_at_precision,
        lt.deadline,
        lt.deadline_raw,
        lt.deadline_precision,
        lt.published_calendar_date,
        lt.deadline_calendar_date,

        (
            lt.deadline_calendar_date IS NOT NULL
        ) AS is_deadline_reliable,

        -- Lifecycle reconciliation (ADR-018 and ADR-047)
        -- 1. Explicit closed/expired in Bronze takes precedence.
        -- 2. Exact deadlines expire strictly after deadline < CURRENT_TIMESTAMP.
        -- 3. Date-only deadlines expire conservatively after UTC day end + 12h margin (36h from UTC midnight).
        -- 4. Relative, unknown, or NULL deadlines never auto-expire.
        -- 5. Future deadlines never promote observed 'unknown' to 'active'.
        -- 6. Absence from bounded collection runs never infers closure.
        lt.observed_status,
        lt.source_status_raw,
        CASE
            WHEN lt.observed_status IN ('closed', 'expired') THEN lt.observed_status
            WHEN lt.deadline_precision = 'exact'
                AND {{ deadline_has_passed(
                    'lt.deadline',
                    'lt.deadline_calendar_date',
                    'lt.deadline_precision',
                    'CURRENT_TIMESTAMP'
                ) }} THEN 'expired'
            WHEN lt.deadline_precision = 'date_only'
                AND {{ deadline_has_passed(
                    'lt.deadline',
                    'lt.deadline_calendar_date',
                    'lt.deadline_precision',
                    'CURRENT_TIMESTAMP'
                ) }} THEN 'expired'
            ELSE lt.observed_status
        END AS effective_status,
        CASE
            WHEN lt.observed_status IN ('closed', 'expired') THEN 'observed_source_status'
            WHEN lt.deadline_precision = 'exact'
                AND {{ deadline_has_passed(
                    'lt.deadline',
                    'lt.deadline_calendar_date',
                    'lt.deadline_precision',
                    'CURRENT_TIMESTAMP'
                ) }} THEN 'exact_deadline_passed'
            WHEN lt.deadline_precision = 'date_only'
                AND {{ deadline_has_passed(
                    'lt.deadline',
                    'lt.deadline_calendar_date',
                    'lt.deadline_precision',
                    'CURRENT_TIMESTAMP'
                ) }} THEN 'date_only_deadline_passed_conservative'
            ELSE 'observed_source_status_retained'
        END AS effective_status_reason,
        CURRENT_TIMESTAMP AS lifecycle_evaluated_at,

        -- Bronze lineage and versioning metadata
        lt.collected_at,
        lt.first_seen_at,
        lt.last_seen_at,
        lt.created_at,
        lt.updated_at,
        lt.content_hash,
        lt.hash_version,
        lt.content_version,
        lt.last_collection_run_id,
        lt.raw_payload

    FROM staged lt

    LEFT JOIN {{ ref('organization_aliases') }} oa
        ON lt.organization_lookup_key = oa.raw_alias_normalized

    LEFT JOIN location_resolved lr
        ON lt.source_listing_id = lr.source_listing_id
)

SELECT
    e.*,

    -- Deterministic surrogate key for standardized organization (NULL when organization is missing)
    CASE
        WHEN e.organization_standardized IS NULL THEN NULL
        ELSE {{ deterministic_sha256_key(["'org'", "LOWER(e.organization_standardized)"]) }}
    END AS organization_key,

    -- Deterministic surrogate key for opportunity location (NULL when location is missing)
    CASE
        WHEN e.location_cleaned IS NULL THEN NULL
        WHEN e.is_location_standardized THEN {{ deterministic_sha256_key([
            "'loc_std'",
            "COALESCE(LOWER(e.standardized_city), '')",
            "COALESCE(LOWER(e.standardized_governorate), '')",
            "COALESCE(LOWER(e.standardized_country), '')",
            "CASE WHEN e.is_online_location_label THEN 'online' ELSE 'physical' END"
        ]) }}
        ELSE {{ deterministic_sha256_key(["'loc_raw'", "LOWER(e.location_cleaned)"]) }}
    END AS location_key,

    -- Clean human-readable display label for opportunity location
    CASE
        WHEN e.location_cleaned IS NULL THEN NULL
        WHEN e.is_online_location_label AND e.standardized_city IS NULL AND e.standardized_country IS NULL THEN 'Online'
        WHEN e.standardized_city IS NOT NULL AND e.standardized_country IS NOT NULL THEN
            e.standardized_city || ', ' || e.standardized_country
        WHEN e.standardized_governorate IS NOT NULL AND e.standardized_country IS NOT NULL THEN
            e.standardized_governorate || ', ' || e.standardized_country
        WHEN e.standardized_country IS NOT NULL THEN e.standardized_country
        ELSE e.location_cleaned
    END AS location_display

FROM enriched e
