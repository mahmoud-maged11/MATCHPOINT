{{
    config(
        indexes=[
            {'columns': ['opportunity_id'], 'unique': True},
            {'columns': ['effective_status', 'opportunity_type']},
            {'columns': ['organization_key']},
            {'columns': ['location_key']},
            {'columns': ['primary_source_name']},
            {'columns': ['published_date_key']}
        ]
    )
}}

SELECT
    -- Canonical primary key and foreign keys
    o.opportunity_id,
    o.primary_source_listing_id,
    o.primary_source_name,
    o.primary_source_url,
    o.organization_key,
    o.location_key,

    -- Reliable calendar date foreign keys.
    -- Exact timestamps use UTC dates; date-only values use source calendar dates.
    CAST(
        TO_CHAR(o.published_calendar_date, 'YYYYMMDD')
        AS INTEGER
    ) AS published_date_key,
    CAST(
        TO_CHAR(o.deadline_calendar_date, 'YYYYMMDD')
        AS INTEGER
    ) AS deadline_date_key,
    CAST(TO_CHAR(o.first_seen_at AT TIME ZONE 'UTC', 'YYYYMMDD') AS INTEGER) AS first_seen_date_key,
    CAST(TO_CHAR(o.last_seen_at AT TIME ZONE 'UTC', 'YYYYMMDD') AS INTEGER) AS last_seen_date_key,

    -- Core canonical business attributes
    o.title,
    o.organization,
    o.description,
    o.opportunity_type,
    o.location_display,
    o.standardized_city,
    o.standardized_governorate,
    o.standardized_country,
    o.country_code,
    o.is_online_location_label,
    o.applicant_eligibility_raw,

    -- Qualifications and salary measures (never averaged across currencies or periods)
    o.experience_level,
    o.experience_level_raw,
    o.experience_years_min,
    o.experience_years_max,
    o.education_level,
    o.requirements,
    o.salary_min,
    o.salary_max,
    CASE
        WHEN o.salary_min IS NOT NULL AND o.salary_max IS NOT NULL THEN
            ROUND(((o.salary_min + o.salary_max) / 2.0)::NUMERIC, 2)
        ELSE NULL
    END AS salary_midpoint,
    o.currency,
    o.salary_period,

    -- Dates and precision
    o.published_at,
    o.published_at_raw,
    o.published_at_precision,
    o.deadline,
    o.deadline_raw,
    o.deadline_precision,
    o.is_deadline_reliable,

    -- Lifecycle status and analytical indicator flags
    o.effective_status,
    o.primary_effective_status,
    o.primary_observed_status,
    o.observed_effective_statuses,
    o.lifecycle_evaluated_at,
    (o.effective_status = 'active') AS is_active,
    (o.effective_status = 'expired') AS is_expired,
    (o.effective_status = 'closed') AS is_closed,
    (o.effective_status = 'unknown') AS is_unknown_status,
    (o.salary_min IS NOT NULL OR o.salary_max IS NOT NULL) AS has_disclosed_salary,
    (o.source_count > 1) AS is_multi_source,

    -- Source attribution, deduplication count, and conflict transparency
    o.source_count,
    o.source_names,
    o.all_source_urls,
    o.match_methods_present,
    o.has_source_attribute_conflicts,
    o.conflicting_attributes,

    -- Preserved canonical JSONB arrays for Backend / API consumption
    o.work_modes,
    o.employment_types,
    o.categories,
    o.required_skills,

    -- Lineage timestamps
    o.first_seen_at,
    o.last_seen_at,
    o.latest_collected_at

FROM {{ ref('silver_opportunities') }} o
