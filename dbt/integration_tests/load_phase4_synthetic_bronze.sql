-- MATCHPOINT Phase 4 Synthetic Integration Test Fixture Loader
--
-- PURPOSE:
--   Loads deterministic synthetic records into Bronze tables on an ISOLATED TEST DATABASE
--   to validate ALL Phase 4 dbt models end-to-end (int_listing_match_features,
--   int_opportunity_match_pairs, int_opportunity_clusters, silver_opportunity_sources,
--   silver_opportunities, silver_opportunity_history).
--
-- SAFETY GUARD:
--   Requires an explicitly authorized test database name.
--   The connected database must match the expected database exactly.
--   Never run this script against a production or primary development database.

BEGIN;

DO $$
DECLARE
    v_expected_database TEXT;
BEGIN
    v_expected_database :=
        current_setting('matchpoint.expected_test_database', TRUE);

    IF v_expected_database IS NULL
       OR v_expected_database NOT IN (
           'matchpoint_test',
           'matchpoint_dbt_review_test'
       )
       OR current_database() IS DISTINCT FROM v_expected_database THEN
        RAISE EXCEPTION
            'SAFETY ABORT: Expected authorized test database %, connected to %',
            v_expected_database,
            current_database();
    END IF;

    RAISE NOTICE
        'PASS SAFETY GUARD: Connected to %',
        current_database();
END;
$$;

-- Clean prior synthetic test rows (strictly scoped to collection_scope = 'synthetic_phase4')
DELETE FROM bronze.source_listing_history
WHERE collection_run_id IN (
    SELECT run_id FROM bronze.collection_runs WHERE collection_scope = 'synthetic_phase4'
);

DELETE FROM bronze.ingestion_observations
WHERE collection_run_id IN (
    SELECT run_id FROM bronze.collection_runs WHERE collection_scope = 'synthetic_phase4'
);

DELETE FROM bronze.source_listings
WHERE last_collection_run_id IN (
    SELECT run_id FROM bronze.collection_runs WHERE collection_scope = 'synthetic_phase4'
);

DELETE FROM bronze.collection_runs
WHERE collection_scope = 'synthetic_phase4';

-- 1. Create synthetic collection runs for all eight sources
INSERT INTO bronze.collection_runs (
    run_id, source_name, collection_scope, collection_mode, status,
    started_at, finished_at, contract_version, hash_version
)
VALUES
    ('11111111-1111-4111-8111-000000000001'::UUID, 'wuzzuf',        'synthetic_phase4', 'api',  'completed', '2026-11-20T08:00:00Z', '2026-11-20T08:05:00Z', '3.0.0', 1),
    ('11111111-1111-4111-8111-000000000002'::UUID, 'forasna',       'synthetic_phase4', 'html', 'completed', '2026-11-20T08:00:00Z', '2026-11-20T08:05:00Z', '3.0.0', 1),
    ('11111111-1111-4111-8111-000000000003'::UUID, 'egyincs',       'synthetic_phase4', 'api',  'completed', '2026-11-20T08:00:00Z', '2026-11-20T08:05:00Z', '3.0.0', 1),
    ('11111111-1111-4111-8111-000000000004'::UUID, 'itida',         'synthetic_phase4', 'html', 'completed', '2026-11-20T08:00:00Z', '2026-11-20T08:05:00Z', '3.0.0', 1),
    ('11111111-1111-4111-8111-000000000005'::UUID, 'nti',           'synthetic_phase4', 'html', 'completed', '2026-11-20T08:00:00Z', '2026-11-20T08:05:00Z', '3.0.0', 1),
    ('11111111-1111-4111-8111-000000000006'::UUID, 'bayt',          'synthetic_phase4', 'html', 'completed', '2026-11-20T08:00:00Z', '2026-11-20T08:05:00Z', '3.0.0', 1),
    ('11111111-1111-4111-8111-000000000007'::UUID, 'devpost',       'synthetic_phase4', 'api',  'completed', '2026-11-20T08:00:00Z', '2026-11-20T08:05:00Z', '3.0.0', 1),
    ('11111111-1111-4111-8111-000000000008'::UUID, 'un_volunteers', 'synthetic_phase4', 'api',  'completed', '2026-11-20T08:00:00Z', '2026-11-20T08:05:00Z', '3.0.0', 1),
    ('11111111-1111-4111-8111-000000000009'::UUID, 'wuzzuf',        'synthetic_phase4', 'api',  'completed', '2026-11-10T09:30:00Z', '2026-11-10T09:35:00Z', '3.0.0', 1);

