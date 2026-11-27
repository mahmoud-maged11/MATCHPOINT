WITH base AS (
    SELECT
        sl.source_listing_id,
        sl.source_name,
        sl.source_opportunity_id,
        sl.source_identity_key,
        sl.source_url,
        sl.title,
        sl.organization_key,
        sl.organization,
        sl.opportunity_type,
        sl.location_key,
        sl.standardized_city,
        sl.standardized_governorate,
        sl.standardized_country,
        sl.country_code,
        sl.is_online_location_label,
        sl.work_modes,
        sl.employment_types,
        sl.categories,
        sl.required_skills,
        sl.description,
        sl.requirements,
        sl.salary_min,
        sl.published_at,
        sl.published_at_precision,
        sl.deadline,
        sl.deadline_precision,
        sl.observed_status,
        sl.effective_status,
        sl.first_seen_at,
        sl.last_seen_at,
        sl.collected_at,
        sl.content_hash,
        sl.content_version,
        sl.last_collection_run_id,

        -- Verified external application URL key present in raw_payload (e.g. Egyincs mapper)
        NULLIF(BTRIM(sl.raw_payload ->> 'application_url'), '') AS external_application_url_raw,

        -- Deterministic source authority rank from single-source-of-truth seed (supported_sources.csv)
        COALESCE(ss.source_authority_rank, 99) AS source_authority_rank,

        -- Deterministic attribute completeness score (tie-breaker for primary source only, NOT identity anchor)
        (
            (CASE WHEN sl.organization IS NOT NULL THEN 1 ELSE 0 END)
            + (CASE WHEN sl.description IS NOT NULL THEN 1 ELSE 0 END)
            + (CASE WHEN sl.location_raw IS NOT NULL THEN 1 ELSE 0 END)
            + (CASE WHEN sl.requirements IS NOT NULL THEN 1 ELSE 0 END)
            + (CASE WHEN sl.salary_min IS NOT NULL THEN 1 ELSE 0 END)
            + (CASE WHEN sl.deadline IS NOT NULL THEN 1 ELSE 0 END)
            + (CASE WHEN sl.published_at IS NOT NULL THEN 1 ELSE 0 END)
            + (CASE WHEN sl.work_modes_state = 'populated' THEN 1 ELSE 0 END)
            + (CASE WHEN sl.employment_types_state = 'populated' THEN 1 ELSE 0 END)
            + (CASE WHEN sl.required_skills_state = 'populated' THEN 1 ELSE 0 END)
        ) AS completeness_score

    FROM {{ ref('silver_source_listings') }} sl
    LEFT JOIN {{ ref('supported_sources') }} ss
        ON sl.source_name = ss.source_name
),

normalized_signals AS (
    SELECT
        b.*,

        -- Conservative normalized title key (lowercased, punctuation collapsed to spaces, Arabic & English preserved)
        -- Never used alone for matching.
        NULLIF(
            BTRIM(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(LOWER(b.title), E'[^a-z0-9\u0600-\u06FF]+', ' ', 'g'),
                    '\s+',
                    ' ',
                    'g'
                )
            ),
            ''
        ) AS title_match_key,

        -- Conservative location/modality signal for Tier 2 composite matching:
        -- Missing locations and broad country-only values ('Egypt') intentionally stay NULL so they
        -- can never be treated as matching evidence.
        CASE
            WHEN b.standardized_city IS NOT NULL THEN
                'city:' || LOWER(b.standardized_city) || ':' || COALESCE(LOWER(b.country_code), '')
            WHEN b.standardized_governorate IS NOT NULL THEN
                'gov:' || LOWER(b.standardized_governorate) || ':' || COALESCE(LOWER(b.country_code), '')
            WHEN b.is_online_location_label
                OR (b.work_modes IS NOT NULL AND b.work_modes ? 'remote') THEN
                'remote'
            ELSE NULL
        END AS location_match_signal,

        -- Fix 1: Symmetric URL normalization (lowercase host + path, preserve functional query string casing)
        {{ normalize_url_for_matching('b.source_url') }} AS source_url_normalized,
        {{ normalize_url_for_matching('b.external_application_url_raw') }} AS external_url_normalized_for_match,

        -- Case-preserved external URL body (host/path without scheme/www/fragment) solely for extracting
        -- case-sensitive source listing identifiers (e.g. Wuzzuf alphanumeric IDs)
        CASE
            WHEN b.external_application_url_raw ~* '^https?://' THEN
                NULLIF(
                    RTRIM(
                        SPLIT_PART(
                            REGEXP_REPLACE(BTRIM(b.external_application_url_raw), '^https?://(www\.)?', '', 'i'),
                            '#',
                            1
                        ),
                        '/'
                    ),
                    ''
                )
            ELSE NULL
        END AS external_url_case_preserved

    FROM base b
),

