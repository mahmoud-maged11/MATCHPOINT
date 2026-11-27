# Downstream Handoff Contract: Airflow & ClickHouse

**Project:** MATCHPOINT

**Consumer Owner:** Andrew (`airflow/dags/`, `clickhouse/`)

**Warehouse Producer Owner:** Momen (`dbt/`)

**Collection and Bronze Ingestion Owner:** Mahmoud

**Analytics Consumer:** Ramadan (Power BI)

**Data Contract:** v3.0.0 (ADR-050)

**Content Hash Version:** 1

**PostgreSQL Version:** 16

**ClickHouse Target Version:** 25.8

This document defines the integration requirements between
persistent Bronze ingestion, the dbt warehouse, Airflow,
ClickHouse, and downstream analytics.

The requirements below do not imply that Airflow or ClickHouse
integration has already been implemented or accepted.

---

## 1. Responsibility Boundaries

| Component | Owner | Responsibility |
|---|---|---|
| Source collection | Mahmoud | Collect and standardize opportunities from eight supported sources. |
| Bronze ingestion | Mahmoud | Validation, identity, hashing, persistence, history, observations, and run telemetry. |
| Warehouse | Momen | Silver normalization, deduplication, canonical identity, Gold models, and data quality. |
| Orchestration | Andrew | Airflow scheduling, dependencies, failure handling, concurrency, and monitoring. |
| Analytical storage | Andrew | ClickHouse schema, extraction, conversion, loading, validation, and publication. |
| Analytics | Ramadan | Power BI semantic models, measures, dashboards, and analytical validation. |

Cross-component contract changes must be coordinated between
the affected owners before implementation.

---

## 2. End-to-End Orchestration Sequence

```text
Source Collection Tasks
        |
        v
Persistent PostgreSQL Bronze Ingestion
        |
        v
Collection Outcome and Persistence Gate
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
Validated Gold Warehouse
        |
        v
ClickHouse Staging Load
        |
        v
Type, Content, and Parity Validation
        |
        v
Consistent Analytical Publication
        |
        v
Power BI Refresh
```

### Mandatory Quality Gates

ClickHouse loading must not begin unless:

- The Bronze persistence gate permits transformation.
- The warehouse seed stage succeeds.
- All required dbt models build successfully.
- All required dbt data tests pass.
- The warehouse target is confirmed.
- The extraction process reads a consistent Gold release.

Power BI refresh must not begin unless the corresponding
ClickHouse release has been validated and published.

Every non-zero required-stage exit code must block the
dependent publication stages.

---

## 3. Bronze Ingestion Integration

Persistent Bronze ingestion is a prerequisite for complete
end-to-end acceptance.

The ingestion implementation must expose sufficient
machine-readable execution information for orchestration.

Required information includes:

- Logical collection run identifier.
- Source name.
- Collection scope.
- Collection mode.
- Run status.
- Start and finish timestamps.
- Records received.
- Records inserted.
- Records updated.
- Records unchanged.
- Records invalid.
- Records stale.
- Records conflicted.
- Error classification.
- Contract version.
- Hash version.

The authoritative persisted run status is maintained in:

`bronze.collection_runs`

Supported run statuses:

- `running`
- `completed`
- `partial`
- `failed`
- `aborted`

Process exit codes alone are not sufficient to determine
whether a collection run is eligible for downstream processing.

The final scraper and ingestion CLI exit-code contract must
be coordinated with the Bronze ingestion owner.

### Source Failure Isolation

A failure in one source must not unnecessarily prevent
independent sources from completing their own ingestion.

Successful persistence from other sources must remain valid.

A partial collection run does not automatically authorize
or prohibit downstream transformation.

The orchestration gate must evaluate:

- Persisted collection outcomes.
- Transaction completion.
- Database health.
- Whether relevant writes are still running.
- Whether partial publication is permitted.
- Whether the resulting warehouse release must be marked degraded.

Failed or incomplete source coverage must be visible
in operational telemetry.

