SELECT
    opportunity_id,
    source_listing_id,
    source_name,
    source_opportunity_id,
    source_identity_key,
    source_url,
    external_application_url_raw,
    canonical_anchor_key,
    match_method,
    match_evidence,
    is_primary_source,
    source_authority_rank,
    completeness_score,
    observed_status,
    effective_status,
    first_seen_at,
    last_seen_at,
    content_hash,
    content_version,
    last_collection_run_id

FROM {{ ref('int_opportunity_clusters') }}
