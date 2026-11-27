# Phase 7: Real Data Integration and End-to-End Acceptance Plan

**Project:** MATCHPOINT

**Data Contract:** v3.0.0 (ADR-050)

**Content Hash Version:** 1

**Review Date:** 2026-11-27

**Target Final Acceptance Date:** 2026-12-04

This document defines the remaining integration and acceptance
requirements for the complete MATCHPOINT platform.

Successful synthetic warehouse testing does not establish
complete end-to-end acceptance or production readiness.

---

## 1. Pipeline Architecture

```text
Source Scrapers
       |
       v
Standardization and Contract Validation
       |
       v
Persistent PostgreSQL Bronze Ingestion
       |
       v
dbt Staging and Intermediate Models
       |
       v
Silver Normalization and Deduplication
       |
       v
Gold Warehouse
       |
       +------------------------+
       |                        |
       v                        v
FastAPI Backend           ClickHouse
       |                        |
       v                        v
React Frontend              Power BI
```

Airflow orchestrates collection, persistence, warehouse
transformation, quality gates, and analytical publication.

Airflow is an orchestration component rather than a
sequential data storage layer.

---

## 2. Component Ownership and Acceptance Status

| Component | Owner | Acceptance Status |
|---|---|---|
| Source collection and validation | Mahmoud | Implemented and tested |
| Bronze physical schema | Mahmoud / Momen | Verified |
| Persistent Bronze ingestion | Mahmoud | Implementation pending |
| Silver normalization and deduplication | Momen | Synthetic validation passed |
| Gold warehouse | Momen | Synthetic validation passed |
| Airflow orchestration | Andrew | Integration acceptance pending |
| ClickHouse analytical storage | Andrew | Integration acceptance pending |
| Power BI analytics | Ramadan | Integration acceptance pending |
| FastAPI backend and matching | Mahmoud | Integration acceptance pending |
| React frontend | Abdel Rahman | Integration acceptance pending |

Component acceptance status describes verified evidence.

It must not be interpreted as a current inventory of every
remote feature branch.

Refresh repository status before final integration.

---

## 3. Verified Implementation Evidence

### 3.1 Source Collection

The collection milestone supports exactly eight sources:

- Wuzzuf
- Forasna
- Egyincs
- ITIDA
- NTI
- Bayt
- Devpost
- UN Volunteers

Collection milestone commit:

`ee3b029`

Verified collection evidence:

- Eight implemented source adapters.
- 665 successful Python tests.
- Standardized Opportunity model.
- Content hashing implementation.
- Approved Data Contract v3.0.0.
- Validated 40-record handover sample.

Persistent PostgreSQL ingestion is a separate milestone.

The collection tests do not establish database persistence,
transaction safety, or ingestion retry correctness.

### 3.2 Bronze Physical Schema

Physical schema milestone commit:

`f7216a9`

Verified implementation:

- Seven PostgreSQL migrations.
- Three database schemas.
- Six Bronze tables.
- 96 Bronze columns.
- 23 distinct SQL validation checks.

The migration and constraint tests establish physical
schema behavior under controlled conditions.

They do not establish correctness of the future Python
ingestion implementation.

### 3.3 Original Warehouse Implementation

Warehouse implementation commits:

- `47f8d09`
- `9d20121`

Warehouse inventory:

| Component | Count |
|---|---:|
| Staging views | 4 |
| Intermediate views | 6 |
| Silver tables | 14 |
| Gold tables | 20 |
| Total dbt models | 44 |
| Lookup seeds | 5 |
| Generic data tests | 443 |
| Singular data tests | 18 |
| Total data tests | 461 |
| Declared Gold indexes | 33 |

Original synthetic validation results remain historical
implementation evidence.

### 3.4 Independent Warehouse Review

Reviewed runtime:

- Python 3.12.10.
- dbt-core 1.12.7.
- dbt-postgres 1.11.0.
- PostgreSQL 16.

Review database:

`matchpoint_dbt_review_test`

Verified results:

