SELECT
    invalid_record_id,
    collection_run_id,
    source_opportunity_id,
    source_url,
    BTRIM(failure_stage) AS failure_stage,
    error_code,
    error_message,
    error_details,
    record_payload,
    rejection_hash,
    observed_at,
    created_at

FROM {{ source('bronze', 'invalid_records') }}
