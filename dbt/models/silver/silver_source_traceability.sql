WITH history_summary AS (
    SELECT
        source_listing_id,
        COUNT(*) AS history_version_count,
        MIN(observed_at) AS first_history_observed_at,
        MAX(observed_at) AS latest_history_observed_at
    FROM {{ ref('silver_listing_history') }}
    GROUP BY source_listing_id
)

SELECT
    sl.source_listing_id,
    sl.source_name,
    sl.source_opportunity_id,
    sl.source_identity_key,
    sl.source_url,
    sl.opportunity_type,
    sl.observed_status,
    sl.effective_status,
    sl.effective_status_reason,
    sl.content_hash,
    sl.hash_version,
    sl.content_version,
    COALESCE(hs.history_version_count, 0) AS history_version_count,
    hs.first_history_observed_at,
    hs.latest_history_observed_at,
    sl.first_seen_at,
    sl.last_seen_at,
    sl.collected_at,
    sl.last_collection_run_id,
    r.collection_scope AS last_collection_scope,
    r.collection_mode AS last_collection_mode,
    r.run_status AS last_collection_run_status,
    r.contract_version AS last_contract_version

FROM {{ ref('silver_source_listings') }} sl
INNER JOIN {{ ref('stg_bronze__collection_runs') }} r
    ON sl.last_collection_run_id = r.run_id
LEFT JOIN history_summary hs
    ON sl.source_listing_id = hs.source_listing_id
