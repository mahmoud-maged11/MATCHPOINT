WITH listing_categories AS (
    SELECT *
    FROM {{ ref('int_listing_categories_normalized') }}
),

category_summary AS (
    SELECT
        category_key,
        MIN(category_name) AS category_name,
        COUNT(DISTINCT source_listing_id) AS source_listing_count
    FROM listing_categories
    GROUP BY category_key
),

raw_category_summary AS (
    SELECT
        lc.category_key,
        JSONB_AGG(
            DISTINCT raw.category_raw
            ORDER BY raw.category_raw
        ) AS observed_raw_categories
    FROM listing_categories lc
    CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS_TEXT(
        lc.observed_raw_categories
    ) AS raw(category_raw)
    GROUP BY lc.category_key
)

SELECT
    c.category_key,
    c.category_name,
    r.observed_raw_categories,
    c.source_listing_count
FROM category_summary c
INNER JOIN raw_category_summary r
    ON c.category_key = r.category_key
