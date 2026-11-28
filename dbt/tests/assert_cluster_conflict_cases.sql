WITH fixture_rows AS (

    SELECT *
    FROM (VALUES

        -- C01: Compatible organizations.
        (101, 'wuzzuf',  'acme', 'job', 'Cairo', 'Cairo', 'EG', 101),
        (102, 'bayt',    'acme', 'job', 'Cairo', 'Cairo', 'EG', 101),

        -- C02: Missing organization is not a conflict.
        (201, 'wuzzuf',  'acme', 'job', 'Cairo', 'Cairo', 'EG', 201),
        (202, 'bayt',    NULL,   'job', 'Cairo', 'Cairo', 'EG', 201),

        -- C03: Missing organization must not bridge conflicts.
        (301, 'wuzzuf',  'acme', 'job', 'Cairo', 'Cairo', 'EG', 301),
        (302, 'bayt',    NULL,   'job', 'Cairo', 'Cairo', 'EG', 302),
        (303, 'forasna', 'beta', 'job', 'Cairo', 'Cairo', 'EG', 303),

        -- C04: Different opportunity types.
        (401, 'wuzzuf',  'acme', 'job',        NULL, NULL, NULL, 401),
        (402, 'bayt',    'acme', 'internship', NULL, NULL, NULL, 402),

        -- C05: City and country-only evidence.
        (501, 'wuzzuf',  'acme', 'job', 'Cairo', 'Cairo', 'EG', 501),
        (502, 'bayt',    'acme', 'job', NULL, NULL, 'EG', 501),

        -- C06: Conflicting standardized geography.
        (601, 'wuzzuf',  'acme', 'job', 'Cairo', 'Cairo', 'EG', 601),
        (602, 'bayt',    'acme', 'job', 'Alexandria', 'Alexandria', 'EG', 602),

        -- C07: Missing geography.
        (701, 'wuzzuf',  'acme', 'job', 'Cairo', 'Cairo', 'EG', 701),
        (702, 'bayt',    'acme', 'job', NULL, NULL, NULL, 701),

        -- C08: Valid Tier 1 fallback.
        (801, 'wuzzuf',  'acme', 'job', 'Cairo', 'Cairo', 'EG', 801),
        (802, 'bayt',    'acme', 'job', 'Cairo', 'Cairo', 'EG', 801),
        (803, 'forasna', 'beta', 'job', 'Cairo', 'Cairo', 'EG', 803),

        -- C09: Invalid Tier 1 fallback.
        (901, 'wuzzuf',  'acme', 'job', 'Cairo', 'Cairo', 'EG', 901),
        (902, 'bayt',    NULL,   'job', 'Cairo', 'Cairo', 'EG', 902),
        (903, 'forasna', 'beta', 'job', 'Cairo', 'Cairo', 'EG', 903),

        -- C10: Duplicate source in connected component.
        (1001, 'wuzzuf', 'acme', 'job', NULL, NULL, NULL, 1001),
        (1002, 'bayt',   'acme', 'job', NULL, NULL, NULL, 1002),
        (1003, 'wuzzuf', 'acme', 'job', NULL, NULL, NULL, 1003)

    ) AS v(
        fixture_id,
        source_name,
        organization_key,
        opportunity_type,
        standardized_city,
        standardized_governorate,
        country_code,
        expected_group
    )

),

fixture_features AS (

    SELECT
        (
            '00000000-0000-0000-0000-'
            || LPAD(fixture_id::TEXT, 12, '0')
        )::UUID AS source_listing_id,

        source_name,
        fixture_id::TEXT AS source_opportunity_id,
        'id:' || fixture_id::TEXT AS source_identity_key,

        'https://example.com/' || fixture_id::TEXT AS source_url,

        NULL::TEXT AS external_application_url_raw,

        organization_key,
        opportunity_type,
        standardized_city,
        standardized_governorate,
        country_code,

        (
            standardized_city IS NOT NULL
            OR standardized_governorate IS NOT NULL
            OR country_code IS NOT NULL
        ) AS is_location_standardized,

        CASE source_name
            WHEN 'wuzzuf' THEN 5
            WHEN 'forasna' THEN 6
            WHEN 'bayt' THEN 7
            ELSE 99
        END AS source_authority_rank,

        5 AS completeness_score,

        '2026-01-01 00:00:00+00'::TIMESTAMPTZ AS first_seen_at,
        '2026-01-02 00:00:00+00'::TIMESTAMPTZ AS last_seen_at,

        NULL::TIMESTAMPTZ AS published_at,
        NULL::TEXT AS published_at_precision,
        NULL::DATE AS published_calendar_date,

        NULL::TIMESTAMPTZ AS deadline,
        NULL::TEXT AS deadline_precision,
        NULL::DATE AS deadline_calendar_date,

        NULL::JSONB AS work_modes,

        'active'::TEXT AS observed_status,
        'active'::TEXT AS effective_status,

        REPEAT('a', 64) AS content_hash,
        1 AS content_version,

        '00000000-0000-0000-0000-999999999999'::UUID
            AS last_collection_run_id,

        FALSE AS is_composite_ambiguous_within_source

    FROM fixture_rows

),

