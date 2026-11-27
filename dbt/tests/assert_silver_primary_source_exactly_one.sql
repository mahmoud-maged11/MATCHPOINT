-- Fails if any canonical opportunity does not have EXACTLY ONE deterministic primary source,
-- or if silver_opportunities.primary_source_listing_id disagrees with silver_opportunity_sources.

WITH primary_counts AS (
    SELECT
        opportunity_id,
        COUNT(*) FILTER (WHERE is_primary_source) AS primary_count,
        MIN(source_listing_id::TEXT) FILTER (WHERE is_primary_source) AS mapped_primary_listing_id
    FROM {{ ref('silver_opportunity_sources') }}
    GROUP BY opportunity_id
)

SELECT
    COALESCE(o.opportunity_id, pc.opportunity_id) AS opportunity_id,
    pc.primary_count,
    o.primary_source_listing_id,
    pc.mapped_primary_listing_id
FROM {{ ref('silver_opportunities') }} o
FULL OUTER JOIN primary_counts pc
    ON o.opportunity_id = pc.opportunity_id
WHERE o.opportunity_id IS NULL
   OR pc.opportunity_id IS NULL
   OR pc.primary_count <> 1
   OR o.primary_source_listing_id::TEXT IS DISTINCT FROM pc.mapped_primary_listing_id
