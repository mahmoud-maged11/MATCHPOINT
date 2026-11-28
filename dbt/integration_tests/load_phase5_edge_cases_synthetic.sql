-- MATCHPOINT Phase 5 Edge-Case Synthetic Bronze Fixture Loader
--
-- PURPOSE:
--   Appends 11 deterministic edge-case listings + 3 edge-case collection runs into Bronze
--   on an explicitly authorized isolated test database WITHOUT disturbing the 41 Phase 4 baseline listings.
--   Closes all 7 testing gaps identified in the Phase 4 & Phase 5 independent audit:
--     EC1/EC2 : Extreme outlier dates (1970-01-01, 2099-12-31, 9999-12-31) -> bounded dim_dates + FK resolution
--     EC3     : Past exact deadline -> effective_status = 'expired'
--     EC4     : Past date_only deadline -> effective_status = 'expired'
--     EC5     : Explicitly closed listing with future deadline -> effective_status = 'closed'
--     EC6     : Relative published_at & relative deadline -> excluded from trends & not falsely expired
--     EC7     : NULL location -> explicit 'unreported' bucket in mart_opportunities_by_location
--     EC8     : Confirmed empty [] JSONB arrays -> 0 bridge rows + 'unreported' in work_mode/employment_type marts
--     EC9     : devpost (hackathon) & un_volunteers (volunteering) non-zero source coverage
--     EC10    : One-sided salary (salary_min only) + multi work_modes & multi employment_types (zero Cartesian)
--     EC11    : Collection run counter anomaly (records_invalid > records_received -> flagged, rate = NULL)

BEGIN;

DO $$
BEGIN
    IF current_setting('matchpoint.expected_test_database', TRUE) IS NULL
       OR current_setting('matchpoint.expected_test_database', TRUE) NOT IN (
           'matchpoint_test',
           'matchpoint_dbt_review_test', 'matchpoint_date_contract_test', 'matchpoint_date_contract_utf8_test'
       )
       OR current_database() IS DISTINCT FROM
           current_setting('matchpoint.expected_test_database', TRUE) THEN
        RAISE EXCEPTION
            'SAFETY ABORT: Expected authorized test database %, connected to %',
            current_setting('matchpoint.expected_test_database', TRUE),
            current_database();
    END IF;

    RAISE NOTICE
        'PASS SAFETY GUARD: Connected to %',
        current_database();
END;
$$;

-- Clean prior edge-case rows only (preserves synthetic_phase4 baseline rows)
DELETE FROM bronze.source_listing_history
WHERE collection_run_id IN (
    SELECT run_id FROM bronze.collection_runs WHERE collection_scope = 'synthetic_phase5_edge'
);

DELETE FROM bronze.ingestion_observations
WHERE collection_run_id IN (
    SELECT run_id FROM bronze.collection_runs WHERE collection_scope = 'synthetic_phase5_edge'
);

DELETE FROM bronze.invalid_records
WHERE collection_run_id IN (
    SELECT run_id FROM bronze.collection_runs WHERE collection_scope = 'synthetic_phase5_edge'
);

DELETE FROM bronze.source_listings
WHERE last_collection_run_id IN (
    SELECT run_id FROM bronze.collection_runs WHERE collection_scope = 'synthetic_phase5_edge'
);

DELETE FROM bronze.collection_runs
WHERE collection_scope = 'synthetic_phase5_edge';

-- 1. Insert edge-case collection runs (including one counter-anomaly run for EC11)
INSERT INTO bronze.collection_runs (
    run_id, source_name, collection_scope, collection_mode, status,
    started_at, finished_at,
    records_received, records_inserted, records_updated, records_unchanged, records_invalid,
    contract_version, hash_version
)
VALUES
    ('11111111-1111-4111-8111-000000000201'::UUID, 'devpost',       'synthetic_phase5_edge', 'api', 'completed',
     '2026-11-21T09:00:00Z', '2026-11-21T09:04:00Z', 10, 1, 0, 9, 0, '3.0.0', 1),
    ('11111111-1111-4111-8111-000000000202'::UUID, 'un_volunteers', 'synthetic_phase5_edge', 'api', 'completed',
     '2026-11-21T09:10:00Z', '2026-11-21T09:12:00Z', 6, 1, 0, 5, 0, '3.0.0', 1),
    ('11111111-1111-4111-8111-000000000203'::UUID, 'wuzzuf',        'synthetic_phase5_edge', 'api', 'partial',
     '2026-11-21T10:00:00Z', '2026-11-21T10:05:00Z', 5, 5, 0, 0, 8, '3.0.0', 1);

