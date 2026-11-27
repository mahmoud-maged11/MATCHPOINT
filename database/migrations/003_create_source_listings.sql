-- MATCHPOINT Data Warehouse
-- Migration: 003
-- Purpose: Store the latest accepted source listings

BEGIN;

CREATE TABLE bronze.source_listings (

    -- Source identity

    source_listing_id UUID PRIMARY KEY
        DEFAULT gen_random_uuid(),

    source_name VARCHAR(50) NOT NULL
        CHECK (source_name IN (
            'wuzzuf',
            'forasna',
            'egyincs',
            'itida',
            'nti',
            'bayt',
            'devpost',
            'un_volunteers'
        )),

    source_opportunity_id TEXT NOT NULL
        CHECK (BTRIM(source_opportunity_id) <> ''),

    source_identity_key TEXT NOT NULL,

    source_url TEXT NOT NULL
        CHECK (BTRIM(source_url) <> ''),


    -- Basic opportunity information

    title TEXT NOT NULL
        CHECK (BTRIM(title) <> ''),

    organization TEXT,

    description TEXT,

    opportunity_type VARCHAR(30) NOT NULL
        CHECK (opportunity_type IN (
            'job',
            'internship',
            'graduate_program',
            'training',
            'scholarship',
            'competition',
            'hackathon',
            'freelance',
            'volunteering',
            'event'
        )),


    -- Location and work classification

    location TEXT,

    work_modes JSONB,

    employment_types JSONB,

    categories JSONB,


    -- Experience and qualifications

    experience_level VARCHAR(20)
        CHECK (experience_level IN (
            'entry_level',
            'junior',
            'mid_level',
            'senior',
            'lead',
            'manager',
            'executive',
            'unknown'
        )),

    experience_level_raw TEXT,

    experience_years_min NUMERIC
        CHECK (experience_years_min >= 0),

    experience_years_max NUMERIC
        CHECK (experience_years_max >= 0),

    education_level TEXT,

    required_skills JSONB,

    requirements TEXT,


    -- Salary information

    salary_min NUMERIC
        CHECK (salary_min >= 0),

    salary_max NUMERIC
        CHECK (salary_max >= 0),

    currency VARCHAR(3)
        CHECK (currency ~ '^[A-Z]{3}$'),

    salary_period VARCHAR(20)
        CHECK (salary_period IN (
            'hourly',
            'daily',
            'weekly',
            'monthly',
            'yearly',
            'project',
            'unknown'
        )),


    -- Publication and deadline dates

    published_at TIMESTAMPTZ,

    published_at_raw TEXT,

    published_at_precision VARCHAR(20)
        CHECK (published_at_precision IN (
            'exact',
            'date_only',
            'relative',
            'unknown'
        )),

    deadline TIMESTAMPTZ,

    deadline_raw TEXT,

    deadline_precision VARCHAR(20)
        CHECK (deadline_precision IN (
            'exact',
            'date_only',
            'relative',
            'unknown'
        )),


    -- Observed opportunity status

    status VARCHAR(20) NOT NULL DEFAULT 'unknown'
        CHECK (status IN (
            'active',
            'expired',
            'closed',
            'unknown'
        )),

    source_status_raw TEXT,


    -- Ingestion and versioning metadata

    collected_at TIMESTAMPTZ NOT NULL,

    first_seen_at TIMESTAMPTZ NOT NULL,

    last_seen_at TIMESTAMPTZ NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    content_hash TEXT NOT NULL
        CHECK (content_hash ~ '^[0-9a-f]{64}$'),

    hash_version INTEGER NOT NULL DEFAULT 1
        CHECK (hash_version = 1),

    content_version INTEGER NOT NULL DEFAULT 1
        CHECK (content_version >= 1),

    last_collection_run_id UUID NOT NULL
        REFERENCES bronze.collection_runs(run_id),


    -- Retained source data

    raw_payload JSONB NOT NULL
        CHECK (JSONB_TYPEOF(raw_payload) = 'object'),


    -- Identity constraints

    CONSTRAINT uq_source_listing_identity
        UNIQUE (source_name, source_identity_key),

    CONSTRAINT chk_source_identity_key
        CHECK (
            source_identity_key =
            'id:' || source_opportunity_id
        ),


    -- Numeric range constraints

    CONSTRAINT chk_experience_range
        CHECK (
            experience_years_min IS NULL
            OR experience_years_max IS NULL
            OR experience_years_min <= experience_years_max
        ),

    CONSTRAINT chk_salary_range
        CHECK (
            salary_min IS NULL
            OR salary_max IS NULL
            OR salary_min <= salary_max
        ),


    -- JSON array constraints

    CONSTRAINT chk_work_modes_array
        CHECK (JSONB_TYPEOF(work_modes) = 'array'),

    CONSTRAINT chk_employment_types_array
        CHECK (JSONB_TYPEOF(employment_types) = 'array'),

    CONSTRAINT chk_categories_array
        CHECK (JSONB_TYPEOF(categories) = 'array'),

    CONSTRAINT chk_required_skills_array
        CHECK (JSONB_TYPEOF(required_skills) = 'array'),


    -- Observation timestamp constraints

    CONSTRAINT chk_listing_seen_dates
        CHECK (
            first_seen_at <= collected_at
            AND collected_at = last_seen_at
        ),

    CONSTRAINT chk_listing_storage_dates
        CHECK (updated_at >= created_at)
);


-- Indexes

CREATE INDEX idx_source_listings_source_status
    ON bronze.source_listings (source_name, status);

CREATE INDEX idx_source_listings_last_seen
    ON bronze.source_listings (last_seen_at DESC);

CREATE INDEX idx_source_listings_deadline
    ON bronze.source_listings (deadline)
    WHERE deadline IS NOT NULL;

CREATE INDEX idx_source_listings_last_run
    ON bronze.source_listings (last_collection_run_id);

COMMIT;