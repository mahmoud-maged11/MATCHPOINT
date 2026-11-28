-- MATCHPOINT Phase 5 Gold Synthetic Enrichment Loader (ISOLATED TEST DATABASE ONLY)
--
-- PURPOSE:
--   Enriches existing synthetic Phase 4 Bronze records in an authorized test database with
--   skills (including cross-source aliases like 'Python' + 'py' across a merged pair),
--   categories, and one synthetic invalid_records row so EVERY Gold dimension, bridge,
--   fact, and mart (including dim_skills, dim_categories, bridge_opportunity_skills,
--   bridge_opportunity_categories, mart_skill_demand, mart_opportunities_by_category,
--   and fct_collection_runs invalid telemetry) is validated with non-zero data without
--   altering Phase 4's 41 listings -> 32 canonical opportunities outcome.

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

-- Validate the synthetic baseline before modifying fixtures.
DO $$
BEGIN
    IF (SELECT COUNT(*) FROM bronze.source_listings)
        IS DISTINCT FROM 41 THEN
        RAISE EXCEPTION
            'FAIL PREFLIGHT: Expected 41 Bronze listings';
    END IF;

    IF (SELECT COUNT(*) FROM bronze.collection_runs)
        IS DISTINCT FROM 9 THEN
        RAISE EXCEPTION
            'FAIL PREFLIGHT: Expected 9 Bronze collection runs';
    END IF;

    IF (
        SELECT COUNT(*)
        FROM bronze.source_listings
        WHERE source_listing_id IN (
            '22222222-2222-4222-8222-000000000101'::UUID,
            '22222222-2222-4222-8222-000000000102'::UUID,
            '22222222-2222-4222-8222-000000000401'::UUID,
            '22222222-2222-4222-8222-000000000402'::UUID,
            '22222222-2222-4222-8222-000000000801'::UUID
        )
    ) IS DISTINCT FROM 5 THEN
        RAISE EXCEPTION
            'FAIL PREFLIGHT: Required enrichment listings missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM bronze.collection_runs
        WHERE run_id =
            '11111111-1111-4111-8111-000000000001'::UUID
          AND source_name = 'wuzzuf'
    ) THEN
        RAISE EXCEPTION
            'FAIL PREFLIGHT: Required Wuzzuf run missing';
    END IF;

    RAISE NOTICE
        'PASS PREFLIGHT: Synthetic enrichment targets verified';
END;
$$;

-- Synthetic fixture updates only.
-- These updates intentionally bypass ingestion hashing and history.
-- They must not be treated as production ingestion examples.

-- Add overlapping skill aliases ('Python' on Wuzzuf + 'py' & 'Postgres' on Egyincs) to Scenario 1 merged pair
-- so bridge_opportunity_skills must deduplicate 'Python' to 1 canonical count (not 2!).
UPDATE bronze.source_listings
SET
    required_skills = '["Python", "SQL", "Docker"]'::JSONB,
    categories = '["Data Engineering", "Software Development"]'::JSONB
WHERE source_listing_id = '22222222-2222-4222-8222-000000000101'::UUID;

UPDATE bronze.source_listings
SET
    required_skills = '["py", "Postgres", "dbt"]'::JSONB,
    categories = '["Data Engineering"]'::JSONB
WHERE source_listing_id = '22222222-2222-4222-8222-000000000102'::UUID;

-- Add skills & categories to Scenario 4 merged pair (Marakez internship)
UPDATE bronze.source_listings
SET
    required_skills = '["Python", "PowerBI", "SQL"]'::JSONB,
    categories = '["Data Analytics"]'::JSONB
WHERE source_listing_id = '22222222-2222-4222-8222-000000000401'::UUID;

UPDATE bronze.source_listings
SET
    required_skills = '["Power BI", "Excel"]'::JSONB,
    categories = '["Data Analytics", "Business Intelligence"]'::JSONB
WHERE source_listing_id = '22222222-2222-4222-8222-000000000402'::UUID;

-- Add skills & categories to Scenario 8 (ITIDA 4-source AI fellowship)
UPDATE bronze.source_listings
SET
    required_skills = '["Machine Learning", "Python"]'::JSONB,
    categories = '["Artificial Intelligence"]'::JSONB
WHERE source_listing_id = '22222222-2222-4222-8222-000000000801'::UUID;

-- Add 1 synthetic rejected record in bronze.invalid_records for fct_collection_runs telemetry testing
DELETE FROM bronze.invalid_records
WHERE collection_run_id = '11111111-1111-4111-8111-000000000001'::UUID
  AND rejection_hash = REPEAT('e', 64);

INSERT INTO bronze.invalid_records (
    collection_run_id, source_opportunity_id, source_url, failure_stage,
    error_code, error_message, error_details, record_payload, rejection_hash, observed_at
)
VALUES (
    '11111111-1111-4111-8111-000000000001'::UUID,
    'syn-invalid-001',
    'https://wuzzuf.net/jobs/p/syn-invalid-001',
    'validation',
    'SYNTHETIC_NEGATIVE_SALARY',
    'Synthetic invalid record for Gold fct_collection_runs telemetry validation',
    '{"field": "salary_min"}'::JSONB,
    '{"salary_min": -500}'::JSONB,
    REPEAT('e', 64),
    '2026-11-20T08:02:00Z'
);

UPDATE bronze.collection_runs
SET records_received = 15, records_invalid = 1
WHERE run_id = '11111111-1111-4111-8111-000000000001'::UUID;

COMMIT;
