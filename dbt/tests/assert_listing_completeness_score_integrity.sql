WITH expected AS (

    SELECT
        sl.source_listing_id,

        (
            NUM_NONNULLS(
                sl.organization,
                sl.description,
                sl.location_raw,
                sl.requirements,
                sl.salary_min,
                sl.deadline_calendar_date,
                sl.published_calendar_date
            )

            + COALESCE(
                (sl.work_modes_state = 'populated')::INTEGER,
                0
            )

            + COALESCE(
                (sl.employment_types_state = 'populated')::INTEGER,
                0
            )

            + COALESCE(
                (sl.required_skills_state = 'populated')::INTEGER,
                0
            )

        ) AS expected_score

    FROM {{ ref('silver_source_listings') }} sl

),

features AS (

    SELECT
        source_listing_id,
        COUNT(*) AS row_count,
        MIN(completeness_score) AS minimum_score,
        MAX(completeness_score) AS maximum_score

    FROM {{ ref('int_listing_match_features') }}

    GROUP BY source_listing_id

),

mappings AS (

    SELECT
        source_listing_id,
        COUNT(*) AS row_count,
        MIN(completeness_score) AS minimum_score,
        MAX(completeness_score) AS maximum_score

    FROM {{ ref('silver_opportunity_sources') }}

    GROUP BY source_listing_id

),

comparison AS (

    SELECT
        COALESCE(
            e.source_listing_id,
            f.source_listing_id,
            m.source_listing_id
        ) AS source_listing_id,

        e.expected_score,

        f.row_count AS feature_row_count,
        f.minimum_score AS feature_minimum_score,
        f.maximum_score AS feature_maximum_score,

        m.row_count AS mapping_row_count,
        m.minimum_score AS mapping_minimum_score,
        m.maximum_score AS mapping_maximum_score

    FROM expected e

    FULL OUTER JOIN features f
        ON e.source_listing_id = f.source_listing_id

    FULL OUTER JOIN mappings m
        ON COALESCE(
            e.source_listing_id,
            f.source_listing_id
        ) = m.source_listing_id

)

SELECT *

FROM comparison

WHERE expected_score IS NULL

   OR expected_score NOT BETWEEN 0 AND 10

   OR feature_row_count IS DISTINCT FROM 1

   OR mapping_row_count IS DISTINCT FROM 1

   OR feature_minimum_score IS DISTINCT FROM expected_score

   OR feature_maximum_score IS DISTINCT FROM expected_score

   OR mapping_minimum_score IS DISTINCT FROM expected_score

   OR mapping_maximum_score IS DISTINCT FROM expected_score
