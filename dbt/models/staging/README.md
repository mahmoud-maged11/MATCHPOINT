# Staging Models (`dbt/models/staging/`)

This directory holds lightweight staging views that read directly from the approved PostgreSQL Bronze tables via dbt's `{{ source('bronze', '...') }}` macro.

## Implemented Models (Phase 3)

- `stg_bronze__source_listings.sql` — 42 columns from `bronze.source_listings` with safe trimming, empty-string-to-NULL normalization on optional text, `status` aliased as `observed_status`, and untouched `NULL` vs `[]` JSONB arrays.
- `stg_bronze__source_listing_history.sql` — 10 columns from `bronze.source_listing_history`.
- `stg_bronze__collection_runs.sql` — 18 columns from `bronze.collection_runs`.
- `stg_bronze__invalid_records.sql` — 12 columns from `bronze.invalid_records`.
- `staging_schema.yml` — Column descriptions and dbt `data_tests`.

All staging models materialize as `view` inside the existing `silver` schema (`+schema: silver` in `dbt_project.yml`).

## Boundaries

- Do **not** recreate or modify physical Bronze tables.
- Business normalization and lifecycle derivation live in `models/intermediate/` and `models/silver/`.
- Cross-source deduplication (`ADR-004`, `ADR-026`) and canonical opportunity identity (`ADR-003`) are deferred to Phase 4.
