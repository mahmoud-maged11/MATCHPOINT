-- MATCHPOINT Data Warehouse
-- Migration: 007
-- Purpose: Store incremental collection checkpoints

BEGIN;

CREATE TABLE bronze.source_checkpoints (

    checkpoint_id UUID PRIMARY KEY
        DEFAULT gen_random_uuid(),

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

    collection_scope TEXT NOT NULL DEFAULT 'default'
        CHECK (BTRIM(collection_scope) <> ''),

    checkpoint_type VARCHAR(30) NOT NULL
        CHECK (checkpoint_type IN (
            'timestamp',
            'cursor',
            'numeric_id',
            'page_number',
            'composite'
        )),

    checkpoint_value JSONB NOT NULL
        CHECK (
            JSONB_TYPEOF(checkpoint_value) = 'object'
            AND checkpoint_value <> '{}'::JSONB
        ),

    last_successful_run_id UUID NOT NULL
        REFERENCES bronze.collection_runs(run_id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_source_checkpoint_scope
        UNIQUE (source_name, collection_scope),

    CONSTRAINT chk_checkpoint_storage_dates
        CHECK (updated_at >= created_at)
);


CREATE INDEX idx_source_checkpoints_last_run
    ON bronze.source_checkpoints (
        last_successful_run_id
    );

COMMIT;