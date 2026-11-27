{{
    config(
        indexes=[
            {'columns': ['source_listing_id'], 'unique': True},
            {'columns': ['opportunity_id']},
            {'columns': ['source_name']}
        ]
    )
}}

SELECT
    os.source_listing_id,
    os.opportunity_id,
    os.source_name,
    os.source_opportunity_id,
    os.source_identity_key,
    os.source_url,
    os.external_application_url_raw,
    os.canonical_anchor_key,
    os.match_method,
    os.match_evidence,
    os.is_primary_source,
    os.source_authority_rank,
    os.completeness_score,
    sl.title AS source_title,
    sl.organization AS source_organization,
    sl.opportunity_type AS source_opportunity_type,
    sl.location_display AS source_location_display,
    os.observed_status,
    os.effective_status,
    os.first_seen_at,
    os.last_seen_at,
    os.content_hash,
    os.content_version,
    os.last_collection_run_id

FROM {{ ref('silver_opportunity_sources') }} os
INNER JOIN {{ ref('silver_source_listings') }} sl
    ON os.source_listing_id = sl.source_listing_id