-- 2. Insert 11 isolated edge-case listings (UUIDs 2001..2011)
INSERT INTO bronze.source_listings (
    source_listing_id, source_name, source_opportunity_id, source_identity_key, source_url,
    title, organization, opportunity_type, location,
    work_modes, employment_types, categories, required_skills,
    salary_min, salary_max, currency, salary_period,
    published_at, published_at_raw, published_at_precision,
    deadline, deadline_raw, deadline_precision,
    status, collected_at, first_seen_at, last_seen_at,
    content_hash, hash_version, content_version, last_collection_run_id, raw_payload
)
VALUES
    -- EC1: Outlier published_at = 1970-01-01 (exact) & deadline = 2099-12-31 (exact)
    ('22222222-2222-4222-8222-000000002001'::UUID, 'wuzzuf', 'edge-ec1', 'id:edge-ec1',
     'https://wuzzuf.net/jobs/p/edge-ec1-outlier-1970-2099',
     'Edge Case Outlier Dates 1970-2099 Engineer', 'EdgeOrg Alpha', 'job', 'Cairo, Egypt',
     '["on_site"]'::JSONB, '["full_time"]'::JSONB, '["Software Engineering"]'::JSONB, '["SQL"]'::JSONB,
     NULL, NULL, NULL, NULL,
     '1970-01-01T00:00:00Z', '1970-01-01T00:00:00Z', 'exact',
     '2099-12-31T23:59:59Z', '2099-12-31T23:59:59Z', 'exact',
     'active', '2026-11-21T10:01:00Z', '2026-11-21T10:01:00Z', '2026-11-21T10:01:00Z',
     REPEAT('a', 64), 1, 1, '11111111-1111-4111-8111-000000000203'::UUID, '{"edge_case": "ec1_outlier_dates"}'::JSONB),

    -- EC2: Extreme outlier deadline = 9999-12-31 (date_only)
    ('22222222-2222-4222-8222-000000002002'::UUID, 'wuzzuf', 'edge-ec2', 'id:edge-ec2',
     'https://wuzzuf.net/jobs/p/edge-ec2-outlier-9999',
     'Edge Case Extreme Deadline 9999 Architect', 'EdgeOrg Beta', 'job', 'Alexandria, Egypt',
     '["hybrid"]'::JSONB, '["full_time"]'::JSONB, '["Architecture"]'::JSONB, '["PostgreSQL"]'::JSONB,
     NULL, NULL, NULL, NULL,
     NULL, '2026-11-15', 'date_only',
     NULL, '9999-12-31', 'date_only',
     'active', '2026-11-21T10:01:00Z', '2026-11-21T10:01:00Z', '2026-11-21T10:01:00Z',
     REPEAT('b', 64), 1, 1, '11111111-1111-4111-8111-000000000203'::UUID, '{"edge_case": "ec2_deadline_9999"}'::JSONB),

    -- EC3: Expired via past EXACT deadline (Bronze status = 'active' -> Gold effective_status = 'expired')
    ('22222222-2222-4222-8222-000000002003'::UUID, 'wuzzuf', 'edge-ec3', 'id:edge-ec3',
     'https://wuzzuf.net/jobs/p/edge-ec3-expired-exact',
     'Edge Case Expired Exact Deadline Analyst', 'EdgeOrg Gamma', 'job', 'Cairo, Egypt',
     '["on_site"]'::JSONB, '["full_time"]'::JSONB, '["Analytics"]'::JSONB, NULL,
     NULL, NULL, NULL, NULL,
     '2025-01-01T10:00:00Z', '2025-01-01T10:00:00Z', 'exact',
     '2025-01-15T12:00:00Z', '2025-01-15T12:00:00Z', 'exact',
     'active', '2026-11-21T10:01:00Z', '2026-11-21T10:01:00Z', '2026-11-21T10:01:00Z',
     REPEAT('c', 64), 1, 1, '11111111-1111-4111-8111-000000000203'::UUID, '{"edge_case": "ec3_expired_exact"}'::JSONB),

    -- EC4: Expired via past DATE_ONLY deadline (Bronze status = 'active' -> Gold effective_status = 'expired')
    ('22222222-2222-4222-8222-000000002004'::UUID, 'wuzzuf', 'edge-ec4', 'id:edge-ec4',
     'https://wuzzuf.net/jobs/p/edge-ec4-expired-date-only',
     'Edge Case Expired DateOnly Deadline Intern', 'EdgeOrg Delta', 'internship', 'Giza, Egypt',
     '["hybrid"]'::JSONB, '["part_time"]'::JSONB, '["Internship"]'::JSONB, NULL,
     NULL, NULL, NULL, NULL,
     NULL, '2025-06-01', 'date_only',
     NULL, '2025-06-30', 'date_only',
     'active', '2026-11-21T10:01:00Z', '2026-11-21T10:01:00Z', '2026-11-21T10:01:00Z',
     REPEAT('d', 64), 1, 1, '11111111-1111-4111-8111-000000000203'::UUID, '{"edge_case": "ec4_expired_date_only"}'::JSONB),

    -- EC5: Explicitly CLOSED listing with future deadline -> effective_status = 'closed'
    ('22222222-2222-4222-8222-000000002005'::UUID, 'wuzzuf', 'edge-ec5', 'id:edge-ec5',
     'https://wuzzuf.net/jobs/p/edge-ec5-closed-explicit',
     'Edge Case Explicitly Closed Specialist', 'EdgeOrg Epsilon', 'job', 'Cairo, Egypt',
     '["on_site"]'::JSONB, '["full_time"]'::JSONB, NULL, NULL,
     NULL, NULL, NULL, NULL,
     NULL, '2026-11-10', 'date_only',
     NULL, '2028-06-30', 'date_only',
     'closed', '2026-11-21T10:01:00Z', '2026-11-21T10:01:00Z', '2026-11-21T10:01:00Z',
     REPEAT('e', 64), 1, 1, '11111111-1111-4111-8111-000000000203'::UUID, '{"edge_case": "ec5_closed"}'::JSONB),

    -- EC6: RELATIVE published_at & RELATIVE past deadline (must NOT enter trends & must NOT falsely expire)
    ('22222222-2222-4222-8222-000000002006'::UUID, 'wuzzuf', 'edge-ec6', 'id:edge-ec6',
     'https://wuzzuf.net/jobs/p/edge-ec6-relative-dates',
     'Edge Case Relative Dates Coordinator', 'EdgeOrg Zeta', 'job', 'Cairo, Egypt',
     '["remote"]'::JSONB, '["full_time"]'::JSONB, NULL, NULL,
     NULL, NULL, NULL, NULL,
     '2026-11-18T00:00:00Z', '3 days ago', 'relative',
     '2025-01-01T00:00:00Z', 'closes soon', 'relative',
     'active', '2026-11-21T10:01:00Z', '2026-11-21T10:01:00Z', '2026-11-21T10:01:00Z',
     REPEAT('f', 64), 1, 1, '11111111-1111-4111-8111-000000000203'::UUID, '{"edge_case": "ec6_relative"}'::JSONB),

    -- EC7: NULL location -> explicit 'unreported' bucket in mart_opportunities_by_location
    ('22222222-2222-4222-8222-000000002007'::UUID, 'wuzzuf', 'edge-ec7', 'id:edge-ec7',
     'https://wuzzuf.net/jobs/p/edge-ec7-null-location',
     'Edge Case Null Location Consultant', 'EdgeOrg Eta', 'job', NULL,
     '["remote"]'::JSONB, '["contract"]'::JSONB, NULL, NULL,
     NULL, NULL, NULL, NULL,
     NULL, '2026-11-16', 'date_only',
     NULL, NULL, NULL,
     'active', '2026-11-21T10:01:00Z', '2026-11-21T10:01:00Z', '2026-11-21T10:01:00Z',
     REPEAT('0', 63) || '1', 1, 1, '11111111-1111-4111-8111-000000000203'::UUID, '{"edge_case": "ec7_null_location"}'::JSONB),

    -- EC8: Confirmed EMPTY [] JSONB arrays -> 0 bridge rows + 'unreported' in work_mode & employment_type marts
    ('22222222-2222-4222-8222-000000002008'::UUID, 'wuzzuf', 'edge-ec8', 'id:edge-ec8',
     'https://wuzzuf.net/jobs/p/edge-ec8-empty-arrays',
     'Edge Case Confirmed Empty Arrays Fellow', 'EdgeOrg Theta', 'scholarship', 'Cairo, Egypt',
     '[]'::JSONB, '[]'::JSONB, '[]'::JSONB, '[]'::JSONB,
     NULL, NULL, NULL, NULL,
     NULL, '2026-11-17', 'date_only',
     NULL, NULL, NULL,
     'active', '2026-11-21T10:01:00Z', '2026-11-21T10:01:00Z', '2026-11-21T10:01:00Z',
     REPEAT('0', 63) || '2', 1, 1, '11111111-1111-4111-8111-000000000203'::UUID, '{"edge_case": "ec8_empty_arrays"}'::JSONB),

    -- EC9A: devpost hackathon record
    ('22222222-2222-4222-8222-000000002009'::UUID, 'devpost', 'edge-ec9-devpost', 'id:edge-ec9-devpost',
     'https://devpost.com/hackathons/edge-ec9-mena-ai-hack',
     'MENA AI Builders Hackathon 2026', 'Devpost Community', 'hackathon', 'Online',
     '["remote"]'::JSONB, NULL, '["AI & Machine Learning"]'::JSONB, '["Python", "Docker"]'::JSONB,
     NULL, NULL, NULL, NULL,
     NULL, '2026-11-12', 'date_only',
     '2027-02-28T23:59:00Z', '2027-02-28T23:59:00Z', 'exact',
     'active', '2026-11-21T09:02:00Z', '2026-11-21T09:02:00Z', '2026-11-21T09:02:00Z',
     REPEAT('0', 63) || '3', 1, 1, '11111111-1111-4111-8111-000000000201'::UUID, '{"edge_case": "ec9_devpost"}'::JSONB),

    -- EC9B: un_volunteers volunteering record
    ('22222222-2222-4222-8222-000000002010'::UUID, 'un_volunteers', 'edge-ec9-unv', 'id:edge-ec9-unv',
     'https://app.unv.org/opportunities/edge-ec9-egypt-data-volunteer',
     'UNV Digital Data Literacy Volunteer Egypt', 'UN Volunteers Egypt', 'volunteering', 'Cairo, Egypt',
     '["remote"]'::JSONB, NULL, '["Community Development"]'::JSONB, '["Excel"]'::JSONB,
     NULL, NULL, NULL, NULL,
     NULL, '2026-11-14', 'date_only',
     NULL, '2027-03-15', 'date_only',
     'active', '2026-11-21T09:11:00Z', '2026-11-21T09:11:00Z', '2026-11-21T09:11:00Z',
     REPEAT('0', 63) || '4', 1, 1, '11111111-1111-4111-8111-000000000202'::UUID, '{"edge_case": "ec9_unv"}'::JSONB),

    -- EC10: One-sided salary (salary_min ONLY) + multi work_modes (2) + multi employment_types (2)
    ('22222222-2222-4222-8222-000000002011'::UUID, 'wuzzuf', 'edge-ec10', 'id:edge-ec10',
     'https://wuzzuf.net/jobs/p/edge-ec10-multi-arrangement-onesided-salary',
     'Edge Case Multi Arrangement One-Sided Salary Freelancer', 'EdgeOrg Iota', 'freelance', 'Cairo, Egypt',
     '["hybrid", "remote"]'::JSONB, '["part_time", "freelance"]'::JSONB, '["Consulting"]'::JSONB, '["SQL"]'::JSONB,
     12000, NULL, 'EGP', 'monthly',
     NULL, '2026-11-19', 'date_only',
     NULL, NULL, NULL,
     'active', '2026-11-21T10:01:00Z', '2026-11-21T10:01:00Z', '2026-11-21T10:01:00Z',
     REPEAT('0', 63) || '5', 1, 1, '11111111-1111-4111-8111-000000000203'::UUID, '{"edge_case": "ec10_multi_arrangement_salary"}'::JSONB);

COMMIT;
