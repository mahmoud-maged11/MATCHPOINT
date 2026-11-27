-- MATCHPOINT Phase 4 Idempotency Verification Script
--
-- USAGE (on isolated test database):
--   1. After Run 1 (`dbt run --target test --profiles-dir .`), create the Run 1 snapshot:
--      psql ... -c "DROP TABLE IF EXISTS silver._tmp_phase4_run1_snapshot;
--                   CREATE TABLE silver._tmp_phase4_run1_snapshot AS
--                   SELECT opportunity_id, source_listing_id, is_primary_source, match_method, canonical_anchor_key
--                   FROM silver.silver_opportunity_sources;"
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
            EXCEPT
            SELECT opportunity_id, source_listing_id, is_primary_source, match_method, canonical_anchor_key
            FROM silver.silver_opportunity_sources
        )
        UNION ALL
        (
            SELECT opportunity_id, source_listing_id, is_primary_source, match_method, canonical_anchor_key
            FROM silver.silver_opportunity_sources
            EXCEPT
            SELECT opportunity_id, source_listing_id, is_primary_source, match_method, canonical_anchor_key
            FROM silver._tmp_phase4_run1_snapshot
        )
    ) diffs;

    IF v_diff_count <> 0 THEN
        RAISE EXCEPTION 'FAIL IDEMPOTENCY: % mapping rows differed between Run 1 and Run 2', v_diff_count;
    END IF;

    DROP TABLE IF EXISTS silver._tmp_phase4_run1_snapshot;
    RAISE NOTICE 'PASS IDEMPOTENCY: Run 1 and Run 2 produced bit-for-bit identical canonical IDs (% listings, % opportunities)',
        v_run2_count, v_opp_run2;
END;
$$;