| Validation | Result |
|---|---|
| Generic test syntax migration | 108 declarations |
| Generic test semantic comparison | No differences |
| Empty Bronze model build | 44 passed |
| Empty Bronze quality gate | 461 passed |
| Phase 4 baseline | 41 listings, 32 opportunities |
| Phase 4 verification | S1-S10 passed |
| Phase 4 mapping idempotency | Passed |
| Gold baseline verification | G1-G6 passed |
| Expanded synthetic dataset | 52 listings, 43 opportunities |
| Expanded edge-case verification | EC1-EC11 passed |
| Gold idempotency | 20 models passed |
| Database authorization negative checks | 18 passed |
| Runner functional checks | 8 passed |
| Final regression quality gate | 461 passed |

Review improvements include:

- Exact direct dependency pinning.
- Supported generic test argument syntax.
- Explicit test database authorization.
- Stronger fixture preconditions.
- NULL-safe integration assertions.
- Duplicate-sensitive comparisons.
- Snapshot overwrite protection.
- Gold schema comparison.
- Process-scoped PostgreSQL JIT configuration.

These results apply to the controlled synthetic datasets.

The complete real-data integration workflow remains pending.

---

## 4. Acceptance Testing Levels

### Level A: Synthetic Warehouse Validation

Purpose:

Validate transformation logic against controlled fixtures
with known expected outcomes.

Includes:

- Positive and negative deduplication scenarios.
- Canonical identity.
- Source attribution.
- Analytical reconciliation.
- Date and lifecycle edge cases.
- Transformation idempotency.

Status:

Verified for the executed synthetic scenarios.

### Level B: Recorded Real-Data Integration

Purpose:

Validate persistent ingestion and warehouse transformation
using previously collected real opportunity records.

Input:

The agreed 40-record collection handover sample.

This level must not require additional live source requests.

Status:

Pending persistent Bronze ingestion.

### Level C: Operational Behavior Validation

Purpose:

Validate behavior under retries, content changes,
partial failures, interruptions, and lifecycle transitions.

Status:

Pending implementation and execution.

### Level D: Complete Platform Integration

Purpose:

Validate the integrated collection, ingestion, warehouse,
orchestration, analytical, backend, and frontend components.

Status:

Pending integration acceptance.

Passing one testing level does not automatically establish
acceptance of subsequent levels.

---

## 5. Test Environment Requirements

Use isolated PostgreSQL test databases.

Do not load synthetic or recorded integration fixtures
into the development or production warehouse.

Protected synthetic scripts allow only:

- `matchpoint_test`
- `matchpoint_dbt_review_test`

Mutating synthetic scripts require explicit authorization
through the PostgreSQL session setting:

`matchpoint.expected_test_database`

Use a separate freshly provisioned database for recorded
real-data integration.

The real-data integration harness must independently
validate its configured database target.

Do not weaken synthetic script authorization to support
arbitrary database names.

### Environment Preparation

Before testing:

- Record the Git commit SHA.
- Record dependency versions.
- Apply migrations 001 through 007.
- Verify the actual database connection.
- Verify the expected initial database state.
- Configure the correct dbt test target.
- Verify runtime credentials without exposing them.
- Prevent concurrent modifications during testing.
- Preserve existing review evidence.

Do not automatically reset or delete an existing database.

Use the standard dbt runner:

`dbt/run_dbt.py`

See:

- [Execution Interface](dbt_execution_interface.md)
- [Integration Test Suite](../integration_tests/README.md)
- [Andrew Handoff](handoff_andrew_airflow_clickhouse.md)

---

## 6. Persistent Bronze Ingestion Acceptance

**Owner:** Mahmoud

### 6.1 Physical Contract Compatibility

Validate integration with all six Bronze tables:

- `bronze.collection_runs`
- `bronze.source_listings`
- `bronze.source_listing_history`
- `bronze.ingestion_observations`
- `bronze.invalid_records`
- `bronze.source_checkpoints`

Verify:

- Required fields and data types.
- Primary and foreign keys.
- Unique identity constraints.
- Source enumeration.
- UTC timestamps.
- JSONB semantics.
- Numeric precision.
- Contract and hash version compatibility.

The ingestion implementation must not bypass the approved
physical schema constraints.

### 6.2 Source Identity

Verify that:

- Source listing identity is separate from canonical identity.
- Every accepted record has a valid source opportunity ID.
- Source identity is scoped by source name.
- Repeated source observations preserve source_listing_id.
- Missing source identity is rejected.
- Different sources are not merged in Bronze.
- Content hashes are not used as listing identities.

