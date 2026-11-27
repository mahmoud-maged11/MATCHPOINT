-- Exercise the production location resolution macro.
-- Uses the actual location seed plus two isolated
-- synthetic full-label aliases.
-- Returns zero rows on success.

WITH scenarios AS (

    SELECT *
    FROM (VALUES

        (1, 'aliases', 'cairo', 'Cairo', 'Cairo', 'Cairo', 'Egypt', 'EG', FALSE, TRUE),
        (2, 'aliases', 'new_cairo', 'New Cairo', 'New Cairo', 'Cairo', 'Egypt', 'EG', FALSE, TRUE),
        (3, 'aliases', 'maadi', 'Maadi', 'Maadi', 'Cairo', 'Egypt', 'EG', FALSE, TRUE),
        (4, 'aliases', 'mansoura', 'Mansoura', 'Mansoura', 'Dakahlia', 'Egypt', 'EG', FALSE, TRUE),
        (5, 'aliases', 'arabic_cairo', 'القاهرة', 'Cairo', 'Cairo', 'Egypt', 'EG', FALSE, TRUE),
        (6, 'aliases', 'arabic_maadi', 'المعادي', 'Maadi', 'Cairo', 'Egypt', 'EG', FALSE, TRUE),
        (7, 'aliases', 'arabic_giza', 'الجيزة', 'Giza', 'Giza', 'Egypt', 'EG', FALSE, TRUE),
        (8, 'aliases', 'arabic_mansoura', 'المنصورة', 'Mansoura', 'Dakahlia', 'Egypt', 'EG', FALSE, TRUE),
        (9, 'formatting', 'outer_spaces', '   Cairo   ', 'Cairo', 'Cairo', 'Egypt', 'EG', FALSE, TRUE),
        (10, 'formatting', 'uppercase', 'CAIRO', 'Cairo', 'Cairo', 'Egypt', 'EG', FALSE, TRUE),
        (11, 'formatting', 'internal_spaces', 'New    Cairo', 'New Cairo', 'Cairo', 'Egypt', 'EG', FALSE, TRUE),
        (12, 'formatting', 'tabs_and_newlines', '	New
Cairo	', 'New Cairo', 'Cairo', 'Egypt', 'EG', FALSE, TRUE),
        (13, 'formatting', 'arabic_comma', 'Cairo، Egypt', 'Cairo', 'Cairo', 'Egypt', 'EG', FALSE, TRUE),
        (14, 'formatting', 'empty_tokens', ', Cairo, , Egypt,', 'Cairo', 'Cairo', 'Egypt', 'EG', FALSE, TRUE),
        (15, 'compatible', 'city_country', 'Cairo, Egypt', 'Cairo', 'Cairo', 'Egypt', 'EG', FALSE, TRUE),
        (16, 'compatible', 'country_city', 'Egypt, Cairo', 'Cairo', 'Cairo', 'Egypt', 'EG', FALSE, TRUE),
        (17, 'compatible', 'district_governorate', 'Maadi, Cairo', 'Maadi', 'Cairo', 'Egypt', 'EG', FALSE, TRUE),
        (18, 'compatible', 'governorate_district', 'Cairo, Maadi', 'Maadi', 'Cairo', 'Egypt', 'EG', FALSE, TRUE),
        (19, 'compatible', 'city_governorate_country', 'Mansoura, Dakahlia, Egypt', 'Mansoura', 'Dakahlia', 'Egypt', 'EG', FALSE, TRUE),
        (20, 'compatible', 'governorate_only', 'Dakahlia', NULL, 'Dakahlia', 'Egypt', 'EG', FALSE, TRUE),
        (21, 'compatible', 'country_only', 'Egypt', NULL, NULL, 'Egypt', 'EG', FALSE, TRUE),
        (22, 'compatible', 'repeated_alias', 'Cairo, Cairo, Egypt', 'Cairo', 'Cairo', 'Egypt', 'EG', FALSE, TRUE),
        (23, 'conflicts', 'different_governorates', 'Dakahlia, Cairo', NULL, NULL, NULL, NULL, FALSE, FALSE),
        (24, 'conflicts', 'different_cities', 'Cairo, Alexandria', NULL, NULL, NULL, NULL, FALSE, FALSE),
        (25, 'conflicts', 'same_governorate_different_cities', 'Maadi, Nasr City', NULL, NULL, NULL, NULL, FALSE, FALSE),
        (26, 'conflicts', 'wrong_governorate', 'Mansoura, Cairo', NULL, NULL, NULL, NULL, FALSE, FALSE),
        (27, 'conflicts', 'late_conflicting_token', 'Maadi, Cairo, Egypt, Alexandria', NULL, NULL, NULL, NULL, FALSE, FALSE),
        (28, 'conflicts', 'reversed_conflict', 'Cairo, Dakahlia', NULL, NULL, NULL, NULL, FALSE, FALSE),
        (29, 'missing', 'null_location', NULL, NULL, NULL, NULL, NULL, FALSE, FALSE),
        (30, 'missing', 'empty_location', '', NULL, NULL, NULL, NULL, FALSE, FALSE),
        (31, 'missing', 'whitespace_location', (' ' || CHR(9) || CHR(10) || ' '), NULL, NULL, NULL, NULL, FALSE, FALSE),
        (32, 'missing', 'unknown_location', 'Unknown Location', NULL, NULL, NULL, NULL, FALSE, FALSE),
        (33, 'missing', 'known_and_unknown', 'Cairo, Unknown Location', NULL, NULL, NULL, NULL, FALSE, FALSE),
        (34, 'missing', 'unknown_fourth_token', 'Maadi, Cairo, Egypt, Unknown Location', NULL, NULL, NULL, NULL, FALSE, FALSE),
        (35, 'online', 'online_label', 'Online', NULL, NULL, NULL, NULL, TRUE, TRUE),
        (36, 'online', 'remote_label', 'Remote', NULL, NULL, NULL, NULL, TRUE, TRUE),
        (37, 'online', 'arabic_remote', 'عن بعد', NULL, NULL, NULL, NULL, TRUE, TRUE),
        (38, 'online', 'compatible_online_aliases', 'Online, Remote', NULL, NULL, NULL, NULL, TRUE, TRUE),
        (39, 'online', 'physical_online_conflict', 'Cairo, Remote', NULL, NULL, NULL, NULL, FALSE, FALSE),
        (40, 'online', 'country_online_conflict', 'Egypt, Online', NULL, NULL, NULL, NULL, FALSE, FALSE),
        (41, 'full_label', 'explicit_full_label', 'Cairo, Special Zone', 'Cairo', 'Cairo', 'Egypt', 'EG', FALSE, TRUE),
        (42, 'full_label', 'full_label_over_tokens', 'Maadi, Nasr City', 'Maadi', 'Cairo', 'Egypt', 'EG', FALSE, TRUE)

    ) AS v(
        case_id,
        category,
        case_name,
        raw_location,
        expected_city,
        expected_governorate,
        expected_country,
        expected_code,
        expected_online,
        expected_standardized
    )

),

fixture_staged AS (

    SELECT
        case_id AS source_listing_id,
        raw_location AS location_raw,
        {{ clean_text('raw_location') }}
            AS location_cleaned,
        {{ normalize_lookup_key('raw_location') }}
            AS location_lookup_key

    FROM scenarios

    WHERE category <> 'full_label'

),

fixture_mappings AS (

    SELECT
        raw_location_normalized,
        standardized_city,
        standardized_governorate,
        standardized_country,
        country_code,
        is_online_location_label

    FROM {{ ref('location_mappings') }}

),

{{ resolve_listing_locations(
    'fixture_staged',
    'fixture_mappings'
) }}

actual_regular AS (

    SELECT
        s.source_listing_id AS case_id,
        s.location_raw,
        r.standardized_city,
        r.standardized_governorate,
        r.standardized_country,
        r.country_code,
        COALESCE(r.is_online_location_label, FALSE)
            AS is_online_location_label,
        (r.source_listing_id IS NOT NULL)
            AS is_location_standardized

    FROM fixture_staged s

    LEFT JOIN location_resolved r
        ON s.source_listing_id = r.source_listing_id

),

actual_full_labels AS (

    WITH full_label_staged AS (

        SELECT
            case_id AS source_listing_id,
            raw_location AS location_raw,
            {{ clean_text('raw_location') }}
                AS location_cleaned,
            {{ normalize_lookup_key('raw_location') }}
                AS location_lookup_key

        FROM scenarios

        WHERE category = 'full_label'

    ),

    full_label_mappings AS (

        SELECT *
        FROM fixture_mappings

        UNION ALL

        SELECT *
        FROM (VALUES

            (
                'cairo, special zone',
                'Cairo',
                'Cairo',
                'Egypt',
                'EG',
                FALSE
            ),

            (
                'maadi, nasr city',
                'Maadi',
                'Cairo',
                'Egypt',
                'EG',
                FALSE
            )

        ) AS v(
            raw_location_normalized,
            standardized_city,
            standardized_governorate,
            standardized_country,
            country_code,
            is_online_location_label
        )

    ),

    {{ resolve_listing_locations(
        'full_label_staged',
        'full_label_mappings'
    ) }}

    result AS (

        SELECT
            s.source_listing_id AS case_id,
            s.location_raw,
            r.standardized_city,
            r.standardized_governorate,
            r.standardized_country,
            r.country_code,
            COALESCE(r.is_online_location_label, FALSE)
                AS is_online_location_label,
            (r.source_listing_id IS NOT NULL)
                AS is_location_standardized

        FROM full_label_staged s

        LEFT JOIN location_resolved r
            ON s.source_listing_id = r.source_listing_id

    )

    SELECT *
    FROM result

),

actual AS (

    SELECT * FROM actual_regular

    UNION ALL

    SELECT * FROM actual_full_labels

),

expected AS (

    SELECT
        case_id,
        raw_location AS location_raw,
        expected_city AS standardized_city,
        expected_governorate AS standardized_governorate,
        expected_country AS standardized_country,
        expected_code AS country_code,
        expected_online AS is_online_location_label,
        expected_standardized AS is_location_standardized

    FROM scenarios

),

missing_or_incorrect AS (

    SELECT * FROM expected

    EXCEPT ALL

    SELECT * FROM actual

),

unexpected_or_duplicate AS (

    SELECT * FROM actual

    EXCEPT ALL

    SELECT * FROM expected

),

failures AS (

    SELECT
        'missing_or_incorrect_result'::TEXT AS failure,
        m.*

    FROM missing_or_incorrect m

    UNION ALL

    SELECT
        'unexpected_or_duplicate_result',
        u.*

    FROM unexpected_or_duplicate u

)

SELECT
    f.*,
    s.category,
    s.case_name

FROM failures f

LEFT JOIN scenarios s
    ON f.case_id = s.case_id
