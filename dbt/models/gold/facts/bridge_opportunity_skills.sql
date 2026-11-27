{{
    config(
        indexes=[
            {'columns': ['opportunity_skill_id'], 'unique': True},
            {'columns': ['opportunity_id']},
            {'columns': ['skill_key']}
        ]
    )
}}

-- Canonical opportunity-to-skill bridge deduplicated across merged sources so a skill
-- listed by multiple sources for the same canonical opportunity is counted once.
-- Uses explicit precedence (explicit_source_tag > extracted) rather than alphabetical MIN().

WITH grouped AS (
    SELECT
        os.opportunity_id,
        ls.skill_key,
        MIN(s.skill_name) AS skill_name,
        MIN(s.skill_group) AS skill_group,
        BOOL_OR(ls.is_alias_mapped) AS is_alias_mapped,
        CASE
            WHEN BOOL_OR(ls.skill_source_type = 'explicit_source_tag') THEN 'explicit_source_tag'
            ELSE 'extracted'
        END AS skill_source_type,
        BOOL_AND(ls.is_candidate_skill) AS is_candidate_skill,
        COUNT(DISTINCT os.source_listing_id) AS supporting_source_count
    FROM {{ ref('silver_opportunity_sources') }} os
    INNER JOIN {{ ref('silver_listing_skills') }} ls
        ON os.source_listing_id = ls.source_listing_id
    INNER JOIN {{ ref('silver_skills') }} s
        ON ls.skill_key = s.skill_key
    GROUP BY
        os.opportunity_id,
        ls.skill_key
)

SELECT
    {{ deterministic_sha256_key(["opportunity_id", "skill_key"]) }} AS opportunity_skill_id,
    opportunity_id,
    skill_key,
    skill_name,
    skill_group,
    is_alias_mapped,
    skill_source_type,
    is_candidate_skill,
    supporting_source_count
FROM grouped
