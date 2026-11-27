-- Fails if matching evidence or match_method consistency is violated:
-- 1. Every silver_opportunity_sources row must have a JSONB object match_evidence with a non-empty 'rule' matching match_method.
-- 2. Merged opportunities (source_count > 1) must not be labeled 'singleton*'.
-- 3. Singletons (source_count = 1) must be labeled 'singleton', 'singleton_ambiguous_composite', or 'singleton_transitive_conflict'.
-- 4. Direct match pairs in int_opportunity_match_pairs must never join two listings from the same source.

WITH evidence_checks AS (
    SELECT
        os.source_listing_id::TEXT AS offending_id,
        'invalid_match_evidence_or_method'::TEXT AS failure_reason
    FROM {{ ref('silver_opportunity_sources') }} os
    INNER JOIN {{ ref('silver_opportunities') }} o
        ON os.opportunity_id = o.opportunity_id
    WHERE JSONB_TYPEOF(os.match_evidence) <> 'object'
       OR NULLIF(BTRIM(os.match_evidence ->> 'rule'), '') IS NULL
       OR (os.match_evidence ->> 'rule') <> os.match_method
       OR (
           o.source_count > 1
           AND os.match_method IN ('singleton', 'singleton_ambiguous_composite', 'singleton_transitive_conflict')
       )
       OR (
           o.source_count = 1
           AND os.match_method NOT IN ('singleton', 'singleton_ambiguous_composite', 'singleton_transitive_conflict')
       )
),

same_source_pair_checks AS (
    SELECT
        p.listing_id_low::TEXT || ' <-> ' || p.listing_id_high::TEXT AS offending_id,
        'same_source_direct_match_pair'::TEXT AS failure_reason
    FROM {{ ref('int_opportunity_match_pairs') }} p
    INNER JOIN {{ ref('silver_source_listings') }} a
        ON p.listing_id_low = a.source_listing_id
    INNER JOIN {{ ref('silver_source_listings') }} b
        ON p.listing_id_high = b.source_listing_id
    WHERE a.source_name = b.source_name
)

SELECT * FROM evidence_checks
UNION ALL
SELECT * FROM same_source_pair_checks
