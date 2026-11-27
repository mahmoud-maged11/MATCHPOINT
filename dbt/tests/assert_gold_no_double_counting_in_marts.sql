-- Fails if Gold analytical marts double-count or drop canonical opportunities or source listings:
-- 1. SUM(primary_canonical_opportunities) across mart_opportunities_by_source == COUNT(*) in fct_opportunities.
-- 2. SUM(primary_active/expired/closed/unknown_opportunities) across mart_opportunities_by_source == fct_opportunities status counts.
-- 3. SUM(total_source_listings) across mart_opportunities_by_source == COUNT(*) in fct_opportunity_sources.
-- 4. SUM(canonical_opportunity_count) across mart_opportunities_by_location (including 'unreported') == COUNT(*) in fct_opportunities.
-- 5. SUM(canonical_opportunity_count) across mart_opportunity_lifecycle_trends == COUNT(*) with non-null published_date_key in fct_opportunities.
-- 6. mart_opportunities_by_work_mode total == bridge_opportunity_work_modes rows + unreported opportunities (zero Cartesian multiplication).
-- 7. mart_opportunities_by_employment_type total == bridge_opportunity_employment_types rows + unreported opportunities (zero Cartesian multiplication).

WITH checks AS (
    SELECT
        'mart_by_source_primary_total'::TEXT AS check_name,
        COALESCE((SELECT SUM(primary_canonical_opportunities) FROM {{ ref('mart_opportunities_by_source') }}), 0) AS mart_total,
        (SELECT COUNT(*) FROM {{ ref('fct_opportunities') }}) AS fact_total

    UNION ALL

    SELECT
        'mart_by_source_primary_active'::TEXT,
        COALESCE((SELECT SUM(primary_active_opportunities) FROM {{ ref('mart_opportunities_by_source') }}), 0),
        (SELECT COUNT(*) FROM {{ ref('fct_opportunities') }} WHERE is_active)

    UNION ALL

    SELECT
        'mart_by_source_primary_expired'::TEXT,
        COALESCE((SELECT SUM(primary_expired_opportunities) FROM {{ ref('mart_opportunities_by_source') }}), 0),
        (SELECT COUNT(*) FROM {{ ref('fct_opportunities') }} WHERE is_expired)

    UNION ALL

    SELECT
        'mart_by_source_primary_closed'::TEXT,
        COALESCE((SELECT SUM(primary_closed_opportunities) FROM {{ ref('mart_opportunities_by_source') }}), 0),
        (SELECT COUNT(*) FROM {{ ref('fct_opportunities') }} WHERE is_closed)

    UNION ALL

    SELECT
        'mart_by_source_primary_unknown'::TEXT,
        COALESCE((SELECT SUM(primary_unknown_opportunities) FROM {{ ref('mart_opportunities_by_source') }}), 0),
        (SELECT COUNT(*) FROM {{ ref('fct_opportunities') }} WHERE is_unknown_status)

    UNION ALL

    SELECT
        'mart_by_source_listings_total'::TEXT,
        COALESCE((SELECT SUM(total_source_listings) FROM {{ ref('mart_opportunities_by_source') }}), 0),
        (SELECT COUNT(*) FROM {{ ref('fct_opportunity_sources') }})

    UNION ALL

    SELECT
        'mart_by_location_full_reconciliation'::TEXT,
        COALESCE((SELECT SUM(canonical_opportunity_count) FROM {{ ref('mart_opportunities_by_location') }}), 0),
        (SELECT COUNT(*) FROM {{ ref('fct_opportunities') }})

    UNION ALL

    SELECT
        'mart_lifecycle_trends_reliable_published'::TEXT,
        COALESCE((SELECT SUM(canonical_opportunity_count) FROM {{ ref('mart_opportunity_lifecycle_trends') }}), 0),
        (SELECT COUNT(*) FROM {{ ref('fct_opportunities') }} WHERE published_date_key IS NOT NULL)

    UNION ALL

    SELECT
        'mart_by_work_mode_no_cartesian_multiplication'::TEXT,
        COALESCE((SELECT SUM(opportunities_with_work_mode_count) FROM {{ ref('mart_opportunities_by_work_mode') }}), 0),
        (
            (SELECT COUNT(*) FROM {{ ref('bridge_opportunity_work_modes') }})
            + (
                SELECT COUNT(*)
                FROM {{ ref('fct_opportunities') }} fo
                WHERE NOT EXISTS (
                    SELECT 1 FROM {{ ref('bridge_opportunity_work_modes') }} wm
                    WHERE wm.opportunity_id = fo.opportunity_id
                )
            )
        )

    UNION ALL

    SELECT
        'mart_by_employment_type_no_cartesian_multiplication'::TEXT,
        COALESCE((SELECT SUM(opportunities_with_employment_type_count) FROM {{ ref('mart_opportunities_by_employment_type') }}), 0),
        (
            (SELECT COUNT(*) FROM {{ ref('bridge_opportunity_employment_types') }})
            + (
                SELECT COUNT(*)
                FROM {{ ref('fct_opportunities') }} fo
                WHERE NOT EXISTS (
                    SELECT 1 FROM {{ ref('bridge_opportunity_employment_types') }} et
                    WHERE et.opportunity_id = fo.opportunity_id
                )
            )
        )
)

SELECT check_name, mart_total, fact_total
FROM checks
WHERE mart_total <> fact_total
