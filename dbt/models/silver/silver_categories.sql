SELECT
    category_key,
    MIN(category_name) AS category_name,
    JSONB_AGG(DISTINCT category_raw ORDER BY category_raw) AS observed_raw_categories,
    COUNT(DISTINCT source_listing_id) AS source_listing_count

FROM {{ ref('int_listing_categories_normalized') }}
GROUP BY category_key
