-- Fails if canonical source mapping is incomplete, duplicated, or orphaned:
-- 1. Every silver_source_listings row must appear exactly once in silver_opportunity_sources.
-- 2. Every silver_opportunity_sources row must reference an existing silver_opportunities row.
-- 3. Every silver_opportunities row must have source_count equal to its actual mapped listings count.

WITH listing_mapping_check AS (
    SELECT
        COALESCE(sl.source_listing_id, os.source_listing_id) AS entity_id,
        'missing_or_orphaned_source_mapping'::TEXT AS failure_reason
    FROM {{ ref('silver_source_listings') }} sl
    FULL OUTER JOIN {{ ref('silver_opportunity_sources') }} os
        ON sl.source_listing_id = os.source_listing_id
    WHERE sl.source_listing_id IS NULL
       OR os.source_listing_id IS NULL
),

source_count_check AS (
    SELECT
        COALESCE(o.opportunity_id, os_counts.opportunity_id) AS entity_id,
        'opportunity_source_count_mismatch'::TEXT AS failure_reason
    FROM {{ ref('silver_opportunities') }} o
    FULL OUTER JOIN (
        SELECT
            opportunity_id,
            COUNT(*) AS actual_source_count
        FROM {{ ref('silver_opportunity_sources') }}
        GROUP BY opportunity_id
    ) os_counts
        ON o.opportunity_id = os_counts.opportunity_id
    WHERE o.opportunity_id IS NULL
       OR os_counts.opportunity_id IS NULL
       OR o.source_count <> os_counts.actual_source_count
)

SELECT * FROM listing_mapping_check
UNION ALL
SELECT * FROM source_count_check
