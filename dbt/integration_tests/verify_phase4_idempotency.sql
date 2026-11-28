-- MATCHPOINT Phase 4 Idempotency Verification Script
--
-- USAGE (on isolated test database):
--   1. After Run 1, execute snapshot_phase4_silver_run1.sql
--      with explicit test database authorization.
--   2. Execute Run 2 (`dbt run --target test --profiles-dir .`).
--   3. Execute this script to verify zero differences between Run 1 and Run 2, then clean up snapshot.

DO $$
DECLARE
    v_run1_count BIGINT;
    v_run2_count BIGINT;
    v_opp_run1 BIGINT;
    v_opp_run2 BIGINT;
    v_diff_count BIGINT;
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

    SELECT COUNT(*), COUNT(DISTINCT opportunity_id)
    INTO v_run1_count, v_opp_run1
    FROM silver._tmp_phase4_run1_snapshot;

    SELECT COUNT(*), COUNT(DISTINCT opportunity_id)
    INTO v_run2_count, v_opp_run2
    FROM silver.silver_opportunity_sources;

    IF v_run1_count <> v_run2_count OR v_opp_run1 <> v_opp_run2 THEN
        RAISE EXCEPTION 'FAIL IDEMPOTENCY: Count mismatch (Run 1: %/% vs Run 2: %/%)',
            v_run1_count, v_opp_run1, v_run2_count, v_opp_run2;
    END IF;

    SELECT COUNT(*) INTO v_diff_count
    FROM (
        (
            SELECT opportunity_id, source_listing_id, is_primary_source, match_method, canonical_anchor_key
            FROM silver._tmp_phase4_run1_snapshot
            EXCEPT ALL
            SELECT opportunity_id, source_listing_id, is_primary_source, match_method, canonical_anchor_key
            FROM silver.silver_opportunity_sources
        )
        UNION ALL
        (
            SELECT opportunity_id, source_listing_id, is_primary_source, match_method, canonical_anchor_key
            FROM silver.silver_opportunity_sources
            EXCEPT ALL
            SELECT opportunity_id, source_listing_id, is_primary_source, match_method, canonical_anchor_key
            FROM silver._tmp_phase4_run1_snapshot
        )
    ) diffs;

    IF v_diff_count <> 0 THEN
        RAISE EXCEPTION 'FAIL IDEMPOTENCY: % mapping rows differed between Run 1 and Run 2', v_diff_count;
    END IF;

    DROP TABLE IF EXISTS silver._tmp_phase4_run1_snapshot;
    RAISE NOTICE 'PASS IDEMPOTENCY: Run 1 and Run 2 produced identical canonical mapping rows (% listings, % opportunities)',
        v_run2_count, v_opp_run2;
END;
$$;