The approved identity key is:

`id:<source_opportunity_id>`

The database uniqueness boundary is:

`(source_name, source_identity_key)`

### 6.3 Transaction Safety

Validate that the following operations remain consistent:

- Current source listing persistence.
- Content-change history.
- Observation ledger insertion.
- Collection-run accounting.

Current listing, required history, and accepted observation
writes must remain atomic at the approved transaction boundary.

Inject a controlled failure during persistence.

Confirm that failed transactions do not leave incomplete
current listings, orphan history, or orphan observations.

### 6.4 Observation Ledger

Verify the uniqueness boundary:

`(source_listing_id, collection_run_id)`

Test:

- First accepted observation.
- Exact same-run retry.
- Conflicting payload within the same logical run.
- Older observation.
- Equal-time conflicting content.
- Newer unchanged observation.
- Newer changed observation.

Confirm that retry handling does not create duplicate
observations or duplicate history versions.

Validate run counters against the implemented accounting
contract.

Do not assume synthetic fixture counters represent
production ingestion behavior.

### 6.5 Invalid Record Persistence

Inject controlled invalid records covering:

- Validation failure.
- Missing source identity.
- Invalid numeric ranges.
- Unsupported source values.
- Invalid date representations.
- Mapping or ingestion failure where applicable.

Verify:

- Correct rejection stage.
- Correct error classification.
- Rejection deduplication.
- Appropriate sanitized diagnostic payload.
- No invalid source listing inserted into the current table.
- Consistent run telemetry.

### 6.6 Checkpoint Safety

All eight sources currently use bounded collection.

Active incremental checkpoint advancement must remain
disabled until source-specific behavior is validated.

Test the checkpoint mechanism independently.

Required scenarios:

- Successful checkpoint persistence.
- Failed collection without checkpoint advancement.
- Partial persistence without checkpoint advancement.
- Retry after interrupted persistence.
- Atomic finalization of successful run and checkpoint.
- Independent Egyincs jobs and lp_course scopes.

Do not advance a checkpoint before all covered records
have been successfully persisted.

Timestamp ties, overlap windows, and cursor recovery
must be validated before enabling incremental collection.

---

## 7. Recorded Real-Data Integration

### 7.1 Handover Sample

Input artifact:

`MATCHPOINT_Data_Collection_Handover_v3.0.0.zip`

Expected sample:

| Source | Records |
|---|---:|
| Wuzzuf | 5 |
| Forasna | 5 |
| Egyincs | 5 |
| ITIDA | 5 |
| NTI | 5 |
| Bayt | 5 |
| Devpost | 5 |
| UN Volunteers | 5 |
| Total | 40 |

The sample was collected and validated during the
collection milestone.

It contains previously recorded real source data.

It is not a newly executed live collection workflow.

### 7.2 Input Validation

Before persistence:

- Verify the sample inventory.
- Validate all records against Opportunity.
- Confirm source names.
- Confirm expected source identity uniqueness.
- Confirm required raw payload presence.
- Preserve original collected_at timestamps.
- Review payloads for sensitive or unnecessary data.

Do not modify original handover files.

Keep the sample outside the Git repository unless
an approved sanitized fixture is created.

### 7.3 First Ingestion

Ingest the sample through the actual Python persistence
implementation.

Do not insert the records directly through SQL as a
substitute for testing the ingestion implementation.

Expected clean-database outcome:

- 40 accepted source listings.
- Five source listings per supported source.
- Stable source listing identities.
- Initial content_version of 1.
- Initial history snapshots.
- Valid observation ledger records.
- Consistent collection-run accounting.

The exact number of collection runs depends on the
approved source and collection-scope execution strategy.

Any rejected sample record must be investigated rather
than silently excluded to satisfy expected counts.

### 7.4 First Warehouse Build

Execute from the repository root using the dedicated
dbt Python environment.

Configure the isolated real-data test target first.

```powershell
$dbtPython = Join-Path $env:USERPROFILE `
    "venvs\matchpoint-dbt\Scripts\python.exe"

$commands = @("debug", "parse", "seed", "run", "test")

