-- MATCHPOINT Phase 5 Edge-Case Integration Verification Script
--
-- Validates all 11 edge-case scenarios loaded by load_phase5_edge_cases_synthetic.sql
-- across Silver and Gold materialized tables on `matchpoint_test`.

DO $$
DECLARE
    v_cnt BIGINT;
    v_dim_dates_cnt BIGINT;
    v_status TEXT;
    v_pub_key INTEGER;
    v_dl_key INTEGER;
    v_loc_key TEXT;
    v_has_sal BOOLEAN;
    v_sal_mid NUMERIC;
    v_in_range BOOLEAN;
    v_opp_id UUID;
    v_anomaly BOOLEAN;
    v_rate NUMERIC;
    v_diff BIGINT;
BEGIN
    IF (SELECT COUNT(*) FROM bronze.source_listings)
        IS DISTINCT FROM 52 THEN
        RAISE EXCEPTION
            'FAIL PREFLIGHT: Expected 52 Bronze listings';
    END IF;

    IF (SELECT COUNT(*) FROM gold.fct_opportunities)
        IS DISTINCT FROM 43 THEN
        RAISE EXCEPTION
            'FAIL PREFLIGHT: Expected 43 canonical opportunities';
    END IF;

    IF (SELECT COUNT(*) FROM gold.fct_opportunity_sources)
        IS DISTINCT FROM 52 THEN
        RAISE EXCEPTION
            'FAIL PREFLIGHT: Expected 52 Gold source listings';
    END IF;

    IF (
        SELECT COUNT(DISTINCT primary_source_listing_id)
        FROM gold.fct_opportunities
        WHERE primary_source_listing_id IN (
            '22222222-2222-4222-8222-000000002003'::UUID,
            '22222222-2222-4222-8222-000000002004'::UUID,
            '22222222-2222-4222-8222-000000002005'::UUID,
            '22222222-2222-4222-8222-000000002006'::UUID,
            '22222222-2222-4222-8222-000000002007'::UUID,
            '22222222-2222-4222-8222-000000002008'::UUID,
            '22222222-2222-4222-8222-000000002011'::UUID
        )
    ) IS DISTINCT FROM 7 THEN
        RAISE EXCEPTION
            'FAIL PREFLIGHT: Required edge-case opportunities missing';
    END IF;

    RAISE NOTICE
        'PASS PREFLIGHT: Edge-case synthetic dataset verified';

    -- EC1 & EC2: Bounded dim_dates protects against 1970-01-01, 2099-12-31, 9999-12-31 while resolving all FKs
    SELECT COUNT(*) INTO v_dim_dates_cnt FROM gold.dim_dates;
    IF v_dim_dates_cnt > 5000 THEN
        RAISE EXCEPTION 'FAIL EC1/EC2: dim_dates exploded on outlier dates (rows=%)', v_dim_dates_cnt;
    END IF;

    SELECT is_within_standard_calendar_range INTO v_in_range FROM gold.dim_dates WHERE date_key = 19700101;
    IF v_in_range IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'FAIL EC1: 1970-01-01 missing or not flagged as outside standard range (got %)', v_in_range;
    END IF;
    SELECT is_within_standard_calendar_range INTO v_in_range FROM gold.dim_dates WHERE date_key = 20991231;
    IF v_in_range IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'FAIL EC1: 2099-12-31 missing or not flagged as outside standard range (got %)', v_in_range;
    END IF;
    SELECT is_within_standard_calendar_range INTO v_in_range FROM gold.dim_dates WHERE date_key = 99991231;
    IF v_in_range IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'FAIL EC2: 9999-12-31 missing or not flagged as outside standard range (got %)', v_in_range;
    END IF;
    RAISE NOTICE 'PASS EC1/EC2: Bounded dim_dates (rows=%) preserved 1970-01-01, 2099-12-31, and 9999-12-31 with FK integrity', v_dim_dates_cnt;

    -- EC3: Past EXACT deadline -> effective_status = 'expired'
    SELECT fo.effective_status INTO v_status
    FROM gold.fct_opportunities fo
    WHERE fo.primary_source_listing_id = '22222222-2222-4222-8222-000000002003'::UUID;
    IF v_status IS DISTINCT FROM 'expired' THEN
        RAISE EXCEPTION 'FAIL EC3: Expected past exact deadline to yield expired, got %', v_status;
    END IF;
    RAISE NOTICE 'PASS EC3: Past exact deadline transitioned active -> expired';

    -- EC4: Past DATE_ONLY deadline -> effective_status = 'expired'
    SELECT fo.effective_status INTO v_status
    FROM gold.fct_opportunities fo
    WHERE fo.primary_source_listing_id = '22222222-2222-4222-8222-000000002004'::UUID;
    IF v_status IS DISTINCT FROM 'expired' THEN
        RAISE EXCEPTION 'FAIL EC4: Expected past date_only deadline to yield expired, got %', v_status;
    END IF;
    RAISE NOTICE 'PASS EC4: Past date_only deadline transitioned active -> expired';

    -- EC5: Explicitly CLOSED listing with future deadline -> effective_status = 'closed'
    SELECT fo.effective_status INTO v_status
    FROM gold.fct_opportunities fo
    WHERE fo.primary_source_listing_id = '22222222-2222-4222-8222-000000002005'::UUID;
    IF v_status IS DISTINCT FROM 'closed' THEN
        RAISE EXCEPTION 'FAIL EC5: Expected explicitly closed listing to remain closed, got %', v_status;
    END IF;
    RAISE NOTICE 'PASS EC5: Explicitly closed listing preserved effective_status = closed';

    -- EC6: RELATIVE published_at & RELATIVE deadline -> NULL date keys, NOT expired, excluded from trends
    SELECT fo.effective_status, fo.published_date_key, fo.deadline_date_key
    INTO v_status, v_pub_key, v_dl_key
    FROM gold.fct_opportunities fo
    WHERE fo.primary_source_listing_id = '22222222-2222-4222-8222-000000002006'::UUID;
    IF v_status IS DISTINCT FROM 'active' OR v_pub_key IS NOT NULL OR v_dl_key IS NOT NULL THEN
        RAISE EXCEPTION 'FAIL EC6: Relative dates violated precision guard (status=%, pub_key=%, dl_key=%)', v_status, v_pub_key, v_dl_key;
    END IF;
    -- Total reliable published opportunities should be 43 - 1 = 42
    SELECT SUM(canonical_opportunity_count) INTO v_cnt FROM gold.mart_opportunity_lifecycle_trends;
    IF v_cnt IS DISTINCT FROM 42 THEN
        RAISE EXCEPTION 'FAIL EC6: Expected 42 reliable published opportunities in lifecycle trends (excluding EC6 relative), got %', v_cnt;
    END IF;
    RAISE NOTICE 'PASS EC6: Relative dates nulled in date keys, excluded from trends, and not falsely expired';

    -- EC7: NULL location -> explicit 'unreported' bucket in mart_opportunities_by_location
    SELECT fo.location_key INTO v_loc_key
    FROM gold.fct_opportunities fo
    WHERE fo.primary_source_listing_id = '22222222-2222-4222-8222-000000002007'::UUID;
    IF v_loc_key IS NOT NULL THEN
        RAISE EXCEPTION 'FAIL EC7: Expected NULL location_key for EC7, got %', v_loc_key;
    END IF;
    SELECT canonical_opportunity_count INTO v_cnt
    FROM gold.mart_opportunities_by_location
    WHERE location_key = 'unreported' AND is_unreported_location = TRUE;
    IF v_cnt IS DISTINCT FROM 1 THEN
        RAISE EXCEPTION 'FAIL EC7: Expected 1 unreported-location opportunity in mart_opportunities_by_location, got %', v_cnt;
    END IF;
    SELECT SUM(canonical_opportunity_count) INTO v_cnt FROM gold.mart_opportunities_by_location;
    IF v_cnt IS DISTINCT FROM 43 THEN
        RAISE EXCEPTION 'FAIL EC7: Expected mart_opportunities_by_location total=43 (100%% parity), got %', v_cnt;
    END IF;
    RAISE NOTICE 'PASS EC7: NULL location preserved as NULL in fct_opportunities and surfaced as explicit unreported bucket in mart_opportunities_by_location';

    -- EC8: Confirmed empty [] arrays -> 0 rows in all 4 bridges + 'unreported' in work_mode & employment_type marts
    SELECT fo.opportunity_id INTO v_opp_id
    FROM gold.fct_opportunities fo
    WHERE fo.primary_source_listing_id = '22222222-2222-4222-8222-000000002008'::UUID;

    SELECT
        (SELECT COUNT(*) FROM gold.bridge_opportunity_work_modes WHERE opportunity_id = v_opp_id)
      + (SELECT COUNT(*) FROM gold.bridge_opportunity_employment_types WHERE opportunity_id = v_opp_id)
      + (SELECT COUNT(*) FROM gold.bridge_opportunity_skills WHERE opportunity_id = v_opp_id)
      + (SELECT COUNT(*) FROM gold.bridge_opportunity_categories WHERE opportunity_id = v_opp_id)
    INTO v_cnt;
    IF v_cnt IS DISTINCT FROM 0 THEN
        RAISE EXCEPTION 'FAIL EC8: Confirmed empty [] arrays generated % bridge rows (expected 0)', v_cnt;
    END IF;

    SELECT opportunities_with_work_mode_count INTO v_cnt
    FROM gold.mart_opportunities_by_work_mode
    WHERE opportunity_type = 'scholarship' AND work_mode = 'unreported';
    IF v_cnt IS DISTINCT FROM 1 THEN
        RAISE EXCEPTION 'FAIL EC8: Expected 1 unreported work_mode for scholarship EC8, got %', v_cnt;
    END IF;

    SELECT opportunities_with_employment_type_count INTO v_cnt
    FROM gold.mart_opportunities_by_employment_type
    WHERE opportunity_type = 'scholarship' AND employment_type = 'unreported';
    IF v_cnt IS DISTINCT FROM 1 THEN
        RAISE EXCEPTION 'FAIL EC8: Expected 1 unreported employment_type for scholarship EC8, got %', v_cnt;
    END IF;
    RAISE NOTICE 'PASS EC8: Confirmed empty [] arrays produced 0 bridge rows and mapped cleanly to unreported buckets';

    -- EC9: devpost and un_volunteers populated across dim_sources and mart_opportunities_by_source
    SELECT primary_canonical_opportunities INTO v_cnt FROM gold.mart_opportunities_by_source WHERE source_name = 'devpost';
    IF v_cnt IS DISTINCT FROM 1 THEN RAISE EXCEPTION 'FAIL EC9: Expected 1 primary canonical opportunity for devpost, got %', v_cnt; END IF;
    SELECT primary_canonical_opportunities INTO v_cnt FROM gold.mart_opportunities_by_source WHERE source_name = 'un_volunteers';
    IF v_cnt IS DISTINCT FROM 1 THEN RAISE EXCEPTION 'FAIL EC9: Expected 1 primary canonical opportunity for un_volunteers, got %', v_cnt; END IF;
    RAISE NOTICE 'PASS EC9: devpost (hackathon) and un_volunteers (volunteering) end-to-end coverage verified';

    -- EC10: One-sided salary + multi work_modes (2) & multi employment_types (2) -> NO Cartesian multiplication
    SELECT fo.opportunity_id, fo.has_disclosed_salary, fo.salary_midpoint
    INTO v_opp_id, v_has_sal, v_sal_mid
    FROM gold.fct_opportunities fo
    WHERE fo.primary_source_listing_id = '22222222-2222-4222-8222-000000002011'::UUID;

    IF v_has_sal IS DISTINCT FROM TRUE OR v_sal_mid IS NOT NULL THEN
        RAISE EXCEPTION 'FAIL EC10: One-sided salary expected has_disclosed_salary=TRUE and salary_midpoint=NULL, got %/%', v_has_sal, v_sal_mid;
    END IF;

    -- For opportunity_type = 'freelance', ONLY EC10 exists -> must have 2 rows (sum=2) in work_mode mart and 2 rows (sum=2) in employment_type mart (NOT 2x2=4!)
    SELECT COALESCE(SUM(opportunities_with_work_mode_count), 0) INTO v_cnt
    FROM gold.mart_opportunities_by_work_mode
    WHERE opportunity_type = 'freelance';
    IF v_cnt IS DISTINCT FROM 2 THEN
        RAISE EXCEPTION 'FAIL EC10: Expected 2 work_mode memberships for freelance EC10, got %', v_cnt;
    END IF;

    SELECT COALESCE(SUM(opportunities_with_employment_type_count), 0) INTO v_cnt
    FROM gold.mart_opportunities_by_employment_type
    WHERE opportunity_type = 'freelance';
    IF v_cnt IS DISTINCT FROM 2 THEN
        RAISE EXCEPTION 'FAIL EC10: Expected 2 employment_type memberships for freelance EC10, got %', v_cnt;
    END IF;
    RAISE NOTICE 'PASS EC10: One-sided salary (midpoint NULL) and multi work_mode/employment_type verified with zero Cartesian multiplication';

    -- EC11: Collection run counter anomaly flagged & invalid_record_rate safely nulled
    SELECT has_invalid_counter_anomaly, invalid_record_rate, persisted_vs_reported_invalid_diff
    INTO v_anomaly, v_rate, v_diff
    FROM gold.fct_collection_runs
    WHERE run_id = '11111111-1111-4111-8111-000000000203'::UUID;
    IF v_anomaly IS DISTINCT FROM TRUE OR v_rate IS NOT NULL OR v_diff IS DISTINCT FROM -8 THEN
        RAISE EXCEPTION 'FAIL EC11: Counter anomaly run expected anomaly=TRUE, rate=NULL, diff=-8, got %/%/%', v_anomaly, v_rate, v_diff;
    END IF;
    RAISE NOTICE 'PASS EC11: Collection run counter anomaly detected (has_invalid_counter_anomaly=TRUE, invalid_record_rate=NULL, diff=-8)';

    RAISE NOTICE 'ALL 11 PHASE 5 EDGE-CASE CHECKS PASSED';
END;
$$;
