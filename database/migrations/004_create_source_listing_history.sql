-- MATCHPOINT Data Warehouse
-- Migration: 004
-- Purpose: Preserve source listing content versions

BEGIN;

CREATE TABLE bronze.source_listing_history (

    history_id UUID PRIMARY KEY
        DEFAULT gen_random_uuid(),

    source_listing_id UUID NOT NULL
        REFERENCES bronze.source_listings(source_listing_id),

    content_version INTEGER NOT NULL
        CHECK (content_version >= 1),

    content_hash TEXT NOT NULL
        CHECK (content_hash ~ '^[0-9a-f]{64}$'),

    hash_version INTEGER NOT NULL DEFAULT 1
        CHECK (hash_version = 1),

    contract_version TEXT NOT NULL
        CHECK (BTRIM(contract_version) <> ''),

    collection_run_id UUID NOT NULL
        REFERENCES bronze.collection_runs(run_id),

    standardized_payload JSONB NOT NULL
        CHECK (JSONB_TYPEOF(standardized_payload) = 'object'),

    observed_at TIMESTAMPTZ NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_listing_history_version
        UNIQUE (source_listing_id, content_version),

    CONSTRAINT uq_listing_history_run
        UNIQUE (source_listing_id, collection_run_id)
);


-- Indexes

CREATE INDEX idx_listing_history_observed
    ON bronze.source_listing_history (
        source_listing_id,
        observed_at DESC
    );

CREATE INDEX idx_listing_history_run
    ON bronze.source_listing_history (collection_run_id);

COMMIT;