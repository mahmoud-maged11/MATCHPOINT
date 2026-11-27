{{
    config(
        indexes=[
            {'columns': ['source_name'], 'unique': True},
            {'columns': ['source_authority_rank'], 'unique': True}
        ]
    )
}}

-- Conformed dimension of all eight approved MATCHPOINT data sources from shared supported_sources.csv seed.

WITH source_listing_stats AS (
    SELECT
        source_name,
        COUNT(*) AS source_listing_count,
        COUNT(DISTINCT opportunity_id) AS canonical_participating_count,
        COUNT(*) FILTER (WHERE is_primary_source) AS canonical_primary_count,
        MIN(first_seen_at) AS earliest_seen_at,
        MAX(last_seen_at) AS latest_seen_at
    FROM {{ ref('fct_opportunity_sources') }}
    GROUP BY source_name
),

run_stats AS (
    SELECT
        source_name,
        COUNT(*) AS total_collection_runs,
        COUNT(*) FILTER (WHERE is_completed) AS completed_collection_runs,
        MAX(started_at) AS latest_run_started_at
    FROM {{ ref('fct_collection_runs') }}
    GROUP BY source_name
)

SELECT
    s.source_name,
    s.source_display_name,
    s.source_authority_rank,
    s.collection_approach,
    COALESCE(ls.source_listing_count, 0) AS source_listing_count,
    COALESCE(ls.canonical_participating_count, 0) AS canonical_participating_count,
    COALESCE(ls.canonical_primary_count, 0) AS canonical_primary_count,
    COALESCE(rs.total_collection_runs, 0) AS total_collection_runs,
    COALESCE(rs.completed_collection_runs, 0) AS completed_collection_runs,
    ls.earliest_seen_at,
    ls.latest_seen_at,
    rs.latest_run_started_at

FROM {{ ref('supported_sources') }} s
LEFT JOIN source_listing_stats ls
    ON s.source_name = ls.source_name
LEFT JOIN run_stats rs
    ON s.source_name = rs.source_name
