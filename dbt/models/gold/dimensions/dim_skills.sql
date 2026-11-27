{{
    config(
        indexes=[
            {'columns': ['skill_key'], 'unique': True}
        ]
    )
}}

WITH canonical_stats AS (
    SELECT
        bs.skill_key,
        COUNT(DISTINCT bs.opportunity_id) AS canonical_opportunity_count,
        COUNT(DISTINCT bs.opportunity_id) FILTER (WHERE o.is_active) AS active_opportunity_count
    FROM {{ ref('bridge_opportunity_skills') }} bs
    INNER JOIN {{ ref('fct_opportunities') }} o
        ON bs.opportunity_id = o.opportunity_id
    GROUP BY bs.skill_key
)

SELECT
    s.skill_key,
    s.skill_name,
    s.skill_group,
    s.is_alias_mapped,
    s.is_candidate_skill,
    s.observed_raw_skills,
    s.source_listing_count,
    COALESCE(cs.canonical_opportunity_count, 0) AS canonical_opportunity_count,
    COALESCE(cs.active_opportunity_count, 0) AS active_opportunity_count

FROM {{ ref('silver_skills') }} s
LEFT JOIN canonical_stats cs
    ON s.skill_key = cs.skill_key
