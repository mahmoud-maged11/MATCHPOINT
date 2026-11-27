-- Fails if any Silver listing violates JSONB array integrity rules (Data Contract v3.0.0 §5.2):
-- 1. Array fields must be NULL or JSONB type 'array'.
-- 2. Array state indicators must match actual NULL vs [] vs populated JSONB state.
-- 3. 'unknown' must never be combined with known standardized values in work_modes or employment_types.

SELECT
    source_listing_id,
    source_name,
    work_modes,
    work_modes_state,
    employment_types,
    employment_types_state,
    categories,
    categories_state,
    required_skills,
    required_skills_state
FROM {{ ref('silver_source_listings') }}
WHERE
    -- Type checks
    (work_modes IS NOT NULL AND JSONB_TYPEOF(work_modes) <> 'array')
    OR (employment_types IS NOT NULL AND JSONB_TYPEOF(employment_types) <> 'array')
    OR (categories IS NOT NULL AND JSONB_TYPEOF(categories) <> 'array')
    OR (required_skills IS NOT NULL AND JSONB_TYPEOF(required_skills) <> 'array')

    -- State consistency checks
    OR (work_modes IS NULL AND work_modes_state <> 'missing')
    OR (work_modes IS NOT NULL AND JSONB_ARRAY_LENGTH(work_modes) = 0 AND work_modes_state <> 'confirmed_empty')
    OR (work_modes IS NOT NULL AND JSONB_ARRAY_LENGTH(work_modes) > 0 AND work_modes_state <> 'populated')

    OR (employment_types IS NULL AND employment_types_state <> 'missing')
    OR (employment_types IS NOT NULL AND JSONB_ARRAY_LENGTH(employment_types) = 0 AND employment_types_state <> 'confirmed_empty')
    OR (employment_types IS NOT NULL AND JSONB_ARRAY_LENGTH(employment_types) > 0 AND employment_types_state <> 'populated')

    OR (categories IS NULL AND categories_state <> 'missing')
    OR (categories IS NOT NULL AND JSONB_ARRAY_LENGTH(categories) = 0 AND categories_state <> 'confirmed_empty')
    OR (categories IS NOT NULL AND JSONB_ARRAY_LENGTH(categories) > 0 AND categories_state <> 'populated')

    OR (required_skills IS NULL AND required_skills_state <> 'missing')
    OR (required_skills IS NOT NULL AND JSONB_ARRAY_LENGTH(required_skills) = 0 AND required_skills_state <> 'confirmed_empty')
    OR (required_skills IS NOT NULL AND JSONB_ARRAY_LENGTH(required_skills) > 0 AND required_skills_state <> 'populated')

    -- Standardized 'unknown' exclusivity checks
    OR (
        work_modes IS NOT NULL
        AND JSONB_ARRAY_LENGTH(work_modes) > 1
        AND work_modes ? 'unknown'
    )
    OR (
        employment_types IS NOT NULL
        AND JSONB_ARRAY_LENGTH(employment_types) > 1
        AND employment_types ? 'unknown'
    )
