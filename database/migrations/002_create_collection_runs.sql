-- MATCHPOINT Data Warehouse
-- Migration: 002
-- Purpose: Create collection run tracking table

BEGIN;

CREATE TABLE bronze.collection_runs (

    run_id UUID PRIMARY KEY,

    source_name VARCHAR(50) NOT NULL
        CHECK (source_name IN (
            'wuzzuf',
            'forasna',
            'egyincs',
            'itida',
            'nti',
            'bayt',
            'devpost',
            'un_volunteers'
        )),

    collection_scope TEXT NOT NULL DEFAULT 'default',

    collection_mode VARCHAR(20) NOT NULL
        CHECK (collection_mode IN (
            'api',
            'html',
            'live'
        )),

    status VARCHAR(20) NOT NULL DEFAULT 'running'
        CHECK (status IN (
            'running',
            'completed',
            'partial',
            'failed',
            'aborted'
        )),

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    finished_at TIMESTAMPTZ,

    records_received BIGINT NOT NULL DEFAULT 0
        CHECK (records_received >= 0),

    records_inserted BIGINT NOT NULL DEFAULT 0
        CHECK (records_inserted >= 0),

    records_updated BIGINT NOT NULL DEFAULT 0
        CHECK (records_updated >= 0),

    records_unchanged BIGINT NOT NULL DEFAULT 0
        CHECK (records_unchanged >= 0),

    records_invalid BIGINT NOT NULL DEFAULT 0
        CHECK (records_invalid >= 0),

    records_stale BIGINT NOT NULL DEFAULT 0
        CHECK (records_stale >= 0),

    records_conflicted BIGINT NOT NULL DEFAULT 0
        CHECK (records_conflicted >= 0),

    contract_version TEXT NOT NULL,

    hash_version INTEGER NOT NULL DEFAULT 1
        CHECK (hash_version = 1),

    error_message TEXT,

    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,

    CONSTRAINT chk_collection_scope
        CHECK (BTRIM(collection_scope) <> ''),

    CONSTRAINT chk_collection_metadata
        CHECK (JSONB_TYPEOF(metadata) = 'object'),

    CONSTRAINT chk_collection_run_dates
        CHECK (
            finished_at IS NULL
            OR finished_at >= started_at
        ),

    CONSTRAINT chk_collection_run_status
        CHECK (
            (status = 'running' AND finished_at IS NULL)
            OR
            (status <> 'running' AND finished_at IS NOT NULL)
        )
);

CREATE INDEX idx_collection_runs_source_started
    ON bronze.collection_runs (
        source_name,
        started_at DESC
    );

COMMIT;