SELECT
    location_key,
    MIN(location_display) AS location_display,
    MIN(standardized_city) AS standardized_city,
    MIN(standardized_governorate) AS standardized_governorate,
    MIN(standardized_country) AS standardized_country,
    MIN(country_code) AS country_code,
    BOOL_OR(is_online_location_label) AS is_online_location_label,
    BOOL_OR(is_location_standardized) AS is_standardized_mapping,
    JSONB_AGG(DISTINCT location_raw ORDER BY location_raw)
        FILTER (WHERE location_raw IS NOT NULL) AS observed_raw_locations,
    COUNT(*) AS source_listing_count

FROM {{ ref('silver_source_listings') }}
WHERE location_key IS NOT NULL
GROUP BY location_key
