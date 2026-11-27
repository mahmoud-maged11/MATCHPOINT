-- Canonical opportunities by standardized opportunity location, including an explicit
-- 'unreported' bucket for opportunities with location_key IS NULL so totals reconcile 100%
-- with gold.fct_opportunities without silently dropping missing-location opportunities.

WITH located AS (
    SELECT
        dl.location_key,
        dl.location_display,
        dl.standardized_city,
        dl.standardized_governorate,
        dl.standardized_country,
        dl.country_code,
        dl.is_online_location_label,
        dl.is_standardized_mapping,
        FALSE AS is_unreported_location,
        COUNT(*) AS canonical_opportunity_count,
        COUNT(*) FILTER (WHERE fo.is_active) AS active_opportunity_count,
        COUNT(*) FILTER (WHERE fo.is_expired) AS expired_opportunity_count,
        COUNT(*) FILTER (WHERE fo.is_closed) AS closed_opportunity_count,
        COUNT(*) FILTER (WHERE fo.is_unknown_status) AS unknown_opportunity_count,
        COUNT(*) FILTER (WHERE fo.has_disclosed_salary) AS disclosed_salary_opportunity_count
    FROM {{ ref('dim_locations') }} dl
    INNER JOIN {{ ref('fct_opportunities') }} fo
        ON dl.location_key = fo.location_key
    GROUP BY
        dl.location_key,
        dl.location_display,
        dl.standardized_city,
        dl.standardized_governorate,
        dl.standardized_country,
        dl.country_code,
        dl.is_online_location_label,
        dl.is_standardized_mapping
),

unreported AS (
    SELECT
        'unreported'::TEXT AS location_key,
        'Unreported'::TEXT AS location_display,
        NULL::TEXT AS standardized_city,
        NULL::TEXT AS standardized_governorate,
        NULL::TEXT AS standardized_country,
        NULL::TEXT AS country_code,
        FALSE AS is_online_location_label,
        FALSE AS is_standardized_mapping,
        TRUE AS is_unreported_location,
        COUNT(*) AS canonical_opportunity_count,
        COUNT(*) FILTER (WHERE fo.is_active) AS active_opportunity_count,
        COUNT(*) FILTER (WHERE fo.is_expired) AS expired_opportunity_count,
        COUNT(*) FILTER (WHERE fo.is_closed) AS closed_opportunity_count,
        COUNT(*) FILTER (WHERE fo.is_unknown_status) AS unknown_opportunity_count,
        COUNT(*) FILTER (WHERE fo.has_disclosed_salary) AS disclosed_salary_opportunity_count
    FROM {{ ref('fct_opportunities') }} fo
    WHERE fo.location_key IS NULL
    HAVING COUNT(*) > 0
)

SELECT * FROM located
UNION ALL
SELECT * FROM unreported
