WITH expanded AS (
    SELECT
        sl.source_listing_id,
        sl.source_name,
        {{ clean_text('elem.raw_category') }} AS category_raw,
        {{ normalize_lookup_key('elem.raw_category') }} AS category_lookup_key,
        elem.elem_pos
    FROM {{ ref('stg_bronze__source_listings') }} sl
    CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS_TEXT(sl.categories)
        WITH ORDINALITY AS elem(raw_category, elem_pos)
    WHERE sl.categories IS NOT NULL
      AND JSONB_TYPEOF(sl.categories) = 'array'
      AND JSONB_ARRAY_LENGTH(sl.categories) > 0
      AND {{ clean_text('elem.raw_category') }} IS NOT NULL
),

keyed AS (
    SELECT
        ex.source_listing_id,
        ex.source_name,
        ex.category_raw,
        ex.category_raw AS category_name,
        {{ deterministic_sha256_key(["'category'", "ex.category_lookup_key"]) }} AS category_key,
        ex.elem_pos
    FROM expanded ex
),

deduplicated AS (
    SELECT
        k.*,
        ROW_NUMBER() OVER (
            PARTITION BY k.source_listing_id, k.category_key
            ORDER BY k.elem_pos ASC
        ) AS rn
    FROM keyed k
)

SELECT
    {{ deterministic_sha256_key(["source_listing_id", "category_key"]) }} AS listing_category_id,
    source_listing_id,
    source_name,
    category_key,
    category_name,
    category_raw
FROM deduplicated
WHERE rn = 1
