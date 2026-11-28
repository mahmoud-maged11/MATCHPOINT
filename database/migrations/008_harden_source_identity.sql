-- MATCHPOINT Data Warehouse
-- Migration: 008
-- Purpose: Enforce bounded source identifiers

BEGIN;

ALTER TABLE bronze.source_listings
    ADD CONSTRAINT chk_source_id_byte_length
    CHECK (
        OCTET_LENGTH(source_opportunity_id)
        BETWEEN 1 AND 512
    );

ALTER TABLE bronze.source_listings
    ADD CONSTRAINT chk_source_id_boundary_whitespace
    CHECK (
        source_opportunity_id !~ '^[[:space:]]|[[:space:]]$'
    );

COMMIT;
