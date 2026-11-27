WITH ranked_members AS (
    SELECT
        os.opportunity_id,
        os.source_listing_id,
        os.is_primary_source,
        os.match_method,
        os.source_authority_rank,
        os.completeness_score,
        ROW_NUMBER() OVER (
            PARTITION BY os.opportunity_id
            ORDER BY
                os.is_primary_source DESC,
                os.source_authority_rank ASC,
                os.completeness_score DESC,
                sl.first_seen_at ASC,
                sl.source_identity_key ASC,
                sl.source_listing_id::TEXT ASC
        ) AS member_priority_rank,
        sl.source_name,
        sl.source_url,
        sl.title,
        sl.organization_key,
        sl.organization,
        sl.description,
        sl.opportunity_type,
        sl.location_key,
        sl.location_display,
        sl.location_raw,
        sl.standardized_city,
        sl.standardized_governorate,
        sl.standardized_country,
        sl.country_code,
        sl.is_online_location_label,
        sl.applicant_eligibility_raw,
        sl.work_modes,
        sl.work_modes_state,
        sl.employment_types,
        sl.employment_types_state,
        sl.categories,
        sl.categories_state,
        sl.required_skills,
        sl.required_skills_state,
        sl.experience_level,
        sl.experience_level_raw,
        sl.experience_years_min,
        sl.experience_years_max,
        sl.education_level,
        sl.requirements,
        sl.salary_min,
        sl.salary_max,
        sl.currency,
        sl.salary_period,
        sl.published_at,
        sl.published_at_raw,
        sl.published_at_precision,
        sl.deadline,
        sl.deadline_raw,
        sl.deadline_precision,
        sl.is_deadline_reliable,
        sl.observed_status,
        sl.effective_status,
        sl.effective_status_reason,
        sl.lifecycle_evaluated_at,
        sl.first_seen_at,
        sl.last_seen_at,
        sl.collected_at,
        CASE
            WHEN sl.employment_types IS NOT NULL
                 AND JSONB_TYPEOF(sl.employment_types) = 'array'
                 AND JSONB_ARRAY_LENGTH(sl.employment_types) > 0
                 AND NOT (sl.employment_types ? 'unknown') THEN
                (
                    SELECT STRING_AGG(LOWER(BTRIM(ev.val)), ',' ORDER BY LOWER(BTRIM(ev.val)))
                    FROM JSONB_ARRAY_ELEMENTS_TEXT(sl.employment_types) AS ev(val)
                    WHERE NULLIF(BTRIM(ev.val), '') IS NOT NULL
                )
            ELSE NULL
        END AS employment_types_signature
    FROM {{ ref('silver_opportunity_sources') }} os
    INNER JOIN {{ ref('silver_source_listings') }} sl
        ON os.source_listing_id = sl.source_listing_id
),

-- Correlated attribute bundle selectors (prevent cross-source field mismatches inside ranges/dates)
best_salary AS (
    SELECT
        opportunity_id,
        salary_min,
        salary_max,
        currency,
        salary_period,
        ROW_NUMBER() OVER (
            PARTITION BY opportunity_id
            ORDER BY member_priority_rank ASC
        ) AS rn
    FROM ranked_members
    WHERE salary_min IS NOT NULL OR salary_max IS NOT NULL
),

best_experience AS (
    SELECT
        opportunity_id,
        experience_level,
        experience_level_raw,
        experience_years_min,
        experience_years_max,
        ROW_NUMBER() OVER (
            PARTITION BY opportunity_id
            ORDER BY member_priority_rank ASC
        ) AS rn
    FROM ranked_members
    WHERE experience_level IS NOT NULL
       OR experience_years_min IS NOT NULL
       OR experience_years_max IS NOT NULL
),

best_published AS (
    SELECT
        opportunity_id,
        published_at,
        published_at_raw,
        published_at_precision,
        ROW_NUMBER() OVER (
            PARTITION BY opportunity_id
            ORDER BY
                (CASE WHEN published_at_precision = 'exact' THEN 1 WHEN published_at_precision = 'date_only' THEN 2 ELSE 3 END) ASC,
                member_priority_rank ASC
        ) AS rn
    FROM ranked_members
    WHERE published_at IS NOT NULL OR published_at_raw IS NOT NULL
),

best_deadline AS (
    SELECT
        opportunity_id,
        deadline,
        deadline_raw,
        deadline_precision,
        is_deadline_reliable,
        ROW_NUMBER() OVER (
            PARTITION BY opportunity_id
            ORDER BY
                (CASE WHEN deadline_precision = 'exact' THEN 1 WHEN deadline_precision = 'date_only' THEN 2 ELSE 3 END) ASC,
                member_priority_rank ASC
        ) AS rn
    FROM ranked_members
    WHERE deadline IS NOT NULL OR deadline_raw IS NOT NULL
),

