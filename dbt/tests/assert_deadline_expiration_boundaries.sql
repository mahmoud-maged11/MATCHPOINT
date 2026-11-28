WITH test_cases (
    case_name,
    timestamp_value,
    calendar_value,
    precision_value,
    evaluated_at,
    expected_expired
) AS (

    VALUES

    (
        'exact_before_deadline',
        TIMESTAMPTZ '2026-11-27 12:00:00+00',
        DATE '2026-11-27',
        'exact',
        TIMESTAMPTZ '2026-11-27 11:59:59.999999+00',
        FALSE
    ),
    (
        'exact_at_deadline',
        TIMESTAMPTZ '2026-11-27 12:00:00+00',
        DATE '2026-11-27',
        'exact',
        TIMESTAMPTZ '2026-11-27 12:00:00+00',
        FALSE
    ),
    (
        'exact_after_deadline',
        TIMESTAMPTZ '2026-11-27 12:00:00+00',
        DATE '2026-11-27',
        'exact',
        TIMESTAMPTZ '2026-11-27 12:00:00.000001+00',
        TRUE
    ),
    (
        'date_only_before_threshold',
        NULL,
        DATE '2026-11-27',
        'date_only',
        TIMESTAMPTZ '2026-11-28 11:59:59.999999+00',
        FALSE
    ),
    (
        'date_only_at_threshold',
        NULL,
        DATE '2026-11-27',
        'date_only',
        TIMESTAMPTZ '2026-11-28 12:00:00+00',
        FALSE
    ),
    (
        'date_only_after_threshold',
        NULL,
        DATE '2026-11-27',
        'date_only',
        TIMESTAMPTZ '2026-11-28 12:00:00.000001+00',
        TRUE
    ),
    (
        'unreliable_exact',
        TIMESTAMPTZ '2020-01-01 00:00:00+00',
        NULL,
        'exact',
        TIMESTAMPTZ '2026-11-27 12:00:00+00',
        FALSE
    ),
    (
        'invalid_date_only',
        NULL,
        NULL,
        'date_only',
        TIMESTAMPTZ '2026-11-27 12:00:00+00',
        FALSE
    ),
    (
        'relative_never_expires',
        TIMESTAMPTZ '2020-01-01 00:00:00+00',
        DATE '2020-01-01',
        'relative',
        TIMESTAMPTZ '2026-11-27 12:00:00+00',
        FALSE
    ),
    (
        'unknown_never_expires',
        NULL,
        NULL,
        'unknown',
        TIMESTAMPTZ '2026-11-27 12:00:00+00',
        FALSE
    ),
    (
        'null_evaluation_time',
        NULL,
        DATE '2026-11-27',
        'date_only',
        NULL,
        FALSE
    ),
    (
        'maximum_calendar_date',
        NULL,
        DATE '9999-12-31',
        'date_only',
        TIMESTAMPTZ '2026-11-27 12:00:00+00',
        FALSE
    )

),

evaluated AS (

    SELECT
        *,
        {{ deadline_has_passed(
            'timestamp_value',
            'calendar_value',
            'precision_value',
            'evaluated_at'
        ) }} AS actual_expired

    FROM test_cases

)

SELECT *
FROM evaluated
WHERE actual_expired IS DISTINCT FROM expected_expired
