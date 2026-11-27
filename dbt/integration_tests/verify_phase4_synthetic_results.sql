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
BEGIN
    -- Scenario 1: Direct Wuzzuf URL match + primary source = wuzzuf + 2 Bronze history rows preserved
    SELECT opportunity_id INTO v_opp_a FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000101'::UUID;
    SELECT opportunity_id INTO v_opp_b FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000102'::UUID;
    IF v_opp_a IS DISTINCT FROM v_opp_b THEN RAISE EXCEPTION 'FAIL S1: Direct Wuzzuf URL pair did not merge'; END IF;
    SELECT primary_source_name INTO v_primary FROM silver.silver_opportunities WHERE opportunity_id = v_opp_a;
    IF v_primary <> 'wuzzuf' THEN RAISE EXCEPTION 'FAIL S1: Expected primary_source_name=wuzzuf, got %', v_primary; END IF;
    SELECT COUNT(*) INTO v_cnt FROM silver.silver_opportunity_history WHERE opportunity_id = v_opp_a;
    IF v_cnt <> 2 THEN RAISE EXCEPTION 'FAIL S1: Expected 2 preserved history rows, got %', v_cnt; END IF;
    RAISE NOTICE 'PASS S1: Exact cross-source URL matching and Bronze history preservation';

    -- Scenario 2: Case-sensitive SharePoint URL path match (Fix 1)
    SELECT opportunity_id INTO v_opp_a FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000201'::UUID;
    SELECT opportunity_id INTO v_opp_b FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000202'::UUID;
    IF v_opp_a IS DISTINCT FROM v_opp_b THEN RAISE EXCEPTION 'FAIL S2: Mixed-case ITIDA SharePoint URL did not merge'; END IF;
    RAISE NOTICE 'PASS S2: Case-sensitive URL path matching';

    -- Scenario 3: Shared specific external application URL (Tier 1B)
    SELECT opportunity_id INTO v_opp_a FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000301'::UUID;
    SELECT opportunity_id INTO v_opp_b FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000302'::UUID;
    IF v_opp_a IS DISTINCT FROM v_opp_b THEN RAISE EXCEPTION 'FAIL S3: Shared specific external URL pair did not merge'; END IF;
    RAISE NOTICE 'PASS S3: Shared external application URL matching';

    -- Scenario 4: Tier 2 composite match (English vs Arabic Cairo)
    SELECT opportunity_id INTO v_opp_a FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000401'::UUID;
    SELECT opportunity_id INTO v_opp_b FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000402'::UUID;
    IF v_opp_a IS DISTINCT FROM v_opp_b THEN RAISE EXCEPTION 'FAIL S4: Composite English/Arabic Cairo pair did not merge'; END IF;
    RAISE NOTICE 'PASS S4: Multi-signal composite matching';

    -- Scenario 5A & 5B: Same-source direct AND transitive duplicate prevention (Fix 2)
    SELECT opportunity_id INTO v_opp_a FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000501'::UUID;
    SELECT opportunity_id INTO v_opp_b FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000502'::UUID;
    IF v_opp_a = v_opp_b THEN RAISE EXCEPTION 'FAIL S5A: Same-source direct listings merged'; END IF;

    SELECT opportunity_id, match_method INTO v_opp_a, v_method FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000511'::UUID;
    SELECT COUNT(DISTINCT opportunity_id) INTO v_cnt
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id IN (
        '22222222-2222-4222-8222-000000000511'::UUID,
        '22222222-2222-4222-8222-000000000512'::UUID,
        '22222222-2222-4222-8222-000000000513'::UUID
    );
    IF v_cnt <> 3 THEN RAISE EXCEPTION 'FAIL S5B: Transitive same-source chain should remain 3 distinct opportunities, got %', v_cnt; END IF;
    IF v_method <> 'singleton_transitive_conflict' THEN RAISE EXCEPTION 'FAIL S5B: Expected singleton_transitive_conflict, got %', v_method; END IF;
    RAISE NOTICE 'PASS S5: Same-source direct and transitive duplicate prevention';

    -- Scenario 6: Ambiguous records stay separate
    SELECT COUNT(DISTINCT opportunity_id) INTO v_cnt
    FROM silver.silver_opportunity_sources
    WHERE source_listing_id IN (
        '22222222-2222-4222-8222-000000000601'::UUID,
        '22222222-2222-4222-8222-000000000602'::UUID,
        '22222222-2222-4222-8222-000000000603'::UUID
    );
    IF v_cnt <> 3 THEN RAISE EXCEPTION 'FAIL S6: Ambiguous records should remain 3 distinct opportunities, got %', v_cnt; END IF;
    RAISE NOTICE 'PASS S6: Ambiguous same-source composite guard';

    -- Scenario 7: Generic application portal exclusion (Fix 4)
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
    IF v_cnt <> 6 THEN RAISE EXCEPTION 'FAIL S7: Generic portal listings merged (expected 6 distinct, got %)', v_cnt; END IF;
    RAISE NOTICE 'PASS S7: Generic application portal exclusion (root + non-root paths)';

    -- Scenario 8: 4-source valid transitive chain + Fix 5 anchor authority preservation
    SELECT opportunity_id INTO v_opp_a FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000801'::UUID;
    SELECT opportunity_id INTO v_opp_b FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000802'::UUID;
    SELECT opportunity_id INTO v_opp_c FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000803'::UUID;
    SELECT opportunity_id INTO v_opp_d FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000804'::UUID;
    IF NOT (v_opp_a = v_opp_b AND v_opp_b = v_opp_c AND v_opp_c = v_opp_d) THEN
        RAISE EXCEPTION 'FAIL S8: 4-source valid transitive chain did not converge';
    END IF;
    SELECT primary_source_name INTO v_primary FROM silver.silver_opportunities WHERE opportunity_id = v_opp_a;
    IF v_primary <> 'itida' THEN
        RAISE EXCEPTION 'FAIL S8: Expected higher-authority itida to remain primary/anchor, got %', v_primary;
    END IF;
    RAISE NOTICE 'PASS S8: 4-source transitive chain convergence and anchor stability';

    -- Scenario 9A & 9B: ADR-019 salary equivalence vs real salary_period + employment_types conflict (Fix 6)
    SELECT opportunity_id INTO v_opp_a FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000901'::UUID;
    SELECT opportunity_id INTO v_opp_b FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000902'::UUID;
    IF v_opp_a IS DISTINCT FROM v_opp_b THEN RAISE EXCEPTION 'FAIL S9A: Salary equivalence pair did not merge'; END IF;
    SELECT o.has_source_attribute_conflicts, o.conflicting_attributes
    INTO v_has_conflicts, v_conflicts
    FROM silver.silver_opportunities o
    WHERE o.opportunity_id = v_opp_a;
    IF v_has_conflicts THEN RAISE EXCEPTION 'FAIL S9A: 10000 vs 10000.00 falsely flagged as conflict: %', v_conflicts; END IF;

    SELECT opportunity_id INTO v_opp_a FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000911'::UUID;
    SELECT opportunity_id INTO v_opp_b FROM silver.silver_opportunity_sources WHERE source_listing_id = '22222222-2222-4222-8222-000000000912'::UUID;
    IF v_opp_a IS DISTINCT FROM v_opp_b THEN RAISE EXCEPTION 'FAIL S9B: Salary/employment conflict pair did not merge'; END IF;
    SELECT o.has_source_attribute_conflicts, o.conflicting_attributes
    INTO v_has_conflicts, v_conflicts
    FROM silver.silver_opportunities o
    WHERE o.opportunity_id = v_opp_a;
    IF NOT v_has_conflicts OR NOT (v_conflicts ? 'salary') OR NOT (v_conflicts ? 'employment_types') THEN
        RAISE EXCEPTION 'FAIL S9B: Expected salary and employment_types conflicts, got %', v_conflicts;
    END IF;
    RAISE NOTICE 'PASS S9: ADR-019 salary normalization and salary/employment_types conflict reporting';

    -- Scenario 10: False-positive prevention (including incompatible work_modes and transitive temporal drift)
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
    IF v_cnt <> 11 THEN RAISE EXCEPTION 'FAIL S10: False-positive prevention failed (expected 11 distinct, got %)', v_cnt; END IF;
    RAISE NOTICE 'PASS S10: False-positive prevention including incompatible work_modes and transitive temporal drift';

    RAISE NOTICE 'ALL PHASE 4 SYNTHETIC INTEGRATION CHECKS PASSED';
END;
$$;
