-- Integrated regression of production pair generation and clustering.
-- All inputs are synthetic. No persistent warehouse dependencies.
-- Returns zero rows on success.

WITH scenario_rows AS (

    SELECT *
    FROM (VALUES

        -- case, member, publication day, publication precision,
        -- publication hour, deadline day, deadline precision,
        -- first-seen day, expected group

        (1, 1,  0, 'date_only', 0, NULL, NULL, 0, 1),
        (1, 2, 45, 'date_only', 0, NULL, NULL, 0, 1),

        (2, 1,  0, 'date_only', 0, NULL, NULL, 0, 1),
        (2, 2, 46, 'date_only', 0, NULL, NULL, 0, 2),

        (3, 1,  0, 'exact', 23, NULL, NULL, 0, 1),
        (3, 2, 45, 'date_only', 0, NULL, NULL, 0, 1),

        (4, 1,  0, 'exact', 23, NULL, NULL, 0, 1),
        (4, 2, 46, 'date_only', 0, NULL, NULL, 0, 2),

        (5, 1, 0, 'date_only', 0, 0, 'date_only', 0, 1),
        (5, 2, 1, 'date_only', 0, 15, 'date_only', 0, 2),

        (6, 1, NULL, NULL, 0, 0, 'date_only', 0, 1),
        (6, 2, NULL, NULL, 0, 14, 'date_only', 0, 1),

        (7, 1, NULL, NULL, 0, 0, 'date_only', 0, 1),
        (7, 2, NULL, NULL, 0, 15, 'date_only', 0, 2),

        (8, 1, 0, 'relative', 0, NULL, NULL, 0, 1),
        (8, 2, 90, 'relative', 0, NULL, NULL, 45, 1),

        (9, 1, 0, 'relative', 0, NULL, NULL, 0, 1),
        (9, 2, 1, 'relative', 0, NULL, NULL, 46, 2),

        -- A-B and B-C compatible; A-C incompatible.
        (10, 1, 0, 'date_only', 0, NULL, NULL, 0, 1),
        (10, 2, 30, 'date_only', 0, NULL, NULL, 0, 2),
        (10, 3, 60, 'date_only', 0, NULL, NULL, 0, 3),

        (11, 1, NULL, NULL, 0, 0, 'date_only', 0, 1),
        (11, 2, NULL, NULL, 0, 10, 'date_only', 0, 2),
        (11, 3, NULL, NULL, 0, 20, 'date_only', 0, 3),

        -- Calendar span is 45 days, but exact span exceeds it.
        (12, 1, 0, 'exact', 0, NULL, NULL, 0, 1),
        (12, 2, 22, 'date_only', 0, NULL, NULL, 0, 2),
        (12, 3, 45, 'exact', 1, NULL, NULL, 0, 3),

        -- Direct verified URL is stronger temporal evidence.
        (13, 1, 0, 'date_only', 0, NULL, NULL, 0, 1),
        (13, 2, 90, 'date_only', 0, NULL, NULL, 0, 1),

        -- Reliable publication supersedes first-seen fallback.
        (14, 1, 0, 'date_only', 0, NULL, NULL, 0, 1),
        (14, 2, 1, 'date_only', 0, NULL, NULL, 90, 1),

        -- Invalid full component retains verified direct URL.
        (15, 1, 0, 'date_only', 0, NULL, NULL, 0, 1),
        (15, 2, 30, 'date_only', 0, NULL, NULL, 0, 1),
        (15, 3, 60, 'date_only', 0, NULL, NULL, 0, 3)

    ) AS v(
        case_id,
        member_id,
        publication_day,
        publication_precision,
        publication_hour,
        deadline_day,
        deadline_precision_value,
        first_seen_day,
        expected_group
    )

),

fixture_base AS (

    SELECT
        s.*,

        (
            '00000000-0000-0000-0000-'
            || LPAD(
                (case_id * 10 + member_id)::TEXT,
                12,
                '0'
            )
        )::UUID AS source_listing_id,

        'fixture-' || case_id::TEXT
            || '-' || member_id::TEXT AS fixture_identity,

        'https://fixture.example/temporal/'
            || case_id::TEXT AS base_url,

        DATE '2026-01-01' AS base_date,

        '2026-01-01 00:00:00+00'::TIMESTAMPTZ
            AS base_timestamp

    FROM scenario_rows s

),

