WITH members AS (
    SELECT *
    FROM (VALUES

        ('date_boundary', NULL, '2026-01-01', 'date_only', 45, FALSE),
        ('date_boundary', NULL, '2026-02-15', 'date_only', 45, FALSE),

        ('date_over', NULL, '2026-01-01', 'date_only', 45, TRUE),
        ('date_over', NULL, '2026-02-16', 'date_only', 45, TRUE),

        ('transitive_publication', NULL, '2026-01-01', 'date_only', 45, TRUE),
        ('transitive_publication', NULL, '2026-02-01', 'date_only', 45, TRUE),
        ('transitive_publication', NULL, '2026-03-01', 'date_only', 45, TRUE),

        ('deadline_boundary', NULL, '2026-01-01', 'date_only', 14, FALSE),
        ('deadline_boundary', NULL, '2026-01-15', 'date_only', 14, FALSE),

        ('deadline_over', NULL, '2026-01-01', 'date_only', 14, TRUE),
        ('deadline_over', NULL, '2026-01-15', 'date_only', 14, TRUE),
        ('deadline_over', NULL, '2026-01-16', 'date_only', 14, TRUE),

        ('mixed_exact_over',
         '2026-01-01 00:00:00+00', '2026-01-01', 'exact', 45, TRUE),

        ('mixed_exact_over',
         NULL, '2026-01-20', 'date_only', 45, TRUE),

        ('mixed_exact_over',
         '2026-02-15 00:00:00.000001+00', '2026-02-15', 'exact', 45, TRUE),

        ('relative_outlier', NULL, '2026-01-01', 'date_only', 45, FALSE),
        ('relative_outlier', NULL, '2026-12-31', 'relative', 45, FALSE),

        ('singleton', NULL, '2026-01-01', 'date_only', 45, FALSE),

        ('all_missing', NULL, NULL, NULL, 45, FALSE),
        ('all_missing', NULL, NULL, 'unknown', 45, FALSE),

        ('infinite_outlier',
         'infinity', '2026-12-31', 'exact', 45, FALSE),

        ('infinite_outlier',
         '2026-01-01 00:00:00+00', '2026-01-01', 'exact', 45, FALSE),

        ('infinite_calendar', NULL, 'infinity', 'date_only', 45, FALSE),
        ('infinite_calendar', NULL, '2026-01-01', 'date_only', 45, FALSE),

        ('unsupported_future_outlier',
         NULL, '10000-01-01', 'date_only', 45, FALSE),

        ('unsupported_future_outlier',
         NULL, '2026-01-01', 'date_only', 45, FALSE),

        ('unsupported_bc_outlier',
         NULL, '0001-01-01 BC', 'date_only', 45, FALSE),

        ('unsupported_bc_outlier',
         NULL, '2026-01-01', 'date_only', 45, FALSE),

        ('mixed_valid',
         '2026-01-01 00:00:00+00', '2026-01-01', 'exact', 45, FALSE),

        ('mixed_valid',
         NULL, '2026-01-20', 'date_only', 45, FALSE),

        ('mixed_valid',
         '2026-02-15 00:00:00+00', '2026-02-15', 'exact', 45, FALSE)

    ) AS v(
        case_name,
        timestamp_value,
        calendar_value,
        precision_value,
        max_days,
        expected
    )
),

typed AS (
    SELECT
        case_name,
        timestamp_value::TIMESTAMPTZ AS timestamp_value,
        calendar_value::DATE AS calendar_value,
        precision_value,
        max_days,
        expected
    FROM members
),

evaluated AS (
    SELECT
        case_name,
        max_days,
        expected,

        {{ temporal_component_exceeds_window(
            'timestamp_value',
            'calendar_value',
            'precision_value',
            'max_days'
        ) }} AS actual

    FROM typed
    GROUP BY case_name, max_days, expected
)

SELECT *
FROM evaluated
WHERE actual IS DISTINCT FROM expected
