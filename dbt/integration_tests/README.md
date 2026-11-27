# Phase 4 & Phase 5 Synthetic Integration Test Suite

## 1. Purpose

This directory contains executable PostgreSQL fixtures,
verification scripts, and idempotency checks for the MATCHPOINT
Silver and Gold warehouse layers.

The suite validates:

- Cross-source opportunity deduplication.
- Canonical opportunity identity.
- Source attribution and primary-source selection.
- Gold dimensions, facts, bridges, and analytical marts.
- Lifecycle and date handling.
- Collection-run telemetry.
- Warehouse transformation idempotency.

All fixtures must execute against an isolated PostgreSQL 16
test database with migrations 001 through 007 applied.

These scripts intentionally live outside `dbt/tests/`.

The dbt singular test runner must not execute fixture DDL
or DML statements as SELECT-based data assertions.

Synthetic integration testing does not replace real ingestion
or end-to-end acceptance testing.

---

## 2. Runtime Requirements

| Component | Reviewed Version |
|---|---|
| Python | 3.12.10 |
| dbt-core | 1.12.7 |
| dbt-postgres | 1.11.0 |
| PostgreSQL | 16.x |
| Data Contract | 3.0.0 |
| Content Hash Version | 1 |

Use the dedicated dbt Python environment.

Install dependencies from `dbt/requirements.txt`.

Use `dbt/run_dbt.py` as the standard dbt execution entry point.

The runner disables PostgreSQL JIT by default for its own
connections without modifying server-wide settings.

See [dbt Execution Interface](../docs/dbt_execution_interface.md)
for runtime configuration and orchestration requirements.

---

## 3. Database Safety Requirements

### 3.1 Allowed Databases

Protected mutating integration scripts allow only:

- `matchpoint_test`
- `matchpoint_dbt_review_test`

The database name must match the explicit PostgreSQL session
setting:

`matchpoint.expected_test_database`

The following conditions cause execution to abort:

- Missing session authorization.
- Unauthorized database name.
- Mismatch between the authorized and actual database names.

The previous substring-based database-name guard is no longer used.

The current guard protects against accidental execution.

It does not replace database-level access controls.

Never execute synthetic fixtures against development or
production databases.

### 3.2 Isolation Requirements

Before executing the complete suite:

- Provision a dedicated test database.
- Apply all seven Bronze migrations.
- Confirm the actual database name.
- Confirm the expected initial Bronze state.
- Configure the dbt test target for the same database.
- Ensure no other process is modifying the test database.
- Ensure no previous integration snapshots remain.

Do not assume that rerunning the baseline loader removes
every fixture created by later phases.

The recommended complete execution sequence starts with a
fresh isolated database.

### 3.3 Transaction Safety

Mutating fixture scripts execute their protected operations
transactionally.

Use PostgreSQL's `ON_ERROR_STOP=1` option.

Stop immediately if a fixture or verification script fails.

Do not continue to subsequent warehouse stages after a failure.

### 3.4 Snapshot Safety

Silver and Gold snapshots are persistent PostgreSQL tables
with test-only names.

They are not session-scoped TEMP tables.

Snapshot creation refuses to overwrite existing snapshots.

Successful idempotency verification removes the corresponding
snapshot tables.

Failed idempotency verification preserves snapshots through
transaction rollback for investigation.

Never automatically delete an existing snapshot merely to
make a subsequent test pass.

---

## 4. Script Inventory

### 4.1 Phase 4: Silver Deduplication

| Script | Responsibility |
|---|---|
| `load_phase4_synthetic_bronze.sql` | Loads 41 baseline listings, 9 collection runs, and 2 Bronze history records. |
| `verify_phase4_synthetic_results.sql` | Validates the 41-listing baseline and all S1-S10 verification groups. |
| `snapshot_phase4_silver_run1.sql` | Creates a protected snapshot of canonical source mappings. |
| `verify_phase4_idempotency.sql` | Compares source mappings between two warehouse builds and removes the snapshot on success. |

The baseline collection scope is `synthetic_phase4`.

### Phase 4 Verification Coverage

- Tier 1A direct Wuzzuf URL matching.
- Case-sensitive ITIDA SharePoint paths.
- Tier 1B shared external URLs with query parameters.
- Tier 2 composite English and Arabic Cairo matching.
- Same-source direct and transitive merge prevention.
- Ambiguous same-source composite matching protection.
- Generic portal exclusions for root and non-root paths.
- Four-source transitive matching chains.
- Canonical anchor authority stability.
- Salary scale equivalence under ADR-019.
- Actual salary-period and employment-type conflicts.
- False-positive prevention.
- Bronze history preservation.