Do not interpret missing listings in a bounded collection
as evidence that those opportunities have closed.

### Airflow Trigger Rules

`ALL_DONE` may be used to schedule an outcome-evaluation task
after independent collection tasks finish.

It must not bypass the Bronze persistence gate.

A downstream transformation task must depend on a successful
explicit gate decision rather than task completion alone.

---

## 4. Standard dbt Runtime

Use the dedicated dbt Python environment.

Reviewed runtime:

- Python 3.12.10.
- dbt-core 1.12.7.
- dbt-postgres 1.11.0.
- PostgreSQL 16.

Install dependencies from:

`dbt/requirements.txt`

Use the standard runner:

`dbt/run_dbt.py`

Do not invoke an unrelated globally installed dbt executable.

The runner:

- Uses dbt from its own Python environment.
- Sets its working directory to the dbt project directory.
- Disables PostgreSQL JIT by default for its connections.
- Preserves existing PostgreSQL connection options.
- Propagates dbt exit codes.
- Does not modify PostgreSQL server-wide configuration.

Linux and Airflow runner validation remain pending.

See [Standard dbt Execution Interface](dbt_execution_interface.md)
for complete runtime and execution requirements.

---

## 5. Required dbt Execution Order

The following Linux commands are integration templates.

Paths must be adapted to the deployed Airflow environment.

```bash
set -euo pipefail

DBT_PYTHON="/opt/venvs/matchpoint-dbt/bin/python"
DBT_RUNNER="/opt/airflow/dbt/run_dbt.py"
DBT_PROFILES="/opt/airflow/dbt_profiles"

: "${DBT_TARGET:?DBT_TARGET is required}"

"$DBT_PYTHON" "$DBT_RUNNER" seed \
    --profiles-dir "$DBT_PROFILES" \
    --target "$DBT_TARGET" \
    --no-use-colors

"$DBT_PYTHON" "$DBT_RUNNER" run \
    --profiles-dir "$DBT_PROFILES" \
    --target "$DBT_TARGET" \
    --no-use-colors

"$DBT_PYTHON" "$DBT_RUNNER" test \
    --profiles-dir "$DBT_PROFILES" \
    --target "$DBT_TARGET" \
    --warn-error \
    --no-use-colors
```

Archive each stage's execution artifacts before the next
command overwrites them.

### Warehouse Inventory

| Component | Count |
|---|---:|
| Lookup seeds | 5 |
| Staging views | 4 |
| Intermediate views | 6 |
| Silver tables | 14 |
| Gold tables | 20 |
| Total dbt models | 44 |
| Generic data tests | 443 |
| Singular data tests | 18 |
| Total data tests | 461 |

Required seeds:

- `supported_sources`
- `organization_aliases`
- `location_mappings`
- `skill_aliases`
- `generic_application_portals`

Run connectivity checks during environment initialization
and troubleshooting.

Run strict static validation in CI and before accepting
warehouse configuration changes.

---

## 6. Environment Variables and Networking

When Airflow runs inside the MATCHPOINT Docker network:

| Variable | Docker Value | Host Development Value |
|---|---|---|
| `POSTGRES_HOST` | `postgres` | `127.0.0.1` |
| `POSTGRES_PORT` | `5432` | Configured published port |
| `POSTGRES_USER` | Runtime role | `matchpoint` |
| `POSTGRES_DB` | Configured warehouse database | `matchpoint` |
| `POSTGRES_PASSWORD` | Runtime secret | Environment variable |
| `POSTGRES_TEST_DB` | Isolated test database | `matchpoint_test` |
| `DBT_TARGET` | Configured target | `dev` or `test` |
| `DBT_SCHEMA` | `silver` | `silver` |
| `DBT_THREADS` | `4` initially | `4` |
| `MATCHPOINT_DBT_JIT` | `off` | `off` |
| `CLICKHOUSE_HOST` | `clickhouse` | `127.0.0.1` |
| `CLICKHOUSE_PORT` | `8123` HTTP or `9000` native | Configured published port |
| `CLICKHOUSE_DB` | `matchpoint_analytics` | `matchpoint_analytics` |
| `CLICKHOUSE_USER` | Runtime role | Configured local role |
| `CLICKHOUSE_PASSWORD` | Runtime secret | Environment variable |

