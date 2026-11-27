-- Fails if Bronze-to-Silver source attribution is broken:
-- 1. Any bronze.source_listings row missing from silver_source_listings.
-- 2. Any silver_source_listings row missing from bronze.source_listings.
-- 3. Any mismatch in source_name, source_opportunity_id, source_identity_key, or source_url.

WITH bronze_listings AS (
    SELECT
        source_listing_id,
        BTRIM(source_name) AS source_name,
        BTRIM(source_opportunity_id) AS source_opportunity_id,
        BTRIM(source_identity_key) AS source_identity_key,
        BTRIM(source_url) AS source_url
    FROM {{ source('bronze', 'source_listings') }}
),

silver_listings AS (
    SELECT
        source_listing_id,
        source_name,
        source_opportunity_id,
        source_identity_key,
        source_url
    FROM {{ ref('silver_source_listings') }}
)

SELECT
    COALESCE(b.source_listing_id, s.source_listing_id) AS source_listing_id,
    b.source_name AS bronze_source_name,
    s.source_name AS silver_source_name,
    b.source_identity_key AS bronze_identity_key,
    s.source_identity_key AS silver_identity_key,
    b.source_url AS bronze_source_url,
    s.source_url AS silver_source_url
FROM bronze_listings b
FULL OUTER JOIN silver_listings s
    ON b.source_listing_id = s.source_listing_id
WHERE b.source_listing_id IS NULL
   OR s.source_listing_id IS NULL
   OR b.source_name IS DISTINCT FROM s.source_name
   OR b.source_opportunity_id IS DISTINCT FROM s.source_opportunity_id
   OR b.source_identity_key IS DISTINCT FROM s.source_identity_key
   OR b.source_url IS DISTINCT FROM s.source_url
