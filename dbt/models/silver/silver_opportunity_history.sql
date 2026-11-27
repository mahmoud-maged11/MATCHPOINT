SELECT
    lh.history_id,
    os.opportunity_id,
    lh.source_listing_id,
    lh.source_name,
    os.is_primary_source,
    os.match_method,
    lh.content_version,
    lh.content_hash,
    lh.hash_version,
    lh.contract_version,
    lh.collection_run_id,
    lh.collection_scope,
    lh.collection_mode,
    lh.standardized_payload,
    lh.observed_at,
    lh.created_at

FROM {{ ref('silver_listing_history') }} lh
INNER JOIN {{ ref('silver_opportunity_sources') }} os
    ON lh.source_listing_id = os.source_listing_id
