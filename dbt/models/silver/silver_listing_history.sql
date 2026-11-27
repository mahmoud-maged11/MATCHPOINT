SELECT
    h.history_id,
    h.source_listing_id,
    r.source_name,
    h.content_version,
    h.content_hash,
    h.hash_version,
    h.contract_version,
    h.collection_run_id,
    r.collection_scope,
    r.collection_mode,
    h.standardized_payload,
    h.observed_at,
    h.created_at

FROM {{ ref('stg_bronze__source_listing_history') }} h
INNER JOIN {{ ref('stg_bronze__collection_runs') }} r
    ON h.collection_run_id = r.run_id
