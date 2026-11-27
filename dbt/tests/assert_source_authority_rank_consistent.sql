-- Fails if source_authority_rank drifts across the shared supported_sources seed,
-- Silver source mappings, Gold opportunity sources, and Gold dim_sources.

WITH silver_rank_drift AS (
    SELECT
        os.source_name,
        os.source_authority_rank AS observed_rank,
        ss.source_authority_rank AS expected_rank,
        'silver_opportunity_sources_drift'::TEXT AS layer
    FROM {{ ref('silver_opportunity_sources') }} os
    INNER JOIN {{ ref('supported_sources') }} ss
        ON os.source_name = ss.source_name
    WHERE os.source_authority_rank IS DISTINCT FROM ss.source_authority_rank
),

gold_fact_rank_drift AS (
    SELECT
        fos.source_name,
        fos.source_authority_rank AS observed_rank,
        ss.source_authority_rank AS expected_rank,
        'fct_opportunity_sources_drift'::TEXT AS layer
    FROM {{ ref('fct_opportunity_sources') }} fos
    INNER JOIN {{ ref('supported_sources') }} ss
        ON fos.source_name = ss.source_name
    WHERE fos.source_authority_rank IS DISTINCT FROM ss.source_authority_rank
),

gold_dim_rank_drift AS (
    SELECT
        ds.source_name,
        ds.source_authority_rank AS observed_rank,
        ss.source_authority_rank AS expected_rank,
        'dim_sources_drift'::TEXT AS layer
    FROM {{ ref('dim_sources') }} ds
    INNER JOIN {{ ref('supported_sources') }} ss
        ON ds.source_name = ss.source_name
    WHERE ds.source_authority_rank IS DISTINCT FROM ss.source_authority_rank
)

SELECT * FROM silver_rank_drift
UNION ALL SELECT * FROM gold_fact_rank_drift
UNION ALL SELECT * FROM gold_dim_rank_drift
