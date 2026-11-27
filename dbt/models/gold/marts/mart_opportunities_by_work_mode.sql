-- Canonical opportunities by opportunity_type and work_mode (replaces the former Cartesian arrangement mart).
-- Counting semantics:
--   Because one opportunity may support multiple work_modes (ADR-002), opportunities_with_work_mode_count
--   is NON-ADDITIVE across work_mode rows for the same opportunity_type. Use gold.fct_opportunities for grand totals.
--   'unreported' represents opportunities where work_modes is NULL or confirmed empty [].

WITH expanded AS (
    SELECT
        fo.opportunity_id,
        fo.opportunity_type,
        COALESCE(wm.work_mode, 'unreported') AS work_mode,
        fo.is_active,
        fo.is_expired,
        fo.is_closed,
        fo.is_unknown_status,
        fo.has_disclosed_salary
    FROM {{ ref('fct_opportunities') }} fo
    LEFT JOIN {{ ref('bridge_opportunity_work_modes') }} wm
        ON fo.opportunity_id = wm.opportunity_id
)

SELECT
    {{ deterministic_sha256_key(["opportunity_type", "work_mode"]) }} AS work_mode_bucket_key,
    opportunity_type,
    work_mode,
    COUNT(DISTINCT opportunity_id) AS opportunities_with_work_mode_count,
    COUNT(DISTINCT opportunity_id) FILTER (WHERE is_active) AS active_opportunities_count,
    COUNT(DISTINCT opportunity_id) FILTER (WHERE is_expired) AS expired_opportunities_count,
    COUNT(DISTINCT opportunity_id) FILTER (WHERE is_closed) AS closed_opportunities_count,
    COUNT(DISTINCT opportunity_id) FILTER (WHERE is_unknown_status) AS unknown_opportunities_count,
    COUNT(DISTINCT opportunity_id) FILTER (WHERE has_disclosed_salary) AS disclosed_salary_opportunities_count

FROM expanded
GROUP BY
    opportunity_type,
    work_mode