foreach ($command in $commands) {

    $dbtArgs = @(
        $command,
        "--profiles-dir", ".",
        "--target", "test",
        "--no-use-colors"
    )

    if ($command -in @("parse", "test")) {
        $dbtArgs += "--warn-error"
    }

    & $dbtPython "dbt/run_dbt.py" @dbtArgs

    if ($LASTEXITCODE -ne 0) {
        throw "Warehouse stage failed: $command"
    }
}
```

Expected:

- Five successful seeds.
- 44 successful models.
- 461 successful dbt data tests.
- Complete source listing attribution.
- No orphan canonical relationships.
- No same-source canonical grouping violations.

The expected number of canonical opportunities must
be determined from reviewed matching evidence.

Do not assume the real sample must produce the same
deduplication ratio as the synthetic dataset.

### 7.5 Real Deduplication Review

Inspect:

- `silver.silver_opportunities`
- `silver.silver_opportunity_sources`
- `silver.silver_opportunity_history`
- `gold.fct_opportunities`
- `gold.fct_opportunity_sources`

Review:

- Confirmed cross-source duplicates.
- Potential false-positive merges.
- Potential false-negative matches.
- Primary-source selection.
- Canonical anchor selection.
- Source attribute conflicts.
- Original source URL preservation.

Review these fields where applicable:

- `has_source_attribute_conflicts`
- `conflicting_attributes`
- `canonical_anchor_key`
- `match_method`

Inspect unmapped organizations, locations, and skills.

Update normalization seeds only when supported by
reviewed source evidence.

Any seed or matching-rule change requires regression
testing.

Do not tune matching rules solely to obtain a preferred
canonical opportunity count.

---

## 8. Idempotency Acceptance Scenarios

The following scenarios must be tested separately.

### ID-01: Warehouse Rebuild

Rebuild Silver and Gold without modifying Bronze or seeds.

Create snapshots before the second build.

Compare:

- Canonical identity.
- Source mappings.
- Primary-source selection.
- Gold schemas.
- Row counts.
- Row contents.

Use symmetric `EXCEPT ALL` or an equivalent
duplicate-sensitive comparison.

Control lifecycle evaluation conditions.

Expected:

Equivalent deterministic warehouse outputs.

The synthetic version of this scenario has passed.

The recorded real-data version remains pending.

### ID-02: Exact Same-Run Ingestion Retry

Retry the same logical collection run using:

- The same collection_run_id.
- The same original observations.
- The same original collected_at timestamps.
- The same observation payloads.

Expected:

- No duplicate source listings.
- No duplicate observations.
- No duplicate history versions.
- No spurious content_version increments.
- No duplicate logical collection-run records.
- No double-counted run telemetry.

The implementation must preserve logical run identity
across retry attempts.

### ID-03: New Run with Unchanged Content

Create a new logical collection run with newer observation
timestamps and unchanged standardized business content.

Expected:

- Stable source listing identity.
- Unchanged content hash.
- Unchanged content_version.
- No additional content-change history.
- Updated last-seen metadata.
- New accepted observation records.
- Valid new collection-run telemetry.

Gold tables containing collection-run or observation
metadata may legitimately change.

Do not require all 20 Gold tables to remain identical.

### ID-04: Changed Content

Modify a meaningful standardized field in a controlled
test record.

Persist it as a newer observation.

Expected:

- Stable source listing identity.
- Changed content hash.
- Incremented content_version.
- New history snapshot.
- Preserved previous history.
- Updated current source listing.

Canonical grouping may legitimately change if the
modified field affects matching evidence.

### ID-05: Repeated Historical Content

Execute a controlled content sequence:

```text
Content A -> Content B -> Content A
```

Expected:

- One stable source listing identity.
- Three sequential content versions.
- Three history snapshots.
- Matching hashes for versions 1 and 3.
- Different hash for version 2.

Content hash recurrence must not suppress a legitimate
new history version.

### ID-06: Stale and Conflicting Observations

Test:

- Older observation arriving after newer content.
- Equal observation timestamp with different content.
- Same-run retry containing a different payload.

Expected:

- No stale overwrite.
- No retroactive content history.
- Explicit conflict or stale outcome.
- Preserved current source listing.
- Correct run telemetry.

### Snapshot Test Limitations

The existing Phase 4 and Phase 5 fixture verifiers contain
synthetic-specific expectations.

Do not apply those expectations directly to the 40-record
real-data sample.

Reuse or adapt snapshot comparison logic only after
reviewing its dataset assumptions and database authorization.

---

## 9. Lifecycle Acceptance

Bronze preserves source-observed status.

Silver and Gold derive effective lifecycle status according
to the approved lifecycle rules.

### LC-01: Exact Deadline

Verify expiration after a confirmed exact deadline.

### LC-02: Date-Only Deadline

Verify expiration according to the approved date-only
interpretation and conservative boundary rules.

Do not invent an exact timestamp for date-only evidence.

### LC-03: Explicit Closure

Verify that explicit closed status remains closed even
when the recorded deadline is in the future.

### LC-04: Relative Deadline

Verify that approximate relative date evidence does not
cause unsupported automatic expiration.

### LC-05: Bounded Collection Absence

Verify that absence from a later bounded collection does
not automatically close a previously observed opportunity.

### LC-06: Reopening

Execute a controlled observation sequence:

```text
active -> closed -> active
```

Use the same source identity and increasing observation
timestamps.

Expected:

- One stable source listing.
- Three sequential content versions.
- Three preserved Bronze history snapshots.
- Corresponding Silver history representation.
- Correct current effective lifecycle status.

### LC-07: Unknown Status

Verify that a future deadline alone does not automatically
convert an unknown source status into active.

### LC-08: Time-Driven Refresh

Build the warehouse before and after a controlled
deadline boundary without modifying Bronze.

Expected:

- Effective lifecycle status changes when appropriate.
- No artificial Bronze content version increment.
- No artificial Bronze history snapshot.
- Updated lifecycle evaluation evidence.

Deterministic clock-controlled lifecycle testing remains
an implementation and acceptance requirement.

Excluding lifecycle_evaluated_at from a comparison does
not freeze the lifecycle evaluation clock.

### Lifecycle Scheduling

Proposed minimum refresh schedule:

- 00:15 UTC.
- 12:15 UTC.

Additional refreshes follow eligible collection workflows.

Cron expression:

`15 0,12 * * *`

A scheduled execution time does not guarantee successful
completion or a strict freshness bound.

Monitor actual successful refresh and publication times.

---

## 10. Production-Scale Performance Acceptance

**Owners:** Momen / Mahmoud / Andrew

The independent review identified PostgreSQL JIT compilation
as the dominant overhead for the tested recursive query.

Measured planning and execution:

| Configuration | Time |
|---|---:|
| JIT enabled | 11685.087 ms |
| JIT disabled | 57.305 ms |

The measurements used the 52-listing synthetic dataset.

The standard runner disables JIT by default for its own
connections.

Production-scale performance remains unverified.

### Required Benchmark Workloads

Test progressively larger representative datasets.

Include:

- Sparse cross-source matching.
- Dense matching candidates.
- Ambiguous matching evidence.
- Long transitive matching chains.
- Large organization and location groups.
- Realistic text and JSON payload sizes.

Use approved recorded data or generated representative
fixtures rather than unnecessary live source requests.

### Query-Plan Validation

Use:

```sql
ANALYZE;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT *
FROM gold.fct_opportunities
WHERE effective_status = 'active'
  AND opportunity_type = 'job'
