-- Fails if Gold core facts diverge from Silver canonical models:
-- 1. fct_opportunities must match silver_opportunities 1-to-1 on opportunity_id, primary_source_listing_id, and source_count.
-- 2. fct_opportunity_sources must match silver_opportunity_sources 1-to-1 on source_listing_id and opportunity_id.

WITH opp_parity AS (
    SELECT
        COALESCE(s.opportunity_id, g.opportunity_id)::TEXT AS entity_id,
        'fct_opportunities_silver_mismatch'::TEXT AS failure_reason
    FROM {{ ref('silver_opportunities') }} s
    FULL OUTER JOIN {{ ref('fct_opportunities') }} g
        ON s.opportunity_id = g.opportunity_id
    WHERE s.opportunity_id IS NULL
       OR g.opportunity_id IS NULL
       OR s.primary_source_listing_id IS DISTINCT FROM g.primary_source_listing_id
       OR s.source_count IS DISTINCT FROM g.source_count
       OR s.effective_status IS DISTINCT FROM g.effective_status
),

source_parity AS (
    SELECT
        COALESCE(s.source_listing_id, g.source_listing_id)::TEXT AS entity_id,
        'fct_opportunity_sources_silver_mismatch'::TEXT AS failure_reason
    FROM {{ ref('silver_opportunity_sources') }} s
    FULL OUTER JOIN {{ ref('fct_opportunity_sources') }} g
        ON s.source_listing_id = g.source_listing_id
    WHERE s.source_listing_id IS NULL
       OR g.source_listing_id IS NULL
       OR s.opportunity_id IS DISTINCT FROM g.opportunity_id
       OR s.is_primary_source IS DISTINCT FROM g.is_primary_source
)

SELECT * FROM opp_parity
UNION ALL
SELECT * FROM source_parity