best_location AS (
    SELECT
        opportunity_id,
        location_key,
        location_display,
        location_raw,
        standardized_city,
        standardized_governorate,
        standardized_country,
        country_code,
        is_online_location_label,
        ROW_NUMBER() OVER (
            PARTITION BY opportunity_id
            ORDER BY member_priority_rank ASC
        ) AS rn
    FROM ranked_members
    WHERE location_key IS NOT NULL
),

best_org AS (
    SELECT
        opportunity_id,
        organization_key,
        organization,
        ROW_NUMBER() OVER (
            PARTITION BY opportunity_id
            ORDER BY member_priority_rank ASC
        ) AS rn
    FROM ranked_members
    WHERE organization_key IS NOT NULL
),

-- Canonical union of standardized work_modes respecting Data Contract §5.2 ('unknown' exclusivity)
work_modes_expanded AS (
    SELECT DISTINCT
        rm.opportunity_id,
        LOWER(BTRIM(elem.val)) AS val
    FROM ranked_members rm
    CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS_TEXT(rm.work_modes) AS elem(val)
    WHERE rm.work_modes IS NOT NULL
      AND JSONB_TYPEOF(rm.work_modes) = 'array'
      AND JSONB_ARRAY_LENGTH(rm.work_modes) > 0
      AND NULLIF(BTRIM(elem.val), '') IS NOT NULL
),

work_modes_merged AS (
    SELECT
        e.opportunity_id,
        JSONB_AGG(e.val ORDER BY e.val) AS canonical_work_modes
    FROM work_modes_expanded e
    WHERE e.val <> 'unknown'
       OR NOT EXISTS (
           SELECT 1
           FROM work_modes_expanded e2
           WHERE e2.opportunity_id = e.opportunity_id
             AND e2.val <> 'unknown'
       )
    GROUP BY e.opportunity_id
),

-- Canonical union of standardized employment_types respecting Data Contract §5.2 ('unknown' exclusivity)
employment_types_expanded AS (
    SELECT DISTINCT
        rm.opportunity_id,
        LOWER(BTRIM(elem.val)) AS val
    FROM ranked_members rm
    CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS_TEXT(rm.employment_types) AS elem(val)
    WHERE rm.employment_types IS NOT NULL
      AND JSONB_TYPEOF(rm.employment_types) = 'array'
      AND JSONB_ARRAY_LENGTH(rm.employment_types) > 0
      AND NULLIF(BTRIM(elem.val), '') IS NOT NULL
),

employment_types_merged AS (
    SELECT
        e.opportunity_id,
        JSONB_AGG(e.val ORDER BY e.val) AS canonical_employment_types
    FROM employment_types_expanded e
    WHERE e.val <> 'unknown'
       OR NOT EXISTS (
           SELECT 1
           FROM employment_types_expanded e2
           WHERE e2.opportunity_id = e.opportunity_id
             AND e2.val <> 'unknown'
       )
    GROUP BY e.opportunity_id
),

-- Canonical union of normalized categories from silver_listing_categories
categories_merged AS (
    SELECT
        os.opportunity_id,
        JSONB_AGG(DISTINCT lc.category_name ORDER BY lc.category_name) AS canonical_categories
    FROM {{ ref('silver_opportunity_sources') }} os
    INNER JOIN {{ ref('silver_listing_categories') }} lc
        ON os.source_listing_id = lc.source_listing_id
    GROUP BY os.opportunity_id
),

-- Canonical union of normalized skills from silver_listing_skills
skills_merged AS (
    SELECT
        os.opportunity_id,
        JSONB_AGG(DISTINCT ls.skill_name ORDER BY ls.skill_name) AS canonical_required_skills
    FROM {{ ref('silver_opportunity_sources') }} os
    INNER JOIN {{ ref('silver_listing_skills') }} ls
        ON os.source_listing_id = ls.source_listing_id
    GROUP BY os.opportunity_id
),

