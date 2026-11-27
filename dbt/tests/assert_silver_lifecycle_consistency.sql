-- Fails if any Silver listing violates ADR-018 and ADR-047 lifecycle invariants:
-- 1. Explicit Bronze 'closed' or 'expired' must take precedence in effective_status.
-- 2. Observed 'unknown' must NEVER be promoted to 'active' (e.g. from a future deadline).
-- 3. Missing, relative, or unknown-precision deadlines must NEVER trigger automatic expiration.
-- 4. effective_status = 'closed' is allowed ONLY when observed_status = 'closed' (never inferred from absence).

SELECT
    source_listing_id,
    source_name,
    observed_status,
    effective_status,
    effective_status_reason,
    deadline,
    deadline_precision
FROM {{ ref('silver_source_listings') }}
WHERE
    -- Rule 1: Explicit closed/expired precedence
    (observed_status IN ('closed', 'expired') AND effective_status <> observed_status)

    -- Rule 2: Unknown cannot become active
    OR (observed_status = 'unknown' AND effective_status = 'active')

    -- Rule 3: Missing or uncertain deadline precision cannot auto-expire
    OR (
        observed_status IN ('active', 'unknown')
        AND (deadline IS NULL OR deadline_precision IS NULL OR deadline_precision IN ('relative', 'unknown'))
        AND effective_status <> observed_status
    )

    -- Rule 4: Closure can never be inferred when Bronze observed_status is not closed
    OR (effective_status = 'closed' AND observed_status <> 'closed')
