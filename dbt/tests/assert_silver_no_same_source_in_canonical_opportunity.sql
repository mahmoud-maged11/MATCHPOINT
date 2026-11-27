-- Fails if any canonical opportunity contains more than one listing from the same source_name.
-- Enforces ADR-042 and Data Contract v3.0.0 §5.12 across the entire connected component, not just direct edges.

SELECT
    opportunity_id,
    source_name,
    COUNT(*) AS listings_from_same_source
FROM {{ ref('silver_opportunity_sources') }}
GROUP BY
    opportunity_id,
    source_name
HAVING COUNT(*) > 1