The verifier includes explicit baseline fixture preconditions,
NULL-safe comparisons, and separate S10 subscenario checks.

The Phase 4 baseline verifier requires exactly 41 Bronze
listings and 41 distinct mapped Silver source listings.

Do not execute it unchanged against the expanded
52-listing Phase 5 dataset.

### Automatic dbt Deduplication Test

`dbt/tests/assert_dedup_positive_and_negative_cases.sql`

This singular data test runs automatically during `dbt test`.

It validates:

- URL normalization.
- Generic application portal exclusions.
- ADR-019 salary conflict normalization.
- Deterministic UUID stability.
- Recursive convergence on a 10-edge, 11-node chain.

---

### 4.2 Phase 5: Gold Baseline

| Script | Responsibility |
|---|---|
| `load_phase5_gold_skills_categories_enrichment.sql` | Enriches selected baseline listings and adds one invalid-record fixture. |
| `verify_phase5_gold_results.sql` | Validates all six Gold baseline verification groups, G1-G6. |

The enrichment preserves the baseline merge topology:

- 41 Bronze source listings.
- 32 canonical opportunities.

Gold baseline verification covers:

- All eight supported sources in `dim_sources`.
- All eight supported sources in `mart_opportunities_by_source`.
- Canonical opportunity and source-listing parity.
- Skill alias normalization.
- Python skill deduplication: 4 raw occurrences to 3 canonical opportunities.
- Power BI skill deduplication: 2 raw occurrences to 1 canonical opportunity.
- Category bridge deduplication.
- Location, work-mode, and employment-type marts.
- Primary-source lifecycle and publication-trend marts.
- Invalid-record telemetry.

The enrichment loader verifies its required baseline
records before modifying data.

The Gold baseline verifier validates its expected fixtures
before evaluating the analytical assertions.

---

### 4.3 Phase 5: Expanded Edge Cases

| Script | Responsibility |
|---|---|
| `load_phase5_edge_cases_synthetic.sql` | Adds 11 isolated edge-case listings and 3 collection runs. |
| `verify_phase5_edge_cases.sql` | Validates all 11 edge-case verification groups, EC1-EC11. |

The edge-case collection scope is `synthetic_phase5_edge`.

The expanded dataset contains:

- 52 Bronze source listings.
- 43 canonical opportunities.
- 12 collection runs.
- All eight supported sources.

Edge-case coverage:

- Outlier dates: 1970-01-01, 2099-12-31, and 9999-12-31.
- Bounded standard date dimension.
- Outlier date foreign-key resolution.
- Expired exact deadlines.
- Expired date-only deadlines.
- Explicitly closed opportunities with future deadlines.
- Relative publication and deadline precision.
- Relative-date trend exclusion.
- NULL location and the unreported analytical bucket.
- Confirmed empty JSONB arrays.
- Devpost hackathon opportunities.
- UN Volunteers volunteering opportunities.
- One-sided disclosed salary.
- Multiple work modes and employment types.
- Prevention of Cartesian multiplication.
- Collection-run counter anomaly detection.

The verifier includes explicit dataset and fixture
preconditions before evaluating edge-case assertions.

---

### 4.4 Gold Idempotency

| Script | Responsibility |
|---|---|
| `snapshot_phase5_gold_run1.sql` | Creates protected snapshots of all 20 Gold models. |
| `verify_phase5_gold_idempotency.sql` | Compares Gold schemas, row counts, and row contents between two warehouse builds. |

The 20 Gold models consist of:

- 6 dimensions.
- 7 facts and bridges.
- 7 analytical marts.

Snapshot tables use the naming convention:

`gold._tmp_run1_*`

The snapshot creation script refuses to overwrite existing
snapshot tables.

The verification script checks:

- Column names and order.
- PostgreSQL column types.
- Type modifiers.
- Column collations.
- Row counts.
- Symmetric row-content differences.

The comparison uses `EXCEPT ALL` in both directions.

Unlike ordinary `EXCEPT`, this detects differences in
duplicate-row multiplicity.

Only `lifecycle_evaluated_at` in `gold.fct_opportunities`
is excluded from the row-content comparison.

