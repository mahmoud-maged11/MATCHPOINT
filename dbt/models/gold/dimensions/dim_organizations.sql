{{
    config(
        indexes=[
            {'columns': ['organization_key'], 'unique': True},
            {'columns': ['has_canonical_opportunities']}
        ]
    )
}}

WITH canonical_stats AS (
    SELECT
        organization_key,
        COUNT(*) AS canonical_opportunity_count,
        COUNT(*) FILTER (WHERE is_active) AS active_opportunity_count
    FROM {{ ref('fct_opportunities') }}
    WHERE organization_key IS NOT NULL
    GROUP BY organization_key
)

SELECT
    o.organization_key,
    o.organization_name,
    o.is_alias_mapped,
    o.observed_raw_names,
    o.source_listing_count,
    COALESCE(cs.canonical_opportunity_count, 0) AS canonical_opportunity_count,
    COALESCE(cs.active_opportunity_count, 0) AS active_opportunity_count,
    (COALESCE(cs.canonical_opportunity_count, 0) > 0) AS has_canonical_opportunities

FROM {{ ref('silver_organizations') }} o
LEFT JOIN canonical_stats cs
    ON o.organization_key = cs.organization_key