The ClickHouse environment variable names define the
proposed loader configuration interface.

The actual loader and its credential configuration must
be implemented and validated by the orchestration owner.

Use the actual Docker Compose network name.

Do not assume a fixed Compose-generated network name.

Never commit:

- `.env`
- Local `profiles.yml`
- Database credentials.
- Airflow connection secrets.
- ClickHouse connection secrets.

Use runtime environment variables or approved secret storage.

Production database roles and permissions remain pending.

---

## 7. Warehouse Materialization and Concurrency

All 14 Silver tables and 20 Gold tables currently use
dbt table materialization.

They are rebuilt during normal dbt runs.

The 10 staging and intermediate models are views.

Incremental warehouse materialization is not implemented.

The `--full-refresh` flag is not required for the current
table models.

Individual table rebuilds are transactional.

The complete multi-model dbt run is not one atomic transaction.

A failed run can leave different models representing
different execution stages.

### Concurrency Requirements

Airflow must prevent overlapping warehouse workflows
against the same target database.

Required controls:

- `max_active_runs=1` for the warehouse DAG.
- Target-specific task pools or equivalent controls.
- Workflow-level serialization across DAGs.
- Coordination with manual and external dbt execution.
- Coordination between Bronze writes and Gold extraction.
- Protection against concurrent ClickHouse publication.

A single-slot Airflow pool on individual tasks does not
guarantee exclusive ownership of an entire multi-task workflow.

The protected workflow must cover the required warehouse
build, quality gate, and consistent downstream extraction.

The standard dbt runner does not implement workflow locking.

Andrew must implement and validate the orchestration-level
concurrency mechanism.

---

## 8. Failure Handling and Retry Policy

### dbt Failures

| Exit Code | Required Action |
|---|---|
| `0` | Continue only after the required stage is validated. |
| `1` | Halt downstream processing and inspect the reported failure. |
| `2` | Halt and classify runtime, configuration, or invocation failure. |
| `130` | Treat execution as interrupted and halt publication. |
| Other non-zero | Halt and investigate. |

Do not classify failures using exit codes alone.

### Retry Requirements

Retry only confirmed transient failures.

Examples:

- Temporary database unavailability.
- Temporary network interruption.
- Recoverable infrastructure failure.

Recommended initial policy:

- Maximum two retries after the initial attempt.
- Initial retry delay of three minutes.
- Backoff for subsequent retries.
- Preserve the same logical operation identity where required.

Do not automatically retry:

- Invalid credentials.
- Missing configuration.
- Invalid SQL or YAML.
- Data-quality assertion failures.
- Unsupported type conversions.
- Deterministic contract violations.

Default unconditional Airflow task retries should remain
disabled until error classification is implemented.

### Execution Timeout

An initial dbt stage timeout of 15 minutes may be used
during controlled integration testing.

Production timeouts must be determined from measured
workloads rather than synthetic execution times alone.

### Recovery

A failed warehouse build must not authorize ClickHouse loading.

After correcting the failure, rebuild and validate the
required warehouse stages before publishing.

A failed ClickHouse load must not replace the last
successfully published analytical release.

---

## 9. Lifecycle Refresh and Freshness

Effective opportunity lifecycle status can change even
when Bronze records remain unchanged.

Gold lifecycle values are materialized during dbt execution.

### Proposed Minimum Refresh Schedule

Run the warehouse lifecycle refresh twice daily:

| UTC Time | Purpose |
|---|---|
| `00:15` | First scheduled lifecycle refresh |
| `12:15` | Second scheduled lifecycle refresh |

Airflow cron expression:

```text
15 0,12 * * *
```

Configure the DAG timezone explicitly as UTC.

Additional refreshes should occur after eligible
scheduled Bronze collection workflows.