ORDER BY published_at DESC NULLS LAST
LIMIT 50;
```

Also benchmark:

- Skill filtering using bridge EXISTS predicates.
- Source attribution by canonical opportunity ID.
- Organization and location filtering.
- Canonical deduplication model execution.
- Full warehouse build duration.
- Full quality-gate duration.

Use normal planner settings for acceptance.

Forced index scans establish index eligibility only.

They do not establish normal cost-based planner behavior.

### Required Performance Evidence

Record:

- Dataset size and distribution.
- Query execution time.
- Planning time.
- Buffer usage.
- Temporary disk usage.
- Relevant memory configuration.
- JIT configuration.
- Matching candidate counts.
- Warehouse build duration.
- Hardware and runtime environment.

Production performance thresholds must be agreed
against measured workload requirements.

Do not extrapolate synthetic benchmark results directly
to production volumes.

---

## 11. Airflow Integration Acceptance

**Owner:** Andrew

Required execution sequence:

```text
Independent Source Collection Tasks
                |
                v
Bronze Persistence and Outcome Gate
                |
                v
dbt Seed
                |
                v
dbt Run
                |
                v
dbt Test
                |
                v
Validated ClickHouse Staging Load
                |
                v
Consistent Analytical Publication
```

Validate:

- Linux execution of run_dbt.py.
- Correct database and profile selection.
- Runtime secret injection.
- Source-level failure isolation.
- Explicit Bronze persistence gate.
- Correct task dependencies.
- Workflow-level concurrency protection.
- Conditional retry behavior.
- Execution artifact retention.
- Lifecycle scheduling.
- Source freshness monitoring.

### Failure-Injection Tests

| Scenario | Required Outcome |
|---|---|
| One source fails | Independent sources can finish; explicit persistence gate evaluates publication eligibility |
| Bronze persistence fails | Unsafe transformation or publication is blocked |
| dbt seed fails | Model build and publication are blocked |
| dbt run fails | Quality-gate acceptance and publication are blocked |
| dbt test fails | ClickHouse loading is blocked |
| ClickHouse staging fails | Previous valid release remains available |
| Duplicate workflow starts | Conflicting execution is prevented |
| Permanent configuration error | No unconditional retries |
| Temporary infrastructure failure | Controlled retry follows approved policy |

Using ALL_DONE alone is not sufficient to authorize
downstream transformation.

A single-task pool alone is not sufficient to guarantee
workflow-level serialization.

---

## 12. ClickHouse Integration Acceptance

**Owner:** Andrew

Source:

`PostgreSQL gold`

Target:

`ClickHouse matchpoint_analytics`

Validate all tables required by the declared analytical
release contract.

### Required Validation

- Schema compatibility.
- Row-count parity.
- Key uniqueness.
- Referential integrity.
- Duplicate-sensitive content parity.
- Numeric precision.
- NULL preservation.
- Empty-array preservation.
- Unicode preservation.
- Outlier date preservation.
- Lifecycle distribution parity.
- Canonical source attribution.
- Consistent release identity.

Test dates including:

- 1970-01-01.
- 2099-12-31.
- 9999-12-31.

Unsupported typed date ranges must use a validated
lossless representation.

Do not silently truncate or clamp source dates.

### Publication Safety

Load data into an isolated staging release.

Validate the entire required analytical dataset before
making it available to consumers.

Per-table atomic replacement does not establish
atomic publication across multiple tables.

Validate:

- Interrupted staging load.
- Interrupted publication.
- Retry without duplicate rows.
- Recovery to the previous valid release.
- Consumer access to a consistent release.

### Reconciliation

Required canonical reconciliation:

```text
PostgreSQL canonical opportunity count
    =
