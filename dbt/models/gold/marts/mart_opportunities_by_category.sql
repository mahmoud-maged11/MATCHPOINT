SELECT
    dc.category_key,
    dc.category_name,
    COUNT(DISTINCT bc.opportunity_id) AS canonical_opportunity_count,
    COUNT(DISTINCT bc.opportunity_id) FILTER (WHERE fo.is_active) AS active_opportunity_count,
    COUNT(DISTINCT bc.opportunity_id) FILTER (WHERE fo.is_expired) AS expired_opportunity_count,
    COUNT(DISTINCT bc.opportunity_id) FILTER (WHERE fo.is_closed) AS closed_opportunity_count,
    COUNT(DISTINCT bc.opportunity_id) FILTER (WHERE fo.is_unknown_status) AS unknown_opportunity_count,
    COUNT(DISTINCT bc.opportunity_id) FILTER (WHERE fo.has_disclosed_salary) AS disclosed_salary_opportunity_count

FROM {{ ref('dim_categories') }} dc
INNER JOIN {{ ref('bridge_opportunity_categories') }} bc
    ON dc.category_key = bc.category_key
INNER JOIN {{ ref('fct_opportunities') }} fo
    ON bc.opportunity_id = fo.opportunity_id
GROUP BY
    dc.category_key,
    dc.category_name
