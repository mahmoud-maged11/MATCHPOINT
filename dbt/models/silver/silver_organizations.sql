SELECT
    organization_key,
    MIN(organization) AS organization_name,
    BOOL_OR(is_organization_alias_mapped) AS is_alias_mapped,
    JSONB_AGG(DISTINCT organization_raw ORDER BY organization_raw)
        FILTER (WHERE organization_raw IS NOT NULL) AS observed_raw_names,
    COUNT(*) AS source_listing_count

FROM {{ ref('silver_source_listings') }}
WHERE organization_key IS NOT NULL
GROUP BY organization_key
