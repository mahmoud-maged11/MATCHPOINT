-- MATCHPOINT Data Warehouse
-- Migration: 009
-- Purpose: Enforce date precision consistency

BEGIN;

ALTER TABLE bronze.source_listings
    ADD CONSTRAINT chk_published_at_precision_consistency
    CHECK (
        (
            published_at IS NULL
            OR published_at_precision IS NOT NULL
        )
        AND (
            published_at_precision IS DISTINCT FROM 'exact'
            OR published_at IS NOT NULL
        )
        AND (
            published_at_precision IS DISTINCT FROM 'date_only'
            OR published_at IS NULL
        )
        AND (
            published_at_precision IS NULL
            OR published_at_precision NOT IN ('relative', 'date_only')
            OR (
                published_at_raw IS NOT NULL
                AND published_at_raw ~ '[^[:space:]]'
            )
        )
    );

ALTER TABLE bronze.source_listings
    ADD CONSTRAINT chk_deadline_precision_consistency
    CHECK (
        (
            deadline IS NULL
            OR deadline_precision IS NOT NULL
        )
        AND (
            deadline_precision IS DISTINCT FROM 'exact'
            OR deadline IS NOT NULL
        )
        AND (
            deadline_precision IS DISTINCT FROM 'date_only'
            OR deadline IS NULL
        )
        AND (
            deadline_precision IS NULL
            OR deadline_precision NOT IN ('relative', 'date_only')
            OR (
                deadline_raw IS NOT NULL
                AND deadline_raw ~ '[^[:space:]]'
            )
        )
    );

COMMIT;
