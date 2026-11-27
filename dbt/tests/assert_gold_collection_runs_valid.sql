-- Fails if fct_collection_runs violates non-negative counter, non-negative duration,
-- or bounded [0, 1] invalid_record_rate invariants.

SELECT
    run_id,
    source_name,
    run_duration_seconds,
    records_received,
    records_invalid,
    persisted_invalid_record_count,
    invalid_record_rate,
    has_invalid_counter_anomaly
FROM {{ ref('fct_collection_runs') }}
WHERE (run_duration_seconds IS NOT NULL AND run_duration_seconds < 0)
   OR records_received < 0
   OR records_inserted < 0
   OR records_updated < 0
   OR records_unchanged < 0
   OR records_invalid < 0
   OR records_stale < 0
   OR records_conflicted < 0
   OR persisted_invalid_record_count < 0
   OR (invalid_record_rate IS NOT NULL AND (invalid_record_rate < 0 OR invalid_record_rate > 1))
   OR (records_received > 0 AND records_invalid <= records_received AND invalid_record_rate IS NULL)
   OR (records_invalid > records_received AND NOT has_invalid_counter_anomaly)
