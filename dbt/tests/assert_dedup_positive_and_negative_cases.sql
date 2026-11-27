-- Phase 4 regression tests.
-- Validate production URL macros, salary conflict semantics,
-- recursive graph convergence and deterministic UUID stability.
-- Returns zero rows on success.

WITH RECURSIVE url_cases AS (

    SELECT *
    FROM (
        VALUES
            (
                'url_host_case_equivalent',
                'https://WWW.ITIDA.gov.eg/English/Programs',
                'https://www.itida.gov.eg/English/Programs',
                TRUE
            ),
            (
                'url_path_case_distinct',
                'https://company.com/jobs/ABC',
                'https://company.com/jobs/abc',
                FALSE
            ),
            (
                'url_query_case_preserved_same',
                'https://CAREERS.acme.eg/Apply/Job?reqId=AbC123',
                'https://careers.acme.eg/Apply/Job?reqId=AbC123',
                TRUE
            ),
            (
                'url_query_case_preserved_diff',
                'https://careers.acme.eg/apply/job?reqId=AbC123',
                'https://careers.acme.eg/apply/job?reqId=abc123',
                FALSE
            ),
            (
                'url_www_distinct',
                'https://www.company.com/jobs/123',
                'https://company.com/jobs/123',
                FALSE
            ),
            (
                'url_scheme_distinct',
                'http://company.com/jobs/123',
                'https://company.com/jobs/123',
                FALSE
            ),
            (
                'url_trailing_slash_distinct',
                'https://company.com/jobs/123/',
                'https://company.com/jobs/123',
                FALSE
            ),
            (
                'url_fragment_distinct',
                'https://company.com/#/jobs/123',
                'https://company.com/#/jobs/456',
                FALSE
            ),
            (
                'url_port_distinct',
                'https://company.com:8443/jobs/123',
                'https://company.com/jobs/123',
                FALSE
            )
    ) AS t(case_name, url_a, url_b, expected_equal)

),

url_failures AS (

    SELECT
        case_name,
        'url_normalization_mismatch'::TEXT AS failure_reason

    FROM url_cases

    WHERE (
        {{ normalize_url_for_matching('url_a') }}
        =
        {{ normalize_url_for_matching('url_b') }}
    ) IS DISTINCT FROM expected_equal

),

portal_cases AS (

    SELECT *
    FROM (
        VALUES
            (
                'portal_wuzzuf_root',
                'https://wuzzuf.net/',
                TRUE
            ),
            (
                'portal_wuzzuf_egypt_search',
                'https://wuzzuf.net/jobs/egypt',
                TRUE
            ),
            (
                'portal_wuzzuf_jobs_dir',
                'https://wuzzuf.net/jobs',
                TRUE
            ),
            (
                'portal_nti_ereg',
                'https://www.nti.sci.eg/ereg/apply',
                TRUE
            ),
            (
                'portal_google_forms',
                'https://docs.google.com/forms/d/e/shared-intake',
                TRUE
            ),
            (
                'portal_linkedin_any',
                'https://www.linkedin.com/jobs/view/999',
                TRUE
            ),
            (
                'portal_generic_careers_leaf',
                'https://careers.company-x.eg/careers',
                TRUE
            ),
            (
                'portal_specific_wuzzuf_job',
                'https://wuzzuf.net/jobs/p/abc123-data-engineer',
                FALSE
            ),
            (
                'portal_specific_company_job',
                'https://careers.company-x.eg/careers/2026-data-engineer',
                FALSE
            ),
            (
                'portal_unverified_query_apply',
                'https://company-x.eg/apply?job_id=42',
                TRUE
            ),
            (
                'portal_generic_directory_with_query',
                'https://wuzzuf.net/jobs?search=python',
                TRUE
            ),
            (
                'portal_specific_deep_path_with_query',
                'https://company-x.eg/jobs/42?ref=ABC',
                FALSE
            )
    ) AS t(case_name, raw_url, expected_excluded)

),

portal_evaluated AS (

    SELECT
        case_name,
        expected_excluded,

        {{ is_generic_application_portal('raw_url') }}
            AS actual_excluded

    FROM portal_cases

),

portal_failures AS (

    SELECT
        case_name,
        'generic_portal_exclusion_mismatch'::TEXT
            AS failure_reason

    FROM portal_evaluated

    WHERE actual_excluded IS DISTINCT FROM expected_excluded

),

