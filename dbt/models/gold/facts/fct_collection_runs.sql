{{
    config(
        indexes=[
            {'columns': ['run_id'], 'unique': True},
            {'columns': ['source_name', 'started_at']}
        ]
    )
}}

-- Operational & data quality telemetry fact table.
-- Note: r.records_invalid reflects the run-level counter reported by persistent ingestion
-- (whose exact counter semantics remain pending definition in Mahmoud's storage module),
-- whereas persisted_invalid_record_count reflects actual rows retained in bronze.invalid_records.
-- Both are preserved separately along with an explicit audit diff rather than assuming equivalence.

WITH invalid_counts AS (
    SELECT
        collection_run_id,
        COUNT(*) AS persisted_invalid_record_count
    FROM {{ ref('stg_bronze__invalid_records') }}
    GROUP BY collection_run_id
)

SELECT
    r.run_id,
    r.source_name,
    r.collection_scope,
    r.collection_mode,
    r.run_status,
    r.started_at,
    r.finished_at,
    CAST(TO_CHAR(r.started_at AT TIME ZONE 'UTC', 'YYYYMMDD') AS INTEGER) AS started_date_key,
    CASE
        WHEN r.finished_at IS NOT NULL THEN
            ROUND(EXTRACT(EPOCH FROM (r.finished_at - r.started_at))::NUMERIC, 2)
        ELSE NULL
    END AS run_duration_seconds,
    r.records_received,
    r.records_inserted,
    r.records_updated,
    r.records_unchanged,
    r.records_invalid,
    r.records_stale,
    r.records_conflicted,
    COALESCE(ic.persisted_invalid_record_count, 0) AS persisted_invalid_record_count,
    (COALESCE(ic.persisted_invalid_record_count, 0) - r.records_invalid) AS persisted_vs_reported_invalid_diff,
    (r.records_invalid > r.records_received) AS has_invalid_counter_anomaly,
    CASE
        WHEN r.records_received > 0 AND r.records_invalid <= r.records_received THEN
            ROUND((r.records_invalid::NUMERIC / r.records_received::NUMERIC), 4)
        ELSE NULL
    END AS invalid_record_rate,
    (r.run_status = 'completed') AS is_completed,
    (r.run_status IN ('failed', 'aborted')) AS is_failed,
    r.contract_version,
    r.hash_version,
    r.error_message

FROM {{ ref('stg_bronze__collection_runs') }} r
LEFT JOIN invalid_counts ic
    ON r.run_id = ic.collection_run_id
