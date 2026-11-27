-- Production clustering model.
-- Shared implementation is also exercised by synthetic tests.

{{ resolve_opportunity_clusters(
    ref('int_listing_match_features'),
    ref('int_opportunity_match_pairs')
) }}
