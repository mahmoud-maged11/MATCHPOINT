-- MATCHPOINT Phase 5 Gold Layer Full 20-Model Idempotency Verification Script
--
-- Performs full symmetric set comparison (EXCEPT in both directions across ALL columns)
-- between Run 1 snapshots (gold._tmp_run1_*) and Run 2 materialized tables (gold.*)
-- for ALL 20 Gold models (6 dimensions, 7 facts/bridges, 7 analytical marts),
-- then cleans up all temporary snapshot tables.

DO $$
DECLARE
    v_model TEXT;
    v_snap TEXT;
    v_cols TEXT;
    v_diff BIGINT;
    v_cnt_r1 BIGINT;
    v_cnt_r2 BIGINT;
    v_total_diffs BIGINT := 0;
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
        RAISE EXCEPTION 'SAFETY ABORT: verify_phase5_gold_idempotency.sql must only run on a test database (current_database = %).', current_database();
    END IF;

    FOREACH v_model IN ARRAY v_models LOOP
        v_snap := '_tmp_run1_' || v_model;

        -- Compare ALL business/key/metric/JSONB columns, excluding only per-run wall-clock evaluation timestamp
        -- (lifecycle_evaluated_at on fct_opportunities intentionally records each dbt run's UTC timestamp).
        SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position)
        INTO v_cols
        FROM information_schema.columns
        WHERE table_schema = 'gold'
          AND table_name = v_model
          AND column_name NOT IN ('lifecycle_evaluated_at');

        EXECUTE format('SELECT COUNT(*) FROM gold.%I', v_snap) INTO v_cnt_r1;
        EXECUTE format('SELECT COUNT(*) FROM gold.%I', v_model) INTO v_cnt_r2;

        EXECUTE format(
            'SELECT COUNT(*) FROM (
                (SELECT %s FROM gold.%I EXCEPT SELECT %s FROM gold.%I)
                UNION ALL
                (SELECT %s FROM gold.%I EXCEPT SELECT %s FROM gold.%I)
            ) diff_rows',
            v_cols, v_snap, v_cols, v_model,
            v_cols, v_model, v_cols, v_snap
        ) INTO v_diff;

        IF v_diff <> 0 OR v_cnt_r1 <> v_cnt_r2 THEN
            v_total_diffs := v_total_diffs + GREATEST(v_diff, 1);
            RAISE NOTICE 'FAIL MODEL IDEMPOTENCY: gold.% (Run1=%, Run2=%, diffs=%)',
                v_model, v_cnt_r1, v_cnt_r2, v_diff;
        ELSE
            RAISE NOTICE 'PASS MODEL IDEMPOTENCY: gold.% (rows=%, diffs=0)', v_model, v_cnt_r2;
        END IF;

        EXECUTE format('DROP TABLE IF EXISTS gold.%I', v_snap);
    END LOOP;

    IF v_total_diffs <> 0 THEN
        RAISE EXCEPTION 'FAIL GOLD IDEMPOTENCY: % total diffs across 20 Gold models', v_total_diffs;
    END IF;

    RAISE NOTICE 'PASS GOLD IDEMPOTENCY: All 20 Gold models produced bit-for-bit identical rows across Run 1 and Run 2 (0 diffs)';
END;
$$;