fixture_features AS (

    SELECT

        source_listing_id,

        CASE member_id
            WHEN 1 THEN 'wuzzuf'
            WHEN 2 THEN 'bayt'
            ELSE 'forasna'
        END AS source_name,

        fixture_identity AS source_opportunity_id,

        'id:' || fixture_identity AS source_identity_key,

        base_url || '/' || member_id::TEXT AS source_url,

        base_url || '/' || member_id::TEXT
            AS source_url_normalized,

        CASE
            WHEN case_id IN (13, 15)
                 AND member_id = 1
            THEN base_url || '/2'
        END AS external_application_url_verified,

        CASE
            WHEN case_id IN (13, 15)
                 AND member_id = 1
            THEN base_url || '/2'
        END AS external_application_url_raw,

        NULL::TEXT AS referenced_source_name,
        NULL::TEXT AS referenced_source_opportunity_id,

        'job'::TEXT AS opportunity_type,

        'organization-' || case_id::TEXT AS organization_key,

        'data-engineer-' || case_id::TEXT AS title_match_key,

        'city:cairo'::TEXT AS location_match_signal,

        'Cairo'::TEXT AS standardized_city,
        'Cairo'::TEXT AS standardized_governorate,
        'EG'::TEXT AS country_code,

        TRUE AS is_location_standardized,
        TRUE AS is_tier2_eligible,
        FALSE AS is_composite_ambiguous_within_source,

        '["on_site"]'::JSONB AS work_modes,

        CASE
            WHEN publication_precision IN ('exact', 'relative')
            THEN base_timestamp
                + publication_day * INTERVAL '24 hours'
                + publication_hour * INTERVAL '1 hour'
        END AS published_at,

        publication_precision AS published_at_precision,

        CASE
            WHEN publication_precision IN ('exact', 'date_only')
            THEN base_date + publication_day
        END AS published_calendar_date,

        CASE
            WHEN deadline_precision_value = 'exact'
            THEN base_timestamp
                + deadline_day * INTERVAL '24 hours'
        END AS deadline,

        deadline_precision_value AS deadline_precision,

        CASE
            WHEN deadline_precision_value IN ('exact', 'date_only')
            THEN base_date + deadline_day
        END AS deadline_calendar_date,

        base_timestamp
            + first_seen_day * INTERVAL '24 hours'
            AS first_seen_at,

        base_timestamp
            + first_seen_day * INTERVAL '24 hours'
            + INTERVAL '24 hours'
            AS last_seen_at,

        CASE member_id
            WHEN 1 THEN 5
            WHEN 2 THEN 7
            ELSE 6
        END AS source_authority_rank,

        5 AS completeness_score,

        'active'::TEXT AS observed_status,
        'active'::TEXT AS effective_status,

        REPEAT('a', 64) AS content_hash,
        1 AS content_version,

        '00000000-0000-0000-0000-999999999999'::UUID
            AS last_collection_run_id

    FROM fixture_base

),

actual_pairs AS (

    {{ generate_opportunity_match_pairs(
        'fixture_features'
    ) }}

),

actual_clusters AS (

    {{ resolve_opportunity_clusters(
        'fixture_features',
        'actual_pairs'
    ) }}

),

reordered_features AS MATERIALIZED (

    SELECT *
    FROM fixture_features
    ORDER BY source_listing_id DESC

),

reordered_pairs AS (

    {{ generate_opportunity_match_pairs(
        'reordered_features'
    ) }}

),

reordered_clusters AS (

    {{ resolve_opportunity_clusters(
        'reordered_features',
        'reordered_pairs'
    ) }}

),

-- Independent expected pair inventory.
-- Stored match_tier 1 = direct URL; 3 = composite.