The schedule is an initial orchestration policy,
not a real-time expiration guarantee.

The refresh workflow must use the same quality gates
and concurrency controls as other warehouse builds.

### Lifecycle Rules

Preserve the distinction between:

- Source-observed status.
- Effective warehouse status.
- Lifecycle evaluation timestamp.

Do not close opportunities solely because they are absent
from a bounded collection.

Explicit source closure and expiration must be preserved
according to the approved warehouse lifecycle rules.

Exact, date-only, relative, and unknown date precision
must retain their documented semantics.

The orchestration layer must not implement an independent
deadline interpretation algorithm.

### Source Freshness

Optional monitoring command:

```bash
"$DBT_PYTHON" "$DBT_RUNNER" source freshness \
    --profiles-dir "$DBT_PROFILES" \
    --target "$DBT_TARGET" \
    --no-use-colors
```

Current provisional thresholds:

- Warning: 24 hours.
- Error: 72 hours.

Configured freshness fields:

- `bronze.collection_runs.started_at`
- `bronze.source_listings.last_seen_at`
- `bronze.ingestion_observations.processed_at`

Aggregate table freshness does not establish that
every supported source is fresh.

Per-source operational freshness monitoring remains required.

Freshness failures are not opportunity closure evidence.

---

## 10. ClickHouse Source-to-Target Mapping

Source schema:

`PostgreSQL gold`

Target database:

`ClickHouse matchpoint_analytics`

All 20 Gold tables are eligible for analytical loading.

The following MergeTree ordering keys are recommendations,
not accepted production DDL.

Validate column names, data types, nullability, cardinality,
and query patterns against the actual Gold schema.

### Core Facts

| Priority | PostgreSQL Source | ClickHouse Target | Proposed ORDER BY |
|---|---|---|---|
| P0 | `gold.fct_opportunities` | `fct_opportunities` | `(effective_status, opportunity_type, opportunity_id)` |
| P0 | `gold.fct_opportunity_sources` | `fct_opportunity_sources` | `(source_name, opportunity_id, source_listing_id)` |
| P0 | `gold.fct_collection_runs` | `fct_collection_runs` | `(source_name, started_at, run_id)` |

### Dimensions

| Priority | PostgreSQL Source | ClickHouse Target | Proposed ORDER BY |
|---|---|---|---|
| P0 | `gold.dim_sources` | `dim_sources` | `(source_authority_rank, source_name)` |
| P0 | `gold.dim_organizations` | `dim_organizations` | `(organization_key)` |
| P0 | `gold.dim_locations` | `dim_locations` | `(location_key)` |
| P0 | `gold.dim_skills` | `dim_skills` | `(skill_key)` |
| P0 | `gold.dim_categories` | `dim_categories` | `(category_key)` |
| P0 | `gold.dim_dates` | `dim_dates` | `(date_key)` |

### Bridges

| Priority | PostgreSQL Source | ClickHouse Target | Proposed ORDER BY |
|---|---|---|---|
| P0 | `gold.bridge_opportunity_skills` | `bridge_opportunity_skills` | `(skill_key, opportunity_id)` |
| P0 | `gold.bridge_opportunity_categories` | `bridge_opportunity_categories` | `(category_key, opportunity_id)` |
| P0 | `gold.bridge_opportunity_work_modes` | `bridge_opportunity_work_modes` | `(work_mode, opportunity_id)` |
| P0 | `gold.bridge_opportunity_employment_types` | `bridge_opportunity_employment_types` | `(employment_type, opportunity_id)` |

### Analytical Marts

