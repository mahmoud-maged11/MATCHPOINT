# MATCHPOINT - Ingestion Recovery Policy

## Status

Recovery behavior validated through integration tests.

Automatic retry orchestration remains pending.

## Retry Policy

- Maximum attempts: 3, including the initial attempt.
- Backoff: 1 second, then 2 seconds.
- Use a fresh database connection for each retry.
- Preserve the original run ID and observation payload.
- Preserve the original collected_at timestamp.
- Do not retry permanent errors automatically.
- Classify database errors using SQLSTATE where available.
- Do not retry every OperationalError indiscriminately.

## Retryable Failures

- Transient database connection failures.
- Deadlock detected: SQLSTATE 40P01.
- Serialization failure: SQLSTATE 40001.
- Lock not available: SQLSTATE 55P03.

## Non-Retryable Failures

- Authentication and authorization failures.
- Invalid source identity.
- Validation failures.
- Programming errors.
- Unexpected integrity constraint violations.

Validation and identity failures should be persisted
as sanitized invalid records when possible.

Unexpected database errors must not be silently
classified as invalid source data.

## Run Recovery

Running runs may be resumed using their original
run ID and original observation payloads, provided
exclusive recovery ownership is established.

Finalized runs must not be reopened.

Partial, failed and aborted runs require a new
logical collection run for further processing.

Completed runs retain their persisted results.

## Unknown Commit Outcome

If a write may have committed before connection loss,
retry the original observation with the same run ID.

The observation ledger prevents duplicate persistence.

For uncertain finalization outcomes, retrieve the
stored collection run and verify its terminal status
and counters before deciding whether to retry.

## Transaction Guarantees

Current listing, content history and observation
ledger writes must remain atomic.

Conflict evidence must be persisted atomically
with its associated ingestion outcome.

A failed transaction must not advance a checkpoint.

## Validated Recovery Scenarios

- Committed insert with lost acknowledgement.
- Committed update with lost acknowledgement.
- Committed rejection with lost acknowledgement.
- Committed finalization with lost acknowledgement.
- Interrupted running collection.
- Recovery after partial finalization.
- Backend termination after history insertion.
- Backend termination after history update.
- Backend termination after observation insertion.

## Validation Results

Recovery integration tests: 9 passed.

Database: matchpoint_ingestion_test.

PostgreSQL backend termination was tested against
individual test connections only.

All six Bronze tables were empty after test cleanup.

## Remaining Implementation

- Automatic retry orchestration.
- Durable preservation of original collection payloads.
- Recovery ownership and abandoned run detection.
- Recovery run lineage.
- Atomic checkpoint advancement.
- Airflow retry integration.
- Full server restart and disaster recovery testing.

## Limitations

Lost acknowledgement was simulated after successful
commit, not through a real network interruption.

Backend termination tests covered failures before commit.

Recovery tests do not establish production availability
or disaster recovery guarantees.