fixture_edges AS (

    SELECT *
    FROM (VALUES
        (101, 102, 2),
        (201, 202, 2),
        (301, 302, 2),
        (302, 303, 2),
        (401, 402, 1),
        (501, 502, 2),
        (601, 602, 2),
        (701, 702, 2),
        (801, 802, 2),
        (802, 803, 3),
        (901, 902, 2),
        (902, 903, 2),
        (1001, 1002, 2),
        (1002, 1003, 2)
    ) AS v(low_id, high_id, match_tier)

),

fixture_pairs AS (

    SELECT
        a.source_listing_id AS listing_id_low,
        b.source_listing_id AS listing_id_high,

        e.match_tier,

        CASE e.match_tier
            WHEN 1 THEN 'fixture_direct_url'
            WHEN 2 THEN 'fixture_shared_url'
            ELSE 'fixture_composite'
        END AS match_method,

        JSONB_BUILD_OBJECT(
            'fixture', TRUE
        ) AS pair_evidence,

        NULL::UUID AS direct_url_target_listing_id

    FROM fixture_edges e

    JOIN fixture_features a
        ON a.source_opportunity_id = e.low_id::TEXT

    JOIN fixture_features b
        ON b.source_opportunity_id = e.high_id::TEXT

),

actual AS (

    {{ resolve_opportunity_clusters(
        'fixture_features',
        'fixture_pairs'
    ) }}

),

actual_mapped AS (

    SELECT
        a.*,
        f.fixture_id,
        f.expected_group

    FROM actual a

    JOIN fixture_rows f
        ON a.source_opportunity_id = f.fixture_id::TEXT

),

expected_sizes AS (

    SELECT
        expected_group,
        COUNT(*) AS expected_size

    FROM fixture_rows
    GROUP BY expected_group

),

failures AS (

    -- Every input must produce exactly one output.

    SELECT
        'listing_preservation' AS failure,
        f.fixture_id::TEXT AS detail

    FROM fixture_rows f

    LEFT JOIN actual_mapped a
        ON f.fixture_id = a.fixture_id

    GROUP BY f.fixture_id

    HAVING COUNT(a.source_listing_id) <> 1

    UNION ALL

    SELECT
        'unexpected_output',
        a.source_listing_id::TEXT

    FROM actual a

    LEFT JOIN fixture_features f
        ON a.source_listing_id = f.source_listing_id

    WHERE f.source_listing_id IS NULL

    UNION ALL

    -- Expected members must share one canonical ID.

    SELECT
        'unexpected_split',
        expected_group::TEXT

    FROM actual_mapped

    GROUP BY expected_group

    HAVING COUNT(DISTINCT opportunity_id) <> 1

    UNION ALL

    -- Different expected groups must never be merged.

    SELECT
        'unexpected_merge',
        opportunity_id::TEXT

    FROM actual_mapped

    GROUP BY opportunity_id

    HAVING COUNT(DISTINCT expected_group) <> 1

    UNION ALL

    SELECT
        'incorrect_component_size',
        a.fixture_id::TEXT

    FROM actual_mapped a

    JOIN expected_sizes e
        ON a.expected_group = e.expected_group

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

    -- Check the actual conflict evidence.

    SELECT
        'missing_organization_conflict',
        fixture_id::TEXT

    FROM actual_mapped

    WHERE fixture_id IN (301, 302, 303, 901, 902, 903)

      AND (
          match_method IS DISTINCT FROM
              'singleton_transitive_conflict'

          OR match_evidence
              -> 'violates_organization_consistency'
              IS DISTINCT FROM 'true'::JSONB
      )

    UNION ALL

    SELECT
        'missing_type_conflict',
        fixture_id::TEXT

    FROM actual_mapped

    WHERE fixture_id IN (401, 402)

      AND match_evidence
          -> 'violates_opportunity_type_consistency'
          IS DISTINCT FROM 'true'::JSONB

    UNION ALL

    SELECT
        'missing_geographic_conflict',
        fixture_id::TEXT

    FROM actual_mapped

    WHERE fixture_id IN (601, 602)

      AND match_evidence
          -> 'violates_geographic_consistency'
          IS DISTINCT FROM 'true'::JSONB

    UNION ALL

    SELECT
        'incorrect_tier1_fallback',
        fixture_id::TEXT

    FROM actual_mapped

    WHERE fixture_id IN (801, 802)

      AND (
          match_evidence ->> 'resolution_mode'
              IS DISTINCT FROM 'tier1_fallback'

          OR match_evidence
              -> 'full_component_conflicts'
              -> 'organization'
              IS DISTINCT FROM 'true'::JSONB
      )

    UNION ALL

    SELECT
        'missing_same_source_conflict',
        fixture_id::TEXT

    FROM actual_mapped

    WHERE fixture_id IN (1001, 1002, 1003)

      AND match_evidence
          -> 'violates_same_source'
          IS DISTINCT FROM 'true'::JSONB

    UNION ALL

    SELECT
        'missing_identity_or_evidence',
        fixture_id::TEXT

    FROM actual_mapped

    WHERE opportunity_id IS NULL
       OR canonical_anchor_key IS NULL
       OR match_evidence IS NULL
       OR match_method IS NULL

)

SELECT *
FROM failures
