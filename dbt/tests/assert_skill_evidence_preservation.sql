-- Validate skill evidence preservation across Intermediate and Silver.
-- Returns zero rows on success.

WITH expected_raw AS (
    SELECT DISTINCT
        sl.source_listing_id,
        {{ clean_text('elem.raw_skill') }} AS skill_raw
    FROM {{ ref('stg_bronze__source_listings') }} sl
    CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS_TEXT(
        CASE
            WHEN JSONB_TYPEOF(sl.required_skills) = 'array'
                THEN sl.required_skills
            ELSE '[]'::JSONB
        END
    ) AS elem(raw_skill)
    WHERE {{ clean_text('elem.raw_skill') }} IS NOT NULL
),

actual_raw AS (
    SELECT DISTINCT
        ls.source_listing_id,
        raw.skill_raw
    FROM {{ ref('int_listing_skills_normalized') }} ls
    CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS_TEXT(
        ls.observed_raw_skills
    ) AS raw(skill_raw)
),

missing_evidence AS (
    SELECT * FROM expected_raw
    EXCEPT
    SELECT * FROM actual_raw
),

unexpected_evidence AS (
    SELECT * FROM actual_raw
    EXCEPT
    SELECT * FROM expected_raw
),

duplicate_skills AS (
    SELECT
        source_listing_id,
        skill_key
    FROM {{ ref('int_listing_skills_normalized') }}
    GROUP BY source_listing_id, skill_key
    HAVING COUNT(*) > 1
),

intermediate_rows AS (
    SELECT
        listing_skill_id,
        source_listing_id,
        source_name,
        skill_key,
        skill_name,
        skill_raw,
        skill_group,
        is_alias_mapped,
        skill_source_type,
        is_candidate_skill,
        observed_raw_skills
    FROM {{ ref('int_listing_skills_normalized') }}
),

silver_rows AS (
    SELECT
        listing_skill_id,
        source_listing_id,
        source_name,
        skill_key,
        skill_name,
        skill_raw,
        skill_group,
        is_alias_mapped,
        skill_source_type,
        is_candidate_skill,
        observed_raw_skills
    FROM {{ ref('silver_listing_skills') }}
),

missing_silver AS (
    SELECT * FROM intermediate_rows
    EXCEPT ALL
    SELECT * FROM silver_rows
),

unexpected_silver AS (
    SELECT * FROM silver_rows
    EXCEPT ALL
    SELECT * FROM intermediate_rows
),

expected_summary AS (
    SELECT
        skill_key,
        COUNT(DISTINCT source_listing_id) AS source_listing_count,
        BOOL_OR(is_alias_mapped) AS is_alias_mapped
    FROM intermediate_rows
    GROUP BY skill_key
),

expected_summary_raw AS (
    SELECT
        ls.skill_key,
        JSONB_AGG(
            DISTINCT raw.skill_raw
            ORDER BY raw.skill_raw
        ) AS observed_raw_skills
    FROM intermediate_rows ls
    CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS_TEXT(
        ls.observed_raw_skills
    ) AS raw(skill_raw)
    GROUP BY ls.skill_key
),

summary_mismatch AS (
    SELECT
        COALESCE(e.skill_key, s.skill_key) AS skill_key
    FROM expected_summary e
    FULL OUTER JOIN {{ ref('silver_skills') }} s
        ON e.skill_key = s.skill_key
    LEFT JOIN expected_summary_raw r
        ON e.skill_key = r.skill_key
    WHERE e.skill_key IS NULL
       OR s.skill_key IS NULL
       OR e.source_listing_count
          IS DISTINCT FROM s.source_listing_count
       OR e.is_alias_mapped
          IS DISTINCT FROM s.is_alias_mapped
       OR r.observed_raw_skills
          IS DISTINCT FROM s.observed_raw_skills
)

SELECT
    'missing_raw_evidence' AS failure_type,
    source_listing_id::TEXT AS record_id,
    skill_raw AS details
FROM missing_evidence

UNION ALL

SELECT
    'unexpected_raw_evidence',
    source_listing_id::TEXT,
    skill_raw
FROM unexpected_evidence

UNION ALL

SELECT
    'duplicate_listing_skill',
    source_listing_id::TEXT,
    skill_key
FROM duplicate_skills

UNION ALL

SELECT
    'missing_silver_row',
    listing_skill_id::TEXT,
    skill_name
FROM missing_silver

UNION ALL

SELECT
    'unexpected_silver_row',
    listing_skill_id::TEXT,
    skill_name
FROM unexpected_silver

UNION ALL

SELECT
    'skill_summary_mismatch',
    skill_key,
    'Silver skill evidence or aggregation mismatch'
FROM summary_mismatch
