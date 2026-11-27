-- Fails if bronze.source_listing_history is not preserved 1-to-1 in silver_opportunity_history
-- or if opportunity_id attribution disagrees with silver_opportunity_sources.

WITH bronze_history AS (
    SELECT
        history_id,
        source_listing_id,
        content_version,
        content_hash
    FROM {{ source('bronze', 'source_listing_history') }}
),

silver_history AS (
    SELECT
        history_id,
        opportunity_id,
        source_listing_id,
        content_version,
        content_hash
    FROM {{ ref('silver_opportunity_history') }}
)

SELECT
    COALESCE(bh.history_id, sh.history_id) AS history_id,
    bh.source_listing_id AS bronze_listing_id,
    sh.source_listing_id AS silver_listing_id,
    sh.opportunity_id AS history_opportunity_id,
    os.opportunity_id AS mapped_opportunity_id
FROM bronze_history bh
FULL OUTER JOIN silver_history sh
    ON bh.history_id = sh.history_id
LEFT JOIN {{ ref('silver_opportunity_sources') }} os
    ON sh.source_listing_id = os.source_listing_id
WHERE bh.history_id IS NULL
   OR sh.history_id IS NULL
   OR bh.source_listing_id IS DISTINCT FROM sh.source_listing_id
   OR bh.content_version IS DISTINCT FROM sh.content_version
   OR bh.content_hash IS DISTINCT FROM sh.content_hash
   OR sh.opportunity_id IS DISTINCT FROM os.opportunity_id
