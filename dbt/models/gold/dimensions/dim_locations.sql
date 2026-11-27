{{
    config(
        indexes=[
            {'columns': ['location_key'], 'unique': True},
            {'columns': ['has_canonical_opportunities']}
        ]
    )
}}

-- Conformed opportunity location dimension (strictly opportunity location; separate from
-- organization headquarters, work_modes, and applicant geographic eligibility).
-- Secondary-only source locations are retained with canonical_opportunity_count = 0 and
-- has_canonical_opportunities = FALSE so downstream consumers can filter reliably.

WITH canonical_stats AS (
    SELECT
        location_key,
        COUNT(*) AS canonical_opportunity_count,
        COUNT(*) FILTER (WHERE is_active) AS active_opportunity_count
    FROM {{ ref('fct_opportunities') }}
    WHERE location_key IS NOT NULL
    GROUP BY location_key
)

SELECT
    l.location_key,
    l.location_display,
    l.standardized_city,
    l.standardized_governorate,
    l.standardized_country,
    l.country_code,
    l.is_online_location_label,
    l.is_standardized_mapping,
    l.observed_raw_locations,
    l.source_listing_count,
    COALESCE(cs.canonical_opportunity_count, 0) AS canonical_opportunity_count,
    COALESCE(cs.active_opportunity_count, 0) AS active_opportunity_count,
    (COALESCE(cs.canonical_opportunity_count, 0) > 0) AS has_canonical_opportunities

FROM {{ ref('silver_locations') }} l
LEFT JOIN canonical_stats cs
    ON l.location_key = cs.location_key
