WITH test_cases AS (

    SELECT *
    FROM (
        VALUES
            (
                'exact_utc',
                '2026-11-27T23:30:00Z'::TIMESTAMPTZ,
                NULL::TEXT,
                'exact',
                '2026-11-27'::DATE
            ),
            (
                'exact_timezone',
                '2026-11-27T01:00:00+02:00'::TIMESTAMPTZ,
                NULL,
                'exact',
                '2026-11-26'::DATE
            ),
            (
                'date_only',
                NULL,
                '2026-11-27',
                'date_only',
                '2026-11-27'::DATE
            ),
            (
                'valid_leap_day',
                NULL,
                '2024-02-29',
                'date_only',
                '2024-02-29'::DATE
            ),
            (
                'invalid_leap_day',
                NULL,
                '2026-02-29',
                'date_only',
                NULL
            ),
            (
                'invalid_month',
                NULL,
                '2026-13-01',
                'date_only',
                NULL
            ),
            (
                'invalid_day',
                NULL,
                '2026-04-31',
                'date_only',
                NULL
            ),
            (
                'extreme_date',
                NULL,
                '9999-12-31',
                'date_only',
                '9999-12-31'::DATE
            ),
            (
                'relative',
                '2026-11-27T12:00:00Z'::TIMESTAMPTZ,
                '2 hours ago',
                'relative',
                NULL
            ),
            (
                'unknown',
                NULL,
                'Unavailable',
                'unknown',
                NULL
            ),
            (
                'invalid_raw',
                NULL,
                'not a date',
                'date_only',
                NULL
            ),
            (
                'missing_raw',
                NULL,
                NULL,
                'date_only',
                NULL
            ),
            (
                'blank_raw',
                NULL,
                ' ',
                'date_only',
                NULL
            ),
            (
                'non_iso_date',
                NULL,
                '27/11/2026',
                'date_only',
                NULL
            ),
            (
                'infinity',
                NULL,
                'infinity',
                'date_only',
                NULL
            ),
            (
                'missing_date',
                NULL,
                NULL,
                NULL,
                NULL
            )
    ) AS cases (
        case_name,
        timestamp_value,
        raw_value,
        precision_value,
        expected_date
    )

),

evaluated AS (

    SELECT
        *,
        {{ reliable_calendar_date(
            'timestamp_value',
            'raw_value',
            'precision_value'
        ) }} AS actual_date

    FROM test_cases

)

SELECT *
FROM evaluated
WHERE actual_date IS DISTINCT FROM expected_date
