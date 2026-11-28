-- Validate source-level calendar dates and lifecycle semantics.
-- Use the recorded evaluation timestamp, not the test execution time.

WITH expected_dates AS (

    SELECT
        sl.*,

        {{ reliable_calendar_date(
            'published_at',
            'published_at_raw',
            'published_at_precision'
        ) }} AS expected_published_date,

        {{ reliable_calendar_date(
            'deadline',
            'deadline_raw',
            'deadline_precision'
        ) }} AS expected_deadline_date

    FROM {{ ref('silver_source_listings') }} sl

),

expiration AS (

    SELECT
        *,

        CASE
            WHEN expected_deadline_date IS NULL
            THEN FALSE

            WHEN deadline_precision = 'exact'
            THEN COALESCE(
                deadline < lifecycle_evaluated_at,
                FALSE
            )

            WHEN deadline_precision = 'date_only'
            THEN COALESCE(
                lifecycle_evaluated_at >
                (
                    (
                        expected_deadline_date::TIMESTAMP
                        + INTERVAL '36 hours'
                    ) AT TIME ZONE 'UTC'
                ),
                FALSE
            )

            ELSE FALSE
        END AS expected_has_expired

    FROM expected_dates

),

expected AS (

    SELECT
        *,

        CASE
            WHEN observed_status IN ('closed', 'expired')
            THEN observed_status

            WHEN expected_has_expired
            THEN 'expired'

            ELSE observed_status
        END AS expected_status,

        CASE
            WHEN observed_status IN ('closed', 'expired')
            THEN 'observed_source_status'

            WHEN expected_has_expired
                 AND deadline_precision = 'exact'
            THEN 'exact_deadline_passed'

            WHEN expected_has_expired
                 AND deadline_precision = 'date_only'
            THEN 'date_only_deadline_passed_conservative'

            ELSE 'observed_source_status_retained'
        END AS expected_reason

    FROM expiration

)

SELECT
    source_listing_id,
    source_name,
    observed_status,
    deadline,
    deadline_raw,
    deadline_precision,
    deadline_calendar_date,
    expected_deadline_date,
    effective_status,
    expected_status,
    effective_status_reason,
    expected_reason,
    lifecycle_evaluated_at

FROM expected

WHERE published_calendar_date
          IS DISTINCT FROM expected_published_date

   OR deadline_calendar_date
          IS DISTINCT FROM expected_deadline_date

   OR is_deadline_reliable
          IS DISTINCT FROM (expected_deadline_date IS NOT NULL)

   OR effective_status
          IS DISTINCT FROM expected_status

   OR effective_status_reason
          IS DISTINCT FROM expected_reason

   OR lifecycle_evaluated_at IS NULL
