WITH expanded AS (
    SELECT DISTINCT
        sl.source_listing_id,
        sl.source_name,
        LOWER(BTRIM(elem.raw_employment_type)) AS employment_type
    FROM {{ ref('silver_source_listings') }} sl
    CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS_TEXT(sl.employment_types) AS elem(raw_employment_type)
    WHERE sl.employment_types IS NOT NULL
      AND JSONB_TYPEOF(sl.employment_types) = 'array'
      AND JSONB_ARRAY_LENGTH(sl.employment_types) > 0
      AND NULLIF(BTRIM(elem.raw_employment_type), '') IS NOT NULL
)

SELECT
    {{ deterministic_sha256_key(["source_listing_id", "employment_type"]) }} AS listing_employment_type_id,
    source_listing_id,
    source_name,
    employment_type
FROM expanded