-- Preserve ADR-019 salary conflict regression cases.
salary_cases AS (

    SELECT *
    FROM (
        VALUES
            (
                'salary_scale_equivalent',
                10000::NUMERIC,
                15000::NUMERIC,
                'EGP',
                'monthly',
                10000.00::NUMERIC,
                15000.00::NUMERIC,
                'egp',
                'MONTHLY',
                FALSE
            ),
            (
                'salary_period_conflict',
                10000::NUMERIC,
                15000::NUMERIC,
                'EGP',
                'monthly',
                10000::NUMERIC,
                15000::NUMERIC,
                'EGP',
                'yearly',
                TRUE
            ),
            (
                'salary_currency_conflict',
                10000::NUMERIC,
                15000::NUMERIC,
                'EGP',
                'monthly',
                10000::NUMERIC,
                15000::NUMERIC,
                'USD',
                'monthly',
                TRUE
            ),
            (
                'salary_amount_conflict',
                10000::NUMERIC,
                15000::NUMERIC,
                'EGP',
                'monthly',
                12000::NUMERIC,
                15000::NUMERIC,
                'EGP',
                'monthly',
                TRUE
            )
    ) AS t(
        case_name,
        min_a,
        max_a,
        cur_a,
        per_a,
        min_b,
        max_b,
        cur_b,
        per_b,
        expected_conflict
    )

),

salary_failures AS (

    SELECT
        case_name,
        'salary_conflict_detection_mismatch'::TEXT
            AS failure_reason

    FROM salary_cases

    WHERE (
        (
            CASE
                WHEN min_a = 0 THEN '0'
                ELSE TRIM_SCALE(min_a)::TEXT
            END
            || ':'
            || CASE
                WHEN max_a = 0 THEN '0'
                ELSE TRIM_SCALE(max_a)::TEXT
            END
            || ':'
            || COALESCE(UPPER(cur_a), '')
            || ':'
            || COALESCE(LOWER(per_a), '')
        )
        <>
        (
            CASE
                WHEN min_b = 0 THEN '0'
                ELSE TRIM_SCALE(min_b)::TEXT
            END
            || ':'
            || CASE
                WHEN max_b = 0 THEN '0'
                ELSE TRIM_SCALE(max_b)::TEXT
            END
            || ':'
            || COALESCE(UPPER(cur_b), '')
            || ':'
            || COALESCE(LOWER(per_b), '')
        )
    ) IS DISTINCT FROM expected_conflict

),

-- Verify recursive convergence across 10 edges and 11 nodes.
long_chain_nodes AS (

    SELECT GENERATE_SERIES(1, 11) AS node_id

),

long_chain_edges AS (

    SELECT
        node_id AS from_id,
        node_id + 1 AS to_id

    FROM long_chain_nodes

    WHERE node_id <= 10

    UNION ALL

    SELECT
        node_id + 1 AS from_id,
        node_id AS to_id

    FROM long_chain_nodes

    WHERE node_id <= 10

),

long_chain_reach(start_id, current_id) AS (

    SELECT
        node_id,
        node_id

    FROM long_chain_nodes

    UNION

    SELECT
        r.start_id,
        e.to_id

    FROM long_chain_reach r

    INNER JOIN long_chain_edges e
        ON r.current_id = e.from_id

),

long_chain_components AS (

    SELECT
        start_id,
        MIN(current_id) AS component_root,
        COUNT(*) AS component_size

    FROM long_chain_reach

    GROUP BY start_id

),

long_chain_failures AS (

    SELECT
        'long_chain_10_edges_node_' || start_id::TEXT
            AS case_name,

        'chain_exceeding_8_edges_split'::TEXT
            AS failure_reason

    FROM long_chain_components

    WHERE component_root <> 1
       OR component_size <> 11

),

uuid_failures AS (

    SELECT
        'uuid_determinism_check'::TEXT AS case_name,
        'deterministic_uuid_mismatch'::TEXT AS failure_reason

    WHERE (
        {{ deterministic_uuid("'wuzzuf:id:abc123'") }}
        =
        {{ deterministic_uuid("'wuzzuf:id:abc123'") }}

        AND

        {{ deterministic_uuid("'wuzzuf:id:abc123'") }}
        <>
        {{ deterministic_uuid("'wuzzuf:id:other'") }}
    ) IS DISTINCT FROM TRUE

)

SELECT * FROM url_failures

UNION ALL

SELECT * FROM portal_failures

UNION ALL

SELECT * FROM salary_failures

UNION ALL

SELECT * FROM long_chain_failures

UNION ALL

SELECT * FROM uuid_failures