-- MATCHPOINT Phase 5 Gold Layer Run-1 Snapshot Helper
--
-- Snapshots ALL 20 Gold models (6 dimensions, 7 facts/bridges, 7 analytical marts)
-- into persistent test-only gold._tmp_run1_* tables prior to executing Run 2 for full idempotency verification.

DO $$
DECLARE
    v_model TEXT;
    v_models TEXT[] := ARRAY[
        -- Dimensions (6)
        'dim_sources',
        'dim_organizations',
        'dim_locations',
        'dim_skills',
        'dim_categories',
        'dim_dates',
        -- Facts & Canonical Bridges (7)
        'fct_opportunities',
        'fct_opportunity_sources',
        'fct_collection_runs',
        'bridge_opportunity_skills',
        'bridge_opportunity_categories',
        'bridge_opportunity_work_modes',
        'bridge_opportunity_employment_types',
        -- Analytical Marts (7)
        'mart_opportunities_by_source',
        'mart_opportunities_by_category',
        'mart_opportunities_by_location',
        'mart_opportunities_by_work_mode',
        'mart_opportunities_by_employment_type',
        'mart_skill_demand',
        'mart_opportunity_lifecycle_trends'
    ];
BEGIN
    IF current_setting('matchpoint.expected_test_database', TRUE) IS NULL
       OR current_setting('matchpoint.expected_test_database', TRUE) NOT IN (
           'matchpoint_test',
           'matchpoint_dbt_review_test'
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

    FOREACH v_model IN ARRAY v_models LOOP
        IF to_regclass(
            format('gold.%I', '_tmp_run1_' || v_model)
        ) IS NOT NULL THEN
            RAISE EXCEPTION
                'SNAPSHOT ABORT: Existing snapshot for gold.% must not be overwritten',
                v_model;
        END IF;
        EXECUTE format('CREATE TABLE gold.%I AS SELECT * FROM gold.%I', '_tmp_run1_' || v_model, v_model);
    END LOOP;

    RAISE NOTICE 'SNAPSHOT COMPLETE: Captured Run 1 state for all % Gold models', array_length(v_models, 1);
END;
$$;
