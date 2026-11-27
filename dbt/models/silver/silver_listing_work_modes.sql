WITH expanded AS (
    SELECT DISTINCT
        sl.source_listing_id,
        sl.source_name,
        LOWER(BTRIM(elem.raw_work_mode)) AS work_mode
    FROM {{ ref('silver_source_listings') }} sl
    CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS_TEXT(sl.work_modes) AS elem(raw_work_mode)
    WHERE sl.work_modes IS NOT NULL
      AND JSONB_TYPEOF(sl.work_modes) = 'array'
      AND JSONB_ARRAY_LENGTH(sl.work_modes) > 0
      AND NULLIF(BTRIM(elem.raw_work_mode), '') IS NOT NULL
)

SELECT
    {{ deterministic_sha256_key(["source_listing_id", "work_mode"]) }} AS listing_work_mode_id,
    source_listing_id,
    source_name,
    work_mode
FROM expanded
