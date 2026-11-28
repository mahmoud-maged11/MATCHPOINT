WITH expected AS (

    SELECT
        opportunity_id,

        published_at,
        published_at_raw,
        published_at_precision,
        published_calendar_date,

        deadline,
        deadline_raw,
        deadline_precision,
        deadline_calendar_date,
        is_deadline_reliable,

        (
            EXTRACT(YEAR FROM published_calendar_date)::INTEGER * 10000
            + EXTRACT(MONTH FROM published_calendar_date)::INTEGER * 100
            + EXTRACT(DAY FROM published_calendar_date)::INTEGER
        ) AS expected_published_key,

        (
            EXTRACT(YEAR FROM deadline_calendar_date)::INTEGER * 10000
            + EXTRACT(MONTH FROM deadline_calendar_date)::INTEGER * 100
            + EXTRACT(DAY FROM deadline_calendar_date)::INTEGER
        ) AS expected_deadline_key

    FROM {{ ref('silver_opportunities') }}

)

SELECT
    COALESCE(
        s.opportunity_id,
        g.opportunity_id
    ) AS opportunity_id,

    g.published_date_key,
    s.expected_published_key,

    g.deadline_date_key,
    s.expected_deadline_key

FROM expected s

FULL OUTER JOIN {{ ref('fct_opportunities') }} g
    USING (opportunity_id)

LEFT JOIN {{ ref('dim_dates') }} pd
    ON g.published_date_key = pd.date_key

LEFT JOIN {{ ref('dim_dates') }} dd
    ON g.deadline_date_key = dd.date_key

WHERE s.opportunity_id IS NULL

   OR g.opportunity_id IS NULL

   OR g.published_date_key
       IS DISTINCT FROM s.expected_published_key

   OR g.deadline_date_key
       IS DISTINCT FROM s.expected_deadline_key

   OR ROW(
       g.published_at,
       g.published_at_raw,
       g.published_at_precision,
       g.deadline,
       g.deadline_raw,
       g.deadline_precision,
       g.is_deadline_reliable
   ) IS DISTINCT FROM ROW(
       s.published_at,
       s.published_at_raw,
       s.published_at_precision,
       s.deadline,
       s.deadline_raw,
       s.deadline_precision,
       s.is_deadline_reliable
   )

   OR (
       g.published_date_key IS NOT NULL
       AND pd.date_key IS NULL
   )

   OR (
       g.deadline_date_key IS NOT NULL
       AND dd.date_key IS NULL
   )

   OR pd.calendar_date
       IS DISTINCT FROM s.published_calendar_date

   OR dd.calendar_date
       IS DISTINCT FROM s.deadline_calendar_date
