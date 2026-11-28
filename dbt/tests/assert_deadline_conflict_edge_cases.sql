WITH test_cases (
    case_name,
    timestamp_value,
    calendar_value,
    precision_value,
    expected_conflict
) AS (

    VALUES

    -- Identical date-only deadlines.
    ('same_date_only', NULL::TIMESTAMPTZ, DATE '2026-12-01', 'date_only', FALSE),
    ('same_date_only', NULL, DATE '2026-12-01', 'date_only', FALSE),

    -- Different date-only deadlines.
    ('different_date_only', NULL, DATE '2026-12-01', 'date_only', TRUE),
    ('different_date_only', NULL, DATE '2026-12-15', 'date_only', TRUE),

    -- Same calendar day but different exact timestamps.
    ('different_exact_times', TIMESTAMPTZ '2026-12-01 10:00+00', DATE '2026-12-01', 'exact', TRUE),
    ('different_exact_times', TIMESTAMPTZ '2026-12-01 15:00+00', DATE '2026-12-01', 'exact', TRUE),

    -- Equivalent exact instants with different timezone offsets.
    ('equivalent_exact_instants', TIMESTAMPTZ '2026-12-01 10:00+00', DATE '2026-12-01', 'exact', FALSE),
    ('equivalent_exact_instants', TIMESTAMPTZ '2026-12-01 12:00+02', DATE '2026-12-01', 'exact', FALSE),

    -- Different precision does not imply conflict.
    ('same_day_mixed_precision', NULL, DATE '2026-12-01', 'date_only', FALSE),
    ('same_day_mixed_precision', TIMESTAMPTZ '2026-12-01 15:00+00', DATE '2026-12-01', 'exact', FALSE),

    -- Different calendar days imply conflict.
    ('different_day_mixed_precision', NULL, DATE '2026-12-01', 'date_only', TRUE),
    ('different_day_mixed_precision', TIMESTAMPTZ '2026-12-15 15:00+00', DATE '2026-12-15', 'exact', TRUE),

    -- Unknown evidence cannot contradict a valid date.
    ('unknown_and_valid', NULL, NULL, 'unknown', FALSE),
    ('unknown_and_valid', NULL, DATE '2026-12-01', 'date_only', FALSE),

    -- Invalid exact evidence cannot contradict a valid date.
    ('invalid_exact_and_valid', TIMESTAMPTZ 'infinity', NULL, 'exact', FALSE),
    ('invalid_exact_and_valid', NULL, DATE '2026-12-01', 'date_only', FALSE),

    -- All dates missing.
    ('all_missing', NULL, NULL, NULL, FALSE),
    ('all_missing', NULL, NULL, 'unknown', FALSE),

    -- Relative evidence must not create conflicts.
    ('relative_and_valid', TIMESTAMPTZ '2026-12-15 10:00+00', DATE '2026-12-15', 'relative', FALSE),
    ('relative_and_valid', NULL, DATE '2026-12-01', 'date_only', FALSE)

),

evaluated AS (

    SELECT
        case_name,

        BOOL_OR(expected_conflict) AS expected_conflict,

        {{ has_deadline_conflict(
            'timestamp_value',
            'calendar_value',
            'precision_value'
        ) }} AS actual_conflict

    FROM test_cases

    GROUP BY case_name

)

SELECT *
FROM evaluated
WHERE actual_conflict IS DISTINCT FROM expected_conflict
