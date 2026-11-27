SELECT
    history_id,
    source_listing_id,
    content_version,
    content_hash,
    hash_version,
    BTRIM(contract_version) AS contract_version,
    collection_run_id,
    standardized_payload,
    observed_at,
    created_at

FROM {{ source('bronze', 'source_listing_history') }}