| Priority | PostgreSQL Source | ClickHouse Target | Proposed ORDER BY |
|---|---|---|---|
| P1 | `gold.mart_opportunities_by_source` | `mart_opportunities_by_source` | `(source_authority_rank, source_name)` |
| P1 | `gold.mart_opportunities_by_category` | `mart_opportunities_by_category` | `(category_key)` |
| P1 | `gold.mart_opportunities_by_location` | `mart_opportunities_by_location` | `(location_key)` |
| P1 | `gold.mart_opportunities_by_work_mode` | `mart_opportunities_by_work_mode` | `(opportunity_type, work_mode)` |
| P1 | `gold.mart_opportunities_by_employment_type` | `mart_opportunities_by_employment_type` | `(opportunity_type, employment_type)` |
| P1 | `gold.mart_skill_demand` | `mart_skill_demand` | `(canonical_opportunity_count, skill_key)` |
| P1 | `gold.mart_opportunity_lifecycle_trends` | `mart_opportunity_lifecycle_trends` | `(published_date_key, opportunity_type, effective_status)` |

MergeTree ordering keys are not uniqueness constraints.

The loader must independently validate required key uniqueness.

P0 and P1 define implementation priorities.

A complete analytical release must include every table
required by its declared consumer contract.

---

## 11. PostgreSQL-to-ClickHouse Type Conversion

Type conversion must preserve business meaning and must
not silently truncate, round, overflow, or discard data.

| PostgreSQL Type | Proposed ClickHouse Representation |
|---|---|
| UUID | UUID |
| TEXT / VARCHAR | String or Nullable(String) |
| BOOLEAN | Bool |
| INTEGER / BIGINT | Compatible signed or validated unsigned integer |
| NUMERIC | Decimal with validated precision and scale |
| TIMESTAMPTZ | UTC DateTime64 where representable, with lossless fallback |
| DATE | ISO String or validated Date32 representation |
| JSONB object | Serialized JSON String |
| JSONB array | Serialized JSON or Array(String) with explicit null-state preservation |

These mappings require validation against actual
source columns and ClickHouse 25.8 behavior.

### Numeric Precision

Do not apply a single fixed Decimal type to every
PostgreSQL NUMERIC column.

The loader must validate:

- Maximum precision.
- Required scale.
- Numeric range.
- Nullability.
- Whether rounding is permitted.

Salary values must not lose precision silently.

Currency and salary-period fields must remain associated
with their corresponding numeric values.

### Timestamp Precision

Normalize timestamp representations to UTC.

Use sufficient DateTime64 precision to preserve the
source timestamp resolution where supported.

Millisecond precision must not be selected automatically
if the source contains meaningful microsecond precision.

Validate representable timestamp ranges before conversion.

### JSON and Array Semantics

Preserve the difference between:

- SQL NULL: unavailable or unreported.
- JSON empty array: confirmed empty.
- Non-empty array: reported values.

A plain `Array(String)` cannot represent SQL NULL by itself.

Use either:

1. A nullable serialized JSON representation.
2. An array column with a separate explicit null-state flag.

Do not convert NULL to an empty array without preserving
the original semantic distinction.

Preserve relevant JSON evidence and Unicode content.

---

## 12. Date Range and Outlier Handling

PostgreSQL Gold preserves dates outside the standard
analytical calendar range.

Synthetic fixtures include:

- `1970-01-01`
- `2099-12-31`
- `9999-12-31`

ClickHouse Date and Date32 cannot represent every
PostgreSQL date value.

DateTime64 also has a bounded representable range.

Do not assume that every PostgreSQL DATE or TIMESTAMPTZ
can be converted directly.

### Recommended Lossless Representation

For date columns that may contain extreme outliers:

- Preserve the original ISO date as String.
- Preserve the original date key.
- Preserve the standard-calendar-range flag.
- Optionally provide a nullable typed analytical date.

Example:

```text
date_key = 99991231
calendar_date_iso = "9999-12-31"
calendar_date_typed = NULL
is_within_standard_calendar_range = false
```

The nullable typed date is a derived convenience field.

The original ISO date remains authoritative for lossless
analytical storage.

Validate the actual supported date and timestamp ranges
against the deployed ClickHouse version.

Do not silently clamp outlier dates to the nearest
supported date.

Outlier foreign-key relationships must remain resolvable
through the preserved date key.

The final representation must be coordinated with the
Power BI consumer.

---

## 13. ClickHouse Loading Strategy