All other columns remain subject to comparison.

---

## 5. Standard Execution Helpers

The following PowerShell helpers are intended for local
Windows development with the existing Docker Compose
PostgreSQL service.

Run from the repository root.

The selected test database must already exist and contain
all seven Bronze migrations.

Supply `POSTGRES_PASSWORD` securely before execution.

```powershell
$ErrorActionPreference = "Stop"

$testDb = "matchpoint_dbt_review_test"

$dbtPython = Join-Path $env:USERPROFILE `
    "venvs\matchpoint-dbt\Scripts\python.exe"

$allowedDatabases = @(
    "matchpoint_test",
    "matchpoint_dbt_review_test"
)

if ($testDb -notin $allowedDatabases) {
    throw "Unauthorized test database."
}

if (-not (Test-Path $dbtPython)) {
    throw "Dedicated dbt Python environment not found."
}

if ([string]::IsNullOrWhiteSpace($env:POSTGRES_PASSWORD)) {
    throw "POSTGRES_PASSWORD is required."
}

$env:POSTGRES_HOST = "127.0.0.1"
$env:POSTGRES_PORT = "5432"
$env:POSTGRES_USER = "matchpoint"
$env:POSTGRES_TEST_DB = $testDb
$env:DBT_TARGET = "test"
$env:DBT_SCHEMA = "silver"
$env:DBT_THREADS = "4"
$env:MATCHPOINT_DBT_JIT = "off"

if (-not (Test-Path "dbt/profiles.yml")) {
    Copy-Item dbt/profiles.yml.example dbt/profiles.yml
}

$actualDb = docker compose exec -T postgres `
    psql -X -U matchpoint -d $testDb `
    -v ON_ERROR_STOP=1 `
    -tAc "SELECT current_database();"

if ($LASTEXITCODE -ne 0) {
    throw "Database verification failed."
}

if (($actualDb | Out-String).Trim() -ne $testDb) {
    throw "Unexpected PostgreSQL database."
}

function Invoke-DbtStage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Stage
    )

    $dbtArgs = @(
        $Stage,
        "--profiles-dir", ".",
        "--target", "test",
        "--no-use-colors"
    )

    if ($Stage -in @("parse", "test")) {
        $dbtArgs += "--warn-error"
    }

    & $dbtPython "dbt/run_dbt.py" @dbtArgs

    if ($LASTEXITCODE -ne 0) {
        throw "dbt stage failed: $Stage"
    }
}

function Invoke-IntegrationSql {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Script
    )

    if ($Script -notmatch '^[a-z0-9_]+\.sql$') {
        throw "Invalid SQL script name."
    }

    $source = "dbt/integration_tests/$Script"

    if (-not (Test-Path $source)) {
        throw "SQL script not found: $source"
    }

    $containerId = docker compose ps -q postgres

    if ($LASTEXITCODE -ne 0 -or -not $containerId) {
        throw "PostgreSQL container not found."
    }

    $containerId = ($containerId | Out-String).Trim()

    $remote = "/tmp/matchpoint_$([guid]::NewGuid().ToString('N')).sql"

    try {
        docker cp $source "${containerId}:$remote"

        if ($LASTEXITCODE -ne 0) {
            throw "SQL script copy failed."
        }

        docker compose exec -T postgres env `
            "PGOPTIONS=-c matchpoint.expected_test_database=$testDb" `
            psql -X -U matchpoint -d $testDb `
            -v ON_ERROR_STOP=1 `
            -f $remote

        if ($LASTEXITCODE -ne 0) {
            throw "Integration SQL failed: $Script"
        }
    }
    finally {
        docker compose exec -T postgres rm -f $remote

        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Container SQL cleanup failed."
        }
    }
}
```

SQL files are copied into the PostgreSQL container rather
than streamed through the PowerShell text pipeline.

This preserves the original UTF-8 fixture bytes, including
Arabic source data.

The helpers stop execution on non-zero dbt or SQL exit codes.

They are intended for a dedicated integration test session.

---

## 6. Recommended Execution Sequence

Start with a fresh isolated database.

Do not execute the following stages against an existing
populated review database without resetting or provisioning
a separate test environment.

### Stage 1: Empty Bronze Sanity Check

```powershell
Invoke-DbtStage "debug"
Invoke-DbtStage "parse"
Invoke-DbtStage "seed"
Invoke-DbtStage "run"
Invoke-DbtStage "test"
```

