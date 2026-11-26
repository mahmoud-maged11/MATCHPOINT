-- MATCHPOINT Data Warehouse
-- Test: Bronze constraint enforcement

BEGIN;

DO $$
DECLARE
    v_run_id UUID := gen_random_uuid();
    v_listing_id UUID := gen_random_uuid();
    v_observed_at TIMESTAMPTZ := NOW();
    v_hash TEXT := REPEAT('a', 64);

BEGIN

    -- Prepare valid collection run

    INSERT INTO bronze.collection_runs (
        run_id,
        source_name,
        collection_mode,
        contract_version
    )
    VALUES (
        v_run_id,
        'wuzzuf',
        'api',
        '3.0.0'
    );


    -- Prepare valid source listing

    INSERT INTO bronze.source_listings (
        source_listing_id,
        source_name,
        source_opportunity_id,
        source_identity_key,
        source_url,
        title,
        opportunity_type,
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
        'negative-test-001',
        'id:negative-test-001',
        'https://example.com/jobs/test',
        'Test Data Engineer',
        'job',
        v_observed_at,
        v_observed_at,
        v_observed_at,
        v_hash,
        v_run_id,
        '{}'::JSONB
    );


    -- Test 1: Unsupported source

    BEGIN
        UPDATE bronze.collection_runs
        SET source_name = 'unsupported_source'
        WHERE run_id = v_run_id;

        RAISE EXCEPTION 'FAIL 1: Unsupported source accepted';

    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'PASS 1: Unsupported source rejected';
    END;


    -- Test 2: Negative record count

    BEGIN
        UPDATE bronze.collection_runs
        SET records_received = -1
        WHERE run_id = v_run_id;

        RAISE EXCEPTION 'FAIL 2: Negative count accepted';

    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'PASS 2: Negative count rejected';
    END;


    -- Test 3: Completed run without finish time

    BEGIN
        UPDATE bronze.collection_runs
        SET status = 'completed'
        WHERE run_id = v_run_id;

        RAISE EXCEPTION 'FAIL 3: Invalid run status accepted';

    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'PASS 3: Invalid run status rejected';
    END;


    -- Test 4: Invalid foreign key

    BEGIN
        UPDATE bronze.source_listings
        SET last_collection_run_id = gen_random_uuid()
        WHERE source_listing_id = v_listing_id;

        RAISE EXCEPTION 'FAIL 4: Invalid foreign key accepted';

    EXCEPTION
        WHEN foreign_key_violation THEN
            RAISE NOTICE 'PASS 4: Invalid foreign key rejected';
    END;


    -- Test 5: Duplicate source identity

    BEGIN
        INSERT INTO bronze.source_listings (
            source_name,
            source_opportunity_id,
            source_identity_key,
            source_url,
            title,
            opportunity_type,
            collected_at,
            first_seen_at,
            last_seen_at,
            content_hash,
            last_collection_run_id,
            raw_payload
        )
        SELECT
            source_name,
            source_opportunity_id,
            source_identity_key,
            source_url,
            title,
            opportunity_type,
            collected_at,
            first_seen_at,
            last_seen_at,
            content_hash,
            last_collection_run_id,
            raw_payload
        FROM bronze.source_listings
        WHERE source_listing_id = v_listing_id;

        RAISE EXCEPTION 'FAIL 5: Duplicate identity accepted';

    EXCEPTION
        WHEN unique_violation THEN
            RAISE NOTICE 'PASS 5: Duplicate identity rejected';
    END;


    -- Test 6: Empty title

    BEGIN
        UPDATE bronze.source_listings
        SET title = '   '
        WHERE source_listing_id = v_listing_id;

        RAISE EXCEPTION 'FAIL 6: Empty title accepted';

    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'PASS 6: Empty title rejected';
    END;


    -- Test 7: Negative salary

    BEGIN
        UPDATE bronze.source_listings
        SET salary_min = -100
        WHERE source_listing_id = v_listing_id;

        RAISE EXCEPTION 'FAIL 7: Negative salary accepted';

    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'PASS 7: Negative salary rejected';
    END;


    -- Test 8: Invalid salary range

    BEGIN
        UPDATE bronze.source_listings
        SET salary_min = 20000,
            salary_max = 10000
        WHERE source_listing_id = v_listing_id;

        RAISE EXCEPTION 'FAIL 8: Invalid salary range accepted';

    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'PASS 8: Invalid salary range rejected';
    END;


    -- Test 9: Invalid content hash

    BEGIN
        UPDATE bronze.source_listings
        SET content_hash = 'invalid-hash'
        WHERE source_listing_id = v_listing_id;

        RAISE EXCEPTION 'FAIL 9: Invalid hash accepted';

    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'PASS 9: Invalid hash rejected';
    END;


    -- Test 10: Invalid raw payload

    BEGIN
        UPDATE bronze.source_listings
        SET raw_payload = '[]'::JSONB
        WHERE source_listing_id = v_listing_id;

        RAISE EXCEPTION 'FAIL 10: Invalid raw payload accepted';

    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'PASS 10: Invalid raw payload rejected';
    END;


    -- Test 11: Invalid JSON array

    BEGIN
        UPDATE bronze.source_listings
        SET work_modes = '{"mode": "remote"}'::JSONB
        WHERE source_listing_id = v_listing_id;

        RAISE EXCEPTION 'FAIL 11: Invalid array accepted';

    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'PASS 11: Invalid array rejected';
    END;


    -- Prepare valid history record

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
        v_hash,
        '3.0.0',
        v_run_id,
        '{}'::JSONB,
        v_observed_at
    );


    -- Test 12: Duplicate history version

    BEGIN
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
            v_hash,
            '3.0.0',
            v_run_id,
            '{}'::JSONB,
            v_observed_at
        );

        RAISE EXCEPTION 'FAIL 12: Duplicate history accepted';

    EXCEPTION
        WHEN unique_violation THEN
            RAISE NOTICE 'PASS 12: Duplicate history rejected';
    END;


    -- Prepare valid observation

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


    -- Test 13: Duplicate observation

    BEGIN
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

        RAISE EXCEPTION 'FAIL 13: Duplicate observation accepted';

    EXCEPTION
        WHEN unique_violation THEN
            RAISE NOTICE 'PASS 13: Duplicate observation rejected';
    END;


    -- Prepare valid rejection record

    INSERT INTO bronze.invalid_records (
        collection_run_id,
        failure_stage,
        error_code,
        error_message,
        rejection_hash
    )
    VALUES (
        v_run_id,
        'validation',
        'TEST_ERROR',
        'Test rejection',
        REPEAT('c', 64)
    );


    -- Test 14: Duplicate rejection

    BEGIN
        INSERT INTO bronze.invalid_records (
            collection_run_id,
            failure_stage,
            error_code,
            error_message,
            rejection_hash
        )
        VALUES (
            v_run_id,
            'validation',
            'TEST_ERROR',
            'Test rejection',
            REPEAT('c', 64)
        );

        RAISE EXCEPTION 'FAIL 14: Duplicate rejection accepted';

    EXCEPTION
        WHEN unique_violation THEN
            RAISE NOTICE 'PASS 14: Duplicate rejection rejected';
    END;


    -- Complete the collection run

    UPDATE bronze.collection_runs
    SET status = 'completed',
        finished_at = NOW(),
        records_received = 2,
        records_inserted = 1,
        records_invalid = 1
    WHERE run_id = v_run_id;


    -- Test 15: Empty checkpoint

    BEGIN
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
            'cursor',
            '{}'::JSONB,
            v_run_id
        );

        RAISE EXCEPTION 'FAIL 15: Empty checkpoint accepted';

    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'PASS 15: Empty checkpoint rejected';
    END;


    -- Prepare valid checkpoint

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
        'cursor',
        '{"cursor": "test-cursor"}'::JSONB,
        v_run_id
    );


    -- Test 16: Duplicate checkpoint

    BEGIN
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
            'cursor',
            '{"cursor": "another-cursor"}'::JSONB,
            v_run_id
        );

        RAISE EXCEPTION 'FAIL 16: Duplicate checkpoint accepted';

    EXCEPTION
        WHEN unique_violation THEN
            RAISE NOTICE 'PASS 16: Duplicate checkpoint rejected';
    END;


    RAISE NOTICE 'ALL 16 NEGATIVE TESTS PASSED';

END;
$$;

ROLLBACK;