WITH test_cases (
    case_name,
    timestamp_value,
    raw_value,
    precision_value,
    expected_date
) AS (

    VALUES

    (
        'exact_utc',
        TIMESTAMPTZ '2026-11-27 10:00:00+00',
        NULL::TEXT,
        'exact',
        DATE '2026-11-27'
    ),
    (
        'exact_timezone_previous_day',
        TIMESTAMPTZ '2026-11-27 01:00:00+02',
        NULL,
        'exact',
        DATE '2026-11-26'
    ),
    (
        'exact_timezone_next_day',
        TIMESTAMPTZ '2026-11-27 23:00:00-05',
        NULL,
        'exact',
        DATE '2026-11-28'
    ),
    (
        'date_only_without_timestamp',
        NULL,
        '2026-11-27',
        'date_only',
        DATE '2026-11-27'
    ),
    (
        'date_only_with_spaces',
        NULL,
        ' 2026-11-27 ',
        'date_only',
        DATE '2026-11-27'
    ),
    (
        'valid_leap_year',
        NULL,
        '2024-02-29',
        'date_only',
        DATE '2024-02-29'
    ),
    (
        'invalid_leap_year',
        NULL,
        '2025-02-29',
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
        'invalid_format',
        NULL,
        '27/11/2026',
        'date_only',
        NULL
    ),
    (
        'year_zero',
        NULL,
        '0000-01-01',
        'date_only',
        NULL
    ),
    (
        'minimum_supported_date',
        NULL,
        '0001-01-01',
        'date_only',
        DATE '0001-01-01'
    ),
    (
        'maximum_supported_date',
        NULL,
        '9999-12-31',
        'date_only',
        DATE '9999-12-31'
    ),
    (
        'exact_positive_infinity',
        TIMESTAMPTZ 'infinity',
        NULL,
        'exact',
        NULL
    ),
    (
        'exact_negative_infinity',
        TIMESTAMPTZ '-infinity',
        NULL,
        'exact',
        NULL
    ),
    (
        'exact_outside_supported_range',
        TIMESTAMPTZ '10000-01-01 00:00:00+00',
        NULL,
        'exact',
        NULL
    ),
    (
        'exact_null_timestamp',
        NULL,
        '2026-11-27',
        'exact',
        NULL
    ),
    (
        'relative_timestamp',
        TIMESTAMPTZ '2026-11-27 00:00:00+00',
        'Yesterday',
        'relative',
        NULL
    ),
    (
        'unknown_precision',
        NULL,
        '2026-11-27',
        'unknown',
        NULL
    ),
    (
        'null_precision',
        NULL,
        '2026-11-27',
        NULL,
        NULL
    ),
    (
        'null_raw_date',
        NULL,
        NULL,
        'date_only',
        NULL
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
