WITH members AS (

    SELECT
        os.opportunity_id,
        os.is_primary_source,
        os.source_authority_rank,
        os.completeness_score,

        sl.source_listing_id,
        sl.source_identity_key,
        sl.first_seen_at,

        sl.published_at,
        sl.published_at_raw,
        sl.published_at_precision,
        sl.published_calendar_date,

        sl.deadline,
        sl.deadline_raw,
        sl.deadline_precision,
        sl.deadline_calendar_date,
        sl.is_deadline_reliable

    FROM {{ ref('silver_opportunity_sources') }} os

    INNER JOIN {{ ref('silver_source_listings') }} sl
        ON os.source_listing_id = sl.source_listing_id

),

expected_publication AS (

    SELECT DISTINCT ON (opportunity_id)
        opportunity_id,
        published_at,
        published_at_raw,
        published_at_precision,
        published_calendar_date

    FROM members

    WHERE published_at IS NOT NULL
       OR published_at_raw IS NOT NULL

    ORDER BY
        opportunity_id,

        CASE
            WHEN published_calendar_date IS NULL THEN 3
            WHEN published_at_precision = 'exact' THEN 1
            WHEN published_at_precision = 'date_only' THEN 2
            ELSE 3
        END,

        is_primary_source DESC,
        source_authority_rank ASC,
        completeness_score DESC,
        first_seen_at ASC,
        source_identity_key ASC,
        source_listing_id::TEXT ASC

),

expected_deadline AS (

    SELECT DISTINCT ON (opportunity_id)
        opportunity_id,
        deadline,
        deadline_raw,
        deadline_precision,
        deadline_calendar_date,
        is_deadline_reliable

    FROM members

    WHERE deadline IS NOT NULL
       OR deadline_raw IS NOT NULL

    ORDER BY
        opportunity_id,

        CASE
            WHEN deadline_calendar_date IS NULL THEN 3
            WHEN deadline_precision = 'exact' THEN 1
            WHEN deadline_precision = 'date_only' THEN 2
            ELSE 3
        END,

        is_primary_source DESC,
        source_authority_rank ASC,
        completeness_score DESC,
        first_seen_at ASC,
        source_identity_key ASC,
        source_listing_id::TEXT ASC

),

actual AS (

    SELECT *
    FROM {{ ref('silver_opportunities') }}

)

SELECT
    a.opportunity_id,
    'publication_bundle_mismatch' AS failure_reason

FROM actual a

LEFT JOIN expected_publication p
    USING (opportunity_id)

WHERE ROW(
    a.published_at,
    a.published_at_raw,
    a.published_at_precision,
    a.published_calendar_date
) IS DISTINCT FROM ROW(
    p.published_at,
    p.published_at_raw,
    p.published_at_precision,
    p.published_calendar_date
)

UNION ALL

SELECT
    a.opportunity_id,
    'deadline_bundle_mismatch'

FROM actual a

LEFT JOIN expected_deadline d
    USING (opportunity_id)

WHERE ROW(
    a.deadline,
    a.deadline_raw,
    a.deadline_precision,
    a.deadline_calendar_date,
    a.is_deadline_reliable
) IS DISTINCT FROM ROW(
    d.deadline,
    d.deadline_raw,
    d.deadline_precision,
    d.deadline_calendar_date,
    COALESCE(d.is_deadline_reliable, FALSE)
)