The current warehouse rebuilds its table models.

Therefore, append-only loading into existing analytical
tables is not appropriate for the current MVP.

Repeated loading must not create duplicate analytical rows.

### Required Loading Workflow

```text
Validated PostgreSQL Gold Release
        |
        v
Consistent Source Extraction
        |
        v
Create Isolated ClickHouse Staging Release
        |
        v
Load Required Facts, Dimensions, Bridges, and Marts
        |
        v
Validate Types, Keys, Counts, and Content
        |
        v
Publish Validated Analytical Release
        |
        v
Allow Consumer Refresh
```

### Consistent PostgreSQL Extraction

Extract data from a consistent warehouse state.

Recommended mechanisms include:

- A read-only repeatable-read PostgreSQL transaction
  covering all required extraction queries.
- An equivalent validated snapshot mechanism.
- Workflow serialization that prevents warehouse rebuilds
  during the extraction window.

Independent extraction queries must not accidentally read
different warehouse generations.

### Per-Table Replacement

ClickHouse `EXCHANGE TABLES` may be used where the
database engine and deployment support atomic exchange.

This provides per-table replacement behavior.

It does not automatically make the replacement of
20 tables one atomic analytical publication.

Do not describe `TRUNCATE` followed by `INSERT` on a live
consumer table as an atomic replacement.

### Release-Level Publication

The loader must provide a consistent analytical release
across all required tables.

Recommended design:

- Assign a unique analytical release identifier.
- Load all required tables into an isolated release.
- Validate the entire release before publication.
- Activate the validated release through a controlled
  consumer-visible publication mechanism.
- Retain the previous valid release for recovery.

Possible implementation approaches include versioned
release schemas, release-specific tables, or an equivalent
validated publication protocol.

The exact publication mechanism remains an implementation
decision for Andrew, coordinated with Ramadan.

Consumers must bind to one consistent release for the
duration of their refresh or analytical operation.

If a release-level publication mechanism is not available,
consumer access must be coordinated during replacement
to prevent mixed-generation reads.

Do not claim full release atomicity until failure-injection
and consumer-consistency tests establish it.

---

## 14. Canonical Identity and Lifecycle Changes

Canonical opportunity IDs are deterministic under the
current matching and anchor-selection rules.

However, later source observations may change matching
evidence or introduce a higher-authority canonical anchor.

Consequently:

- Canonical opportunity IDs may change across releases.
- Canonical groups may merge or split.
- Effective lifecycle status may change.
- Primary-source selection may change.
- Bridge relationships may change.

ClickHouse loading must not assume that canonical IDs
are permanently immutable across warehouse releases.

Full analytical replacement must remove obsolete canonical
rows and relationships.

Source listing identity remains separate from canonical
opportunity identity.

Persistent canonical aliasing and reconciliation across
identity changes are separate future requirements.

---

## 15. Post-Load Validation

Row-count parity is required but is not sufficient.

Validate the staged ClickHouse release before publication.

### Required Checks

| Check | Requirement |
|---|---|
| Schema compatibility | Required columns and compatible types exist. |
| Row counts | Match the corresponding PostgreSQL extraction. |
| Key uniqueness | Required analytical keys contain no duplicates. |
| Referential integrity | Required fact and bridge references resolve. |
| NULL preservation | Missing values retain their intended meaning. |
| Array semantics | NULL and confirmed empty arrays remain distinguishable. |
| Numeric precision | No unauthorized rounding or overflow. |
| Date preservation | Outlier dates and date keys remain recoverable. |
| Unicode preservation | Arabic and other source text remain intact. |
| Content parity | Compare normalized source and target contents. |
| Lifecycle parity | Effective status distributions match the source release. |
| Source attribution | Primary-source totals reconcile to canonical totals. |
| Release consistency | All required tables belong to the same release. |

Content comparison may use deterministic normalized
row fingerprints or equivalent field-level comparisons.

The comparison must preserve duplicate multiplicity.

Cross-database fingerprints require an agreed canonical
serialization format.