ClickHouse canonical opportunity count
```

Required primary-source reconciliation:

```text
SUM(primary_canonical_opportunities)
    =
COUNT(*) FROM fct_opportunities
```

Required location reconciliation:

```text
SUM(canonical_opportunity_count)
    =
COUNT(*) FROM fct_opportunities
```

Location reconciliation must include the unreported bucket.

Do not apply additive reconciliation to overlapping
skills, categories, work modes, or employment types.

---

## 13. Power BI Integration Acceptance

**Owner:** Ramadan

Validate the semantic model against a consistent
published ClickHouse release.

### Required Checks

- Canonical opportunity totals.
- Source listing totals.
- Correct fact and dimension relationships.
- Correct many-to-many bridge handling.
- Distinct opportunity counting.
- Primary-source reconciliation.
- Non-additive metric handling.
- Lifecycle status distribution.
- Source coverage.
- Publication freshness.
- Unreported location handling.
- Salary currency and period separation.
- Outlier date handling.

Do not treat undisclosed salary as zero.

Do not aggregate incompatible currencies or salary
periods without an approved conversion policy.

Apply the standard calendar range filter to trend visuals
where required by the analytical contract.

Power BI refresh must consume one consistent analytical
release.

Dashboard totals must reconcile with the corresponding
published release rather than an independently changing
PostgreSQL warehouse state.

---

## 14. FastAPI Integration Acceptance

**Owner:** Mahmoud

Opportunity-serving endpoints must consume the approved
Gold warehouse interface using a read-only warehouse role.

Do not expose Bronze raw payloads or intermediate
matching models through public endpoints.

Application-specific writes, such as user profiles,
must use separately approved application storage.

### Opportunity Retrieval

Validate:

- Opportunity listing responses.
- Opportunity detail responses.
- Pagination.
- Filtering.
- Sorting.
- Empty result handling.
- Invalid request handling.
- Database failure handling.

An empty opportunity dataset must return the documented
successful empty response.

### Source Traceability

Verify preservation of:

- Canonical opportunity identity.
- Original source attribution.
- All original source URLs.
- Primary source.
- Effective lifecycle status.
- Relevant eligibility evidence.

Preserve:

- `all_source_urls`
- `applicant_eligibility_raw`

Unknown eligibility must not be presented as confirmed
applicant eligibility.

### Multi-Value Filtering

Use EXISTS predicates or equivalent deduplicated
query patterns for bridge-based filtering.

Verify that filtering by multiple skills, categories,
work modes, or employment types does not multiply
canonical result rows.

Pagination totals must represent canonical opportunities.

### Matching Acceptance

Validate the approved matching algorithm separately.

Required scenarios:

- Relevant opportunity ranking.
- Missing applicant information.
- Missing opportunity requirements.
- Multiple matching skills.
- Unknown eligibility.
- Expired or closed opportunities.
- Stable score interpretation.
- Deterministic tie handling where applicable.

Do not present a relevance score as a guarantee of
eligibility, acceptance, or employment.

The final matching contract and scoring thresholds
remain backend implementation requirements.

### Security Acceptance

Validate:

- Request validation.
- Parameterized database queries.
- Read-only warehouse access.
- Credential isolation.
- Authentication and authorization where required.
- Appropriate error responses.
- No sensitive information leakage.

---

## 15. React Frontend Integration Acceptance

**Owner:** Abdel Rahman

The frontend must consume the approved FastAPI interface.

Mock data is acceptable during independent frontend
development.

Mock data does not establish backend integration.

### Required Integration Checks

- API connection configuration.
- Opportunity listing display.
- Opportunity detail display.
- Search and filtering.
- Pagination.
- Loading states.
- Empty states.
- Error states.
- Source attribution.
- Original opportunity links.
- Effective lifecycle status.
- Matching score display where supported.

### Data Contract Compatibility

Validate:

- All eight supported source values.
- All ten supported opportunity types.
- Approved work-mode values.
- Approved employment-type values.
- NULL and confirmed empty collection semantics.
- Missing salary and deadline handling.
- Unknown eligibility handling.

The frontend must not invent missing source information.

### User Interface Acceptance

Validate:

- Responsive layouts.
- Arabic RTL support.
- English LTR support.
- Keyboard navigation.
- Readable form validation.
- Accessible status and error messages.

Do not rely exclusively on color to communicate status.

### Authentication Boundary

Frontend authentication behavior must follow the actual
backend authentication contract.

Mock authentication must not be presented as a
production security mechanism.

---

## 16. Master End-to-End Acceptance Matrix

| ID | Acceptance Dimension | Required Evidence | Current Status |
|---|---|---|---|
| E2E-01 | Source collection | Eight supported adapters and validated handover sample | Collection milestone verified |
| E2E-02 | Physical schema | Seven migrations and 23 distinct SQL checks | Verified |
| E2E-03 | Persistent ingestion | Actual Python persistence of recorded real data | Pending |
| E2E-04 | Source identity | Stable identities and duplicate prevention | Pending ingestion |
| E2E-05 | Observation ledger | Same-run retry and conflict validation | Pending ingestion |
| E2E-06 | Content history | Atomic version progression and history preservation | Pending ingestion |
| E2E-07 | Checkpoints | Safe advancement and failure recovery | Pending |
| E2E-08 | Warehouse data quality | 461 tests on recorded real data | Synthetic pass only |
| E2E-09 | Canonical consistency | Reviewed real deduplication evidence | Synthetic pass only |
| E2E-10 | Source traceability | Complete real-data attribution and URL preservation | Synthetic pass only |
| E2E-11 | Lifecycle | Controlled reopening and time-driven refresh | Partially validated |
| E2E-12 | Transformation idempotency | Real-data snapshot equivalence | Synthetic pass only |
| E2E-13 | Ingestion idempotency | Same-run retry and new-run behavior | Pending |
| E2E-14 | Performance | Representative workload benchmarks | Small synthetic benchmark only |
| E2E-15 | Airflow orchestration | Successful gated workflow execution | Pending |
| E2E-16 | Failure handling | Controlled failure-injection evidence | Partially validated |
| E2E-17 | ClickHouse conversion | Lossless type and content validation | Pending |
| E2E-18 | Analytical publication | Consistent release and recovery tests | Pending |
| E2E-19 | Power BI | Dashboard reconciliation | Pending |
| E2E-20 | FastAPI | Endpoint, matching, and security validation | Pending |
| E2E-21 | React frontend | Actual API integration and UI validation | Pending |
| E2E-22 | Freshness | Successful refresh and publication monitoring | Pending |
| E2E-23 | Reproducibility | Fresh-environment integration execution | Pending complete integration |
| E2E-24 | Deployment security | Runtime roles, secrets, and access validation | Pending |

No pending criterion may be marked passed without
corresponding execution evidence.

---

## 17. Required Acceptance Evidence

Each acceptance execution must record:

- Acceptance test identifier.
- Responsible owner.
- Git commit SHA.
- Runtime versions.
- Data contract version.
- Hash version.
- Target environment.
- Dataset identifier.
- Expected outcome.
- Actual outcome.
- Execution timestamps.
- Exit code where applicable.
- Relevant execution artifacts.
- Failure details.
- Final acceptance status.

Supported acceptance statuses:

- NOT_STARTED
- BLOCKED
- FAILED
- PARTIAL
- PASSED

Document the blocker or failed assertion explicitly.

Do not replace failed execution evidence with a later
successful result without preserving the relevant history.

---

## 18. Release Acceptance Checklist

### Collection and Persistence

- [ ] Persist the 40-record handover sample.
- [ ] Verify all eight source identities.
- [ ] Validate collection-run accounting.
- [ ] Validate same-run retry behavior.
- [ ] Validate new-run unchanged behavior.
- [ ] Validate changed-content history.
- [ ] Validate stale and conflicting observations.
- [ ] Validate invalid-record persistence.
- [ ] Validate transaction rollback.
- [ ] Validate checkpoint recovery.

### Warehouse

- [ ] Build all models on recorded real data.
- [ ] Pass the complete dbt quality gate.
- [ ] Review real deduplication outcomes.
- [ ] Validate real source attribution.
- [ ] Validate real-data transformation idempotency.
- [ ] Validate cross-stage canonical mapping behavior.
- [ ] Validate lifecycle reopening.
- [ ] Validate time-controlled expiration.
- [ ] Complete remaining negative integration tests.
- [ ] Benchmark representative workloads.

### Orchestration and Analytics

- [ ] Validate Linux dbt runner execution.
- [ ] Execute the complete Airflow workflow.
- [ ] Validate partial-source failure handling.
- [ ] Validate workflow-level concurrency protection.
- [ ] Validate quality-gate failure blocking.
- [ ] Validate ClickHouse type conversions.
- [ ] Validate source-to-target content parity.
- [ ] Validate analytical publication recovery.
- [ ] Reconcile Power BI dashboard totals.

### Application

- [ ] Validate FastAPI opportunity endpoints.
- [ ] Validate matching behavior.
- [ ] Validate API filtering and pagination.
- [ ] Validate frontend API integration.
- [ ] Validate frontend loading and error states.
- [ ] Validate application security boundaries.

### Deployment

- [ ] Validate runtime database roles.
- [ ] Validate secret management.
- [ ] Validate deployment configuration.
- [ ] Validate monitoring.
- [ ] Validate backup and recovery requirements.
- [ ] Archive final acceptance evidence.

---

## 19. Final Acceptance Policy

The target final acceptance date is 2026-12-04.

The target date does not override required correctness,
security, or data-integrity checks.

Distinguish between:

1. Implemented components.
2. Independently tested components.
3. Integrated components.
4. Accepted end-to-end workflows.
5. Production-ready deployment.

A graduation-project demonstration may use an explicitly
documented limited integration scope.

Any incomplete or simulated component must be identified
as such during the demonstration.

The current Bronze physical schema and synthetic
warehouse transformation results are verified milestones.

Persistent ingestion, recorded real-data integration,
operational behavior, downstream integration, and final
platform acceptance remain separate requirements.