WITH expanded AS (
    SELECT
        sl.source_listing_id,
        sl.source_name,
        {{ clean_text('elem.raw_skill') }} AS skill_raw,
        {{ normalize_lookup_key('elem.raw_skill') }} AS skill_lookup_key,
        elem.elem_pos
    FROM {{ ref('stg_bronze__source_listings') }} sl
    CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS_TEXT(
        CASE
            WHEN JSONB_TYPEOF(sl.required_skills) = 'array'
                THEN sl.required_skills
            ELSE '[]'::JSONB
        END
    ) WITH ORDINALITY AS elem(raw_skill, elem_pos)
    WHERE {{ clean_text('elem.raw_skill') }} IS NOT NULL
),

mapped AS (
    SELECT
        ex.source_listing_id,
        ex.source_name,
        ex.skill_raw,
        COALESCE(
            sa.standardized_skill_name,
            ex.skill_raw
        ) AS skill_name,
        sa.skill_group,
        (sa.raw_skill_normalized IS NOT NULL) AS is_alias_mapped,
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

ranked AS (
    SELECT
        k.*,
        ROW_NUMBER() OVER (
            PARTITION BY k.source_listing_id, k.skill_key
            ORDER BY
                k.is_alias_mapped DESC,
                k.elem_pos ASC
        ) AS rn
    FROM keyed k
),

aggregated AS (
    SELECT
        source_listing_id,
        skill_key,
        JSONB_AGG(
            DISTINCT skill_raw
            ORDER BY skill_raw
        ) AS observed_raw_skills,
        BOOL_OR(is_alias_mapped) AS is_alias_mapped,
        BOOL_OR(is_candidate_skill) AS is_candidate_skill,
        MIN(skill_group) AS skill_group
    FROM keyed
    GROUP BY
        source_listing_id,
        skill_key
)

SELECT
    {{ deterministic_sha256_key(["r.source_listing_id", "r.skill_key"]) }} AS listing_skill_id,
    r.source_listing_id,
    r.source_name,
    r.skill_key,
    r.skill_name,
    r.skill_raw,
    a.skill_group,
    a.is_alias_mapped,
    r.skill_source_type,
    a.is_candidate_skill,
    a.observed_raw_skills
FROM ranked r
INNER JOIN aggregated a
    ON r.source_listing_id = a.source_listing_id
   AND r.skill_key = a.skill_key
WHERE r.rn = 1
