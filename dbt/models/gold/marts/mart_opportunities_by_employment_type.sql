-- Canonical opportunities by opportunity_type and employment_type (replaces the former Cartesian arrangement mart).
-- Counting semantics:
--   Because one opportunity may support multiple employment_types (ADR-001), opportunities_with_employment_type_count
--   is NON-ADDITIVE across employment_type rows for the same opportunity_type. Use gold.fct_opportunities for grand totals.
--   'unreported' represents opportunities where employment_types is NULL or confirmed empty [].

WITH expanded AS (
    SELECT
        fo.opportunity_id,
        fo.opportunity_type,
        COALESCE(et.employment_type, 'unreported') AS employment_type,
        fo.is_active,
        fo.is_expired,
        fo.is_closed,
        fo.is_unknown_status,
        fo.has_disclosed_salary
    FROM {{ ref('fct_opportunities') }} fo
    LEFT JOIN {{ ref('bridge_opportunity_employment_types') }} et
        ON fo.opportunity_id = et.opportunity_id
)

SELECT
    {{ deterministic_sha256_key(["opportunity_type", "employment_type"]) }} AS employment_type_bucket_key,
    opportunity_type,
    employment_type,
    COUNT(DISTINCT opportunity_id) AS opportunities_with_employment_type_count,
    COUNT(DISTINCT opportunity_id) FILTER (WHERE is_active) AS active_opportunities_count,
    COUNT(DISTINCT opportunity_id) FILTER (WHERE is_expired) AS expired_opportunities_count,
    COUNT(DISTINCT opportunity_id) FILTER (WHERE is_closed) AS closed_opportunities_count,
    COUNT(DISTINCT opportunity_id) FILTER (WHERE is_unknown_status) AS unknown_opportunities_count,
    COUNT(DISTINCT opportunity_id) FILTER (WHERE has_disclosed_salary) AS disclosed_salary_opportunities_count

FROM expanded
GROUP BY
    opportunity_type,
    employment_type