url_parsed AS (
    SELECT
        ns.*,

        -- Extract lowercase host, path-without-query, and query presence from external_url_normalized_for_match
        LOWER(SPLIT_PART(SPLIT_PART(ns.external_url_normalized_for_match, '/', 1), '?', 1)) AS external_url_host,
        SPLIT_PART(ns.external_url_normalized_for_match, '?', 1) AS external_url_host_and_path,
        (POSITION('?' IN COALESCE(ns.external_url_normalized_for_match, '')) > 0) AS external_url_has_query,
        CASE
            WHEN ns.external_url_normalized_for_match IS NOT NULL
                 AND POSITION('/' IN SPLIT_PART(ns.external_url_normalized_for_match, '?', 1)) > 0 THEN
                NULLIF(
                    BTRIM(
                        SUBSTRING(
                            SPLIT_PART(ns.external_url_normalized_for_match, '?', 1)
                            FROM POSITION('/' IN SPLIT_PART(ns.external_url_normalized_for_match, '?', 1)) + 1
                        ),
                        '/'
                    ),
                    ''
                )
            ELSE NULL
        END AS external_url_path_only,

        -- Verified cross-source listing identifier extraction from case-preserved external URL (ADR-026)
        CASE
            WHEN ns.external_url_case_preserved ~* '^wuzzuf\.net/jobs/p/[^/?#]+' THEN 'wuzzuf'
            WHEN ns.external_url_case_preserved ~* '^bayt\.com/.+/jobs/.+-[0-9]+/?(\?.*)?$' THEN 'bayt'
            WHEN ns.external_url_case_preserved ~* '^app\.unv\.org/opportunities/[^/?#]+' THEN 'un_volunteers'
            ELSE NULL
        END AS referenced_source_name,

        CASE
            WHEN ns.external_url_case_preserved ~* '^wuzzuf\.net/jobs/p/[^/?#]+' THEN
                SPLIT_PART(
                    (REGEXP_MATCH(ns.external_url_case_preserved, '^wuzzuf\.net/jobs/p/([^/?#]+)', 'i'))[1],
                    '-',
                    1
                )
            WHEN ns.external_url_case_preserved ~* '^bayt\.com/.+/jobs/.+-[0-9]+/?(\?.*)?$' THEN
                (REGEXP_MATCH(ns.external_url_case_preserved, '-([0-9]+)/?(\?.*)?$', 'i'))[1]
            WHEN ns.external_url_case_preserved ~* '^app\.unv\.org/opportunities/[^/?#]+' THEN
                (REGEXP_MATCH(ns.external_url_case_preserved, '^app\.unv\.org/opportunities/([^/?#]+)', 'i'))[1]
            ELSE NULL
        END AS referenced_source_opportunity_id

    FROM normalized_signals ns
),

portal_filtered AS (
    SELECT
        up.*,
        (up.external_url_path_only IS NOT NULL) AS external_url_has_specific_path,

        -- Fix 4: Exclude generic platform roots, social links, shorteners, shared form endpoints,
        -- exact generic directory paths, generic path prefixes, AND generic single-segment leaf paths
        -- (e.g. company.com/careers, company.com/jobs, company.com/apply without query/ID)
        (
            EXISTS (
                SELECT 1
                FROM {{ ref('generic_application_portals') }} gp
                WHERE (
                    gp.match_scope = 'host_any_generic_portal'
                    AND (
                        up.external_url_host = gp.portal_pattern
                        OR up.external_url_host LIKE '%.' || gp.portal_pattern
                    )
                )
                OR (
                    gp.match_scope = 'host_root_only'
                    AND (
                        up.external_url_host = gp.portal_pattern
                        OR up.external_url_host LIKE '%.' || gp.portal_pattern
                    )
                    AND up.external_url_path_only IS NULL
                )
                OR (
                    gp.match_scope = 'path_prefix_generic'
                    AND (
                        up.external_url_host_and_path = gp.portal_pattern
                        OR up.external_url_host_and_path LIKE gp.portal_pattern || '/%'
                    )
                )
                OR (
                    gp.match_scope = 'path_exact_generic'
                    AND up.external_url_host_and_path = gp.portal_pattern
                    AND NOT up.external_url_has_query
                )
            )
            OR (
                -- Generic single-segment careers/apply leaf without specific job slug or query params
                up.external_url_path_only IS NOT NULL
                AND NOT up.external_url_has_query
                AND up.external_url_path_only IN (
                    'careers',
                    'career',
                    'jobs',
                    'apply',
                    'register',
                    'registration',
                    'opportunities',
                    'internships',
                    'vacancies',
                    'join-us',
                    'work-with-us',
                    'en/careers',
                    'en/jobs',
                    'ar/careers',
                    'ar/jobs'
                )
            )
        ) AS is_external_url_generic_portal

    FROM url_parsed up
),

final_features AS (
    SELECT
        pf.*,

        -- Qualified specific external application URL eligible for Tier 1 matching
        CASE
            WHEN pf.external_url_normalized_for_match IS NOT NULL
                AND pf.external_url_has_specific_path
                AND NOT pf.is_external_url_generic_portal THEN pf.external_url_normalized_for_match
            ELSE NULL
        END AS external_application_url_verified,

        -- Tier 2 composite eligibility requires ALL 4 non-null signals and title length >= 4
        (
            pf.title_match_key IS NOT NULL
            AND LENGTH(pf.title_match_key) >= 4
            AND pf.organization_key IS NOT NULL
            AND pf.opportunity_type IS NOT NULL
            AND pf.location_match_signal IS NOT NULL
        ) AS is_tier2_eligible

    FROM portal_filtered pf
)

SELECT
    ff.*,

    -- Ambiguity guard: if a single source has multiple listings with the identical Tier 2 tuple,
    -- disallow automatic Tier 2 merging on that tuple to prevent ambiguous cross-source grouping.
    CASE
        WHEN ff.is_tier2_eligible THEN
            (
                COUNT(*) OVER (
                    PARTITION BY
                        ff.source_name,
                        ff.title_match_key,
                        ff.organization_key,
                        ff.opportunity_type,
                        ff.location_match_signal
                ) > 1
            )
        ELSE FALSE
    END AS is_composite_ambiguous_within_source

FROM final_features ff
