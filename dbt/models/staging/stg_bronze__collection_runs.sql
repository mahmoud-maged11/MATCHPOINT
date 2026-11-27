SELECT
    run_id,
    BTRIM(source_name) AS source_name,
    BTRIM(collection_scope) AS collection_scope,
    BTRIM(collection_mode) AS collection_mode,
    BTRIM(status) AS run_status,
    started_at,
    finished_at,
    records_received,
    records_inserted,
    records_updated,
    records_unchanged,
    records_invalid,
    records_stale,
    records_conflicted,
    BTRIM(contract_version) AS contract_version,
    hash_version,
    NULLIF(BTRIM(error_message), '') AS error_message,
    metadata

FROM {{ source('bronze', 'collection_runs') }}
