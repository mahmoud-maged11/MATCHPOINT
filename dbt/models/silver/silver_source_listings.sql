SELECT
    -- Source identity and attribution
    source_listing_id,
    source_name,
    source_opportunity_id,
    source_identity_key,
    source_url,

    -- Opportunity details (cleaned + raw preserved)
    title,
    title_raw,
    organization_key,
    organization_standardized AS organization,
    organization_raw,
    is_organization_alias_mapped,
    description,
    opportunity_type,

    -- Opportunity location (kept separate from organization location, work_modes, and eligibility)
    location_key,
    location_display,
    location_raw,
    standardized_city,
    standardized_governorate,
    standardized_country,
    country_code,
    is_online_location_label,
    is_location_standardized,
    applicant_eligibility_raw,

    -- Preserved Bronze JSONB arrays + explicit missing/empty/populated state
    work_modes,
    work_modes_state,
    employment_types,
    employment_types_state,
    categories,
    categories_state,
    required_skills,
    required_skills_state,

    -- Qualifications and salary
    experience_level,
    experience_level_raw,
    experience_years_min,
    experience_years_max,
    education_level,
    requirements,
    salary_min,
    salary_max,
    currency,
    salary_period,

    -- Dates, precision, and lifecycle reconciliation (ADR-018, ADR-047)
    published_at,
    published_at_raw,
    published_at_precision,
    deadline,
    deadline_raw,
    deadline_precision,
    is_deadline_reliable,
    observed_status,
    source_status_raw,
    effective_status,
    effective_status_reason,
    lifecycle_evaluated_at,

    -- Bronze ingestion and versioning metadata
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

FROM {{ ref('int_listings_cleaned') }}