-- Group-level aggregations, attribution arrays, lifecycle synthesis, and explicit conflict detection
group_agg AS (
    SELECT
        opportunity_id,
        COUNT(*) AS source_count,
        JSONB_AGG(DISTINCT source_name ORDER BY source_name) AS source_names,
        JSONB_AGG(DISTINCT match_method ORDER BY match_method) AS match_methods_present,
        JSONB_AGG(
            JSONB_BUILD_OBJECT(
                'source_name', source_name,
                'source_listing_id', source_listing_id::TEXT,
                'source_url', source_url,
                'is_primary_source', is_primary_source,
                'match_method', match_method,
                'effective_status', effective_status
            )
            ORDER BY member_priority_rank ASC
        ) AS all_source_urls,
        JSONB_AGG(DISTINCT effective_status ORDER BY effective_status) AS observed_effective_statuses,

        -- Conservative canonical effective_status: explicit closed > expired > active > unknown (ADR-047)
        CASE
            WHEN BOOL_OR(effective_status = 'closed') THEN 'closed'
            WHEN BOOL_OR(effective_status = 'expired') THEN 'expired'
            WHEN BOOL_OR(effective_status = 'active') THEN 'active'
            ELSE 'unknown'
        END AS effective_status,

        -- Non-null fallback text attributes ordered by member_priority_rank
        (ARRAY_AGG(description ORDER BY member_priority_rank ASC) FILTER (WHERE description IS NOT NULL))[1] AS best_description,
        (ARRAY_AGG(requirements ORDER BY member_priority_rank ASC) FILTER (WHERE requirements IS NOT NULL))[1] AS best_requirements,
        (ARRAY_AGG(education_level ORDER BY member_priority_rank ASC) FILTER (WHERE education_level IS NOT NULL))[1] AS best_education_level,
        (ARRAY_AGG(applicant_eligibility_raw ORDER BY member_priority_rank ASC) FILTER (WHERE applicant_eligibility_raw IS NOT NULL))[1] AS best_applicant_eligibility_raw,

        -- Array empty/missing awareness
        BOOL_OR(work_modes_state = 'confirmed_empty') AS any_work_modes_confirmed_empty,
        BOOL_OR(employment_types_state = 'confirmed_empty') AS any_employment_types_confirmed_empty,
        BOOL_OR(categories_state = 'confirmed_empty') AS any_categories_confirmed_empty,
        BOOL_OR(required_skills_state = 'confirmed_empty') AS any_required_skills_confirmed_empty,

        -- Explicit source attribute conflict flags (never silently discard conflicts)
        (COUNT(DISTINCT LOWER(title)) > 1) AS conflict_title,
        (COUNT(DISTINCT organization_key) FILTER (WHERE organization_key IS NOT NULL) > 1) AS conflict_organization,
        (COUNT(DISTINCT opportunity_type) > 1) AS conflict_opportunity_type,
        (COUNT(DISTINCT location_key) FILTER (WHERE location_key IS NOT NULL) > 1) AS conflict_location,
        (COUNT(DISTINCT effective_status) > 1) AS conflict_effective_status,
        -- Fix 6: ADR-019 numeric scale normalization (TRIM_SCALE) + currency + salary_period
        (
            COUNT(
                DISTINCT
                COALESCE(
                    CASE
                        WHEN salary_min IS NULL THEN ''
                        WHEN salary_min = 0 THEN '0'
                        ELSE TRIM_SCALE(salary_min)::TEXT
                    END,
                    ''
                )
                || ':' ||
                COALESCE(
                    CASE
                        WHEN salary_max IS NULL THEN ''
                        WHEN salary_max = 0 THEN '0'
                        ELSE TRIM_SCALE(salary_max)::TEXT
                    END,
                    ''
                )
                || ':' || COALESCE(UPPER(currency), '')
                || ':' || COALESCE(LOWER(salary_period), '')
            )
            FILTER (WHERE salary_min IS NOT NULL OR salary_max IS NOT NULL) > 1
        ) AS conflict_salary,
        -- Conflict detection for differing populated known employment_types across merged sources
        (COUNT(DISTINCT employment_types_signature) FILTER (WHERE employment_types_signature IS NOT NULL) > 1) AS conflict_employment_types,
        (
            COUNT(DISTINCT deadline)
            FILTER (WHERE deadline IS NOT NULL AND deadline_precision IN ('exact', 'date_only')) > 1
        ) AS conflict_deadline,

        -- Lineage timestamps across all merged sources
        MIN(first_seen_at) AS first_seen_at,
        MAX(last_seen_at) AS last_seen_at,
        MAX(collected_at) AS latest_collected_at,
        MAX(lifecycle_evaluated_at) AS lifecycle_evaluated_at

    FROM ranked_members
    GROUP BY opportunity_id
),

primary_member AS (
    SELECT *
    FROM ranked_members
    WHERE is_primary_source
),

conflicts_built AS (
    SELECT
        ga.*,
        ARRAY_REMOVE(
            ARRAY[
                CASE WHEN ga.conflict_title THEN 'title' END,
                CASE WHEN ga.conflict_organization THEN 'organization' END,
                CASE WHEN ga.conflict_opportunity_type THEN 'opportunity_type' END,
                CASE WHEN ga.conflict_location THEN 'location' END,
                CASE WHEN ga.conflict_effective_status THEN 'effective_status' END,
                CASE WHEN ga.conflict_salary THEN 'salary' END,
                CASE WHEN ga.conflict_employment_types THEN 'employment_types' END,
                CASE WHEN ga.conflict_deadline THEN 'deadline' END
            ],
            NULL
        ) AS conflict_list
    FROM group_agg ga
)

