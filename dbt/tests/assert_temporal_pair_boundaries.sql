WITH cases AS (
    SELECT *
    FROM (VALUES

        ('exact_boundary',
         '2026-01-01 00:00:00+00', '2026-01-01', 'exact',
         '2026-02-15 00:00:00+00', '2026-02-15', 'exact',
         45, TRUE),

        ('exact_over_boundary',
         '2026-01-01 00:00:00+00', '2026-01-01', 'exact',
         '2026-02-15 00:00:00.000001+00', '2026-02-15', 'exact',
         45, FALSE),

        ('date_only_boundary',
         NULL, '2026-01-01', 'date_only',
         NULL, '2026-02-15', 'date_only',
         45, TRUE),

        ('date_only_over_boundary',
         NULL, '2026-01-01', 'date_only',
         NULL, '2026-02-16', 'date_only',
         45, FALSE),

        ('deadline_boundary',
         NULL, '2026-01-01', 'date_only',
         NULL, '2026-01-15', 'date_only',
         14, TRUE),

        ('deadline_over_boundary',
         NULL, '2026-01-01', 'date_only',
         NULL, '2026-01-16', 'date_only',
         14, FALSE),

        ('mixed_boundary',
         '2026-01-01 23:59:59+00', '2026-01-01', 'exact',
         NULL, '2026-02-15', 'date_only',
         45, TRUE),

        ('mixed_over_boundary',
         '2026-01-01 23:59:59+00', '2026-01-01', 'exact',
         NULL, '2026-02-16', 'date_only',
         45, FALSE),

        ('equivalent_timezone',
         '2026-01-02 01:00:00+02', '2026-01-01', 'exact',
         '2026-01-01 23:00:00+00', '2026-01-01', 'exact',
         0, TRUE),

        ('relative_calendar',
         NULL, '2026-01-01', 'relative',
         NULL, '2026-01-01', 'date_only',
         45, FALSE),

        ('unknown_calendar',
         NULL, '2026-01-01', 'unknown',
         NULL, '2026-01-01', 'date_only',
         45, FALSE),

        ('missing_precision',
         NULL, '2026-01-01', NULL,
         NULL, '2026-01-01', 'date_only',
         45, FALSE),

        ('missing_calendar',
         NULL, NULL, 'date_only',
         NULL, '2026-01-01', 'date_only',
         45, FALSE),

        ('infinite_exact',
         'infinity', '2026-01-01', 'exact',
         '2026-01-01 00:00:00+00', '2026-01-01', 'exact',
         45, FALSE),

        ('negative_infinite_exact',
         '-infinity', '2026-01-01', 'exact',
         NULL, '2026-01-01', 'date_only',
         45, FALSE),

        ('infinite_calendar',
         NULL, 'infinity', 'date_only',
         NULL, '2026-01-01', 'date_only',
         45, FALSE),

        ('inconsistent_exact_calendar',
         '2026-01-01 00:00:00+00', '2026-01-02', 'exact',
         NULL, '2026-01-02', 'date_only',
         45, FALSE),

        ('missing_exact_timestamp',
         NULL, '2026-01-01', 'exact',
         NULL, '2026-01-01', 'date_only',
         45, FALSE),

        ('minimum_supported_date',
         NULL, '0001-01-01', 'date_only',
         NULL, '0001-01-01', 'date_only',
         0, TRUE),

        ('maximum_supported_date',
         NULL, '9999-12-31', 'date_only',
         NULL, '9999-12-31', 'date_only',
         0, TRUE),

        ('unsupported_future_calendar',
         NULL, '10000-01-01', 'date_only',
         NULL, '10000-01-01', 'date_only',
         0, FALSE),

        ('unsupported_bc_calendar',
         NULL, '0001-01-01 BC', 'date_only',
         NULL, '0001-01-01 BC', 'date_only',
         0, FALSE),

        ('unsupported_exact_year',
         '10000-01-01 00:00:00+00',
         '10000-01-01', 'exact',
         NULL, '9999-12-31', 'date_only',
         45, FALSE),

        ('legacy_date_only_timestamp',
         '2026-01-01 00:00:00+00', '2026-01-01', 'date_only',
         NULL, '2026-02-15', 'date_only',
         45, TRUE)

    ) AS v(
        case_name,
        left_ts,
        left_day,
        left_precision,
        right_ts,
        right_day,
        right_precision,
        max_days,
        expected
    )
),

typed AS (
    SELECT
        case_name,
        left_ts::TIMESTAMPTZ AS left_ts,
        left_day::DATE AS left_day,
        left_precision,
        right_ts::TIMESTAMPTZ AS right_ts,
        right_day::DATE AS right_day,
        right_precision,
        max_days,
        expected
    FROM cases
),

evaluated AS (
    SELECT
        *,
        {{ temporal_pair_within_window(
            'left_ts', 'left_day', 'left_precision',
            'right_ts', 'right_day', 'right_precision',
            'max_days'
        ) }} AS actual_forward,

        {{ temporal_pair_within_window(
            'right_ts', 'right_day', 'right_precision',
            'left_ts', 'left_day', 'left_precision',
            'max_days'
        ) }} AS actual_reverse
    FROM typed
)

SELECT *
FROM evaluated
WHERE actual_forward IS DISTINCT FROM expected
   OR actual_reverse IS DISTINCT FROM expected
