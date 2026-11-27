-- Source contribution, deduplication overlap, lifecycle breakdown, and run quality metrics.
-- Aggregation semantics:
--   - primary_* columns are strictly ADDITIVE across all eight sources (sum = gold.fct_opportunities totals).
--   - *_contributed_* columns are NON-ADDITIVE across sources because a multi-source opportunity
--     contributes to every participating source row.

WITH source_opp_metrics AS (
    SELECT
        fos.source_name,
        COUNT(*) AS total_source_listings,
        COUNT(DISTINCT fos.opportunity_id) AS canonical_opportunities_contributed,
        COUNT(*) FILTER (WHERE fos.is_primary_source) AS primary_canonical_opportunities,
        COUNT(*) FILTER (WHERE fo.is_multi_source) AS multi_source_listings,

        -- Strictly additive primary-source lifecycle counts (SUM across sources = fct_opportunities status totals)
        COUNT(*) FILTER (WHERE fos.is_primary_source AND fo.is_active) AS primary_active_opportunities,
        COUNT(*) FILTER (WHERE fos.is_primary_source AND fo.is_expired) AS primary_expired_opportunities,
        COUNT(*) FILTER (WHERE fos.is_primary_source AND fo.is_closed) AS primary_closed_opportunities,
        COUNT(*) FILTER (WHERE fos.is_primary_source AND fo.is_unknown_status) AS primary_unknown_opportunities,

        -- Non-additive contributed lifecycle counts (an opportunity on 2 sources counts under both)
        COUNT(DISTINCT fos.opportunity_id) FILTER (WHERE fo.is_active) AS active_contributed_opportunities,
        COUNT(DISTINCT fos.opportunity_id) FILTER (WHERE fo.is_expired) AS expired_contributed_opportunities,
        COUNT(DISTINCT fos.opportunity_id) FILTER (WHERE fo.is_closed) AS closed_contributed_opportunities,
        COUNT(DISTINCT fos.opportunity_id) FILTER (WHERE fo.is_unknown_status) AS unknown_contributed_opportunities
    FROM {{ ref('fct_opportunity_sources') }} fos
    INNER JOIN {{ ref('fct_opportunities') }} fo
        ON fos.opportunity_id = fo.opportunity_id
    GROUP BY fos.source_name
),

run_quality_metrics AS (
    SELECT
        source_name,
        COUNT(*) AS total_runs,
        COUNT(*) FILTER (WHERE is_completed) AS completed_runs,
        COUNT(*) FILTER (WHERE is_failed) AS failed_runs,
        COALESCE(SUM(records_received), 0) AS total_records_received,
        COALESCE(SUM(records_invalid), 0) AS total_records_invalid_reported,
        COALESCE(SUM(persisted_invalid_record_count), 0) AS total_invalid_records_persisted
    FROM {{ ref('fct_collection_runs') }}
    GROUP BY source_name
)

SELECT
    ds.source_name,
    ds.source_display_name,
    ds.source_authority_rank,
    ds.collection_approach,
    COALESCE(som.total_source_listings, 0) AS total_source_listings,
    COALESCE(som.canonical_opportunities_contributed, 0) AS canonical_opportunities_contributed,
    COALESCE(som.primary_canonical_opportunities, 0) AS primary_canonical_opportunities,
    COALESCE(som.multi_source_listings, 0) AS multi_source_listings,
    COALESCE(som.primary_active_opportunities, 0) AS primary_active_opportunities,
    COALESCE(som.primary_expired_opportunities, 0) AS primary_expired_opportunities,
    COALESCE(som.primary_closed_opportunities, 0) AS primary_closed_opportunities,
    COALESCE(som.primary_unknown_opportunities, 0) AS primary_unknown_opportunities,
    COALESCE(som.active_contributed_opportunities, 0) AS active_contributed_opportunities,
    COALESCE(som.expired_contributed_opportunities, 0) AS expired_contributed_opportunities,
    COALESCE(som.closed_contributed_opportunities, 0) AS closed_contributed_opportunities,
    COALESCE(som.unknown_contributed_opportunities, 0) AS unknown_contributed_opportunities,
    COALESCE(rqm.total_runs, 0) AS total_runs,
    COALESCE(rqm.completed_runs, 0) AS completed_runs,
    COALESCE(rqm.failed_runs, 0) AS failed_runs,
    COALESCE(rqm.total_records_received, 0) AS total_records_received,
    COALESCE(rqm.total_records_invalid_reported, 0) AS total_records_invalid_reported,
    COALESCE(rqm.total_invalid_records_persisted, 0) AS total_invalid_records_persisted,
    ds.latest_run_started_at,
    ds.latest_seen_at

FROM {{ ref('dim_sources') }} ds
LEFT JOIN source_opp_metrics som
    ON ds.source_name = som.source_name
LEFT JOIN run_quality_metrics rqm
    ON ds.source_name = rqm.source_name
