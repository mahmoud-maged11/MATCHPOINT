{{
    config(
        indexes=[
            {'columns': ['category_key'], 'unique': True}
        ]
    )
}}

WITH canonical_stats AS (
    SELECT
        bc.category_key,
        COUNT(DISTINCT bc.opportunity_id) AS canonical_opportunity_count,
        COUNT(DISTINCT bc.opportunity_id) FILTER (WHERE o.is_active) AS active_opportunity_count
    FROM {{ ref('bridge_opportunity_categories') }} bc
    INNER JOIN {{ ref('fct_opportunities') }} o
        ON bc.opportunity_id = o.opportunity_id
    GROUP BY bc.category_key
)

SELECT
    c.category_key,
    c.category_name,
    c.observed_raw_categories,
    c.source_listing_count,
    COALESCE(cs.canonical_opportunity_count, 0) AS canonical_opportunity_count,
    COALESCE(cs.active_opportunity_count, 0) AS active_opportunity_count

FROM {{ ref('silver_categories') }} c
LEFT JOIN canonical_stats cs
    ON c.category_key = cs.category_key
