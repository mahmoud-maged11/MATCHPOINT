WITH members AS (
    SELECT
        os.opportunity_id,
        os.is_primary_source,
        os.source_authority_rank,
        os.completeness_score,
        sl.*
    FROM {{ ref('silver_opportunity_sources') }} os
    JOIN {{ ref('silver_source_listings') }} sl
        ON os.source_listing_id = sl.source_listing_id
),

expected_experience AS (
    SELECT DISTINCT ON (opportunity_id)
        opportunity_id,
        experience_level,
        experience_level_raw,
        experience_years_min,
        experience_years_max
    FROM members
    WHERE experience_level IS NOT NULL
       OR experience_level_raw IS NOT NULL
       OR experience_years_min IS NOT NULL
       OR experience_years_max IS NOT NULL
    ORDER BY
        opportunity_id,
        (
            COALESCE(experience_level <> 'unknown', FALSE)
            OR experience_years_min IS NOT NULL
            OR experience_years_max IS NOT NULL
        ) DESC,
        is_primary_source DESC,
        source_authority_rank,
        completeness_score DESC,
        first_seen_at,
        source_identity_key,
        source_listing_id::TEXT
),

expected_location AS (
    SELECT DISTINCT ON (opportunity_id)
        opportunity_id,
        location_key,
        location_display,
        location_raw,
        standardized_city,
        standardized_governorate,
        standardized_country,
        country_code,
        is_online_location_label
    FROM members
    WHERE location_key IS NOT NULL
    ORDER BY
        opportunity_id,
        COALESCE(is_location_standardized, FALSE) DESC,
        is_primary_source DESC,
        source_authority_rank,
        completeness_score DESC,
        first_seen_at,
        source_identity_key,
        source_listing_id::TEXT
),

expected_skills AS (
    SELECT
        os.opportunity_id,
        JSONB_AGG(
            DISTINCT s.skill_name
            ORDER BY s.skill_name
        ) AS skills
    FROM {{ ref('silver_opportunity_sources') }} os
    JOIN {{ ref('silver_listing_skills') }} ls
        ON os.source_listing_id = ls.source_listing_id
    JOIN {{ ref('silver_skills') }} s
        ON ls.skill_key = s.skill_key
    GROUP BY os.opportunity_id
),

expected_categories AS (
    SELECT
        os.opportunity_id,
        JSONB_AGG(
            DISTINCT c.category_name
            ORDER BY c.category_name
        ) AS categories
    FROM {{ ref('silver_opportunity_sources') }} os
    JOIN {{ ref('silver_listing_categories') }} lc
        ON os.source_listing_id = lc.source_listing_id
    JOIN {{ ref('silver_categories') }} c
        ON lc.category_key = c.category_key
    GROUP BY os.opportunity_id
),

array_states AS (
    SELECT
        opportunity_id,
        BOOL_OR(required_skills_state = 'confirmed_empty')
            AS skills_empty,
        BOOL_OR(categories_state = 'confirmed_empty')
            AS categories_empty
    FROM members
    GROUP BY opportunity_id
),

known_work_modes AS (
    SELECT
        m.opportunity_id,
        m.source_listing_id,
        ARRAY_AGG(
            DISTINCT LOWER(BTRIM(e.val))
            ORDER BY LOWER(BTRIM(e.val))
        ) AS modes
    FROM members m
    CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS_TEXT(
        CASE
            WHEN JSONB_TYPEOF(m.work_modes) = 'array'
            THEN m.work_modes
            ELSE '[]'::JSONB
        END
    ) e(val)
    WHERE NOT (m.work_modes ? 'unknown')
      AND NULLIF(BTRIM(e.val), '') IS NOT NULL
    GROUP BY m.opportunity_id, m.source_listing_id
),

expected_conflicts AS (
    SELECT
        opportunity_id,
        COUNT(DISTINCT modes) > 1 AS work_modes_conflict
    FROM known_work_modes
    GROUP BY opportunity_id
),

actual AS (
    SELECT *
    FROM {{ ref('silver_opportunities') }}
)

SELECT
    a.opportunity_id,
    'experience_bundle_mismatch' AS failure
FROM actual a
LEFT JOIN expected_experience e USING (opportunity_id)
WHERE ROW(
    a.experience_level,
    a.experience_level_raw,
    a.experience_years_min,
    a.experience_years_max
) IS DISTINCT FROM ROW(
    e.experience_level,
    e.experience_level_raw,
    e.experience_years_min,
    e.experience_years_max
)

UNION ALL

SELECT
    a.opportunity_id,
    'location_bundle_mismatch'
FROM actual a
LEFT JOIN expected_location l USING (opportunity_id)
WHERE ROW(
    a.location_key,
    a.location_display,
    a.location_raw,
    a.standardized_city,
    a.standardized_governorate,
    a.standardized_country,
    a.country_code,
    a.is_online_location_label
) IS DISTINCT FROM ROW(
    l.location_key,
    l.location_display,
    l.location_raw,
    l.standardized_city,
    l.standardized_governorate,
    l.standardized_country,
    l.country_code,
    COALESCE(l.is_online_location_label, FALSE)
)

UNION ALL

SELECT
    a.opportunity_id,
    'canonical_skills_mismatch'
FROM actual a
LEFT JOIN expected_skills s USING (opportunity_id)
LEFT JOIN array_states st USING (opportunity_id)
WHERE a.required_skills IS DISTINCT FROM
    COALESCE(
        s.skills,
        CASE WHEN st.skills_empty THEN '[]'::JSONB END
    )

UNION ALL

SELECT
    a.opportunity_id,
    'canonical_categories_mismatch'
FROM actual a
LEFT JOIN expected_categories c USING (opportunity_id)
LEFT JOIN array_states st USING (opportunity_id)
WHERE a.categories IS DISTINCT FROM
    COALESCE(
        c.categories,
        CASE WHEN st.categories_empty THEN '[]'::JSONB END
    )

UNION ALL

SELECT
    a.opportunity_id,
    'work_modes_conflict_mismatch'
FROM actual a
LEFT JOIN expected_conflicts c USING (opportunity_id)
WHERE (a.conflicting_attributes ? 'work_modes')
    IS DISTINCT FROM
    COALESCE(c.work_modes_conflict, FALSE)