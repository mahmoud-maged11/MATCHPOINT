SELECT
    -- Source identity
    source_listing_id,
    BTRIM(source_name) AS source_name,
    BTRIM(source_opportunity_id) AS source_opportunity_id,
    BTRIM(source_identity_key) AS source_identity_key,
    BTRIM(source_url) AS source_url,

    -- Basic opportunity information
    BTRIM(title) AS title,
    NULLIF(BTRIM(organization), '') AS organization,
    NULLIF(BTRIM(description), '') AS description,
    BTRIM(opportunity_type) AS opportunity_type,

    -- Location and work classification (NULL vs [] JSONB arrays preserved untouched)
    NULLIF(BTRIM(location), '') AS location,
    work_modes,
    employment_types,
    categories,

    -- Experience and qualifications
    NULLIF(BTRIM(experience_level), '') AS experience_level,
    NULLIF(BTRIM(experience_level_raw), '') AS experience_level_raw,
    experience_years_min,
    experience_years_max,
    NULLIF(BTRIM(education_level), '') AS education_level,
    required_skills,
    NULLIF(BTRIM(requirements), '') AS requirements,

    -- Salary information
    salary_min,
    salary_max,
    NULLIF(BTRIM(currency), '') AS currency,
    NULLIF(BTRIM(salary_period), '') AS salary_period,

    -- Publication and deadline dates (original raw strings and precision preserved)
    published_at,
    NULLIF(BTRIM(published_at_raw), '') AS published_at_raw,
    NULLIF(BTRIM(published_at_precision), '') AS published_at_precision,
    deadline,
    NULLIF(BTRIM(deadline_raw), '') AS deadline_raw,
    NULLIF(BTRIM(deadline_precision), '') AS deadline_precision,

    -- Observed status preserved explicitly prior to downstream lifecycle derivation
    BTRIM(status) AS observed_status,
    NULLIF(BTRIM(source_status_raw), '') AS source_status_raw,

    -- Ingestion and versioning metadata
    collected_at,
    first_seen_at,
    last_seen_at,
    created_at,
    updated_at,
    content_hash,
    hash_version,
    content_version,
    last_collection_run_id,

    -- Retained permitted source evidence
    raw_payload

FROM {{ source('bronze', 'source_listings') }}