Do not compare database-specific hash functions without
validating equivalent input serialization.

### Mandatory Reconciliation

The following must reconcile:

```text
ClickHouse canonical opportunity count
    =
PostgreSQL canonical opportunity count
```

```text
SUM(primary_canonical_opportunities)
    =
COUNT(*) FROM fct_opportunities
```

The source mart must contain all eight supported sources.

Bridge and mart counts must follow their documented grain.

Do not require sums across non-additive categories,
skills, work modes, or employment types to equal the
canonical opportunity count.

---

## 16. Analytical Semantics for Power BI

The ClickHouse analytical release must preserve
the PostgreSQL Gold business semantics.

### Counting Rules

- Count canonical opportunities from `fct_opportunities`.
- Count source listings from `fct_opportunity_sources`.
- Use distinct canonical opportunity IDs when traversing
  many-to-many bridge relationships.
- Do not sum source-listing counts as canonical counts.
- Do not sum overlapping skill or category populations
  as if they were mutually exclusive.

### Salary Rules

- Preserve currency.
- Preserve salary period.
- Preserve one-sided salary ranges.
- Do not treat undisclosed salary as zero.
- Do not combine incompatible currencies or salary periods
  without an approved conversion policy.

### Location Rules

Preserve the explicit `unreported` analytical bucket.

Do not replace unknown location with an inferred city
or country without an approved normalization rule.

### Lifecycle Rules

Use the warehouse-provided effective lifecycle status.

Preserve lifecycle evaluation timestamps and release freshness.

Power BI refresh must depend on successful publication
of the validated analytical release.

---

## 17. Execution Evidence and Monitoring

Each orchestration workflow must retain:

- Workflow run identifier.
- Source collection run identifiers.
- Git commit SHA.
- Data contract version.
- Hash version.
- Warehouse target.
- Runtime dependency versions.
- Stage start and finish timestamps.
- Stage exit codes.
- Failure classification.
- dbt model execution results.
- dbt data-test results.
- ClickHouse analytical release identifier.
- Source and target row counts.
- Type-conversion validation results.
- Publication status.

Relevant dbt artifacts:

- `dbt/target/run_results.json`
- `dbt/target/manifest.json`
- `dbt/logs/dbt.log`

Archive artifacts after each relevant stage.

A later dbt command may overwrite previous artifacts.

Do not include credentials in execution logs.

### Required Operational Alerts

- Source collection failure.
- Partial collection coverage.
- Bronze persistence failure.
- Warehouse build failure.
- Data-quality failure.
- Source freshness violation.
- ClickHouse load failure.
- Type-conversion failure.
- Source-to-target parity failure.
- Analytical publication failure.
- Stale published release.

---

## 18. Idempotency and Recovery Requirements

Separate the following behaviors:

### Warehouse Transformation Idempotency

Repeated builds over unchanged Bronze inputs should
produce equivalent outputs under equivalent evaluation
conditions.

Time-dependent lifecycle changes are legitimate differences.

### Ingestion Idempotency

Retrying the same logical collection run must not create
duplicate observations, listings, or history versions.

This behavior belongs to the persistent ingestion contract.

### ClickHouse Loading Idempotency

Retrying a failed analytical load must not:

- Append duplicate analytical rows.
- Publish incomplete tables.
- Replace a valid release with an invalid release.
- Mix different warehouse generations.

A new collection run may legitimately change telemetry,
last-seen metadata, lifecycle status, or canonical grouping.

Do not require every Gold table to remain identical
after a new logical collection run.

### Recovery Requirements

Validate recovery from:

- Source failure.
- Bronze persistence interruption.
- dbt build failure.
- dbt test failure.
- ClickHouse staging-load failure.
- Partial publication attempt.
- Duplicate workflow execution.
- Interrupted analytical consumer refresh.

Preserve the last successfully published analytical
release until a validated replacement is available.

---

## 19. Independent Warehouse Review Evidence

The original warehouse implementation results remain
historical evidence.

