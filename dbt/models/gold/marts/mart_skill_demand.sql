WITH opportunities_with_skills AS (
    SELECT COUNT(DISTINCT opportunity_id) AS total_opps_with_skills
    FROM {{ ref('bridge_opportunity_skills') }}
),

skill_counts AS (
    SELECT
        ds.skill_key,
        ds.skill_name,
        ds.skill_group,
        ds.is_alias_mapped,
        ds.is_candidate_skill,
        COUNT(DISTINCT bs.opportunity_id) AS canonical_opportunity_count,
        COUNT(DISTINCT bs.opportunity_id) FILTER (WHERE fo.is_active) AS active_opportunity_count,
        COUNT(DISTINCT bs.opportunity_id) FILTER (WHERE fo.is_expired) AS expired_opportunity_count,
        COUNT(DISTINCT bs.opportunity_id) FILTER (WHERE fo.is_closed) AS closed_opportunity_count,
        COUNT(DISTINCT bs.opportunity_id) FILTER (WHERE fo.is_unknown_status) AS unknown_opportunity_count
    FROM {{ ref('dim_skills') }} ds
    INNER JOIN {{ ref('bridge_opportunity_skills') }} bs
        ON ds.skill_key = bs.skill_key
    INNER JOIN {{ ref('fct_opportunities') }} fo
        ON bs.opportunity_id = fo.opportunity_id
    GROUP BY
        ds.skill_key,
        ds.skill_name,
        ds.skill_group,
        ds.is_alias_mapped,
        ds.is_candidate_skill
)

SELECT
    sc.skill_key,
    sc.skill_name,
    sc.skill_group,
    sc.is_alias_mapped,
    sc.is_candidate_skill,
    sc.canonical_opportunity_count,
    sc.active_opportunity_count,
    sc.expired_opportunity_count,
    sc.closed_opportunity_count,
    sc.unknown_opportunity_count,
    CASE
        WHEN ows.total_opps_with_skills > 0 THEN
            ROUND((sc.canonical_opportunity_count::NUMERIC / ows.total_opps_with_skills::NUMERIC), 4)
        ELSE NULL
    END AS share_of_opportunities_with_skills

FROM skill_counts sc
CROSS JOIN opportunities_with_skills ows
