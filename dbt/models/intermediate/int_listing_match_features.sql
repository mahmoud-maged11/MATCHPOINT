{{ config(materialized='table') }}

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
        sl.location_raw,
        sl.is_location_standardized,
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
        sl.published_calendar_date,
        sl.deadline,
        sl.deadline_precision,
        sl.deadline_calendar_date,
        sl.observed_status,
        sl.effective_status,
        sl.first_seen_at,
        sl.last_seen_at,
        sl.collected_at,
        sl.content_hash,
        sl.content_version,
        sl.last_collection_run_id,

        CASE
            WHEN JSONB_TYPEOF(
                sl.raw_payload -> 'application_url'
            ) = 'string'
            THEN sl.raw_payload ->> 'application_url'
            ELSE NULL
        END AS external_application_url_raw,

        COALESCE(
            ss.source_authority_rank,
            99
        ) AS source_authority_rank,

        (
            (CASE WHEN sl.organization IS NOT NULL THEN 1 ELSE 0 END)
            + (CASE WHEN sl.description IS NOT NULL THEN 1 ELSE 0 END)
            + (CASE WHEN sl.location_raw IS NOT NULL THEN 1 ELSE 0 END)
            + (CASE WHEN sl.requirements IS NOT NULL THEN 1 ELSE 0 END)
            + (CASE WHEN sl.salary_min IS NOT NULL THEN 1 ELSE 0 END)
            + (CASE WHEN sl.deadline_calendar_date IS NOT NULL THEN 1 ELSE 0 END)
            + (CASE WHEN sl.published_calendar_date IS NOT NULL THEN 1 ELSE 0 END)
            + (CASE WHEN sl.work_modes_state = 'populated' THEN 1 ELSE 0 END)
            + (CASE WHEN sl.employment_types_state = 'populated' THEN 1 ELSE 0 END)
            + (CASE WHEN sl.required_skills_state = 'populated' THEN 1 ELSE 0 END)
        ) AS completeness_score

    FROM {{ ref('silver_source_listings') }} sl

    LEFT JOIN {{ ref('supported_sources') }} ss
        ON sl.source_name = ss.source_name

),

normalized_signals AS MATERIALIZED (

    SELECT
        b.*,

        -- Conservative title normalization.
        -- Never used as standalone matching evidence.
        NULLIF(
            BTRIM(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        LOWER(b.title),
                        E'[^a-z0-9\u0600-\u06FF]+',
                        ' ',
                        'g'
                    ),
                    '[[:space:]]+',
                    ' ',
                    'g'
                )
            ),
            ''
        ) AS title_match_key,

        -- Conservative Tier 2 location matching.
        -- Never replace unresolved geographic evidence
        -- with a generic remote signal.
        CASE

            WHEN b.is_location_standardized
                AND b.standardized_city IS NOT NULL
                AND b.country_code IS NOT NULL
            THEN
                'city:'
                || LOWER(b.standardized_city)
                || ':'
                || LOWER(b.country_code)

            WHEN b.is_location_standardized
                AND b.standardized_governorate IS NOT NULL
                AND b.country_code IS NOT NULL
            THEN
                'gov:'
                || LOWER(b.standardized_governorate)
                || ':'
                || LOWER(b.country_code)

            WHEN b.is_location_standardized
                AND b.is_online_location_label
            THEN 'remote'

            -- Explicit but unresolved or country-only
            -- location is insufficient for Tier 2.
            WHEN {{ clean_text('b.location_raw') }}
                IS NOT NULL
            THEN NULL

            -- Remote fallback is permitted only when
            -- location is missing and remote is the
            -- sole declared work mode.
            WHEN b.work_modes = '["remote"]'::JSONB
            THEN 'remote'

            ELSE NULL

        END AS location_match_signal,

        -- Preserve URL path, query, fragment and scheme.
        -- Only scheme and host are case-normalized.
        {{ normalize_url_for_matching('b.source_url') }}
            AS source_url_normalized,

        {{ normalize_url_for_matching('b.external_application_url_raw') }}
            AS external_url_normalized_for_match,

        -- Separate representation used for source-ID extraction.
        {{ url_reference_body('b.external_application_url_raw') }}
            AS external_url_case_preserved

    FROM base b

),

url_parsed AS MATERIALIZED (

    SELECT
        ns.*,

        REGEXP_REPLACE(
            {{ url_host_for_matching('ns.external_application_url_raw') }},
            '^www\.',
            ''
        ) AS external_url_host,

        REGEXP_REPLACE(
            {{ url_host_for_matching('ns.external_application_url_raw') }},
            '^www\.',
            ''
        )
        ||
        COALESCE(
            {{ url_path_for_matching('ns.external_application_url_raw') }},
            ''
        ) AS external_url_host_and_path,

        (
            POSITION(
                '?' IN SPLIT_PART(
                    COALESCE(
                        ns.external_url_normalized_for_match,
                        ''
                    ),
                    '#',
                    1
                )
            ) > 0
        ) AS external_url_has_query,

        NULLIF(
            BTRIM(
                {{ url_path_for_matching('ns.external_application_url_raw') }},
                '/'
            ),
            ''
        ) AS external_url_path_only,

        -- Extract source identity from authority and path only.
        -- Query parameters and fragments are not identity evidence.
        (
            sr.source_reference ->> 'source_name'
        ) AS referenced_source_name,

        (
            sr.source_reference ->> 'source_opportunity_id'
        ) AS referenced_source_opportunity_id

    FROM normalized_signals ns

    CROSS JOIN LATERAL (
        SELECT
            {{ extract_source_reference(
                'ns.external_application_url_raw'
            ) }} AS source_reference
    ) sr

),

portal_filtered AS MATERIALIZED (

    SELECT
        up.*,

        (
            up.external_url_path_only IS NOT NULL
        ) AS external_url_has_specific_path,

        -- Single source of truth for generic portal exclusions.
        {{ is_generic_application_portal('up.external_application_url_raw') }}
            AS is_external_url_generic_portal

    FROM url_parsed up

),

final_features AS (

    SELECT
        pf.*,

        -- Only non-generic, specific URLs qualify for Tier 1.
        CASE
            WHEN pf.external_url_normalized_for_match IS NOT NULL
                AND pf.external_url_has_specific_path
                AND NOT pf.is_external_url_generic_portal
            THEN pf.external_url_normalized_for_match

            ELSE NULL
        END AS external_application_url_verified,

        -- All four signals must be available for Tier 2.
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

    -- Prevent ambiguous composite matching within one source.
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