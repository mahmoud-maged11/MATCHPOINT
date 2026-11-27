-- Publication and lifecycle trend mart strictly limited to canonical opportunities
-- with reliable publication dates (exact or date_only precision per ADR-006).
-- Never fabricates publication dates from collected_at or relative date labels.

SELECT
    {{ deterministic_sha256_key(["dd.date_key", "fo.opportunity_type", "fo.effective_status"]) }} AS trend_bucket_key,
    dd.date_key AS published_date_key,
    dd.calendar_date AS published_date,
    dd.year AS published_year,
    dd.month AS published_month,
    fo.opportunity_type,
    fo.effective_status,
    COUNT(*) AS canonical_opportunity_count,
    COUNT(*) FILTER (WHERE fo.is_multi_source) AS multi_source_opportunity_count,
    COUNT(*) FILTER (WHERE fo.has_disclosed_salary) AS disclosed_salary_opportunity_count

FROM {{ ref('fct_opportunities') }} fo
INNER JOIN {{ ref('dim_dates') }} dd
    ON fo.published_date_key = dd.date_key
WHERE fo.published_date_key IS NOT NULL
GROUP BY
    dd.date_key,
    dd.calendar_date,
    dd.year,
    dd.month,
    fo.opportunity_type,
    fo.effective_status
