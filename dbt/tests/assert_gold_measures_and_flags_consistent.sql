-- Fails if fct_opportunities violates internal flag, salary midpoint, or date precision invariants:
-- 1. Exactly one lifecycle flag (is_active, is_expired, is_closed, is_unknown_status) must be TRUE.
-- 2. salary_midpoint must be NULL unless both salary_min and salary_max are present, and within [min, max].
-- 3. is_multi_source must equal (source_count > 1).
-- 4. published_date_key must be NULL unless published_at is present with exact/date_only precision.

SELECT
    opportunity_id,
    effective_status,
    source_count,
    is_multi_source,
    salary_min,
    salary_max,
    salary_midpoint,
    published_at,
    published_at_precision,
    published_date_key
FROM {{ ref('fct_opportunities') }}
WHERE
    (
        (CASE WHEN is_active THEN 1 ELSE 0 END)
        + (CASE WHEN is_expired THEN 1 ELSE 0 END)
        + (CASE WHEN is_closed THEN 1 ELSE 0 END)
        + (CASE WHEN is_unknown_status THEN 1 ELSE 0 END)
    ) <> 1
    OR is_multi_source <> (source_count > 1)
    OR ((salary_min IS NULL OR salary_max IS NULL) AND salary_midpoint IS NOT NULL)
    OR (
        salary_min IS NOT NULL
        AND salary_max IS NOT NULL
        AND (salary_midpoint IS NULL OR salary_midpoint < salary_min OR salary_midpoint > salary_max)
    )
    OR (
        (published_at IS NULL OR published_at_precision NOT IN ('exact', 'date_only'))
        AND published_date_key IS NOT NULL
    )
    OR (
        published_at IS NOT NULL
        AND published_at_precision IN ('exact', 'date_only')
        AND published_date_key IS NULL
    )
