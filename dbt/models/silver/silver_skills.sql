WITH listing_skills AS (
    SELECT *
    FROM {{ ref('int_listing_skills_normalized') }}
),

skill_summary AS (
    SELECT
        skill_key,
        COALESCE(
            MIN(skill_name) FILTER (
                WHERE is_alias_mapped
            ),
            MIN(skill_name)
        ) AS skill_name,
        MIN(skill_group) AS skill_group,
        BOOL_OR(is_alias_mapped) AS is_alias_mapped,
        BOOL_OR(is_candidate_skill) AS is_candidate_skill,
        COUNT(DISTINCT source_listing_id) AS source_listing_count
    FROM listing_skills
    GROUP BY skill_key
),

raw_skill_summary AS (
    SELECT
        ls.skill_key,
        JSONB_AGG(
            DISTINCT raw.skill_raw
            ORDER BY raw.skill_raw
        ) AS observed_raw_skills
    FROM listing_skills ls
    CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS_TEXT(
        ls.observed_raw_skills
    ) AS raw(skill_raw)
    GROUP BY ls.skill_key
)

SELECT
    s.skill_key,
    s.skill_name,
    s.skill_group,
    s.is_alias_mapped,
    s.is_candidate_skill,
    r.observed_raw_skills,
    s.source_listing_count
FROM skill_summary s
INNER JOIN raw_skill_summary r
    ON s.skill_key = r.skill_key
