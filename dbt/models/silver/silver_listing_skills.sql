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
