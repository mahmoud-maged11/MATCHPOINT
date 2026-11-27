WITH f AS (
    SELECT *
    FROM {{ ref('int_listing_match_features') }}
),

-- Tier 1A: Direct verified cross-source URL / source-ID reference (ADR-026)
-- Example: An Egyincs listing whose verified application_url points directly to a Wuzzuf/Bayt/UNV listing
-- or directly equals another source's specific source_url.
tier1a_direct_url AS (
    SELECT
        LEAST(a.source_listing_id::TEXT, b.source_listing_id::TEXT)::UUID AS listing_id_low,
        GREATEST(a.source_listing_id::TEXT, b.source_listing_id::TEXT)::UUID AS listing_id_high,
        b.source_listing_id AS direct_url_target_listing_id,
        1 AS match_tier,
        'direct_cross_source_url'::TEXT AS match_method,
        JSONB_BUILD_OBJECT(
            'rule', 'direct_cross_source_url',
            'tier', 1,
            'pointer_listing_id', a.source_listing_id::TEXT,
            'pointer_source', a.source_name,
            'target_listing_id', b.source_listing_id::TEXT,
            'target_source', b.source_name,
            'matched_on_source_id', (
                a.referenced_source_name = b.source_name
                AND a.referenced_source_opportunity_id = b.source_opportunity_id
            ),
            'matched_on_normalized_url', (
                a.external_application_url_verified = b.source_url_normalized
            ),
            'verified_application_url', a.external_application_url_verified
        ) AS pair_evidence
    FROM f a
    INNER JOIN f b
        ON a.source_name <> b.source_name
       AND a.external_application_url_verified IS NOT NULL
       AND (
           (
               a.referenced_source_name = b.source_name
               AND a.referenced_source_opportunity_id IS NOT NULL
               AND a.referenced_source_opportunity_id = b.source_opportunity_id
           )
           OR (
               a.external_application_url_verified = b.source_url_normalized
           )
       )
),

-- Tier 1B: Shared specific external application URL across two different sources (ADR-026)
-- Requires non-generic deep URL + same opportunity_type + non-conflicting organizations (when both known).
tier1b_shared_url AS (
    SELECT
        a.source_listing_id AS listing_id_low,
        b.source_listing_id AS listing_id_high,
        NULL::UUID AS direct_url_target_listing_id,
        2 AS match_tier,
        'shared_external_application_url'::TEXT AS match_method,
        JSONB_BUILD_OBJECT(
            'rule', 'shared_external_application_url',
            'tier', 1,
            'shared_application_url', a.external_application_url_verified,
            'opportunity_type', a.opportunity_type,
            'organization_consistent', (
                a.organization_key IS NULL
                OR b.organization_key IS NULL
                OR a.organization_key = b.organization_key
            )
        ) AS pair_evidence
    FROM f a
    INNER JOIN f b
        ON a.source_listing_id::TEXT < b.source_listing_id::TEXT
       AND a.source_name <> b.source_name
       AND a.external_application_url_verified IS NOT NULL
       AND a.external_application_url_verified = b.external_application_url_verified
       AND a.opportunity_type = b.opportunity_type
       AND (
           a.organization_key IS NULL
           OR b.organization_key IS NULL
           OR a.organization_key = b.organization_key
       )
),