Expected:

- 5 seeds loaded successfully.
- 44 models built successfully.
- 461 dbt tests passed.
- No Bronze source listings.
- No canonical opportunities.
- 8 supported source dimension rows.

Lookup dimensions may contain rows even when Bronze is empty.

### Stage 2: Phase 4 Baseline

```powershell
Invoke-IntegrationSql "load_phase4_synthetic_bronze.sql"

Invoke-DbtStage "run"
Invoke-DbtStage "test"

Invoke-IntegrationSql "verify_phase4_synthetic_results.sql"
```

Expected:

- 41 Bronze source listings.
- 32 canonical opportunities.
- 41 canonical source mappings.
- 9 collection runs.
- 2 Bronze history records.
- All S1-S10 verification groups passed.

### Stage 3: Phase 4 Baseline Idempotency

```powershell
Invoke-IntegrationSql "snapshot_phase4_silver_run1.sql"

Invoke-DbtStage "run"

Invoke-IntegrationSql "verify_phase4_idempotency.sql"
```

Expected:

- No canonical mapping differences.
- No canonical identity differences.
- No primary-source selection differences.
- No match-method differences.
- No canonical-anchor differences.
- Successful removal of the Silver snapshot.

The Silver comparison includes:

- `opportunity_id`
- `source_listing_id`
- `is_primary_source`
- `match_method`
- `canonical_anchor_key`

Both comparison directions use `EXCEPT ALL`.

### Stage 4: Gold Baseline Enrichment

```powershell
Invoke-IntegrationSql "load_phase5_gold_skills_categories_enrichment.sql"

Invoke-DbtStage "run"
Invoke-DbtStage "test"

Invoke-IntegrationSql "verify_phase4_synthetic_results.sql"

Invoke-IntegrationSql "verify_phase5_gold_results.sql"
```

Expected:

- 41 Bronze source listings.
- 32 canonical opportunities.
- 1 invalid record.
- All S1-S10 verification groups passed.
- All G1-G6 verification groups passed.

### Stage 5: Expanded Edge Cases

```powershell
Invoke-IntegrationSql "load_phase5_edge_cases_synthetic.sql"

Invoke-DbtStage "run"
Invoke-DbtStage "test"

Invoke-IntegrationSql "verify_phase5_edge_cases.sql"
```

Expected:

- 52 Bronze source listings.
- 43 canonical opportunities.
- 52 canonical source mappings.
- 12 collection runs.
- 1 invalid record.
- All EC1-EC11 verification groups passed.

EC1 and EC2 may appear together in a single SQL notice.

Do not run the exact-count Phase 4 baseline verifier
against this expanded dataset.

A dedicated baseline-subset comparison is required
to establish that appending edge cases preserves every
previous baseline canonical mapping.

That cross-stage assertion is not established by the
same-dataset idempotency checks alone.

### Stage 6: Expanded Warehouse Idempotency

Run this stage without changing Bronze data or seeds.

```powershell
Invoke-IntegrationSql "snapshot_phase4_silver_run1.sql"

Invoke-IntegrationSql "snapshot_phase5_gold_run1.sql"

Invoke-DbtStage "run"
Invoke-DbtStage "test"

Invoke-IntegrationSql "verify_phase4_idempotency.sql"

Invoke-IntegrationSql "verify_phase5_gold_idempotency.sql"
```

Expected:

- No Silver canonical mapping differences.
- No Gold schema differences.
- No Gold row-count differences.
- No Gold row-content differences.
- All 20 Gold model comparisons passed.
- Successful removal of all verification snapshots.

The complete sequence above is the recommended regression
workflow. Individual stages were independently validated,
but this exact revised sequence has not been rerun as a
single uninterrupted workflow.

---

## 7. Idempotency Semantics and Limitations

Warehouse transformation idempotency means that repeated
warehouse builds over unchanged inputs produce equivalent
outputs under equivalent evaluation conditions.

The comparison must preserve duplicate-row multiplicity.

The following are separate acceptance scenarios:

1. Rebuilding unchanged Bronze data.
2. Retrying the same logical ingestion run.
3. Collecting unchanged content in a new ingestion run.
4. Collecting changed opportunity content.
5. Reopening a previously closed opportunity.
6. Rebuilding after a lifecycle deadline has passed.

Only the first scenario is established by the current
warehouse snapshot comparisons.

A new collection run may legitimately change:

