-- Exercise the production match pair macro.
-- Each scenario contains two isolated synthetic listings.
-- Returns zero rows on success.

WITH scenarios AS (

    SELECT *
    FROM (VALUES

        (1,  'direct_source_id',          1),
        (2,  'direct_normalized_url',     1),
        (3,  'cross_type_direct',         NULL),
        (4,  'shared_external_url',       2),
        (5,  'conflicting_organization',  NULL),
        (6,  'generic_portal_excluded',   NULL),
        (7,  'different_path_case',       NULL),
        (8,  'same_source',               NULL),
        (9,  'ambiguous_composite',       NULL),
        (10, 'compatible_composite',      3),
        (11, 'conflicting_work_modes',    NULL),
        (12, 'missing_work_modes',        3),
        (13, 'publication_boundary',     3),
        (14, 'publication_over_boundary',NULL),
        (15, 'deadline_boundary',        3),
        (16, 'deadline_over_boundary',   NULL),
        (17, 'first_seen_boundary',      3),
        (18, 'first_seen_over_boundary', NULL),
        (19, 'all_rules_priority',       1),
        (20, 'shared_url_priority',      2),
        (21, 'missing_organization',     2),
        (22, 'relative_date_fallback',   3),
        (23, 'deadline_conflict',        NULL),
        (24, 'different_query',          NULL)

    ) AS v(
        case_id,
        case_name,
        expected_tier
    )

),

fixture_base AS (

    SELECT
        s.*,
        side,

        (
            '00000000-0000-0000-0000-'
            || LPAD(
                (case_id * 10 + side)::TEXT,
                12,
                '0'
            )
        )::UUID AS source_listing_id,

        'https://fixture.example/case/'
            || case_id::TEXT AS base_url,

        '2026-01-01 00:00:00+00'::TIMESTAMPTZ
            AS base_date

    FROM scenarios s

    CROSS JOIN (VALUES (1), (2)) AS sides(side)

),

fixture_features_raw AS (

    SELECT

        source_listing_id,

        CASE
            WHEN side = 1 OR case_id = 8
                THEN 'egyincs'
            ELSE 'wuzzuf'
        END AS source_name,

        'fixture-' || case_id::TEXT
            || '-' || side::TEXT
            AS source_opportunity_id,

        CASE
            WHEN case_id = 3 AND side = 2
                THEN 'internship'
            ELSE 'job'
        END AS opportunity_type,

        base_url || '/listing/'
            || side::TEXT AS source_url_normalized,

        CASE

            WHEN case_id IN (1, 3)
                 AND side = 1
                THEN base_url || '/reference'

            WHEN case_id = 2 AND side = 1
                THEN base_url || '/listing/2'

            WHEN case_id IN (4, 5, 8, 20, 21)
                THEN base_url || '/application/42'

            WHEN case_id = 7 AND side = 1
                THEN base_url || '/jobs/ABC'

            WHEN case_id = 7 AND side = 2
                THEN base_url || '/jobs/abc'

            WHEN case_id = 19
                THEN base_url || '/listing/2'

            WHEN case_id = 24 AND side = 1
                THEN base_url || '/jobs/42?ref=ABC'

            WHEN case_id = 24 AND side = 2
                THEN base_url || '/jobs/42?ref=abc'

            -- Generic portal already excluded upstream.
            ELSE NULL

        END AS external_application_url_verified,

        CASE
            WHEN case_id IN (1, 3)
                 AND side = 1
                THEN 'wuzzuf'
            ELSE NULL
        END AS referenced_source_name,

        CASE
            WHEN case_id IN (1, 3)
                 AND side = 1
                THEN 'fixture-' || case_id::TEXT || '-2'
            ELSE NULL
        END AS referenced_source_opportunity_id,

        CASE
            WHEN case_id = 5 AND side = 2
                THEN 'different-org-' || case_id::TEXT

            WHEN case_id = 21 AND side = 2
                THEN NULL

            ELSE 'organization-' || case_id::TEXT
        END AS organization_key,

        'data-engineer-' || case_id::TEXT
            AS title_match_key,

        'city:cairo'::TEXT AS location_match_signal,

        (
            case_id IN (
                9, 10, 11, 12, 13, 14,
                15, 16, 17, 18, 19, 20,
                22, 23
            )
        ) AS is_tier2_eligible,

        (
            case_id = 9 AND side = 1
        ) AS is_composite_ambiguous_within_source,

        CASE
            WHEN case_id = 11 AND side = 2
                THEN '["remote"]'::JSONB

            WHEN case_id = 12 AND side = 2
                THEN NULL::JSONB

            ELSE '["on_site"]'::JSONB
        END AS work_modes,

        CASE

            WHEN case_id IN (13, 14, 22, 23)
                 AND side = 1
                THEN base_date

            WHEN case_id = 13 AND side = 2
                THEN base_date + INTERVAL '45 days'

            WHEN case_id = 14 AND side = 2
                THEN base_date
                    + INTERVAL '45 days 1 second'

            WHEN case_id = 22 AND side = 2
                THEN base_date + INTERVAL '90 days'

            WHEN case_id = 23 AND side = 2
                THEN base_date + INTERVAL '1 day'

            ELSE NULL::TIMESTAMPTZ

        END AS published_at,

        CASE
            WHEN case_id = 22
                THEN 'relative'

            WHEN case_id IN (13, 14, 23)
                THEN 'exact'

            ELSE NULL
        END AS published_at_precision,

        CASE

            WHEN case_id IN (15, 16, 23)
                 AND side = 1
                THEN base_date

            WHEN case_id = 15 AND side = 2
                THEN base_date + INTERVAL '14 days'

            WHEN case_id = 16 AND side = 2
                THEN base_date
                    + INTERVAL '14 days 1 second'

            WHEN case_id = 23 AND side = 2
                THEN base_date + INTERVAL '20 days'

            ELSE NULL::TIMESTAMPTZ

        END AS deadline,

        CASE
            WHEN case_id IN (15, 16, 23)
                THEN 'exact'
            ELSE NULL
        END AS deadline_precision,

        CASE

            WHEN case_id = 17 AND side = 2
                THEN base_date + INTERVAL '45 days'

            WHEN case_id = 18 AND side = 2
                THEN base_date
                    + INTERVAL '45 days 1 second'

            WHEN case_id = 22 AND side = 2
                THEN base_date + INTERVAL '10 days'

            ELSE base_date

        END AS first_seen_at

    FROM fixture_base

),