expected_pair_rows AS (

    SELECT *
    FROM (VALUES

        (1, 1, 2, 3, 'published_at_within_45d'),
        (3, 1, 2, 3, 'published_at_within_45d'),
        (6, 1, 2, 3, 'deadline_within_14d'),
        (8, 1, 2, 3, 'first_seen_at_within_45d'),

        (10, 1, 2, 3, 'published_at_within_45d'),
        (10, 2, 3, 3, 'published_at_within_45d'),

        (11, 1, 2, 3, 'deadline_within_14d'),
        (11, 2, 3, 3, 'deadline_within_14d'),

        (12, 1, 2, 3, 'published_at_within_45d'),
        (12, 2, 3, 3, 'published_at_within_45d'),

        (13, 1, 2, 1, NULL),

        (14, 1, 2, 3, 'published_at_within_45d'),

        (15, 1, 2, 1, NULL),
        (15, 2, 3, 3, 'published_at_within_45d')

    ) AS v(
        case_id,
        low_member,
        high_member,
        match_tier,
        temporal_basis
    )

),

expected_pairs AS (

    SELECT

        a.source_listing_id AS listing_id_low,
        b.source_listing_id AS listing_id_high,

        e.match_tier,

        CASE e.match_tier
            WHEN 1 THEN 'direct_cross_source_url'
            ELSE 'multi_signal_composite'
        END AS match_method,

        CASE
            WHEN e.match_tier = 1
            THEN b.source_listing_id
        END AS direct_url_target_listing_id,

        e.temporal_basis

    FROM expected_pair_rows e

    JOIN fixture_base a
        ON a.case_id = e.case_id
       AND a.member_id = e.low_member

    JOIN fixture_base b
        ON b.case_id = e.case_id
       AND b.member_id = e.high_member

),

actual_pairs_comparable AS (

    SELECT
        listing_id_low,
        listing_id_high,
        match_tier,
        match_method,
        direct_url_target_listing_id,
        pair_evidence ->> 'temporal_basis' AS temporal_basis

    FROM actual_pairs

),

missing_pairs AS (

    SELECT * FROM expected_pairs

    EXCEPT ALL

    SELECT * FROM actual_pairs_comparable

),

unexpected_pairs AS (

    SELECT * FROM actual_pairs_comparable

    EXCEPT ALL

    SELECT * FROM expected_pairs

),

actual_mapped AS (

    SELECT
        a.*,
        f.case_id,
        f.member_id,
        f.expected_group

    FROM actual_clusters a

    JOIN fixture_base f
        ON a.source_listing_id = f.source_listing_id

),

expected_sizes AS (

    SELECT
        case_id,
        expected_group,
        COUNT(*) AS expected_size

    FROM fixture_base

    GROUP BY case_id, expected_group

),

identity_expected AS (

    SELECT

        f.source_listing_id,

        FIRST_VALUE(
            f.source_name || ':' || f.source_identity_key
        ) OVER (
            PARTITION BY b.case_id, b.expected_group
            ORDER BY f.source_authority_rank,
                     f.source_name,
                     f.source_identity_key
        ) AS expected_anchor,

        ROW_NUMBER() OVER (
            PARTITION BY b.case_id, b.expected_group
            ORDER BY f.source_authority_rank
        ) = 1 AS expected_primary

    FROM fixture_features f

    JOIN fixture_base b
        ON f.source_listing_id = b.source_listing_id

),

cluster_order_drift AS (

    (
        SELECT * FROM actual_clusters
        EXCEPT ALL
        SELECT * FROM reordered_clusters
    )

    UNION ALL

    (
        SELECT * FROM reordered_clusters
        EXCEPT ALL
        SELECT * FROM actual_clusters
    )

),

pair_order_drift AS (

    (
        SELECT * FROM actual_pairs
        EXCEPT ALL
        SELECT * FROM reordered_pairs
    )

    UNION ALL

    (
        SELECT * FROM reordered_pairs
        EXCEPT ALL
        SELECT * FROM actual_pairs
    )

),

