SELECT
    listing_category_id,
    source_listing_id,
    source_name,
    category_key,
    category_name,
    category_raw,
    observed_raw_categories
FROM {{ ref('int_listing_categories_normalized') }}