fixture_features AS (
    SELECT
        f.*,
        CASE
            WHEN published_at_precision = 'exact'
            THEN (published_at AT TIME ZONE 'UTC')::DATE
        END AS published_calendar_date,
        CASE
            WHEN deadline_precision = 'exact'
            THEN (deadline AT TIME ZONE 'UTC')::DATE
        END AS deadline_calendar_date
    FROM fixture_features_raw f
),

actual AS (

    {{ generate_opportunity_match_pairs(
        'fixture_features'
    ) }}

),

expected AS (

    SELECT

        a.source_listing_id AS listing_id_low,

        b.source_listing_id AS listing_id_high,

        CASE
            WHEN s.expected_tier = 1
                THEN b.source_listing_id
            ELSE NULL::UUID
        END AS direct_url_target_listing_id,

        s.expected_tier AS match_tier,

        CASE s.expected_tier
            WHEN 1 THEN 'direct_cross_source_url'
            WHEN 2 THEN 'shared_external_application_url'
            WHEN 3 THEN 'multi_signal_composite'
        END AS match_method

    FROM scenarios s

    JOIN fixture_base a
        ON a.case_id = s.case_id
       AND a.side = 1

    JOIN fixture_base b
        ON b.case_id = s.case_id
       AND b.side = 2

    WHERE s.expected_tier IS NOT NULL

),

actual_comparable AS (

    SELECT
        listing_id_low,
        listing_id_high,
        direct_url_target_listing_id,
        match_tier,
        match_method

    FROM actual

),

missing_pairs AS (

    SELECT * FROM expected

    EXCEPT ALL

    SELECT * FROM actual_comparable

),

unexpected_pairs AS (

    SELECT * FROM actual_comparable

    EXCEPT ALL

    SELECT * FROM expected

),

failures AS (

    SELECT

        'missing_expected_pair'::TEXT AS failure,

        listing_id_low::TEXT AS detail

    FROM missing_pairs

    UNION ALL

    SELECT

        'unexpected_or_duplicate_pair',

        listing_id_low::TEXT

    FROM unexpected_pairs

    UNION ALL

    SELECT

        'invalid_pair_order',

        listing_id_low::TEXT

    FROM actual

    WHERE listing_id_low >= listing_id_high

    UNION ALL

    SELECT

        'missing_match_evidence',

        listing_id_low::TEXT

    FROM actual

    WHERE pair_evidence IS NULL

       OR JSONB_TYPEOF(pair_evidence)
           IS DISTINCT FROM 'object'

       OR pair_evidence ->> 'rule'
           IS DISTINCT FROM match_method

    UNION ALL

    SELECT

        'incorrect_direct_reference_evidence',

        a.listing_id_low::TEXT

    FROM actual a

    JOIN fixture_base f
        ON f.source_listing_id = a.listing_id_low

    WHERE f.case_id = 1

      AND a.pair_evidence -> 'matched_on_source_id'
          IS DISTINCT FROM 'true'::JSONB

    UNION ALL

    SELECT

        'incorrect_direct_url_evidence',

        a.listing_id_low::TEXT

    FROM actual a

    JOIN fixture_base f
        ON f.source_listing_id = a.listing_id_low

    WHERE f.case_id = 2

      AND a.pair_evidence -> 'matched_on_normalized_url'
          IS DISTINCT FROM 'true'::JSONB

    UNION ALL

    SELECT

        'incorrect_temporal_basis',

        a.listing_id_low::TEXT

    FROM actual a

    JOIN fixture_base f
        ON f.source_listing_id = a.listing_id_low

    WHERE f.case_id IN (13, 15, 17, 22)

      AND a.pair_evidence ->> 'temporal_basis'

          IS DISTINCT FROM (

              CASE f.case_id

                  WHEN 13
                      THEN 'published_at_within_45d'

                  WHEN 15
                      THEN 'deadline_within_14d'

                  ELSE 'first_seen_at_within_45d'

              END

          )

)

SELECT *
FROM failures
