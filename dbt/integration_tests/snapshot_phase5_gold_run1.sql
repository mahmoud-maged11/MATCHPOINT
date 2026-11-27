-- MATCHPOINT Phase 5 Gold Layer Run-1 Snapshot Helper
--
-- Snapshots ALL 20 Gold models (6 dimensions, 7 facts/bridges, 7 analytical marts)
-- into temporary gold._tmp_run1_* tables prior to executing Run 2 for full idempotency verification.

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
    IF current_database() NOT ILIKE '%test%' THEN
        RAISE EXCEPTION 'SAFETY ABORT: snapshot_phase5_gold_run1.sql must only run on a test database (current_database = %).', current_database();
    END IF;

    FOREACH v_model IN ARRAY v_models LOOP
        EXECUTE format('DROP TABLE IF EXISTS gold.%I', '_tmp_run1_' || v_model);
        EXECUTE format('CREATE TABLE gold.%I AS SELECT * FROM gold.%I', '_tmp_run1_' || v_model, v_model);
    END LOOP;

    RAISE NOTICE 'SNAPSHOT COMPLETE: Captured Run 1 state for all % Gold models', array_length(v_models, 1);
END;
$$;
