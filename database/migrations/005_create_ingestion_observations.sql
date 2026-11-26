-- MATCHPOINT Data Warehouse
-- Migration: 005
-- Purpose: Track processed observations and ensure idempotency

BEGIN;

CREATE TABLE bronze.ingestion_observations (

    source_listing_id UUID NOT NULL
        REFERENCES bronze.source_listings(source_listing_id),

    collection_run_id UUID NOT NULL
        REFERENCES bronze.collection_runs(run_id),

    observation_hash TEXT NOT NULL
        CHECK (observation_hash ~ '^[0-9a-f]{64}$'),

    observed_at TIMESTAMPTZ NOT NULL,

    outcome VARCHAR(20) NOT NULL
        CHECK (outcome IN (
            'inserted',
            'updated',
            'unchanged',
            'stale',
            'conflicted'
        )),

    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_ingestion_observations
        PRIMARY KEY (
            source_listing_id,
            collection_run_id
        )
);


-- Indexes

CREATE INDEX idx_ingestion_observations_run
    ON bronze.ingestion_observations (
        collection_run_id
    );

CREATE INDEX idx_ingestion_observations_seen
    ON bronze.ingestion_observations (
        source_listing_id,
        observed_at DESC
    );

COMMIT;