WITH expanded AS (
    SELECT
        sl.source_listing_id,
        sl.source_name,
        {{ clean_text('elem.raw_skill') }} AS skill_raw,
        {{ normalize_lookup_key('elem.raw_skill') }} AS skill_lookup_key,
        elem.elem_pos
    FROM {{ ref('stg_bronze__source_listings') }} sl
    CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS_TEXT(sl.required_skills)
        WITH ORDINALITY AS elem(raw_skill, elem_pos)
    WHERE sl.required_skills IS NOT NULL
      AND JSONB_TYPEOF(sl.required_skills) = 'array'
      AND JSONB_ARRAY_LENGTH(sl.required_skills) > 0
      AND {{ clean_text('elem.raw_skill') }} IS NOT NULL
),

mapped AS (
    SELECT
        ex.source_listing_id,
        ex.source_name,
        ex.skill_raw,
        COALESCE(sa.standardized_skill_name, ex.skill_raw) AS skill_name,
        sa.skill_group,
        (sa.raw_skill_normalized IS NOT NULL) AS is_alias_mapped,
        -- All skills from bronze.source_listings.required_skills are explicit source-provided tags
        -- (kept distinguishable from any future NLP-extracted skills and marked as candidate skills per ADR-007)
        'explicit_source_tag'::TEXT AS skill_source_type,
        TRUE AS is_candidate_skill,
        ex.elem_pos
    FROM expanded ex
    LEFT JOIN {{ ref('skill_aliases') }} sa
        ON ex.skill_lookup_key = sa.raw_skill_normalized
),

keyed AS (
    SELECT
        m.*,
        {{ deterministic_sha256_key(["'skill'", "LOWER(m.skill_name)"]) }} AS skill_key
    FROM mapped m
),

deduplicated AS (
    SELECT
        k.*,
        ROW_NUMBER() OVER (
            PARTITION BY k.source_listing_id, k.skill_key
            ORDER BY k.elem_pos ASC
        ) AS rn
    FROM keyed k
)

SELECT
    {{ deterministic_sha256_key(["source_listing_id", "skill_key"]) }} AS listing_skill_id,
    source_listing_id,
    source_name,
    skill_key,
    skill_name,
    skill_raw,
    skill_group,
    is_alias_mapped,
    skill_source_type,
    is_candidate_skill
FROM deduplicated
WHERE rn = 1
