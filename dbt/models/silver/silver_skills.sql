SELECT
    skill_key,
    MIN(skill_name) AS skill_name,
    MIN(skill_group) AS skill_group,
    BOOL_OR(is_alias_mapped) AS is_alias_mapped,
    BOOL_OR(is_candidate_skill) AS is_candidate_skill,
    JSONB_AGG(DISTINCT skill_raw ORDER BY skill_raw) AS observed_raw_skills,
    COUNT(DISTINCT source_listing_id) AS source_listing_count

FROM {{ ref('int_listing_skills_normalized') }}
GROUP BY skill_key
