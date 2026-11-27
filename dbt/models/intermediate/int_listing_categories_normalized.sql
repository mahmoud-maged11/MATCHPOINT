WITH expanded AS (
    SELECT
        sl.source_listing_id,
        sl.source_name,
        {{ clean_text('elem.raw_category') }} AS category_raw,
        {{ normalize_lookup_key('elem.raw_category') }} AS category_lookup_key,
        elem.elem_pos
    FROM {{ ref('stg_bronze__source_listings') }} sl
    CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS_TEXT(
        CASE
            WHEN JSONB_TYPEOF(sl.categories) = 'array'
                THEN sl.categories
            ELSE '[]'::JSONB
        END
    ) WITH ORDINALITY AS elem(raw_category, elem_pos)
    WHERE {{ clean_text('elem.raw_category') }} IS NOT NULL
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

ranked AS (
    SELECT
        k.*,
        ROW_NUMBER() OVER (
            PARTITION BY k.source_listing_id, k.category_key
            ORDER BY k.elem_pos ASC
        ) AS rn
    FROM keyed k
),

aggregated AS (
    SELECT
        source_listing_id,
        category_key,
        JSONB_AGG(
            DISTINCT category_raw
            ORDER BY category_raw
        ) AS observed_raw_categories
    FROM keyed
    GROUP BY
        source_listing_id,
        category_key
)

SELECT
    {{ deterministic_sha256_key(["r.source_listing_id", "r.category_key"]) }} AS listing_category_id,
    r.source_listing_id,
    r.source_name,
    r.category_key,
    r.category_name,
    r.category_raw,
    a.observed_raw_categories
FROM ranked r
INNER JOIN aggregated a
    ON r.source_listing_id = a.source_listing_id
   AND r.category_key = a.category_key
WHERE r.rn = 1
