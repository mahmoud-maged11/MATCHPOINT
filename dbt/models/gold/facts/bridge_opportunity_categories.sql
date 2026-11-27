{{
    config(
        indexes=[
            {'columns': ['opportunity_category_id'], 'unique': True},
            {'columns': ['opportunity_id']},
            {'columns': ['category_key']}
        ]
    )
}}

-- Canonical opportunity-to-category bridge deduplicated across merged sources (kept separate from skills per ADR-007).

WITH grouped AS (
    SELECT
        os.opportunity_id,
        lc.category_key,
        MIN(c.category_name) AS category_name,
        COUNT(DISTINCT os.source_listing_id) AS supporting_source_count
    FROM {{ ref('silver_opportunity_sources') }} os
    INNER JOIN {{ ref('silver_listing_categories') }} lc
        ON os.source_listing_id = lc.source_listing_id
    INNER JOIN {{ ref('silver_categories') }} c
        ON lc.category_key = c.category_key
    GROUP BY
        os.opportunity_id,
        lc.category_key
)

SELECT
    {{ deterministic_sha256_key(["opportunity_id", "category_key"]) }} AS opportunity_category_id,
    opportunity_id,
    category_key,
    category_name,
    supporting_source_count
FROM grouped
