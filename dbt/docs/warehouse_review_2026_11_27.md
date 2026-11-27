# MATCHPOINT Warehouse Technical Review

**Date:** 2026-11-27

**Branch:** feature/data-warehouse

**Component owner:** Momen

**Technical review and hardening:** Mahmoud

**Status:** Synthetic warehouse validation completed.

## 1. Final Validation Results

| Metric | Result |
|---|---:|
| Bronze tables | 6 |
| Bronze columns | 96 |
| SQL migrations | 7 |
| Staging models | 4 |
| Intermediate models | 6 |
| Silver models | 14 |
| Gold models | 20 |
| Total dbt models | 44 |
| Seeds | 5 |
| Supported sources | 8 |
| Total dbt data tests | 483 |
| Passed dbt data tests | 483 |
| Failed tests | 0 |
| Skipped tests | 0 |
| Baseline source listings | 41 |
| Baseline canonical opportunities | 33 |
| Expanded source listings | 52 |
| Expanded canonical opportunities | 44 |
| Expanded source mappings | 52 |
| Expanded collection runs | 12 |
| Expanded history records | 2 |
| Expanded invalid records | 1 |
| Silver integration scenarios | S1-S10 passed |
| Gold integration scenarios | G1-G6 passed |
| Expanded edge cases | EC1-EC11 passed |
| Gold idempotency | 20/20 passed |
| Silver mapping idempotency | Passed |

Validation used PostgreSQL 16 and a fresh isolated
matchpoint_test database.

Runtime:

- Python 3.12.10.
- dbt-core 1.12.7.
- dbt-postgres 1.11.0.
- Session-level PostgreSQL JIT disabled through run_dbt.py.
- Final dbt rebuild: 3.43 seconds.
- Final dbt test execution: 10.88 seconds.

Performance measurements apply only to the local
synthetic workload.

## 2. Technical Improvements

### Staging and source evidence

- Preserve source identities without destructive trimming.
- Preserve original source evidence.
- Validate supported contract and hash versions.
- Verify staging row and attribute preservation.

### Normalization and deterministic keys

- Normalize whitespace before trimming.
- Serialize deterministic key inputs using JSON arrays.
- Distinguish null values from literal strings.
- Prevent delimiter-based key ambiguity.
- Preserve case-sensitive URL paths and query parameters.
- Reject generic application portals as direct match evidence.
- Extract source references from validated hosts and paths.
- Prevent query-string injection into source ID extraction.

### Matching and deduplication

- Require compatible opportunity types for direct matching.
- Use conservative standardized geographic evidence.
- Reject incompatible transitive cluster merges.
- Preserve organization, opportunity type and geographic
  conflict evidence.
- Retain every source listing and its canonical mapping.
- Extract matching and clustering logic into reusable macros.
- Test positive, negative and ambiguous matching scenarios.

### Skills and categories

- Preserve distinct cleaned source labels.
- Retain alias and normalization evidence.
- Prevent duplicate listing-to-skill and listing-to-category
  relationships.
- Select consistent canonical names from shared dimensions.
- Preserve null versus confirmed-empty semantics.
- Verify source evidence and Gold bridge preservation.

### Canonical opportunities

- Prefer informative experience evidence over unknown values.
- Prefer standardized location evidence.
- Preserve coherent experience and location attribute bundles.
- Detect conflicting known work modes.
- Verify complete canonical mapping coverage.
- Verify exactly one primary source per canonical opportunity.

### Gold analytical layer

- Align skill and category bridge names with dimensions.
- Protect work mode and employment type array expansion.
- Preserve supporting source listing counts.
- Validate bridge relationships and canonical counts.
- Verify repeated Gold builds against saved snapshots.

## 3. Architecture and Integration Impacts

### Derived keys

The deterministic surrogate-key serialization changed.

Affected derived keys must be rebuilt consistently across
Silver, Gold and downstream analytical destinations.

Do not combine old and new derived-key generations.

This change does not modify the Bronze source identity
contract or the Python content-hash algorithm.

### Canonical identities

Canonical opportunity IDs are deterministic for unchanged
matching inputs and cluster membership.

The current implementation does not guarantee permanent
canonical IDs when new listings change cluster membership,
matching rules or canonical anchors.

A persistent canonical identity registry and merge/split
reconciliation remain deferred.

### Lifecycle

Silver effective status is time-dependent.

Bronze observed status remains source evidence.

A lifecycle refresh schedule and operational reconciliation
must be established during orchestration integration.

### Analytical semantics

- Count distinct canonical opportunity IDs for opportunity KPIs.
- Source contribution counts are not additive across sources.
- Skill, category, employment type and work mode groups
  may overlap.
- Skill demand shares can sum to more than 100 percent.
- Unreported work modes and employment types combine missing
  and confirmed-empty values in their analytical marts.
- Lifecycle marts describe current effective status grouped
  by publication date, not historical status transitions.
- ISO week-year and date-label presentation improvements
  remain deferred.

## 4. Historical Results

Earlier warehouse validation recorded:

- 461 dbt data tests.
- 41 listings and 32 canonical opportunities.
- 52 listings and 43 canonical opportunities.

These are historical results, not current acceptance targets.

The revised URL matching fixtures and conservative
deduplication rules produced the final validated baseline
of 33 canonical opportunities and expanded result of 44.

All 52 expanded source listings remain represented.

## 5. Remaining Acceptance Requirements

- Implement persistent Python PostgreSQL ingestion.
- Implement collection run, observation ledger and history writes.
- Validate retry, concurrency and transaction recovery behavior.
- Ingest the recorded 40-record handover sample.
- Validate all eight real source-to-Bronze integrations.
- Run the current dbt quality gate against recorded real data.
- Integrate Airflow orchestration.
- Integrate ClickHouse loading and Power BI analytics.
- Validate downstream derived-key compatibility.
- Establish lifecycle refresh and reconciliation policies.
- Validate production-scale performance.
- Validate Linux and Airflow runtime compatibility.
- Configure CI and deployment permissions.
- Complete production authorization and privacy review.

Synthetic warehouse acceptance is complete.

Production readiness and Phase 7 end-to-end acceptance
remain open.

## 6. Ownership

Existing team ownership remains unchanged.

- Mahmoud: collection, ingestion, backend and matching.
- Momen: warehouse transformations and analytical models.
- Andrew: orchestration and ClickHouse.
- Ramadan: analytics and Power BI.
- Abdel Rahman: frontend.

Technical review completion does not imply independent
approval or integration acceptance by every team member.
