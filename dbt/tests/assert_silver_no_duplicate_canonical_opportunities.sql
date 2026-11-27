-- Fails if any verified cross-source match pair in int_opportunity_match_pairs was NOT converged
-- into the same canonical opportunity_id, EXCEPT when the component was explicitly split by
-- component-level transitive conflict protection ('singleton_transitive_conflict' or 'tier1_fallback').

SELECT
    p.listing_id_low,
    p.listing_id_high,
    p.match_tier,
    p.match_method,
    os_low.opportunity_id AS opportunity_id_low,
    os_high.opportunity_id AS opportunity_id_high,
    os_low.match_method AS low_resolved_method,
    os_high.match_method AS high_resolved_method
FROM {{ ref('int_opportunity_match_pairs') }} p
INNER JOIN {{ ref('silver_opportunity_sources') }} os_low
    ON p.listing_id_low = os_low.source_listing_id
INNER JOIN {{ ref('silver_opportunity_sources') }} os_high
    ON p.listing_id_high = os_high.source_listing_id
WHERE os_low.opportunity_id <> os_high.opportunity_id
  -- Only Tier 2 edges dropped during tier1_fallback OR edges rejected by transitive conflict may stay unmerged
  AND NOT (
      os_low.match_method = 'singleton_transitive_conflict'
      OR os_high.match_method = 'singleton_transitive_conflict'
      OR (
          p.match_tier = 3
          AND (
              (os_low.match_evidence ->> 'resolution_mode') = 'tier1_fallback'
              OR (os_high.match_evidence ->> 'resolution_mode') = 'tier1_fallback'
          )
      )
  )
