-- MATCHPOINT Phase 5 Gold Layer Integration Verification Script
--
-- Validates materialized Gold dimensions, facts, canonical bridges, and analytical marts
-- against the synthetic dataset in `matchpoint_test`.

DO $$
DECLARE
    v_cnt BIGINT;
    v_opp_s1 UUID;
    v_py_canonical BIGINT;
    v_py_raw_listings BIGINT;
    v_invalid_cnt BIGINT;
BEGIN
    -- Reject missing or incomplete synthetic enrichment.
    IF (SELECT COUNT(*) FROM bronze.source_listings)
        IS DISTINCT FROM 41 THEN
        RAISE EXCEPTION
            'FAIL PREFLIGHT: Expected 41 Bronze listings';
    END IF;

    IF (SELECT COUNT(*) FROM bronze.invalid_records)
        IS DISTINCT FROM 1 THEN
        RAISE EXCEPTION
            'FAIL PREFLIGHT: Expected 1 synthetic invalid record';
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
          AND jsonb_array_length(required_skills) > 0
          AND jsonb_array_length(categories) > 0
    ) IS DISTINCT FROM 5 THEN
        RAISE EXCEPTION
            'FAIL PREFLIGHT: Required enrichment data missing';
    END IF;

    RAISE NOTICE
        'PASS PREFLIGHT: Gold synthetic dataset verified';

    -- 1. All 8 approved sources exist in dim_sources and mart_opportunities_by_source
    SELECT COUNT(*) INTO v_cnt FROM gold.dim_sources;
    IF v_cnt IS DISTINCT FROM 8 THEN RAISE EXCEPTION 'FAIL G1: Expected 8 sources in gold.dim_sources, got %', v_cnt; END IF;
    SELECT COUNT(*) INTO v_cnt FROM gold.mart_opportunities_by_source;
    IF v_cnt IS DISTINCT FROM 8 THEN RAISE EXCEPTION 'FAIL G1: Expected 8 sources in gold.mart_opportunities_by_source, got %', v_cnt; END IF;
    RAISE NOTICE 'PASS G1: All 8 Data Contract v3.0.0 sources represented in dim_sources and mart_opportunities_by_source';

    -- 2. Canonical grain parity: 41 source listings -> 33 canonical opportunities
    SELECT COUNT(*) INTO v_cnt FROM gold.fct_opportunities;
    IF v_cnt IS DISTINCT FROM 33 THEN RAISE EXCEPTION 'FAIL G2: Expected 33 canonical opportunities in gold.fct_opportunities, got %', v_cnt; END IF;
    SELECT COUNT(*) INTO v_cnt FROM gold.fct_opportunity_sources;
    IF v_cnt IS DISTINCT FROM 41 THEN RAISE EXCEPTION 'FAIL G2: Expected 41 source listings in gold.fct_opportunity_sources, got %', v_cnt; END IF;
    SELECT SUM(primary_canonical_opportunities) INTO v_cnt FROM gold.mart_opportunities_by_source;
    IF v_cnt IS DISTINCT FROM 33 THEN RAISE EXCEPTION 'FAIL G2: mart_opportunities_by_source primary sum expected 33, got %', v_cnt; END IF;
    RAISE NOTICE 'PASS G2: Canonical opportunity count parity (41 listings -> 33 canonical opportunities, zero double-counting)';

    -- 3. Skill alias & canonical bridge deduplication:
    -- Scenario 1 has 'Python' on Wuzzuf AND 'py' on Egyincs (same canonical opportunity).
    -- Scenario 4 has 'Python' on Wuzzuf, Scenario 8 has 'Python' on ITIDA.
    -- Total raw source listings with Python = 4, but deduplicated canonical opportunities with Python MUST be 3!
    SELECT opportunity_id INTO v_opp_s1
    FROM gold.fct_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000101'::UUID;

    SELECT COUNT(*) INTO v_cnt
    FROM gold.bridge_opportunity_skills
    WHERE opportunity_id = v_opp_s1 AND skill_name = 'Python';
    IF v_cnt IS DISTINCT FROM 1 THEN RAISE EXCEPTION 'FAIL G3: Python duplicated on merged Scenario 1 opportunity (count=%)', v_cnt; END IF;

    SELECT canonical_opportunity_count, source_listing_count
    INTO v_py_canonical, v_py_raw_listings
    FROM gold.dim_skills
    WHERE skill_name = 'Python';
    IF v_py_canonical IS DISTINCT FROM 3 OR v_py_raw_listings IS DISTINCT FROM 4 THEN
        RAISE EXCEPTION 'FAIL G3: Expected Python canonical=3 / raw_listings=4, got %/%', v_py_canonical, v_py_raw_listings;
    END IF;

    SELECT canonical_opportunity_count INTO v_cnt FROM gold.mart_skill_demand WHERE skill_name = 'Power BI';
    IF v_cnt IS DISTINCT FROM 1 THEN RAISE EXCEPTION 'FAIL G3: PowerBI + Power BI on merged Scenario 4 should count as 1 canonical opportunity, got %', v_cnt; END IF;
    RAISE NOTICE 'PASS G3: Canonical skill bridge deduplication and alias consolidation verified (Python: 4 raw -> 3 canonical; Power BI: 2 raw -> 1 canonical)';

    -- 4. Category bridge deduplication (Data Engineering on both Wuzzuf & Egyincs in S1 -> 1 canonical)
    SELECT canonical_opportunity_count INTO v_cnt
    FROM gold.mart_opportunities_by_category
    WHERE category_name = 'Data Engineering';
    IF v_cnt IS DISTINCT FROM 1 THEN RAISE EXCEPTION 'FAIL G4: Data Engineering duplicated across merged S1 sources (got %)', v_cnt; END IF;
    RAISE NOTICE 'PASS G4: Canonical category bridge deduplication verified';

    -- 5. Location, Work Mode, Employment Type, and Lifecycle Trends marts populated and consistent
    SELECT SUM(canonical_opportunity_count) INTO v_cnt FROM gold.mart_opportunities_by_location;
    IF v_cnt IS DISTINCT FROM 33 THEN RAISE EXCEPTION 'FAIL G5: Expected 33 opportunities across mart_opportunities_by_location, got %', v_cnt; END IF;
    SELECT COUNT(*) INTO v_cnt FROM gold.mart_opportunities_by_work_mode;
    IF v_cnt = 0 THEN RAISE EXCEPTION 'FAIL G5: mart_opportunities_by_work_mode is empty'; END IF;
    SELECT COUNT(*) INTO v_cnt FROM gold.mart_opportunities_by_employment_type;
    IF v_cnt = 0 THEN RAISE EXCEPTION 'FAIL G5: mart_opportunities_by_employment_type is empty'; END IF;
    SELECT SUM(canonical_opportunity_count) INTO v_cnt FROM gold.mart_opportunity_lifecycle_trends;
    IF v_cnt IS DISTINCT FROM 33 THEN RAISE EXCEPTION 'FAIL G5: Expected 33 opportunities with reliable published_at in mart_opportunity_lifecycle_trends, got %', v_cnt; END IF;
    SELECT SUM(primary_active_opportunities + primary_expired_opportunities + primary_closed_opportunities + primary_unknown_opportunities)
    INTO v_cnt FROM gold.mart_opportunities_by_source;
    IF v_cnt IS DISTINCT FROM 33 THEN RAISE EXCEPTION 'FAIL G5: Expected primary lifecycle breakdown sum=33, got %', v_cnt; END IF;
    RAISE NOTICE 'PASS G5: Location, work_mode, employment_type, source primary lifecycle, and publication trend marts verified';

    -- 6. Collection run & invalid record telemetry in fct_collection_runs & mart_opportunities_by_source
    SELECT persisted_invalid_record_count INTO v_invalid_cnt
    FROM gold.fct_collection_runs
    WHERE run_id = '11111111-1111-4111-8111-000000000001'::UUID;
    IF v_invalid_cnt IS DISTINCT FROM 1 THEN RAISE EXCEPTION 'FAIL G6: Expected 1 persisted invalid record on Wuzzuf run, got %', v_invalid_cnt; END IF;
    SELECT total_invalid_records_persisted INTO v_invalid_cnt
    FROM gold.mart_opportunities_by_source
    WHERE source_name = 'wuzzuf';
    IF v_invalid_cnt IS DISTINCT FROM 1 THEN RAISE EXCEPTION 'FAIL G6: Expected 1 persisted invalid record on mart_opportunities_by_source(wuzzuf), got %', v_invalid_cnt; END IF;
    RAISE NOTICE 'PASS G6: Collection run and invalid record telemetry verified';

    RAISE NOTICE 'ALL PHASE 5 GOLD INTEGRATION CHECKS PASSED';
END;
$$;
