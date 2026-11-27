-- Fails if any Silver listing violates Data Contract v3.0.0 experience bounds:
-- experience_years_min and experience_years_max must be non-negative,
-- and experience_years_min <= experience_years_max when both exist.

SELECT
    source_listing_id,
    source_name,
    experience_years_min,
    experience_years_max
FROM {{ ref('silver_source_listings') }}
WHERE (experience_years_min IS NOT NULL AND experience_years_min < 0)
   OR (experience_years_max IS NOT NULL AND experience_years_max < 0)
   OR (
       experience_years_min IS NOT NULL
       AND experience_years_max IS NOT NULL
       AND experience_years_min > experience_years_max
   )
