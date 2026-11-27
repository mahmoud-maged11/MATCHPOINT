-- MATCHPOINT Phase 4 Synthetic Integration Verification Script
--
-- Run AFTER:
--   1. load_phase4_synthetic_bronze.sql
--   2. dbt seed --target test --profiles-dir .
--   3. dbt run  --target test --profiles-dir .
--   4. dbt test --target test --profiles-dir .
--
-- Verifies actual materialized rows in silver.silver_opportunity_sources,
-- silver.silver_opportunities, and silver.silver_opportunity_history.

DO $$
DECLARE
    v_opp_a UUID;
    v_opp_b UUID;
    v_opp_c UUID;
    v_opp_d UUID;
    v_primary TEXT;
    v_cnt INT;
    v_has_conflicts BOOLEAN;
    v_conflicts JSONB;
    v_method TEXT;
    v_expected_count INT;
    v_actual_count INT;
BEGIN
    -- Preflight: verify complete synthetic listing coverage
    SELECT COUNT(*)
    INTO v_expected_count
    FROM bronze.source_listings sl
    JOIN bronze.collection_runs cr
        ON sl.last_collection_run_id = cr.run_id
    WHERE cr.collection_scope = 'synthetic_phase4';

    IF v_expected_count <> 41 THEN
        RAISE EXCEPTION
            'FAIL PREFLIGHT: Expected 41 Bronze listings, got %',
            v_expected_count;
    END IF;

    SELECT COUNT(DISTINCT sl.source_listing_id)
    INTO v_actual_count
    FROM bronze.source_listings sl
    JOIN bronze.collection_runs cr
        ON sl.last_collection_run_id = cr.run_id
    JOIN silver.silver_opportunity_sources sos
        ON sl.source_listing_id = sos.source_listing_id
    JOIN silver.silver_opportunities so
        ON sos.opportunity_id = so.opportunity_id
    WHERE cr.collection_scope = 'synthetic_phase4';

    IF v_actual_count <> v_expected_count THEN
        RAISE EXCEPTION
            'FAIL PREFLIGHT: Expected % mapped listings, got %',
            v_expected_count, v_actual_count;
    END IF;

    RAISE NOTICE
        'PASS PREFLIGHT: All 41 listings mapped to canonical opportunities';

    -- Scenario 1: Direct Wuzzuf URL match and history preservation
    SELECT opportunity_id INTO v_opp_a
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000101'::UUID;

    SELECT opportunity_id INTO v_opp_b
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000102'::UUID;

    IF v_opp_a IS NULL
        OR v_opp_b IS NULL
        OR v_opp_a IS DISTINCT FROM v_opp_b THEN
        RAISE EXCEPTION 'FAIL S1: Direct Wuzzuf URL pair did not merge';
    END IF;

    SELECT primary_source_name INTO v_primary
    FROM silver.silver_opportunities
    WHERE opportunity_id = v_opp_a;

    IF v_primary IS DISTINCT FROM 'wuzzuf' THEN
        RAISE EXCEPTION
            'FAIL S1: Expected primary_source_name=wuzzuf, got %',
            v_primary;
    END IF;

    SELECT COUNT(*) INTO v_cnt
    FROM silver.silver_opportunity_history
    WHERE opportunity_id = v_opp_a;

    IF v_cnt <> 2 THEN
        RAISE EXCEPTION
            'FAIL S1: Expected 2 preserved history rows, got %',
            v_cnt;
    END IF;

    RAISE NOTICE 'PASS S1: Exact cross-source URL matching and Bronze history preservation';

    -- Scenario 2: Case-sensitive SharePoint URL path match
    SELECT opportunity_id INTO v_opp_a
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000201'::UUID;

    SELECT opportunity_id INTO v_opp_b
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000202'::UUID;

    IF v_opp_a IS NULL
        OR v_opp_b IS NULL
        OR v_opp_a IS DISTINCT FROM v_opp_b THEN
        RAISE EXCEPTION 'FAIL S2: Mixed-case ITIDA SharePoint URL did not merge';
    END IF;

    RAISE NOTICE 'PASS S2: Case-sensitive URL path matching';

    -- Scenario 3: Shared specific external application URL
    SELECT opportunity_id INTO v_opp_a
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000301'::UUID;

    SELECT opportunity_id INTO v_opp_b
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000302'::UUID;

    IF v_opp_a IS NULL
        OR v_opp_b IS NULL
        OR v_opp_a IS DISTINCT FROM v_opp_b THEN
        RAISE EXCEPTION 'FAIL S3: Shared specific external URL pair did not merge';
    END IF;

    RAISE NOTICE 'PASS S3: Shared external application URL matching';

    -- Scenario 4: Tier 2 composite match (English vs Arabic Cairo)
    SELECT opportunity_id INTO v_opp_a
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000401'::UUID;

    SELECT opportunity_id INTO v_opp_b
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000402'::UUID;

    IF v_opp_a IS NULL
        OR v_opp_b IS NULL
        OR v_opp_a IS DISTINCT FROM v_opp_b THEN
        RAISE EXCEPTION 'FAIL S4: Composite English/Arabic Cairo pair did not merge';
    END IF;

    RAISE NOTICE 'PASS S4: Multi-signal composite matching';

    -- Scenario 5A: Same-source direct duplicate prevention
    SELECT opportunity_id INTO v_opp_a
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000501'::UUID;

    SELECT opportunity_id INTO v_opp_b
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000502'::UUID;

    IF v_opp_a IS NULL
        OR v_opp_b IS NULL
        OR v_opp_a = v_opp_b THEN
        RAISE EXCEPTION 'FAIL S5A: Same-source direct listings merged or missing';
    END IF;

    -- Scenario 5B: Same-source transitive duplicate prevention
    SELECT opportunity_id, match_method
    INTO v_opp_a, v_method
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000511'::UUID;

    SELECT COUNT(DISTINCT opportunity_id) INTO v_cnt
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id IN (
        '22222222-2222-4222-8222-000000000511'::UUID,
        '22222222-2222-4222-8222-000000000512'::UUID,
        '22222222-2222-4222-8222-000000000513'::UUID
    );

    IF v_cnt <> 3 THEN
        RAISE EXCEPTION
            'FAIL S5B: Transitive same-source chain should remain 3 distinct opportunities, got %',
            v_cnt;
    END IF;

    IF v_method IS DISTINCT FROM 'singleton_transitive_conflict' THEN
        RAISE EXCEPTION
            'FAIL S5B: Expected singleton_transitive_conflict, got %',
            v_method;
    END IF;

    RAISE NOTICE 'PASS S5: Same-source direct and transitive duplicate prevention';

    -- Scenario 6: Ambiguous records stay separate
    SELECT COUNT(DISTINCT opportunity_id) INTO v_cnt
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id IN (
        '22222222-2222-4222-8222-000000000601'::UUID,
        '22222222-2222-4222-8222-000000000602'::UUID,
        '22222222-2222-4222-8222-000000000603'::UUID
    );

    IF v_cnt <> 3 THEN
        RAISE EXCEPTION
            'FAIL S6: Ambiguous records should remain 3 distinct opportunities, got %',
            v_cnt;
    END IF;

    RAISE NOTICE 'PASS S6: Ambiguous same-source composite guard';

    -- Scenario 7: Generic application portal exclusion
    SELECT COUNT(DISTINCT opportunity_id) INTO v_cnt
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id IN (
        '22222222-2222-4222-8222-000000000701'::UUID,
        '22222222-2222-4222-8222-000000000702'::UUID,
        '22222222-2222-4222-8222-000000000703'::UUID,
        '22222222-2222-4222-8222-000000000704'::UUID,
        '22222222-2222-4222-8222-000000000705'::UUID,
        '22222222-2222-4222-8222-000000000706'::UUID
    );

    IF v_cnt <> 6 THEN
        RAISE EXCEPTION
            'FAIL S7: Generic portal listings merged (expected 6 distinct, got %)',
            v_cnt;
    END IF;

    RAISE NOTICE 'PASS S7: Generic application portal exclusion (root + non-root paths)';

    -- Scenario 8: Four-source valid transitive chain
    SELECT opportunity_id INTO v_opp_a
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000801'::UUID;

    SELECT opportunity_id INTO v_opp_b
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000802'::UUID;

    SELECT opportunity_id INTO v_opp_c
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000803'::UUID;

    SELECT opportunity_id INTO v_opp_d
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000804'::UUID;

    IF v_opp_a IS NULL
        OR v_opp_b IS NULL
        OR v_opp_c IS NULL
        OR v_opp_d IS NULL
        OR v_opp_a IS DISTINCT FROM v_opp_b
        OR v_opp_b IS DISTINCT FROM v_opp_c
        OR v_opp_c IS DISTINCT FROM v_opp_d THEN
        RAISE EXCEPTION 'FAIL S8: 4-source valid transitive chain did not converge';
    END IF;

    SELECT primary_source_name INTO v_primary
    FROM silver.silver_opportunities
    WHERE opportunity_id = v_opp_a;

    IF v_primary IS DISTINCT FROM 'itida' THEN
        RAISE EXCEPTION
            'FAIL S8: Expected higher-authority itida to remain primary/anchor, got %',
            v_primary;
    END IF;

    RAISE NOTICE 'PASS S8: 4-source transitive chain convergence and anchor stability';

    -- Scenario 9A: ADR-019 salary equivalence
    SELECT opportunity_id INTO v_opp_a
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000901'::UUID;

    SELECT opportunity_id INTO v_opp_b
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000902'::UUID;

    IF v_opp_a IS NULL
        OR v_opp_b IS NULL
        OR v_opp_a IS DISTINCT FROM v_opp_b THEN
        RAISE EXCEPTION 'FAIL S9A: Salary equivalence pair did not merge';
    END IF;

    SELECT o.has_source_attribute_conflicts, o.conflicting_attributes
    INTO v_has_conflicts, v_conflicts
    FROM silver.silver_opportunities o
    WHERE o.opportunity_id = v_opp_a;

    IF v_has_conflicts IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION
            'FAIL S9A: 10000 vs 10000.00 falsely flagged as conflict: %',
            v_conflicts;
    END IF;

    -- Scenario 9B: Salary and employment type conflicts
    SELECT opportunity_id INTO v_opp_a
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000911'::UUID;

    SELECT opportunity_id INTO v_opp_b
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id = '22222222-2222-4222-8222-000000000912'::UUID;

    IF v_opp_a IS NULL
        OR v_opp_b IS NULL
        OR v_opp_a IS DISTINCT FROM v_opp_b THEN
        RAISE EXCEPTION 'FAIL S9B: Salary/employment conflict pair did not merge';
    END IF;

    SELECT o.has_source_attribute_conflicts, o.conflicting_attributes
    INTO v_has_conflicts, v_conflicts
    FROM silver.silver_opportunities o
    WHERE o.opportunity_id = v_opp_a;

    IF v_has_conflicts IS DISTINCT FROM TRUE
        OR (v_conflicts ? 'salary') IS DISTINCT FROM TRUE
        OR (v_conflicts ? 'employment_types') IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION
            'FAIL S9B: Expected salary and employment_types conflicts, got %',
            v_conflicts;
    END IF;

    RAISE NOTICE 'PASS S9: ADR-019 salary normalization and salary/employment_types conflict reporting';

    -- Scenario 10A: Independent false-positive pair
    SELECT COUNT(DISTINCT opportunity_id) INTO v_cnt
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id IN (
        '22222222-2222-4222-8222-000000001001'::UUID,
        '22222222-2222-4222-8222-000000001002'::UUID
    );

    IF v_cnt <> 2 THEN
        RAISE EXCEPTION
            'FAIL S10A: Expected 2 distinct opportunities, got %',
            v_cnt;
    END IF;

    RAISE NOTICE 'PASS S10A';

    -- Scenario 10B: Independent false-positive pair
    SELECT COUNT(DISTINCT opportunity_id) INTO v_cnt
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id IN (
        '22222222-2222-4222-8222-000000001011'::UUID,
        '22222222-2222-4222-8222-000000001012'::UUID
    );

    IF v_cnt <> 2 THEN
        RAISE EXCEPTION
            'FAIL S10B: Expected 2 distinct opportunities, got %',
            v_cnt;
    END IF;

    RAISE NOTICE 'PASS S10B';

    -- Scenario 10C: Independent false-positive pair
    SELECT COUNT(DISTINCT opportunity_id) INTO v_cnt
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id IN (
        '22222222-2222-4222-8222-000000001021'::UUID,
        '22222222-2222-4222-8222-000000001022'::UUID
    );

    IF v_cnt <> 2 THEN
        RAISE EXCEPTION
            'FAIL S10C: Expected 2 distinct opportunities, got %',
            v_cnt;
    END IF;

    RAISE NOTICE 'PASS S10C';

    -- Scenario 10D: Independent false-positive group
    SELECT COUNT(DISTINCT opportunity_id) INTO v_cnt
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id IN (
        '22222222-2222-4222-8222-000000001031'::UUID,
        '22222222-2222-4222-8222-000000001032'::UUID,
        '22222222-2222-4222-8222-000000001033'::UUID
    );

    IF v_cnt <> 3 THEN
        RAISE EXCEPTION
            'FAIL S10D: Expected 3 distinct opportunities, got %',
            v_cnt;
    END IF;

    RAISE NOTICE 'PASS S10D';

    -- Scenario 10E: Independent false-positive pair
    SELECT COUNT(DISTINCT opportunity_id) INTO v_cnt
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id IN (
        '22222222-2222-4222-8222-000000001041'::UUID,
        '22222222-2222-4222-8222-000000001042'::UUID
    );

    IF v_cnt <> 2 THEN
        RAISE EXCEPTION
            'FAIL S10E: Expected 2 distinct opportunities, got %',
            v_cnt;
    END IF;

    RAISE NOTICE 'PASS S10E';

    -- Scenario 10: Combined false-positive prevention
    SELECT COUNT(DISTINCT opportunity_id) INTO v_cnt
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id IN (
        '22222222-2222-4222-8222-000000001001'::UUID,
        '22222222-2222-4222-8222-000000001002'::UUID,
        '22222222-2222-4222-8222-000000001011'::UUID,
        '22222222-2222-4222-8222-000000001012'::UUID,
        '22222222-2222-4222-8222-000000001021'::UUID,
        '22222222-2222-4222-8222-000000001022'::UUID,
        '22222222-2222-4222-8222-000000001031'::UUID,
        '22222222-2222-4222-8222-000000001032'::UUID,
        '22222222-2222-4222-8222-000000001033'::UUID,
        '22222222-2222-4222-8222-000000001041'::UUID,
        '22222222-2222-4222-8222-000000001042'::UUID
    );

    IF v_cnt <> 11 THEN
        RAISE EXCEPTION
            'FAIL S10: False-positive prevention failed (expected 11 distinct, got %)',
            v_cnt;
    END IF;

    RAISE NOTICE 'PASS S10: False-positive prevention including incompatible work_modes and transitive temporal drift';

    RAISE NOTICE 'ALL PHASE 4 SYNTHETIC INTEGRATION CHECKS PASSED';
END;
$$;