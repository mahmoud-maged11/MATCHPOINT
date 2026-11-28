{{
    config(
        indexes=[
            {'columns': ['date_key'], 'unique': True},
            {'columns': ['calendar_date'], 'unique': True}
        ]
    )
}}

-- Bounded calendar dimension protecting against extreme outlier dates (e.g. 1970-01-01, 2099-12-31, 9999-12-31)
-- while preserving 100% FK resolvability by unioning all genuinely observed fact dates outside the spine.

WITH standard_bounds AS (
    SELECT
        DATE '2020-01-01' AS spine_start,
        ((CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::DATE + INTERVAL '5 years')::DATE AS spine_end
),

standard_spine AS (
    SELECT
        GENERATE_SERIES(spine_start, spine_end, INTERVAL '1 day')::DATE AS calendar_date
    FROM standard_bounds
),

observed_dates AS (
    SELECT published_calendar_date AS calendar_date
    FROM {{ ref('silver_opportunities') }}
    WHERE published_calendar_date IS NOT NULL

    UNION

    SELECT deadline_calendar_date AS calendar_date
    FROM {{ ref('silver_opportunities') }}
    WHERE deadline_calendar_date IS NOT NULL

    UNION

    SELECT (first_seen_at AT TIME ZONE 'UTC')::DATE AS calendar_date
    FROM {{ ref('fct_opportunities') }}

    UNION

    SELECT (last_seen_at AT TIME ZONE 'UTC')::DATE AS calendar_date
    FROM {{ ref('fct_opportunities') }}

    UNION

    SELECT (started_at AT TIME ZONE 'UTC')::DATE AS calendar_date
    FROM {{ ref('fct_collection_runs') }}
),

all_dates AS (
    SELECT calendar_date FROM standard_spine
    UNION
    SELECT calendar_date FROM observed_dates
)

SELECT
    CAST(TO_CHAR(a.calendar_date, 'YYYYMMDD') AS INTEGER) AS date_key,
    a.calendar_date,
    EXTRACT(YEAR FROM a.calendar_date)::INTEGER AS year,
    EXTRACT(QUARTER FROM a.calendar_date)::INTEGER AS quarter,
    EXTRACT(MONTH FROM a.calendar_date)::INTEGER AS month,
    BTRIM(TO_CHAR(a.calendar_date, 'Month')) AS month_name,
    EXTRACT(WEEK FROM a.calendar_date)::INTEGER AS week_of_year,
    EXTRACT(DAY FROM a.calendar_date)::INTEGER AS day_of_month,
    EXTRACT(ISODOW FROM a.calendar_date)::INTEGER AS iso_day_of_week,
    BTRIM(TO_CHAR(a.calendar_date, 'Day')) AS day_name,
    -- Egypt standard weekend: Friday (5) and Saturday (6) in ISO day-of-week
    (EXTRACT(ISODOW FROM a.calendar_date)::INTEGER IN (5, 6)) AS is_egypt_weekend,
    (a.calendar_date BETWEEN sb.spine_start AND sb.spine_end) AS is_within_standard_calendar_range

FROM all_dates a
CROSS JOIN standard_bounds sb
