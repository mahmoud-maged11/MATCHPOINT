-- Fails if fct_opportunities violates internal flag, salary midpoint, or date precision invariants:
-- 1. Exactly one lifecycle flag (is_active, is_expired, is_closed, is_unknown_status) must be TRUE.
-- 2. salary_midpoint must be NULL unless both salary_min and salary_max are present, and within [min, max].
-- 3. is_multi_source must equal (source_count > 1).
-- 4. Published and deadline date keys must match reliable calendar dates.

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
    published_date_key,
    deadline,
    deadline_precision,
    deadline_date_key
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
    OR published_date_key IS DISTINCT FROM
        CAST(
            TO_CHAR(
                {{ reliable_calendar_date(
                    'published_at',
                    'published_at_raw',
                    'published_at_precision'
                ) }},
                'YYYYMMDD'
            ) AS INTEGER
        )
    OR deadline_date_key IS DISTINCT FROM
        CAST(
            TO_CHAR(
                {{ reliable_calendar_date(
                    'deadline',
                    'deadline_raw',
                    'deadline_precision'
                ) }},
                'YYYYMMDD'
            ) AS INTEGER
        )
