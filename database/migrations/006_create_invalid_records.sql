-- MATCHPOINT Data Warehouse
-- Migration: 006
-- Purpose: Retain rejected records and ingestion conflicts

BEGIN;

CREATE TABLE bronze.invalid_records (

    invalid_record_id UUID PRIMARY KEY
        DEFAULT gen_random_uuid(),

    collection_run_id UUID NOT NULL
        REFERENCES bronze.collection_runs(run_id),

    source_opportunity_id TEXT,

    source_url TEXT,

    failure_stage VARCHAR(30) NOT NULL
        CHECK (failure_stage IN (
            'extraction',
            'mapping',
            'validation',
            'identity',
            'ingestion'
        )),

    error_code TEXT NOT NULL
        CHECK (BTRIM(error_code) <> ''),

    error_message TEXT NOT NULL
        CHECK (BTRIM(error_message) <> ''),

    error_details JSONB NOT NULL DEFAULT '{}'::JSONB
        CHECK (JSONB_TYPEOF(error_details) = 'object'),

    record_payload JSONB,

    rejection_hash TEXT NOT NULL
        CHECK (rejection_hash ~ '^[0-9a-f]{64}$'),

    observed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_invalid_record_rejection
        UNIQUE (
            collection_run_id,
            rejection_hash
        )
);


-- Indexes

CREATE INDEX idx_invalid_records_stage
    ON bronze.invalid_records (
        failure_stage,
        created_at DESC
    );

CREATE INDEX idx_invalid_records_error_code
    ON bronze.invalid_records (error_code);

COMMIT;