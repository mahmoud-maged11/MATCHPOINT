# MATCHPOINT - Data Engineering Handover

## 1. Acceptance Snapshot

Validation date: 2026-11-28

Scope: Source ingestion, PostgreSQL Bronze persistence,
dbt Silver transformations, cross-source deduplication,
and Gold analytical models.

This is a validated local integrated warehouse baseline,
not an externally deployed production service.

## 2. Architecture

Eight source adapters
    -> Python mapping and validation
    -> PostgreSQL Bronze
    -> dbt Silver
    -> Canonical opportunity resolution
    -> dbt Gold
    -> Future ClickHouse analytical serving

PostgreSQL remains the authoritative warehouse.

## 3. Supported Sources

| Source | Stored source listings |
| --- | ---: |
| Egyincs | 8489 |
| Bayt | 5133 |
| Wuzzuf | 4852 |
| Forasna | 2780 |
| ITIDA | 515 |
| NTI | 294 |
| Devpost | 82 |
| UN Volunteers | 57 |
| Total | 22202 |

Counts represent persisted source listings, not certified
complete website coverage or currently active opportunities.

## 4. Bronze Acceptance

| Table | Rows |
| --- | ---: |
| collection_runs | 27 |
| source_listings | 22202 |
| source_listing_history | 22202 |
| ingestion_observations | 31736 |
| invalid_records | 56 |
| source_checkpoints | 1 |
| Total | 76224 |

The integrated Bronze database was consolidated atomically.

Source and target row integrity was verified using
primary-key-ordered SHA-256 comparisons.

Existing Bayt records were preserved.

All nine database migrations were applied and verified.

Historical rejection records remain available for auditing.

The invalid record count is historical and does not imply
56 currently missing opportunities.

## 5. Ingestion Infrastructure

Implemented capabilities include:

- Persistent PostgreSQL ingestion.
- Batch persistence.
- Atomic transactions.
- Collection run tracking.
- Collection snapshots.
- Automatic recovery.
- Retry policies.
- Source locking and concurrency protection.
- Checkpoint management.
- Full and incremental loading strategies.
- Reconciliation and publication protection.

Incremental loading is enabled only for supported scopes.
Do not assume every source supports incremental loading.

## 6. Silver and Cross-Source Deduplication

| Metric | Final value |
| --- | ---: |
| Source listings | 22202 |
| Source mappings | 22202 |
| Canonical opportunities | 22164 |
| Cross-source match pairs | 74 |
| Merged pairs | 38 |
| Unmerged pairs | 36 |
| Organization aliases | 68 |
| Organization records | 3762 |

Organization alias hardening expanded the dictionary
from 21 to 68 exact aliases.

The number of merged pairs increased from 3 to 38.

All original source listings were preserved.

Previously accepted merges were retained.

No same-source duplicates are permitted within
a canonical opportunity.

Matching prioritizes verified evidence and conservative
conflict resolution over aggressive duplicate removal.

The observed merge rate is not a measured recall score.

## 7. Known Matching Limitations

Thirty-six detected pairs remain unmerged.

Thirty-four pairs retain organization conflicts.

Three pairs retain geographic conflicts.
One of these also has an organization conflict.

B.TECH and Elsewedy Electric contain potential geographic
granularity false negatives: Cairo versus New Cairo.

Etisal Retail & Care remains unresolved due to organization
and specific-location differences.

Ambiguous organization identities, subsidiaries and
branch relationships must not be merged automatically.

No claim is made that all real-world duplicates have
been discovered or that matching precision is 100 percent.

## 8. Gold Analytical Layer

The Gold fact table contains 22164 canonical opportunities.

Source attribution retains all 22202 source mappings.

Consumers must distinguish canonical opportunity grain
from source listing grain.

Use canonical opportunity identifiers for unique
opportunity counts.

Source participation counts may overlap.

Refer to dbt/docs/gold_data_dictionary.md for detailed
table grain, measures, relationships and field semantics.

## 9. Runtime

Validated warehouse runtime:

- PostgreSQL 16
- Python 3.12
- dbt-core 1.12.7
- dbt-postgres 1.11.0
- Docker Linux runtime
- dbt/Dockerfile

Build the dbt runtime from the repository root:

    docker build -t matchpoint-dbt:1.0 -f dbt/Dockerfile dbt

The runtime requires a mounted dbt project, an appropriate
profile, database credentials and PostgreSQL connectivity.

Never commit actual database credentials.

Windows Application Control blocked the unsigned native
dbt launcher. The Linux Docker runtime was validated
without changing Windows security policies.

The base image tag and transitive dependencies are not
fully digest-locked.

## 10. Validation Results

- Initial integrated dbt seeds: 5/5 passed.
- Initial integrated dbt models: 44/44 passed.
- Initial integrated dbt tests: 495/495 passed.
- Alias-hardening downstream models: 32/32 passed.
- Final dbt tests after alias hardening: 495/495 passed.
- Cross-source structural audit: 8/8 passed.
- Alias rebuild regression audit: 9/9 passed.
- Bayt targeted regression suite: 183 tests passed.
- Bayt Bronze reconciliation: 12/12 passed.

These results describe the recorded acceptance runs.
They are not a substitute for CI on subsequent changes.

## 11. Collection Coverage Limitations

Bayt: all 5133 identities in the reconciled discovery
snapshot were persisted and accounted for.

ITIDA: unresolved discovery pages remain documented.

NTI: exhaustive website coverage was not certified.

Wuzzuf: historical records and incomplete coverage
certification must be distinguished from stored counts.

Egyincs: unresolved reconciliation identities remain
documented in the reconciliation backlog.

Do not interpret a partial collection as proof that
unobserved listings are expired or deleted.

## 12. Operational Artifacts

Backups, collection evidence, raw diagnostic reports
and validation artifacts are maintained outside Git.

Local artifact root:

    %LOCALAPPDATA%\MATCHPOINT\Validation

PostgreSQL custom-format backups were generated and
verified for integrity and readability.

A full disaster-recovery restore was not certified.

## 13. Downstream Handover

ClickHouse:

- Consume validated Gold analytical models.
- Preserve canonical and source-level grain.
- Do not implement independent opportunity deduplication.
- Use a controlled refresh and publication strategy.

Backend:

- Consume the documented canonical opportunity interface.
- Preserve source attribution and original application links.
- Separate application-owned transactional data from
  warehouse-owned analytical data.

Power BI:

- Use canonical opportunity counts.
- Prevent double counting through bridge relationships.
- Preserve unknown values and date precision.

Airflow:

- Coordinate collection, persistence, transformation,
  validation and downstream publication.
- Respect source-specific loading and checkpoint contracts.
- Do not publish failed or partially rebuilt warehouse states.

These downstream integrations are separate work packages
and are not certified by this warehouse acceptance.

## 14. Related Documentation

- docs/data_contract.md
- docs/architecture_decisions.md
- docs/pending_tasks.md
- docs/ingestion_recovery_policy.md
- docs/ingestion_transaction_validation.md
- dbt/docs/dbt_execution_interface.md
- dbt/docs/gold_data_dictionary.md
- dbt/docs/handoff_andrew_airflow_clickhouse.md
- dbt/docs/handoff_mahmoud_fastapi.md
- dbt/docs/handoff_ramadan_powerbi.md

## 15. Acceptance Decision

The integrated PostgreSQL and dbt warehouse baseline
is accepted with documented source coverage and
deduplication limitations.

Future matching improvements must preserve source
identity, prevent false merges, and pass regression tests.
