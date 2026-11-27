-- MATCHPOINT Data Warehouse
-- Test: Bronze valid records and relationships

BEGIN;

DO $$
DECLARE
    v_run_id UUID := gen_random_uuid();
    v_listing_id UUID := gen_random_uuid();
    v_observed_at TIMESTAMPTZ := NOW();
    v_content_hash TEXT := REPEAT('a', 64);

BEGIN

    -- Test 1: Collection run

    INSERT INTO bronze.collection_runs (
        run_id,
        source_name,
        collection_scope,
        collection_mode,
        contract_version
    )
    VALUES (
        v_run_id,
        'wuzzuf',
        'default',
        'api',
        '3.0.0'
    );

    RAISE NOTICE 'PASS 1: Collection run inserted';


    -- Test 2: Source listing

    INSERT INTO bronze.source_listings (
        source_listing_id,
        source_name,
        source_opportunity_id,
        source_identity_key,
        source_url,
        title,
        organization,
        opportunity_type,
        work_modes,
        employment_types,
        salary_min,
        salary_max,
        currency,
        salary_period,
        status,
        collected_at,
        first_seen_at,
        last_seen_at,
        content_hash,
        last_collection_run_id,
        raw_payload
    )
    VALUES (
        v_listing_id,
        'wuzzuf',
        'test-001',
        'id:test-001',
        'https://example.com/jobs/test-001',
        'Data Engineer',
        'Test Company',
        'job',
        '["hybrid"]'::JSONB,
        '["full_time"]'::JSONB,
        15000,
        20000,
        'EGP',
        'monthly',
        'active',
        v_observed_at,
        v_observed_at,
        v_observed_at,
        v_content_hash,
        v_run_id,
        '{"test": true}'::JSONB
    );

    RAISE NOTICE 'PASS 2: Source listing inserted';


    -- Test 3: Listing history

    INSERT INTO bronze.source_listing_history (
        source_listing_id,
        content_version,
        content_hash,
        contract_version,
        collection_run_id,
        standardized_payload,
        observed_at
    )
    VALUES (
        v_listing_id,
        1,
        v_content_hash,
        '3.0.0',
        v_run_id,
        '{"title": "Data Engineer", "test": true}'::JSONB,
        v_observed_at
    );

    RAISE NOTICE 'PASS 3: History record inserted';


    -- Test 4: Ingestion observation

    INSERT INTO bronze.ingestion_observations (
        source_listing_id,
        collection_run_id,
        observation_hash,
        observed_at,
        outcome
    )
    VALUES (
        v_listing_id,
        v_run_id,
        REPEAT('b', 64),
        v_observed_at,
        'inserted'
    );

    RAISE NOTICE 'PASS 4: Observation inserted';


    -- Test 5: Invalid record

    INSERT INTO bronze.invalid_records (
        collection_run_id,
        failure_stage,
        error_code,
        error_message,
        record_payload,
        rejection_hash,
        observed_at
    )
    VALUES (
        v_run_id,
        'validation',
        'TEST_INVALID_SALARY',
        'Salary cannot be negative',
        '{"salary_min": -100}'::JSONB,
        REPEAT('c', 64),
        v_observed_at
    );

    RAISE NOTICE 'PASS 5: Invalid record retained';


    -- Test 6: Complete collection run

    UPDATE bronze.collection_runs
    SET
        status = 'completed',
        finished_at = NOW(),
        records_received = 2,
        records_inserted = 1,
        records_invalid = 1
    WHERE run_id = v_run_id;

    RAISE NOTICE 'PASS 6: Collection run completed';


    -- Test 7: Source checkpoint

    INSERT INTO bronze.source_checkpoints (
        source_name,
        collection_scope,
        checkpoint_type,
        checkpoint_value,
        last_successful_run_id
    )
    VALUES (
        'wuzzuf',
        'default',
        'composite',
        JSONB_BUILD_OBJECT(
            'modified_at', v_observed_at,
            'last_id', 'test-001'
        ),
        v_run_id
    );

    RAISE NOTICE 'PASS 7: Checkpoint inserted';

    RAISE NOTICE 'ALL VALID RECORD TESTS PASSED';

END;
$$;

ROLLBACK;