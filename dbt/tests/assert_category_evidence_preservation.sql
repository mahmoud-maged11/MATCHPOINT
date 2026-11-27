-- Validate category evidence preservation across Intermediate and Silver.
-- Returns zero rows on success.

WITH cleaned_source AS (
    SELECT
        sl.source_listing_id,
        {{ clean_text('elem.raw_category') }} AS category_raw,
        {{ normalize_lookup_key('elem.raw_category') }} AS category_lookup_key
    FROM {{ ref('stg_bronze__source_listings') }} sl
    CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS_TEXT(
        CASE
            WHEN JSONB_TYPEOF(sl.categories) = 'array'
                THEN sl.categories
            ELSE '[]'::JSONB
        END
    ) AS elem(raw_category)
    WHERE {{ clean_text('elem.raw_category') }} IS NOT NULL
),

expected_raw AS (
    SELECT DISTINCT
        source_listing_id,
        {{ deterministic_sha256_key(["'category'", "category_lookup_key"]) }} AS category_key,
        category_raw
    FROM cleaned_source
),

actual_raw AS (
    SELECT
        lc.source_listing_id,
        lc.category_key,
        raw.category_raw
    FROM {{ ref('int_listing_categories_normalized') }} lc
    CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS_TEXT(
        lc.observed_raw_categories
    ) AS raw(category_raw)
),

missing_evidence AS (
    SELECT * FROM expected_raw
    EXCEPT ALL
    SELECT * FROM actual_raw
),

unexpected_evidence AS (
    SELECT * FROM actual_raw
    EXCEPT ALL
    SELECT * FROM expected_raw
),

duplicate_categories AS (
    SELECT
        source_listing_id,
        category_key
    FROM {{ ref('int_listing_categories_normalized') }}
    GROUP BY source_listing_id, category_key
    HAVING COUNT(*) > 1
),

invalid_representative AS (
    SELECT
        listing_category_id,
        category_raw
    FROM {{ ref('int_listing_categories_normalized') }}
    WHERE (
        observed_raw_categories ? category_raw
    ) IS DISTINCT FROM TRUE
),

intermediate_rows AS (
    SELECT
        listing_category_id,
        source_listing_id,
        source_name,
        category_key,
        category_name,
        category_raw,
        observed_raw_categories
    FROM {{ ref('int_listing_categories_normalized') }}
),

silver_rows AS (
    SELECT
        listing_category_id,
        source_listing_id,
        source_name,
        category_key,
        category_name,
        category_raw,
        observed_raw_categories
    FROM {{ ref('silver_listing_categories') }}
),

missing_silver AS (
    SELECT * FROM intermediate_rows
    EXCEPT ALL
    SELECT * FROM silver_rows
),

unexpected_silver AS (
    SELECT * FROM silver_rows
    EXCEPT ALL
    SELECT * FROM intermediate_rows
),

expected_summary AS (
    SELECT
        category_key,
        COUNT(DISTINCT source_listing_id) AS source_listing_count,
        JSONB_AGG(
            DISTINCT category_raw
            ORDER BY category_raw
        ) AS observed_raw_categories
    FROM expected_raw
    GROUP BY category_key
),

summary_mismatch AS (
    SELECT
        COALESCE(e.category_key, s.category_key) AS category_key
    FROM expected_summary e
    FULL OUTER JOIN {{ ref('silver_categories') }} s
        ON e.category_key = s.category_key
    WHERE e.category_key IS NULL
       OR s.category_key IS NULL
       OR e.source_listing_count
          IS DISTINCT FROM s.source_listing_count
       OR e.observed_raw_categories
          IS DISTINCT FROM s.observed_raw_categories
)

SELECT
    'missing_raw_evidence' AS failure_type,
    source_listing_id::TEXT AS record_id,
    category_raw AS details
FROM missing_evidence

UNION ALL

SELECT
    'unexpected_raw_evidence',
    source_listing_id::TEXT,
    category_raw
FROM unexpected_evidence

UNION ALL

SELECT
    'duplicate_listing_category',
    source_listing_id::TEXT,
    category_key
FROM duplicate_categories

UNION ALL

SELECT
    'invalid_representative',
    listing_category_id::TEXT,
    category_raw
FROM invalid_representative

UNION ALL

SELECT
    'missing_silver_row',
    listing_category_id::TEXT,
    category_name
FROM missing_silver

UNION ALL

SELECT
    'unexpected_silver_row',
    listing_category_id::TEXT,
    category_name
FROM unexpected_silver

UNION ALL

SELECT
    'category_summary_mismatch',
    category_key,
    'Silver category evidence or aggregation mismatch'
FROM summary_mismatch
