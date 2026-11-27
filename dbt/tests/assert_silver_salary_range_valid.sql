-- Fails if any Silver listing violates Data Contract v3.0.0 salary bounds:
-- salary_min and salary_max must be non-negative, and salary_min <= salary_max when both exist.

SELECT
    source_listing_id,
    source_name,
    salary_min,
    salary_max
FROM {{ ref('silver_source_listings') }}
WHERE (salary_min IS NOT NULL AND salary_min < 0)
   OR (salary_max IS NOT NULL AND salary_max < 0)
   OR (salary_min IS NOT NULL AND salary_max IS NOT NULL AND salary_min > salary_max)
