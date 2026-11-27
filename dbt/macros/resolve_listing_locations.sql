{% macro resolve_listing_locations(staged_relation, mappings_relation) -%}
-- Resolve the full label first, otherwise inspect every
-- non-empty comma-separated location token.
location_candidates AS (

    SELECT
        s.source_listing_id,
        m.raw_location_normalized AS matched_alias,
        m.standardized_city,
        m.standardized_governorate,
        m.standardized_country,
        m.country_code,
        m.is_online_location_label

    FROM {{ staged_relation }} s

    INNER JOIN {{ mappings_relation }} m
        ON s.location_lookup_key = m.raw_location_normalized

    UNION ALL

    SELECT
        s.source_listing_id,
        m.raw_location_normalized AS matched_alias,
        m.standardized_city,
        m.standardized_governorate,
        m.standardized_country,
        m.country_code,
        m.is_online_location_label

    FROM {{ staged_relation }} s

    CROSS JOIN LATERAL REGEXP_SPLIT_TO_TABLE(
        REPLACE(s.location_cleaned, CHR(1548), ','),
        ','
    ) AS token(raw_token)

    LEFT JOIN {{ mappings_relation }} m
        ON {{ normalize_lookup_key('token.raw_token') }}
            = m.raw_location_normalized

    WHERE {{ clean_text('token.raw_token') }} IS NOT NULL

      AND NOT EXISTS (
          SELECT 1
          FROM {{ mappings_relation }} full_mapping
          WHERE full_mapping.raw_location_normalized
              = s.location_lookup_key
      )

),

-- Prefer the most specific complete mapping row.
location_ranked AS (

    SELECT
        c.*,

        ROW_NUMBER() OVER (
            PARTITION BY c.source_listing_id

            ORDER BY
                CASE
                    WHEN c.standardized_city IS NOT NULL
                         AND c.standardized_city
                             IS DISTINCT FROM
                             c.standardized_governorate
                        THEN 5

                    WHEN c.standardized_city IS NOT NULL
                        THEN 4

                    WHEN c.standardized_governorate IS NOT NULL
                        THEN 3

                    WHEN c.standardized_country IS NOT NULL
                        THEN 2

                    WHEN c.is_online_location_label
                        THEN 1

                    ELSE 0
                END DESC,

                c.matched_alias NULLS LAST

        ) AS mapping_rank

    FROM location_candidates c

),

-- Reject unresolved tokens, incompatible geography,
-- and mixed physical/online location labels.
location_resolved AS (

    SELECT
        r.source_listing_id,
        r.standardized_city,
        r.standardized_governorate,
        r.standardized_country,
        r.country_code,
        r.is_online_location_label

    FROM location_ranked r

    WHERE r.mapping_rank = 1
      AND r.matched_alias IS NOT NULL

      AND NOT EXISTS (

          SELECT 1

          FROM location_candidates c

          WHERE c.source_listing_id = r.source_listing_id

            AND (

                c.matched_alias IS NULL

                OR c.is_online_location_label
                    IS DISTINCT FROM
                    r.is_online_location_label

                OR (
                    c.country_code IS NOT NULL
                    AND c.country_code
                        IS DISTINCT FROM r.country_code
                )

                OR (
                    c.standardized_country IS NOT NULL
                    AND c.standardized_country
                        IS DISTINCT FROM r.standardized_country
                )

                OR (
                    c.standardized_governorate IS NOT NULL
                    AND c.standardized_governorate
                        IS DISTINCT FROM
                        r.standardized_governorate
                )

                OR (
                    c.standardized_city IS NOT NULL

                    AND c.standardized_city
                        IS DISTINCT FROM r.standardized_city

                    AND c.standardized_city
                        IS DISTINCT FROM
                        r.standardized_governorate
                )

            )

      )

),
{%- endmacro %}