The independent review used:

- Python 3.12.10.
- dbt-core 1.12.7.
- dbt-postgres 1.11.0.
- PostgreSQL 16.
- Isolated database `matchpoint_dbt_review_test`.

Verified synthetic results include:

| Validation | Result |
|---|---|
| Empty Bronze model build | 44 successful models |
| Empty Bronze quality gate | 461 passed |
| Phase 4 baseline | 41 listings, 32 canonical opportunities |
| Expanded edge-case dataset | 52 listings, 43 canonical opportunities |
| Gold idempotency | 20 models passed |
| Database authorization negative checks | 18 passed |
| Runner functional checks | 8 passed |
| Final regression quality gate | 461 passed |

The reviewed synthetic dataset covers all eight
supported sources.

The independent review also identified PostgreSQL JIT
compilation overhead in the recursive deduplication query.

Measured query planning and execution:

| Configuration | Time |
|---|---:|
| JIT enabled | 11685.087 ms |
| JIT disabled | 57.305 ms |

The runner defaults to JIT disabled for its connections.

These measurements apply to the tested query and
synthetic dataset only.

Production-scale performance remains unverified.

---

## 20. Andrew's Implementation Acceptance Checklist

### Airflow

- [ ] Configure the dedicated dbt runtime.
- [ ] Validate Linux runner execution.
- [ ] Configure runtime secrets and database connections.
- [ ] Implement independent source collection tasks.
- [ ] Integrate persistent Bronze ingestion outcomes.
- [ ] Implement the explicit Bronze persistence gate.
- [ ] Implement the seed, run, and test sequence.
- [ ] Archive execution artifacts.
- [ ] Implement workflow-level concurrency protection.
- [ ] Implement conditional transient-error retries.
- [ ] Configure lifecycle refresh scheduling in UTC.
- [ ] Implement per-source freshness monitoring.
- [ ] Block downstream loading after quality-gate failure.

### ClickHouse

- [ ] Verify the deployed ClickHouse version.
- [ ] Inspect the actual PostgreSQL Gold schema.
- [ ] Implement and validate P0 table definitions.
- [ ] Implement and validate P1 table definitions.
- [ ] Validate ordering keys against query requirements.
- [ ] Preserve numeric precision and nullability.
- [ ] Preserve Unicode and JSON semantics.
- [ ] Preserve outlier dates and date keys.
- [ ] Implement consistent PostgreSQL extraction.
- [ ] Implement isolated staging loads.
- [ ] Validate row counts, keys, and content parity.
- [ ] Implement consistent analytical publication.
- [ ] Implement idempotent retry and recovery behavior.
- [ ] Test interrupted loading and publication.
- [ ] Provision least-privilege runtime roles.

### Power BI Handoff

- [ ] Coordinate the published analytical schema.
- [ ] Document analytical table grains.
- [ ] Document non-additive metrics.
- [ ] Validate canonical and source-listing counting.
- [ ] Validate currency and salary-period semantics.
- [ ] Validate outlier date representations.
- [ ] Bind consumer refresh to a consistent release.
- [ ] Verify publication freshness and lifecycle metadata.

### End-to-End Acceptance

- [ ] Validate real persisted data from all eight sources.
- [ ] Validate same-run ingestion retry behavior.
- [ ] Validate content-change history.
- [ ] Validate lifecycle reopening and expiration.
- [ ] Validate checkpoint recovery.
- [ ] Validate production-scale warehouse performance.
- [ ] Validate complete Airflow-to-ClickHouse execution.
- [ ] Validate Power BI reconciliation.

---

## 21. Current Acceptance Boundary

The Bronze physical schema and synthetic warehouse
transformation behavior have been independently validated.

The current synthetic results do not establish:

- Persistent ingestion correctness.
- Complete Airflow orchestration.
- ClickHouse type-conversion correctness.
- Release-level atomic publication.
- Production-scale performance.
- Power BI integration correctness.
- Production readiness.

These requirements remain open until implementation
and execution evidence establish acceptance.