failures AS (

    SELECT
        'missing_expected_pair'::TEXT AS failure,
        listing_id_low::TEXT || ':' ||
            listing_id_high::TEXT AS detail

    FROM missing_pairs

    UNION ALL

    SELECT
        'unexpected_or_duplicate_pair',
        listing_id_low::TEXT || ':' ||
            listing_id_high::TEXT

    FROM unexpected_pairs

    UNION ALL

    SELECT
        'listing_preservation',
        f.source_listing_id::TEXT

    FROM fixture_base f

    LEFT JOIN actual_clusters a
        ON f.source_listing_id = a.source_listing_id

    GROUP BY f.source_listing_id

    HAVING COUNT(a.source_listing_id) <> 1

    UNION ALL

    SELECT
        'unexpected_output',
        a.source_listing_id::TEXT

    FROM actual_clusters a

    LEFT JOIN fixture_base f
        ON a.source_listing_id = f.source_listing_id

    WHERE f.source_listing_id IS NULL

    UNION ALL

    SELECT
        'unexpected_split',
        case_id::TEXT || ':' || expected_group::TEXT

    FROM actual_mapped

    GROUP BY case_id, expected_group

    HAVING COUNT(DISTINCT opportunity_id) <> 1

    UNION ALL

    SELECT
        'unexpected_merge',
        opportunity_id::TEXT

    FROM actual_mapped

    GROUP BY opportunity_id

    HAVING COUNT(
        DISTINCT (case_id, expected_group)
    ) <> 1

    UNION ALL

    SELECT
        'incorrect_component_size',
        a.source_listing_id::TEXT

    FROM actual_mapped a

    JOIN expected_sizes e
        ON a.case_id = e.case_id
       AND a.expected_group = e.expected_group

    WHERE a.component_size
        IS DISTINCT FROM e.expected_size

    UNION ALL

    SELECT
        'incorrect_primary_count',
        opportunity_id::TEXT

    FROM actual_mapped

    GROUP BY opportunity_id

    HAVING COUNT(*) FILTER (
        WHERE is_primary_source
    ) <> 1

    UNION ALL

    SELECT
        'incorrect_identity_or_primary',
        a.source_listing_id::TEXT

    FROM actual_clusters a

    JOIN identity_expected e
        ON a.source_listing_id = e.source_listing_id

    WHERE a.canonical_anchor_key
              IS DISTINCT FROM e.expected_anchor

       OR a.is_primary_source
              IS DISTINCT FROM e.expected_primary

       OR a.opportunity_id IS NULL

    UNION ALL

    SELECT
        'missing_publication_conflict',
        source_listing_id::TEXT

    FROM actual_mapped

    WHERE case_id IN (10, 12)

      AND (
          match_method IS DISTINCT FROM
              'singleton_transitive_conflict'

          OR match_evidence -> 'violates_published_span'
              IS DISTINCT FROM 'true'::JSONB
      )

    UNION ALL

    SELECT
        'missing_deadline_conflict',
        source_listing_id::TEXT

    FROM actual_mapped

    WHERE case_id = 11

      AND (
          match_method IS DISTINCT FROM
              'singleton_transitive_conflict'

          OR match_evidence -> 'violates_deadline_span'
              IS DISTINCT FROM 'true'::JSONB
      )

    UNION ALL

    SELECT
        'incorrect_direct_url_preservation',
        source_listing_id::TEXT

    FROM actual_mapped

    WHERE case_id = 13

      AND match_method IS DISTINCT FROM
          'direct_cross_source_url'

    UNION ALL

    SELECT
        'incorrect_tier1_temporal_fallback',
        source_listing_id::TEXT

    FROM actual_mapped

    WHERE case_id = 15
      AND member_id IN (1, 2)

      AND (
          match_method IS DISTINCT FROM
              'direct_cross_source_url'

          OR match_evidence ->> 'resolution_mode'
              IS DISTINCT FROM 'tier1_fallback'

          OR match_evidence
              -> 'full_component_conflicts'
              -> 'published_span'
              IS DISTINCT FROM 'true'::JSONB
      )

    UNION ALL

    SELECT
        'missing_match_evidence',
        source_listing_id::TEXT

    FROM actual_clusters

    WHERE match_evidence IS NULL
       OR JSONB_TYPEOF(match_evidence)
              IS DISTINCT FROM 'object'
       OR match_method IS NULL

    UNION ALL

    SELECT
        'cluster_input_order_drift',
        source_listing_id::TEXT

    FROM cluster_order_drift

    UNION ALL

    SELECT
        'pair_input_order_drift',
        listing_id_low::TEXT

    FROM pair_order_drift

)

SELECT *
FROM failures
