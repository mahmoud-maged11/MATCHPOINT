WITH bronze_listings AS (
    SELECT source_listing_id
    FROM {{ source('bronze', 'source_listings') }}
),

source_listings AS (
    SELECT source_listing_id
    FROM {{ ref('silver_source_listings') }}
),

mappings AS (
    SELECT
        source_listing_id,
        opportunity_id,
        is_primary_source
    FROM {{ ref('silver_opportunity_sources') }}
),

opportunities AS (
    SELECT
        opportunity_id,
        primary_source_listing_id,
        source_count
    FROM {{ ref('silver_opportunities') }}
),

missing_silver AS (
    SELECT source_listing_id
    FROM bronze_listings

    EXCEPT ALL

    SELECT source_listing_id
    FROM source_listings
),

unexpected_silver AS (
    SELECT source_listing_id
    FROM source_listings

    EXCEPT ALL

    SELECT source_listing_id
    FROM bronze_listings
),

missing_mapping AS (
    SELECT source_listing_id
    FROM source_listings

    EXCEPT ALL

    SELECT source_listing_id
    FROM mappings
),

unexpected_mapping AS (
    SELECT source_listing_id
    FROM mappings

    EXCEPT ALL

    SELECT source_listing_id
    FROM source_listings
),

mapping_summary AS (
    SELECT
        opportunity_id,
        COUNT(*) AS actual_source_count,
        COUNT(*) FILTER (
            WHERE is_primary_source IS TRUE
        ) AS primary_count
    FROM mappings
    GROUP BY opportunity_id
),

invalid_opportunities AS (
    SELECT
        COALESCE(
            o.opportunity_id,
            m.opportunity_id
        ) AS opportunity_id
    FROM opportunities o
    FULL OUTER JOIN mapping_summary m
        ON o.opportunity_id = m.opportunity_id
    WHERE o.opportunity_id IS NULL
       OR m.opportunity_id IS NULL
       OR m.primary_count IS DISTINCT FROM 1
       OR o.source_count
          IS DISTINCT FROM m.actual_source_count
),

invalid_primary AS (
    SELECT o.opportunity_id
    FROM opportunities o
    WHERE NOT EXISTS (
        SELECT 1
        FROM mappings m
        WHERE m.opportunity_id = o.opportunity_id
          AND m.source_listing_id =
              o.primary_source_listing_id
          AND m.is_primary_source IS TRUE
    )
),

duplicate_opportunities AS (
    SELECT opportunity_id
    FROM opportunities
    GROUP BY opportunity_id
    HAVING COUNT(*) > 1
)

SELECT
    'missing_silver_listing' AS failure_type,
    source_listing_id::TEXT AS record_id
FROM missing_silver

UNION ALL

SELECT
    'unexpected_silver_listing',
    source_listing_id::TEXT
FROM unexpected_silver

UNION ALL

SELECT
    'missing_source_mapping',
    source_listing_id::TEXT
FROM missing_mapping

UNION ALL

SELECT
    'unexpected_or_duplicate_mapping',
    source_listing_id::TEXT
FROM unexpected_mapping

UNION ALL

SELECT
    'invalid_opportunity_membership',
    opportunity_id::TEXT
FROM invalid_opportunities

UNION ALL

SELECT
    'invalid_primary_source',
    opportunity_id::TEXT
FROM invalid_primary

UNION ALL

SELECT
    'duplicate_opportunity',
    opportunity_id::TEXT
FROM duplicate_opportunities