- Collection-run telemetry.
- Observation timestamps.
- Last-seen metadata.
- Source freshness metrics.

The passage of time may legitimately change effective
opportunity lifecycle status even when Bronze is unchanged.

Excluding `lifecycle_evaluated_at` does not freeze the
effective lifecycle evaluation time.

Deterministic clock-controlled lifecycle testing remains
a pending acceptance requirement.

---

## 8. Safety and Negative Testing

The independent review verified rejection of:

- Missing database authorization.
- Unauthorized database names.
- Mismatched database authorization.
- Missing baseline fixtures.
- Missing Gold enrichment fixtures.
- Missing expanded edge-case fixtures.
- Attempts to overwrite existing Gold snapshots.

The original six mutating scripts were subjected to
18 database-authorization negative checks.

All 18 checks passed.

The new Silver snapshot script uses the same explicit
database-authorization pattern.

Its complete independent negative-test matrix remains pending.

The Gold overwrite-rejection check confirmed that all
20 existing snapshot tables retained their original
identities, row counts, and content fingerprints.

Additional deliberate schema-drift and duplicate-multiplicity
failure-injection tests remain pending.

---

## 9. Independent Review Evidence

The original Phase 4 and Phase 5 implementation results
remain historical evidence.

The independent review used:

- Python 3.12.10.
- dbt-core 1.12.7.
- dbt-postgres 1.11.0.
- PostgreSQL 16.
- `matchpoint_dbt_review_test`.

Verified review results:

| Validation | Result |
|---|---|
| Generic test syntax migration | 108 declarations |
| Generic test semantic comparison | No differences |
| Empty Bronze dbt model build | 44 successful models |
| Empty Bronze dbt quality gate | 461 passed |
| Phase 4 baseline | 41 listings, 32 opportunities |
| Phase 4 verification | S1-S10 passed |
| Phase 4 baseline idempotency | No mapping differences |
| Gold baseline verification | G1-G6 passed |
| Expanded edge-case dataset | 52 listings, 43 opportunities |
| Edge-case verification | EC1-EC11 passed |
| Gold idempotency | 20 models passed |
| Database authorization negative checks | 18 passed |
| Runner functional checks | 8 passed |
| Final regression quality gate | 461 passed |

The independent review strengthened:

- Database authorization.
- Fixture preconditions.
- NULL-safe assertions.
- Duplicate-sensitive comparisons.
- Snapshot overwrite protection.
- Gold schema comparison.
- Dependency version compatibility.
- Process-scoped JIT configuration.

Synthetic fixtures intentionally contain controlled
inconsistencies for testing analytical anomaly detection.

They are not equivalent to complete records produced by
the future persistent ingestion pipeline.

---

## 10. Index and Query-Plan Validation

The original implementation declared 33 PostgreSQL indexes
across 13 Gold dimensions, facts, and bridges.

Historical validation checked index presence through
`pg_indexes` and representative query plans using:

```sql
SET enable_seqscan = off;
```

This establishes index eligibility and predicate compatibility.

It does not prove that PostgreSQL's default cost-based
planner will prefer those indexes under realistic workloads.

### Independent JIT Investigation

The independent review measured the recursive deduplication
query using the expanded 52-listing synthetic dataset.

| Configuration | Planning + Execution |
|---|---:|
| JIT enabled | 11685.087 ms |
| JIT disabled | 57.305 ms |

The observed overhead was dominated by JIT compilation.

The standard runner now defaults to:

```text
MATCHPOINT_DBT_JIT=off
```

Server-wide PostgreSQL settings remain unchanged.

Production-scale recursive matching performance,
memory consumption, index selection, and concurrent
workload behavior remain pending validation.

---

## 11. Remaining Acceptance Requirements

- Persistent Python Bronze ingestion.
- Real collected data from all eight supported sources.
- Complete collection-run telemetry.
- Same-run ingestion retry idempotency.
- Observation ledger validation.
- Content-change history validation.
- Cross-stage baseline mapping preservation.
- Lifecycle reopening and time-controlled expiration.
- Incremental checkpoint persistence and recovery.
- Production-scale performance testing.
- Linux and Airflow runner validation.
- Workflow-level concurrency protection.
- ClickHouse extraction and publication validation.
- CI/CD execution.
- Production database permission provisioning.

The synthetic integration suite validates warehouse
transformation behavior under controlled conditions.

It does not establish complete end-to-end acceptance
or production readiness.