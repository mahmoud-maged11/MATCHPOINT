WITH members AS (

    SELECT
        os.opportunity_id,
        sl.deadline,
        sl.deadline_precision,
        sl.deadline_calendar_date

    FROM {{ ref('silver_opportunity_sources') }} os

    INNER JOIN {{ ref('silver_source_listings') }} sl
        ON os.source_listing_id = sl.source_listing_id

),

expected AS (

    SELECT
        opportunity_id,

        (
            MIN(deadline_calendar_date)
                <> MAX(deadline_calendar_date)

            OR

            MIN(deadline) FILTER (
                WHERE deadline_precision = 'exact'
                  AND deadline_calendar_date IS NOT NULL
            )
            <>
            MAX(deadline) FILTER (
                WHERE deadline_precision = 'exact'
                  AND deadline_calendar_date IS NOT NULL
            )

        ) AS expected_conflict

    FROM members

    GROUP BY opportunity_id

)

SELECT
    a.opportunity_id,
    a.conflicting_attributes,

    COALESCE(
        e.expected_conflict,
        FALSE
    ) AS expected_deadline_conflict

FROM {{ ref('silver_opportunities') }} a

LEFT JOIN expected e
    USING (opportunity_id)

WHERE (a.conflicting_attributes ? 'deadline')
    IS DISTINCT FROM
    COALESCE(e.expected_conflict, FALSE)
