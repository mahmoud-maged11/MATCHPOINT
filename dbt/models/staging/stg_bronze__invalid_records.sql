SELECT
    invalid_record_id,
    collection_run_id,
    NULLIF(BTRIM(source_opportunity_id), '') AS source_opportunity_id,
    NULLIF(BTRIM(source_url), '') AS source_url,
    BTRIM(failure_stage) AS failure_stage,
    BTRIM(error_code) AS error_code,
    BTRIM(error_message) AS error_message,
    error_details,
    record_payload,
    rejection_hash,
    observed_at,
    created_at

FROM {{ source('bronze', 'invalid_records') }}