SELECT
    -- Canonical identity
    pm.opportunity_id,

    -- Primary source attribution + multi-source summary
    pm.source_listing_id AS primary_source_listing_id,
    pm.source_name AS primary_source_name,
    pm.source_url AS primary_source_url,
    cb.source_count,
    cb.source_names,
    cb.all_source_urls,
    cb.match_methods_present,

    -- Canonical opportunity attributes (primary preferred with deterministic non-null secondary fallback)
    pm.title,
    bo.organization_key,
    bo.organization,
    cb.best_description AS description,
    pm.opportunity_type,

    -- Canonical opportunity location
    bl.location_key,
    bl.location_display,
    bl.location_raw,
    bl.standardized_city,
    bl.standardized_governorate,
    bl.standardized_country,
    bl.country_code,
    COALESCE(bl.is_online_location_label, FALSE) AS is_online_location_label,
    cb.best_applicant_eligibility_raw AS applicant_eligibility_raw,

    -- Canonical merged JSONB arrays (preserving NULL vs confirmed [] semantics)
    CASE
        WHEN wm.canonical_work_modes IS NOT NULL THEN wm.canonical_work_modes
        WHEN cb.any_work_modes_confirmed_empty THEN '[]'::JSONB
        ELSE NULL
    END AS work_modes,
    CASE
        WHEN et.canonical_employment_types IS NOT NULL THEN et.canonical_employment_types
        WHEN cb.any_employment_types_confirmed_empty THEN '[]'::JSONB
        ELSE NULL
    END AS employment_types,
    CASE
        WHEN cm.canonical_categories IS NOT NULL THEN cm.canonical_categories
        WHEN cb.any_categories_confirmed_empty THEN '[]'::JSONB
        ELSE NULL
    END AS categories,
    CASE
        WHEN sm.canonical_required_skills IS NOT NULL THEN sm.canonical_required_skills
        WHEN cb.any_required_skills_confirmed_empty THEN '[]'::JSONB
        ELSE NULL
    END AS required_skills,

    -- Correlated qualification and salary bundles
    be.experience_level,
    be.experience_level_raw,
    be.experience_years_min,
    be.experience_years_max,
    cb.best_education_level AS education_level,
    cb.best_requirements AS requirements,
    bs.salary_min,
    bs.salary_max,
    bs.currency,
    bs.salary_period,

    -- Correlated date bundles
    bp.published_at,
    bp.published_at_raw,
    bp.published_at_precision,
    bd.deadline,
    bd.deadline_raw,
    bd.deadline_precision,
    COALESCE(bd.is_deadline_reliable, FALSE) AS is_deadline_reliable,

    -- Lifecycle status (canonical conservative status + primary status + full observed set)
    cb.effective_status,
    pm.effective_status AS primary_effective_status,
    pm.observed_status AS primary_observed_status,
    cb.observed_effective_statuses,
    cb.lifecycle_evaluated_at,

    -- Explicit cross-source attribute conflict transparency
    (COALESCE(ARRAY_LENGTH(cb.conflict_list, 1), 0) > 0) AS has_source_attribute_conflicts,
    TO_JSONB(COALESCE(cb.conflict_list, ARRAY[]::TEXT[])) AS conflicting_attributes,

    -- Lineage timestamps
    cb.first_seen_at,
    cb.last_seen_at,
    cb.latest_collected_at

FROM primary_member pm
INNER JOIN conflicts_built cb
    ON pm.opportunity_id = cb.opportunity_id
LEFT JOIN best_org bo
    ON pm.opportunity_id = bo.opportunity_id
   AND bo.rn = 1
LEFT JOIN best_location bl
    ON pm.opportunity_id = bl.opportunity_id
   AND bl.rn = 1
LEFT JOIN best_salary bs
    ON pm.opportunity_id = bs.opportunity_id
   AND bs.rn = 1
LEFT JOIN best_experience be
    ON pm.opportunity_id = be.opportunity_id
   AND be.rn = 1
LEFT JOIN best_published bp
    ON pm.opportunity_id = bp.opportunity_id
   AND bp.rn = 1
LEFT JOIN best_deadline bd
    ON pm.opportunity_id = bd.opportunity_id
   AND bd.rn = 1
LEFT JOIN work_modes_merged wm
    ON pm.opportunity_id = wm.opportunity_id
LEFT JOIN employment_types_merged et
    ON pm.opportunity_id = et.opportunity_id
LEFT JOIN categories_merged cm
    ON pm.opportunity_id = cm.opportunity_id
LEFT JOIN skills_merged sm
    ON pm.opportunity_id = sm.opportunity_id