-- 2. Insert synthetic listings covering all 12 Phase 4 test scenarios
INSERT INTO bronze.source_listings (
    source_listing_id, source_name, source_opportunity_id, source_identity_key, source_url,
    title, organization, opportunity_type, location, work_modes, employment_types,
    salary_min, salary_max, currency, salary_period,
    published_at, published_at_raw, published_at_precision,
    status, collected_at, first_seen_at, last_seen_at,
    content_hash, hash_version, content_version, last_collection_run_id, raw_payload
)
VALUES
    -- SCENARIO 1: Tier 1A direct cross-source Wuzzuf URL reference (Egyincs -> Wuzzuf)
    ('22222222-2222-4222-8222-000000000101'::UUID, 'wuzzuf', 'synS1W', 'id:synS1W',
     'https://wuzzuf.net/jobs/p/synS1W-data-engineer-cairo',
     'Data Engineer', 'TechNova Egypt', 'job', 'Cairo, Egypt', '["hybrid"]'::JSONB, '["full_time"]'::JSONB,
     25000, 35000, 'EGP', 'monthly',
     '2026-11-10T09:00:00Z', '2026-11-10T09:00:00Z', 'exact',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T10:00:00Z', '2026-11-20T08:01:00Z',
     REPEAT('1', 64), 1, 2, '11111111-1111-4111-8111-000000000001'::UUID, '{"scenario": "s1_direct_url"}'::JSONB),

    ('22222222-2222-4222-8222-000000000102'::UUID, 'egyincs', 'syn-s1-e', 'id:syn-s1-e',
     'https://egyincs.com/jobs/syn-s1-e',
     'Data Engineer (Repost)', 'TechNova Egypt', 'job', 'Cairo', '["hybrid"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL,
     '2026-11-11T09:00:00Z', '2026-11-11T09:00:00Z', 'exact',
     'unknown', '2026-11-20T08:01:00Z', '2026-11-11T10:00:00Z', '2026-11-20T08:01:00Z',
     REPEAT('2', 64), 1, 1, '11111111-1111-4111-8111-000000000003'::UUID,
     '{"scenario": "s1_direct_url", "application_url": "https://wuzzuf.net/jobs/p/synS1W-data-engineer-cairo"}'::JSONB),

    -- SCENARIO 2: Unverified URL variants must remain distinct
    ('22222222-2222-4222-8222-000000000201'::UUID, 'itida', 'program:tiec-track', 'id:program:tiec-track',
     'https://itida.gov.eg/english/programs/pages/tiec-track.aspx',
     'TIEC Innovation Track', 'ITIDA', 'training', 'Smart Village, Egypt', '["hybrid"]'::JSONB, NULL,
     NULL, NULL, NULL, NULL,
     '2026-11-01T00:00:00Z', '2026-11-01', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-01T08:00:00Z', '2026-11-20T08:01:00Z',
     REPEAT('3', 64), 1, 1, '11111111-1111-4111-8111-000000000004'::UUID, '{"scenario": "s2_case_url"}'::JSONB),

    ('22222222-2222-4222-8222-000000000202'::UUID, 'egyincs', 'syn-s2-e', 'id:syn-s2-e',
     'https://egyincs.com/courses/syn-s2-e',
     'ITIDA TIEC Program', 'ITIDA', 'training', 'Giza', '["hybrid"]'::JSONB, NULL,
     NULL, NULL, NULL, NULL,
     '2026-11-02T00:00:00Z', '2026-11-02', 'date_only',
     'unknown', '2026-11-20T08:01:00Z', '2026-11-02T08:00:00Z', '2026-11-20T08:01:00Z',
     REPEAT('4', 64), 1, 1, '11111111-1111-4111-8111-000000000003'::UUID,
     '{"scenario": "s2_case_url", "application_url": "https://www.ITIDA.gov.eg/English/Programs/Pages/TIEC-Track.aspx/"}'::JSONB),

    -- SCENARIO 3: Shared specific external application URL (Tier 1B) with query param preserved
    ('22222222-2222-4222-8222-000000000301'::UUID, 'forasna', 'syn-s3-f', 'id:syn-s3-f',
     'https://forasna.com/job/p/syn-s3-f',
     'Backend Python Engineer', 'Acme Egypt', 'job', 'New Cairo', '["on_site"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL,
     '2026-11-05T00:00:00Z', '2026-11-05', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-05T08:00:00Z', '2026-11-20T08:01:00Z',
     REPEAT('5', 64), 1, 1, '11111111-1111-4111-8111-000000000002'::UUID,
     '{"scenario": "s3_shared_url", "application_url": "https://careers.acme-egypt.com/Openings/Backend-2026?reqId=AbC42"}'::JSONB),

    ('22222222-2222-4222-8222-000000000302'::UUID, 'bayt', 'syn-s3-b', 'id:syn-s3-b',
     'https://www.bayt.com/en/egypt/jobs/backend-python-302',
     'Python Backend Developer', 'Acme Egypt', 'job', 'New Cairo, Egypt', '["on_site"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL,
     '2026-11-06T00:00:00Z', '2026-11-06', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-06T08:00:00Z', '2026-11-20T08:01:00Z',
     REPEAT('6', 64), 1, 1, '11111111-1111-4111-8111-000000000006'::UUID,
     '{"scenario": "s3_shared_url", "application_url": "https://CAREERS.acme-egypt.com/Openings/Backend-2026?reqId=AbC42"}'::JSONB),

    -- SCENARIO 4: Tier 2 composite match (English vs Arabic Cairo, compatible work_modes, 5d apart)
    ('22222222-2222-4222-8222-000000000401'::UUID, 'wuzzuf', 'syn-s4-w', 'id:syn-s4-w',
     'https://wuzzuf.net/jobs/p/syn-s4-w-intern',
     'Data Analytics Intern', 'Marakez', 'internship', 'Cairo, Egypt', '["hybrid"]'::JSONB, NULL,
     NULL, NULL, NULL, NULL,
     '2026-11-01T10:00:00Z', '2026-11-01T10:00:00Z', 'exact',
     'active', '2026-11-20T08:01:00Z', '2026-11-01T10:00:00Z', '2026-11-20T08:01:00Z',
     REPEAT('7', 64), 1, 1, '11111111-1111-4111-8111-000000000001'::UUID, '{"scenario": "s4_composite"}'::JSONB),

    ('22222222-2222-4222-8222-000000000402'::UUID, 'forasna', 'syn-s4-f', 'id:syn-s4-f',
     'https://forasna.com/job/p/syn-s4-f',
     'Data Analytics Intern!', 'Marakez', 'internship', 'القاهرة', '["hybrid", "on_site"]'::JSONB, NULL,
     NULL, NULL, NULL, NULL,
     '2026-11-06T10:00:00Z', '2026-11-06T10:00:00Z', 'exact',
     'active', '2026-11-20T08:01:00Z', '2026-11-06T10:00:00Z', '2026-11-20T08:01:00Z',
     REPEAT('8', 64), 1, 1, '11111111-1111-4111-8111-000000000002'::UUID, '{"scenario": "s4_composite"}'::JSONB),

    -- SCENARIO 5A: Same-source direct duplicate prevention (2 distinct Wuzzuf listings)
    ('22222222-2222-4222-8222-000000000501'::UUID, 'wuzzuf', 'syn-s5-w1', 'id:syn-s5-w1',
     'https://wuzzuf.net/jobs/p/syn-s5-w1-ops',
     'Operations Specialist', 'Delta Logistics', 'job', 'Alexandria', '["on_site"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL,
     '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     REPEAT('9', 64), 1, 1, '11111111-1111-4111-8111-000000000001'::UUID, '{"scenario": "s5_same_source_direct"}'::JSONB),

    ('22222222-2222-4222-8222-000000000502'::UUID, 'wuzzuf', 'syn-s5-w2', 'id:syn-s5-w2',
     'https://wuzzuf.net/jobs/p/syn-s5-w2-ops',
     'Operations Specialist', 'Delta Logistics', 'job', 'Alexandria', '["on_site"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL,
     '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     REPEAT('a', 64), 1, 1, '11111111-1111-4111-8111-000000000001'::UUID, '{"scenario": "s5_same_source_direct"}'::JSONB),

    -- SCENARIO 5B: Same-source transitive prevention (Fix 2: W1 - Forasna - W2 via shared URL must split!)
    ('22222222-2222-4222-8222-000000000511'::UUID, 'wuzzuf', 'syn-s5-tr-w1', 'id:syn-s5-tr-w1',
     'https://wuzzuf.net/jobs/p/syn-s5-tr-w1',
     'Cloud Architect A', 'NileCloud', 'job', 'Cairo', '["hybrid"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL,
     '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     REPEAT('b', 64), 1, 1, '11111111-1111-4111-8111-000000000001'::UUID,
     '{"scenario": "s5_same_source_transitive", "application_url": "https://careers.nilecloud.eg/roles/shared-cohort-511"}'::JSONB),

    ('22222222-2222-4222-8222-000000000512'::UUID, 'forasna', 'syn-s5-tr-f1', 'id:syn-s5-tr-f1',
     'https://forasna.com/job/p/syn-s5-tr-f1',
     'Cloud Architect Bridge', 'NileCloud', 'job', 'Cairo', '["hybrid"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL,
     '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     REPEAT('c', 64), 1, 1, '11111111-1111-4111-8111-000000000002'::UUID,
     '{"scenario": "s5_same_source_transitive", "application_url": "https://careers.nilecloud.eg/roles/shared-cohort-511"}'::JSONB),

    ('22222222-2222-4222-8222-000000000513'::UUID, 'wuzzuf', 'syn-s5-tr-w2', 'id:syn-s5-tr-w2',
     'https://wuzzuf.net/jobs/p/syn-s5-tr-w2',
     'Cloud Architect B', 'NileCloud', 'job', 'Cairo', '["hybrid"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL,
     '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     REPEAT('d', 64), 1, 1, '11111111-1111-4111-8111-000000000001'::UUID,
     '{"scenario": "s5_same_source_transitive", "application_url": "https://careers.nilecloud.eg/roles/shared-cohort-511"}'::JSONB),

    -- SCENARIO 6: Ambiguous same-source composite candidates + cross-source candidate (ALL 3 stay separate)
    ('22222222-2222-4222-8222-000000000601'::UUID, 'wuzzuf', 'syn-s6-w1', 'id:syn-s6-w1',
     'https://wuzzuf.net/jobs/p/syn-s6-w1',
     'Support Engineer', 'AmbiguousCorp', 'job', 'Giza', '["on_site"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL,
     '2026-11-12T00:00:00Z', '2026-11-12', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-12T08:00:00Z', '2026-11-20T08:01:00Z',
     REPEAT('e', 64), 1, 1, '11111111-1111-4111-8111-000000000001'::UUID, '{"scenario": "s6_ambiguous"}'::JSONB),

    ('22222222-2222-4222-8222-000000000602'::UUID, 'wuzzuf', 'syn-s6-w2', 'id:syn-s6-w2',
     'https://wuzzuf.net/jobs/p/syn-s6-w2',
     'Support Engineer', 'AmbiguousCorp', 'job', 'Giza', '["on_site"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL,
     '2026-11-12T00:00:00Z', '2026-11-12', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-12T08:00:00Z', '2026-11-20T08:01:00Z',
     REPEAT('f', 64), 1, 1, '11111111-1111-4111-8111-000000000001'::UUID, '{"scenario": "s6_ambiguous"}'::JSONB),

    ('22222222-2222-4222-8222-000000000603'::UUID, 'forasna', 'syn-s6-f1', 'id:syn-s6-f1',
     'https://forasna.com/job/p/syn-s6-f1',
     'Support Engineer', 'AmbiguousCorp', 'job', 'Giza', '["on_site"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL,
     '2026-11-12T00:00:00Z', '2026-11-12', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-12T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000000603', 1, 1, '11111111-1111-4111-8111-000000000002'::UUID, '{"scenario": "s6_ambiguous"}'::JSONB),

    -- SCENARIO 7: Generic application portal exclusions (Fix 4: non-root generic paths must NOT merge)
    ('22222222-2222-4222-8222-000000000701'::UUID, 'egyincs', 'syn-s7-a1', 'id:syn-s7-a1',
     'https://egyincs.com/jobs/syn-s7-a1',
     'Accountant Junior', 'PortalOrgA', 'job', 'Cairo', '["on_site"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL,
     '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'unknown', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000000701', 1, 1, '11111111-1111-4111-8111-000000000003'::UUID,
     '{"scenario": "s7_generic_portal", "application_url": "https://wuzzuf.net/jobs/egypt"}'::JSONB),

    ('22222222-2222-4222-8222-000000000702'::UUID, 'forasna', 'syn-s7-a2', 'id:syn-s7-a2',
     'https://forasna.com/job/p/syn-s7-a2',
     'HR Coordinator', 'PortalOrgA', 'job', 'Cairo', '["on_site"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL,
     '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000000702', 1, 1, '11111111-1111-4111-8111-000000000002'::UUID,
     '{"scenario": "s7_generic_portal", "application_url": "https://wuzzuf.net/jobs/egypt"}'::JSONB),

    ('22222222-2222-4222-8222-000000000703'::UUID, 'egyincs', 'syn-s7-b1', 'id:syn-s7-b1',
     'https://egyincs.com/courses/syn-s7-b1',
     'Embedded Systems Course', 'NTI', 'training', 'Cairo', '["on_site"]'::JSONB, NULL,
     NULL, NULL, NULL, NULL,
     '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'unknown', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000000703', 1, 1, '11111111-1111-4111-8111-000000000003'::UUID,
     '{"scenario": "s7_generic_portal", "application_url": "https://www.nti.sci.eg/ereg/"}'::JSONB),

    ('22222222-2222-4222-8222-000000000704'::UUID, 'nti', 'syn-s7-b2', 'id:syn-s7-b2',
     'https://www.nti.sci.eg/course/syn-s7-b2',
     'Cybersecurity Track', 'NTI', 'training', 'Cairo', '["on_site"]'::JSONB, NULL,
     NULL, NULL, NULL, NULL,
     '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'unknown', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000000704', 1, 1, '11111111-1111-4111-8111-000000000005'::UUID,
     '{"scenario": "s7_generic_portal", "application_url": "https://www.nti.sci.eg/ereg/"}'::JSONB),

    ('22222222-2222-4222-8222-000000000705'::UUID, 'egyincs', 'syn-s7-c1', 'id:syn-s7-c1',
     'https://egyincs.com/jobs/syn-s7-c1',
     'Sales Rep', 'GenericCareersOrg', 'job', 'Cairo', '["on_site"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL,
     '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'unknown', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000000705', 1, 1, '11111111-1111-4111-8111-000000000003'::UUID,
     '{"scenario": "s7_generic_portal", "application_url": "https://company-generic.eg/careers"}'::JSONB),

    ('22222222-2222-4222-8222-000000000706'::UUID, 'bayt', 'syn-s7-c2', 'id:syn-s7-c2',
     'https://www.bayt.com/en/egypt/jobs/designer-706',
     'UI Designer', 'GenericCareersOrg', 'job', 'Cairo', '["on_site"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL,
     '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000000706', 1, 1, '11111111-1111-4111-8111-000000000006'::UUID,
     '{"scenario": "s7_generic_portal", "application_url": "https://company-generic.eg/careers"}'::JSONB),

    -- SCENARIO 8: Valid 4-source transitive chain + Fix 5 Anchor Stability (ITIDA rank 1 MUST beat Wuzzuf rank 5 even when Egyincs points directly to Wuzzuf!)
    ('22222222-2222-4222-8222-000000000801'::UUID, 'itida', 'program:syn-s8-ai', 'id:program:syn-s8-ai',
     'https://itida.gov.eg/english/programs/pages/syn-s8-ai.aspx',
     'National AI Fellowship', 'ITIDA', 'training', 'Cairo', '["hybrid"]'::JSONB, NULL,
     NULL, NULL, NULL, NULL,
     '2026-11-05T00:00:00Z', '2026-11-05', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-05T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000000801', 1, 1, '11111111-1111-4111-8111-000000000004'::UUID, '{"scenario": "s8_transitive_anchor"}'::JSONB),

    ('22222222-2222-4222-8222-000000000802'::UUID, 'wuzzuf', 'synS8W', 'id:synS8W',
     'https://wuzzuf.net/jobs/p/synS8W-national-ai-fellowship',
     'National AI Fellowship', 'ITIDA', 'training', 'Cairo, Egypt', '["hybrid"]'::JSONB, NULL,
     NULL, NULL, NULL, NULL,
     '2026-11-06T00:00:00Z', '2026-11-06', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-06T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000000802', 1, 1, '11111111-1111-4111-8111-000000000001'::UUID, '{"scenario": "s8_transitive_anchor"}'::JSONB),

    ('22222222-2222-4222-8222-000000000803'::UUID, 'egyincs', 'syn-s8-e', 'id:syn-s8-e',
     'https://egyincs.com/courses/syn-s8-e',
     'AI Fellowship Egypt', 'ITIDA', 'training', 'Cairo', '["hybrid"]'::JSONB, NULL,
     NULL, NULL, NULL, NULL,
     '2026-11-07T00:00:00Z', '2026-11-07', 'date_only',
     'unknown', '2026-11-20T08:01:00Z', '2026-11-07T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000000803', 1, 1, '11111111-1111-4111-8111-000000000003'::UUID,
     '{"scenario": "s8_transitive_anchor", "application_url": "https://wuzzuf.net/jobs/p/synS8W-national-ai-fellowship"}'::JSONB),

    ('22222222-2222-4222-8222-000000000804'::UUID, 'forasna', 'syn-s8-f', 'id:syn-s8-f',
     'https://forasna.com/job/p/syn-s8-f',
     'National AI Fellowship', 'Information Technology Industry Development Agency', 'training', 'القاهرة', '["hybrid"]'::JSONB, NULL,
     NULL, NULL, NULL, NULL,
     '2026-11-08T00:00:00Z', '2026-11-08', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-08T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000000804', 1, 1, '11111111-1111-4111-8111-000000000002'::UUID, '{"scenario": "s8_transitive_anchor"}'::JSONB),

    -- SCENARIO 9A: ADR-019 numeric scale equivalence (10000 vs 10000.00 -> NO salary conflict)
    ('22222222-2222-4222-8222-000000000901'::UUID, 'wuzzuf', 'syn-s9-eq-w', 'id:syn-s9-eq-w',
     'https://wuzzuf.net/jobs/p/syn-s9-eq-w',
     'BI Analyst', 'FinMetrics', 'job', 'Cairo', '["hybrid"]'::JSONB, '["full_time"]'::JSONB,
     10000, 15000, 'EGP', 'monthly',
     '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000000901', 1, 1, '11111111-1111-4111-8111-000000000001'::UUID, '{"scenario": "s9_salary_equiv"}'::JSONB),

    ('22222222-2222-4222-8222-000000000902'::UUID, 'forasna', 'syn-s9-eq-f', 'id:syn-s9-eq-f',
     'https://forasna.com/job/p/syn-s9-eq-f',
     'BI Analyst', 'FinMetrics', 'job', 'Cairo', '["hybrid"]'::JSONB, '["full_time"]'::JSONB,
     10000.00, 15000.00, 'EGP', 'monthly',
     '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000000902', 1, 1, '11111111-1111-4111-8111-000000000002'::UUID, '{"scenario": "s9_salary_equiv"}'::JSONB),

    -- SCENARIO 9B: Real salary_period conflict + employment_types conflict (Fix 6)
    ('22222222-2222-4222-8222-000000000911'::UUID, 'wuzzuf', 'syn-s9-cf-w', 'id:syn-s9-cf-w',
     'https://wuzzuf.net/jobs/p/syn-s9-cf-w',
     'ML Platform Engineer', 'DeepNile', 'job', 'Cairo', '["remote"]'::JSONB, '["full_time"]'::JSONB,
     15000, 20000, 'EGP', 'monthly',
     '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000000911', 1, 1, '11111111-1111-4111-8111-000000000001'::UUID, '{"scenario": "s9_salary_emp_conflict"}'::JSONB),

    ('22222222-2222-4222-8222-000000000912'::UUID, 'bayt', 'syn-s9-cf-b', 'id:syn-s9-cf-b',
     'https://www.bayt.com/en/egypt/jobs/ml-platform-912',
     'ML Platform Engineer', 'DeepNile', 'job', 'Cairo', '["remote"]'::JSONB, '["contract"]'::JSONB,
     15000, 20000, 'EGP', 'yearly',
     '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000000912', 1, 1, '11111111-1111-4111-8111-000000000006'::UUID, '{"scenario": "s9_salary_emp_conflict"}'::JSONB),

    -- SCENARIO 10: False-positive prevention (title-only, missing org, country-only loc, incompatible work_mode, temporal drift)
    -- 10A: Title-only different orgs
    ('22222222-2222-4222-8222-000000001001'::UUID, 'wuzzuf', 'syn-s10-t1', 'id:syn-s10-t1',
     'https://wuzzuf.net/jobs/p/syn-s10-t1',
     'Full Stack Developer', 'OrgAlpha', 'job', 'Cairo', '["on_site"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL, '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000001001', 1, 1, '11111111-1111-4111-8111-000000000001'::UUID, '{"scenario": "s10_fp_title_only"}'::JSONB),

    ('22222222-2222-4222-8222-000000001002'::UUID, 'bayt', 'syn-s10-t2', 'id:syn-s10-t2',
     'https://www.bayt.com/en/egypt/jobs/fs-1002',
     'Full Stack Developer', 'OrgBeta', 'job', 'Cairo', '["on_site"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL, '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000001002', 1, 1, '11111111-1111-4111-8111-000000000006'::UUID, '{"scenario": "s10_fp_title_only"}'::JSONB),

    -- 10B: Missing org (NULL)
    ('22222222-2222-4222-8222-000000001011'::UUID, 'wuzzuf', 'syn-s10-o1', 'id:syn-s10-o1',
     'https://wuzzuf.net/jobs/p/syn-s10-o1',
     'Confidential Analyst', NULL, 'job', 'Cairo', '["on_site"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL, '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000001011', 1, 1, '11111111-1111-4111-8111-000000000001'::UUID, '{"scenario": "s10_fp_missing_org"}'::JSONB),

    ('22222222-2222-4222-8222-000000001012'::UUID, 'forasna', 'syn-s10-o2', 'id:syn-s10-o2',
     'https://forasna.com/job/p/syn-s10-o2',
     'Confidential Analyst', NULL, 'job', 'Cairo', '["on_site"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL, '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000001012', 1, 1, '11111111-1111-4111-8111-000000000002'::UUID, '{"scenario": "s10_fp_missing_org"}'::JSONB),

    -- 10C: Country-only location ('Egypt') must NOT match
    ('22222222-2222-4222-8222-000000001021'::UUID, 'wuzzuf', 'syn-s10-l1', 'id:syn-s10-l1',
     'https://wuzzuf.net/jobs/p/syn-s10-l1',
     'Field Coordinator', 'BroadOrg', 'job', 'Egypt', '["on_site"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL, '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000001021', 1, 1, '11111111-1111-4111-8111-000000000001'::UUID, '{"scenario": "s10_fp_country_only"}'::JSONB),

    ('22222222-2222-4222-8222-000000001022'::UUID, 'bayt', 'syn-s10-l2', 'id:syn-s10-l2',
     'https://www.bayt.com/en/egypt/jobs/fc-1022',
     'Field Coordinator', 'BroadOrg', 'job', 'Egypt', '["on_site"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL, '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000001022', 1, 1, '11111111-1111-4111-8111-000000000006'::UUID, '{"scenario": "s10_fp_country_only"}'::JSONB),

    -- 10D: Transitive Tier 2 temporal drift (Day 1 - Day 40 - Day 79 -> span 78d > 45d must split!)
    ('22222222-2222-4222-8222-000000001031'::UUID, 'wuzzuf', 'syn-s10-d1', 'id:syn-s10-d1',
     'https://wuzzuf.net/jobs/p/syn-s10-d1',
     'QA Automation Engineer', 'DriftCorp', 'job', 'Cairo', '["hybrid"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL, '2026-08-01T00:00:00Z', '2026-08-01', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-08-01T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000001031', 1, 1, '11111111-1111-4111-8111-000000000001'::UUID, '{"scenario": "s10_fp_temporal_drift"}'::JSONB),

    ('22222222-2222-4222-8222-000000001032'::UUID, 'forasna', 'syn-s10-d2', 'id:syn-s10-d2',
     'https://forasna.com/job/p/syn-s10-d2',
     'QA Automation Engineer', 'DriftCorp', 'job', 'Cairo', '["hybrid"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL, '2026-09-10T00:00:00Z', '2026-09-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-09-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000001032', 1, 1, '11111111-1111-4111-8111-000000000002'::UUID, '{"scenario": "s10_fp_temporal_drift"}'::JSONB),

    ('22222222-2222-4222-8222-000000001033'::UUID, 'bayt', 'syn-s10-d3', 'id:syn-s10-d3',
     'https://www.bayt.com/en/egypt/jobs/qa-1033',
     'QA Automation Engineer', 'DriftCorp', 'job', 'Cairo', '["hybrid"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL, '2026-10-19T00:00:00Z', '2026-10-19', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-10-19T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000001033', 1, 1, '11111111-1111-4111-8111-000000000006'::UUID, '{"scenario": "s10_fp_temporal_drift"}'::JSONB),

    -- 10E: Incompatible work_modes (on_site vs remote)
    ('22222222-2222-4222-8222-000000001041'::UUID, 'wuzzuf', 'syn-s10-wm1', 'id:syn-s10-wm1',
     'https://wuzzuf.net/jobs/p/syn-s10-wm1',
     'Systems Engineer', 'ModeCorp', 'job', 'Cairo', '["on_site"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL, '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000001041', 1, 1, '11111111-1111-4111-8111-000000000001'::UUID, '{"scenario": "s10_fp_work_mode"}'::JSONB),

    ('22222222-2222-4222-8222-000000001042'::UUID, 'bayt', 'syn-s10-wm2', 'id:syn-s10-wm2',
     'https://www.bayt.com/en/egypt/jobs/se-1042',
     'Systems Engineer', 'ModeCorp', 'job', 'Cairo', '["remote"]'::JSONB, '["full_time"]'::JSONB,
     NULL, NULL, NULL, NULL, '2026-11-10T00:00:00Z', '2026-11-10', 'date_only',
     'active', '2026-11-20T08:01:00Z', '2026-11-10T08:00:00Z', '2026-11-20T08:01:00Z',
     '0000000000000000000000000000000000000000000000000000000000001042', 1, 1, '11111111-1111-4111-8111-000000000006'::UUID, '{"scenario": "s10_fp_work_mode"}'::JSONB);

-- 3. Insert Bronze history records (verifying A->B content version preservation in silver_opportunity_history)
INSERT INTO bronze.source_listing_history (
    history_id, source_listing_id, content_version, content_hash, hash_version,
    contract_version, collection_run_id, standardized_payload, observed_at
)
VALUES
    ('33333333-3333-4333-8333-000000000101'::UUID, '22222222-2222-4222-8222-000000000101'::UUID, 1,
     REPEAT('0', 64), 1, '3.0.0', '11111111-1111-4111-8111-000000000009'::UUID,
     '{"title": "Data Engineer", "salary_min": 20000}'::JSONB, '2026-11-10T10:00:00Z'),
    ('33333333-3333-4333-8333-000000000102'::UUID, '22222222-2222-4222-8222-000000000101'::UUID, 2,
     REPEAT('1', 64), 1, '3.0.0', '11111111-1111-4111-8111-000000000001'::UUID,
     '{"title": "Data Engineer", "salary_min": 25000}'::JSONB, '2026-11-20T08:01:00Z');

COMMIT;
