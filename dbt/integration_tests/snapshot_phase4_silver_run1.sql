-- MATCHPOINT Phase 4 Silver Run-1 Snapshot Helper
--
-- Captures canonical mapping rows in a persistent test snapshot.
-- Explicit test database authorization is required.
-- An existing snapshot is never silently overwritten.

DO $$
DECLARE
    v_expected_database TEXT;
    v_listing_count BIGINT;
    v_opportunity_count BIGINT;
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

    IF to_regclass('silver._tmp_phase4_run1_snapshot') IS NOT NULL THEN
        RAISE EXCEPTION
            'SNAPSHOT ABORT: Phase 4 Run 1 snapshot already exists';
    END IF;

    CREATE TABLE silver._tmp_phase4_run1_snapshot AS
    SELECT
        opportunity_id,
        source_listing_id,
        is_primary_source,
        match_method,
        canonical_anchor_key
    FROM silver.silver_opportunity_sources;

    SELECT
        COUNT(*),
        COUNT(DISTINCT opportunity_id)
    INTO
        v_listing_count,
        v_opportunity_count
    FROM silver._tmp_phase4_run1_snapshot;

    IF v_listing_count = 0 THEN
        RAISE EXCEPTION
            'SNAPSHOT ABORT: Cannot snapshot empty canonical mappings';
    END IF;

    RAISE NOTICE
        'SNAPSHOT COMPLETE: % listings mapped to % opportunities',
        v_listing_count,
        v_opportunity_count;
END;
$$;
