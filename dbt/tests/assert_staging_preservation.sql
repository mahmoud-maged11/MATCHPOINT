-- Verify row preservation and protected evidence across staging.
-- Compare both directions using EXCEPT ALL.

{% set protected_columns = {
    'source_listings': [
        'source_listing_id',
        'source_name',
        'source_opportunity_id',
        'source_identity_key',
        'source_url',
        'experience_level_raw',
        'published_at_raw',
        'deadline_raw',
        'source_status_raw',
        'published_at',
        'deadline',
        'work_modes',
        'employment_types',
        'categories',
        'required_skills',
        'salary_min',
        'salary_max',
        'experience_years_min',
        'experience_years_max',
        'raw_payload',
        'content_hash',
        'hash_version',
        'content_version',
        'collected_at',
        'first_seen_at',
        'last_seen_at',
        'created_at',
        'updated_at',
        'last_collection_run_id'
    ],
    'collection_runs': [
        'run_id',
        'contract_version',
        'hash_version',
        'started_at',
        'finished_at',
        'records_received',
        'records_inserted',
        'records_updated',
        'records_unchanged',
        'records_invalid',
        'records_stale',
        'records_conflicted',
        'metadata'
    ],
    'source_listing_history': [
        'history_id',
        'source_listing_id',
        'content_version',
        'content_hash',
        'hash_version',
        'contract_version',
        'collection_run_id',
        'standardized_payload',
        'observed_at',
        'created_at'
    ],
    'invalid_records': [
        'invalid_record_id',
        'collection_run_id',
        'source_opportunity_id',
        'source_url',
        'failure_stage',
        'error_code',
        'error_message',
        'error_details',
        'record_payload',
        'rejection_hash',
        'observed_at',
        'created_at'
    ]
} %}

{% for table, columns in protected_columns.items() %}

SELECT
    '{{ table }}' AS table_name,
    'bronze_minus_staging' AS difference_type,
    to_jsonb(d) AS difference
FROM (
    SELECT {{ columns | join(', ') }}
    FROM {{ source('bronze', table) }}

    EXCEPT ALL

    SELECT {{ columns | join(', ') }}
    FROM {{ ref('stg_bronze__' ~ table) }}
) AS d

UNION ALL

SELECT
    '{{ table }}' AS table_name,
    'staging_minus_bronze' AS difference_type,
    to_jsonb(d) AS difference
FROM (
    SELECT {{ columns | join(', ') }}
    FROM {{ ref('stg_bronze__' ~ table) }}

    EXCEPT ALL

    SELECT {{ columns | join(', ') }}
    FROM {{ source('bronze', table) }}
) AS d

{% if not loop.last %}
UNION ALL
{% endif %}

{% endfor %}