-- Tier 2: Conservative multi-signal structured composite match (ADR-004)
-- Requires ALL of:
--   1. Different sources (never auto-merge distinct IDs within the same source)
--   2. Non-null normalized title (len >= 4) + non-null organization_key + exact opportunity_type + non-null city/gov/remote signal
--   3. Non-ambiguous within each source (count = 1 per source for this tuple)
--   4. Compatible work_modes (not mutually exclusive on_site vs remote when both populated)
--   5. Temporal compatibility (published_at <= 45d when both reliable; deadline <= 14d when both reliable;
--      otherwise first_seen_at <= 45d guard)
tier2_composite AS (
    SELECT
        a.source_listing_id AS listing_id_low,
        b.source_listing_id AS listing_id_high,
        NULL::UUID AS direct_url_target_listing_id,
        3 AS match_tier,
        'multi_signal_composite'::TEXT AS match_method,
        JSONB_BUILD_OBJECT(
            'rule', 'multi_signal_composite',
            'tier', 2,
            'matched_signals', JSONB_BUILD_ARRAY(
                'normalized_title',
                'normalized_organization',
                'opportunity_type',
                'location_or_remote_signal',
                'work_mode_compatibility',
                'temporal_window'
            ),
            'title_match_key', a.title_match_key,
            'organization_key', a.organization_key,
            'opportunity_type', a.opportunity_type,
            'location_match_signal', a.location_match_signal,
            'temporal_basis', CASE
                WHEN a.published_at IS NOT NULL
                    AND a.published_at_precision IN ('exact', 'date_only')
                    AND b.published_at IS NOT NULL
                    AND b.published_at_precision IN ('exact', 'date_only') THEN 'published_at_within_45d'
                WHEN a.deadline IS NOT NULL
                    AND a.deadline_precision IN ('exact', 'date_only')
                    AND b.deadline IS NOT NULL
                    AND b.deadline_precision IN ('exact', 'date_only') THEN 'deadline_within_14d'
                ELSE 'first_seen_at_within_45d'
            END
        ) AS pair_evidence
    FROM f a
    INNER JOIN f b
        ON a.source_listing_id::TEXT < b.source_listing_id::TEXT
       AND a.source_name <> b.source_name
       AND a.is_tier2_eligible
       AND b.is_tier2_eligible
       AND NOT a.is_composite_ambiguous_within_source
       AND NOT b.is_composite_ambiguous_within_source
       AND a.title_match_key = b.title_match_key
       AND a.organization_key = b.organization_key
       AND a.opportunity_type = b.opportunity_type
       AND a.location_match_signal = b.location_match_signal
       -- Work mode compatibility guard: if both have known non-unknown work_modes, require at least one overlap
       AND (
           a.work_modes IS NULL
           OR b.work_modes IS NULL
           OR JSONB_ARRAY_LENGTH(a.work_modes) = 0
           OR JSONB_ARRAY_LENGTH(b.work_modes) = 0
           OR a.work_modes ? 'unknown'
           OR b.work_modes ? 'unknown'
           OR EXISTS (
               SELECT 1
               FROM JSONB_ARRAY_ELEMENTS_TEXT(a.work_modes) wa(val)
               INNER JOIN JSONB_ARRAY_ELEMENTS_TEXT(b.work_modes) wb(val)
                   ON wa.val = wb.val
           )
       )
       -- Reliable publication date compatibility guard (when both reliable)
       AND (
           NOT (
               a.published_at IS NOT NULL
               AND a.published_at_precision IN ('exact', 'date_only')
               AND b.published_at IS NOT NULL
               AND b.published_at_precision IN ('exact', 'date_only')
           )
           OR ABS(EXTRACT(EPOCH FROM (a.published_at - b.published_at))) <= (45 * 86400)
       )
       -- Reliable deadline compatibility guard (when both reliable)
       AND (
           NOT (
               a.deadline IS NOT NULL
               AND a.deadline_precision IN ('exact', 'date_only')
               AND b.deadline IS NOT NULL
               AND b.deadline_precision IN ('exact', 'date_only')
           )
           OR ABS(EXTRACT(EPOCH FROM (a.deadline - b.deadline))) <= (14 * 86400)
       )
       -- Fallback observation recency guard when neither reliable published_at nor reliable deadline is shared
       AND (
           (
               a.published_at IS NOT NULL
               AND a.published_at_precision IN ('exact', 'date_only')
               AND b.published_at IS NOT NULL
               AND b.published_at_precision IN ('exact', 'date_only')
           )
           OR (
               a.deadline IS NOT NULL
               AND a.deadline_precision IN ('exact', 'date_only')
               AND b.deadline IS NOT NULL
               AND b.deadline_precision IN ('exact', 'date_only')
           )
           OR ABS(EXTRACT(EPOCH FROM (a.first_seen_at - b.first_seen_at))) <= (45 * 86400)
       )
),

all_pairs AS (
    SELECT * FROM tier1a_direct_url
    UNION ALL
    SELECT * FROM tier1b_shared_url
    UNION ALL
    SELECT * FROM tier2_composite
),

ranked_pairs AS (
    SELECT
        listing_id_low,
        listing_id_high,
        direct_url_target_listing_id,
        match_tier,
        match_method,
        pair_evidence,
        ROW_NUMBER() OVER (
            PARTITION BY listing_id_low, listing_id_high
            ORDER BY match_tier ASC, match_method ASC, direct_url_target_listing_id::TEXT ASC NULLS LAST
        ) AS rn
    FROM all_pairs
)

SELECT
    listing_id_low,
    listing_id_high,
    direct_url_target_listing_id,
    match_tier,
    match_method,
    pair_evidence
FROM ranked_pairs
WHERE rn = 1
