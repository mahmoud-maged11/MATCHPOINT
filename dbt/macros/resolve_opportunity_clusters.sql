{% macro resolve_opportunity_clusters(features_relation, pairs_relation) -%}
WITH RECURSIVE features AS (
    SELECT *
    FROM {{ features_relation }}
),

pairs AS (
    SELECT *
    FROM {{ pairs_relation }}
),

-- Symmetric undirected edge list for all verified cross-source pairs
undirected_edges AS (
    SELECT
        listing_id_low AS from_id,
        listing_id_high AS to_id,
        match_tier,
        match_method,
        pair_evidence
    FROM pairs
    UNION ALL
    SELECT
        listing_id_high AS from_id,
        listing_id_low AS to_id,
        match_tier,
        match_method,
        pair_evidence
    FROM pairs
),

-- Fix 3: PostgreSQL 16 set-deduplicating UNION connected components (no exponential path enumeration,
-- automatic cycle termination, and no artificial depth-8 truncation).
full_reachability(start_id, current_id) AS (
    SELECT
        f.source_listing_id AS start_id,
        f.source_listing_id AS current_id
    FROM features f

    UNION

    SELECT
        r.start_id,
        e.to_id AS current_id
    FROM full_reachability r
    INNER JOIN undirected_edges e
        ON r.current_id = e.from_id
),

full_components AS (
    SELECT
        start_id AS source_listing_id,
        MIN(current_id::TEXT) AS raw_component_key,
        COUNT(*) AS raw_component_size
    FROM full_reachability
    GROUP BY start_id
),

-- Fix 2: Validate component-wide invariants across every full connected component:
-- 1. No canonical component may contain multiple listings from the same source_name.
-- 2. All components must have compatible known organization,
--    opportunity type and standardized geographic evidence.
-- 3. For components containing Tier 2 edges:
--    a) Reliable published_at span across the component must not exceed 45 days.
--    b) Reliable deadline span across the component must not exceed 14 days.
--    c) Component must not combine mutually exclusive known work_modes (e.g. exclusively on_site + exclusively remote).
full_component_tier2_flag AS (
    SELECT DISTINCT
        fc.raw_component_key,
        TRUE AS has_tier2_edge
    FROM full_components fc
    INNER JOIN undirected_edges e
        ON fc.source_listing_id = e.from_id
    WHERE e.match_tier = 3
),

full_component_validation AS (
    SELECT
        fc.raw_component_key,
        COUNT(*) AS member_count,
        COUNT(DISTINCT f.source_name) AS distinct_source_count,
        (COUNT(DISTINCT f.source_name) < COUNT(*)) AS violates_same_source,
        COALESCE(BOOL_OR(t2.has_tier2_edge), FALSE) AS has_tier2_edge,
        (
            COALESCE(BOOL_OR(t2.has_tier2_edge), FALSE)
            AND {{ temporal_component_exceeds_window(
                'f.published_at',
                'f.published_calendar_date',
                'f.published_at_precision',
                45
            ) }}
        ) AS violates_published_span,
        (
            COALESCE(BOOL_OR(t2.has_tier2_edge), FALSE)
            AND {{ temporal_component_exceeds_window(
                'f.deadline',
                'f.deadline_calendar_date',
                'f.deadline_precision',
                14
            ) }}
        ) AS violates_deadline_span,
        (
            COALESCE(BOOL_OR(t2.has_tier2_edge), FALSE)
            AND EXISTS (
                SELECT 1
                FROM full_components fc1
                INNER JOIN features f1
                    ON fc1.source_listing_id = f1.source_listing_id
                INNER JOIN full_components fc2
                    ON fc2.raw_component_key = fc1.raw_component_key
                   AND fc1.source_listing_id::TEXT < fc2.source_listing_id::TEXT
                INNER JOIN features f2
                    ON fc2.source_listing_id = f2.source_listing_id
                WHERE fc1.raw_component_key = fc.raw_component_key
                  AND f1.work_modes IS NOT NULL
                  AND f2.work_modes IS NOT NULL
                  AND JSONB_ARRAY_LENGTH(f1.work_modes) > 0
                  AND JSONB_ARRAY_LENGTH(f2.work_modes) > 0
                  AND NOT (f1.work_modes ? 'unknown')
                  AND NOT (f2.work_modes ? 'unknown')
                  AND NOT EXISTS (
                      SELECT 1
                      FROM JSONB_ARRAY_ELEMENTS_TEXT(f1.work_modes) w1(val)
                      INNER JOIN JSONB_ARRAY_ELEMENTS_TEXT(f2.work_modes) w2(val)
                          ON w1.val = w2.val
                  )
            )
        ) AS violates_work_mode_consistency,
        (
            COUNT(DISTINCT NULLIF(
                BTRIM(f.organization_key), ''
            )) > 1
        ) AS violates_organization_consistency,
        (
            COUNT(DISTINCT f.opportunity_type) > 1
        ) AS violates_opportunity_type_consistency,
        (
            COUNT(DISTINCT LOWER(f.standardized_city))
                FILTER (
                    WHERE f.is_location_standardized
                ) > 1

            OR COUNT(DISTINCT LOWER(f.standardized_governorate))
                FILTER (
                    WHERE f.is_location_standardized
                ) > 1

            OR COUNT(DISTINCT UPPER(f.country_code))
                FILTER (
                    WHERE f.is_location_standardized
                ) > 1
        ) AS violates_geographic_consistency
    FROM full_components fc
    INNER JOIN features f
        ON fc.source_listing_id = f.source_listing_id
    LEFT JOIN full_component_tier2_flag t2
        ON fc.raw_component_key = t2.raw_component_key
    GROUP BY fc.raw_component_key
),

full_component_status AS (
    SELECT
        raw_component_key,
        violates_same_source,
        violates_published_span,
        violates_deadline_span,
        violates_work_mode_consistency,
        violates_organization_consistency,
        violates_opportunity_type_consistency,
        violates_geographic_consistency,
        (
            violates_same_source
            OR violates_published_span
            OR violates_deadline_span
            OR violates_work_mode_consistency
            OR violates_organization_consistency
            OR violates_opportunity_type_consistency
            OR violates_geographic_consistency
        ) AS is_full_component_invalid
    FROM full_component_validation
),

-- Fallback for invalid full components: re-evaluate using Tier 1 (URL) edges ONLY so valid Tier 1
-- links are not lost when a Tier 2 transitive edge caused the conflict.
tier1_edges AS (
    SELECT
        from_id,
        to_id,
        match_tier,
        match_method,
        pair_evidence
    FROM undirected_edges
    WHERE match_tier IN (1, 2)
),

tier1_reachability(start_id, current_id) AS (
    SELECT
        f.source_listing_id AS start_id,
        f.source_listing_id AS current_id
    FROM features f

    UNION

    SELECT
        r.start_id,
        e.to_id AS current_id
    FROM tier1_reachability r
    INNER JOIN tier1_edges e
        ON r.current_id = e.from_id
),

tier1_components AS (
    SELECT
        start_id AS source_listing_id,
        MIN(current_id::TEXT) AS t1_component_key,
        COUNT(*) AS t1_component_size
    FROM tier1_reachability
    GROUP BY start_id
),

tier1_component_validation AS (
    SELECT
        t1.t1_component_key,
        (COUNT(DISTINCT f.source_name) < COUNT(*))
            AS t1_violates_same_source,
        (
            COUNT(DISTINCT NULLIF(
                BTRIM(f.organization_key), ''
            )) > 1
        ) AS t1_violates_organization_consistency,
        (
            COUNT(DISTINCT f.opportunity_type) > 1
        ) AS t1_violates_opportunity_type_consistency,
        (
            COUNT(DISTINCT LOWER(f.standardized_city))
                FILTER (
                    WHERE f.is_location_standardized
                ) > 1

            OR COUNT(DISTINCT LOWER(f.standardized_governorate))
                FILTER (
                    WHERE f.is_location_standardized
                ) > 1

            OR COUNT(DISTINCT UPPER(f.country_code))
                FILTER (
                    WHERE f.is_location_standardized
                ) > 1
        ) AS t1_violates_geographic_consistency
    FROM tier1_components t1
    INNER JOIN features f
        ON t1.source_listing_id = f.source_listing_id
    GROUP BY t1.t1_component_key
),

tier1_component_status AS (
    SELECT
        *,
        (
            t1_violates_same_source
            OR t1_violates_organization_consistency
            OR t1_violates_opportunity_type_consistency
            OR t1_violates_geographic_consistency
        ) AS is_tier1_component_invalid
    FROM tier1_component_validation
),

-- Resolve final conservative component assignment per listing:
-- 1. If full component is valid -> keep full component.
-- 2. Else if Tier 1-only component is valid and has size > 1 -> keep Tier 1 component.
-- 3. Else -> retain listing conservatively as an isolated singleton with 'singleton_transitive_conflict'.
resolved_assignments AS (
    SELECT
        f.source_listing_id,
        CASE
            WHEN NOT fcs.is_full_component_invalid THEN 'full:' || fc.raw_component_key
            WHEN NOT t1v.is_tier1_component_invalid AND t1c.t1_component_size > 1 THEN 't1:' || t1c.t1_component_key
            ELSE 'conflict_singleton:' || f.source_listing_id::TEXT
        END AS component_group_key,
        CASE
            WHEN NOT fcs.is_full_component_invalid THEN 'full'
            WHEN NOT t1v.is_tier1_component_invalid AND t1c.t1_component_size > 1 THEN 'tier1_fallback'
            ELSE 'conflict_singleton'
        END AS resolution_mode,
        fcs.violates_same_source,
        fcs.violates_published_span,
        fcs.violates_deadline_span,
        fcs.violates_work_mode_consistency,
        fcs.violates_organization_consistency,
        fcs.violates_opportunity_type_consistency,
        fcs.violates_geographic_consistency,
        t1v.t1_violates_same_source,
        t1v.t1_violates_organization_consistency,
        t1v.t1_violates_opportunity_type_consistency,
        t1v.t1_violates_geographic_consistency
    FROM features f
    INNER JOIN full_components fc
        ON f.source_listing_id = fc.source_listing_id
    INNER JOIN full_component_status fcs
        ON fc.raw_component_key = fcs.raw_component_key
    INNER JOIN tier1_components t1c
        ON f.source_listing_id = t1c.source_listing_id
    INNER JOIN tier1_component_status t1v
        ON t1c.t1_component_key = t1v.t1_component_key
),

component_sizes AS (
    SELECT
        component_group_key,
        COUNT(*) AS component_size
    FROM resolved_assignments
    GROUP BY component_group_key
),

-- Identify listings that are explicitly targeted by a Tier 1A direct cross-source URL within their FINAL component
direct_url_targets AS (
    SELECT DISTINCT
        p.direct_url_target_listing_id AS source_listing_id
    FROM pairs p
    INNER JOIN resolved_assignments ra_low
        ON p.listing_id_low = ra_low.source_listing_id
    INNER JOIN resolved_assignments ra_high
        ON p.listing_id_high = ra_high.source_listing_id
    WHERE p.direct_url_target_listing_id IS NOT NULL
      AND ra_low.component_group_key = ra_high.component_group_key
),

-- Best supporting match edge WITHIN the listing's final resolved component
listing_best_edge AS (
    SELECT
        e.from_id AS source_listing_id,
        e.match_tier,
        e.match_method,
        e.pair_evidence,
        ROW_NUMBER() OVER (
            PARTITION BY e.from_id
            ORDER BY e.match_tier ASC, e.match_method ASC, e.to_id::TEXT ASC
        ) AS rn
    FROM undirected_edges e
    INNER JOIN resolved_assignments ra_from
        ON e.from_id = ra_from.source_listing_id
    INNER JOIN resolved_assignments ra_to
        ON e.to_id = ra_to.source_listing_id
    WHERE ra_from.component_group_key = ra_to.component_group_key
),

component_enriched AS (
    SELECT
        ra.component_group_key,
        ra.resolution_mode,
        ra.violates_same_source,
        ra.violates_published_span,
        ra.violates_deadline_span,
        ra.violates_work_mode_consistency,
        ra.violates_organization_consistency,
        ra.violates_opportunity_type_consistency,
        ra.violates_geographic_consistency,
        ra.t1_violates_same_source,
        ra.t1_violates_organization_consistency,
        ra.t1_violates_opportunity_type_consistency,
        ra.t1_violates_geographic_consistency,
        cs.component_size,
        f.source_listing_id,
        f.source_name,
        f.source_opportunity_id,
        f.source_identity_key,
        f.source_url,
        f.external_application_url_raw,
        f.source_authority_rank,
        f.completeness_score,
        f.first_seen_at,
        f.last_seen_at,
        f.observed_status,
        f.effective_status,
        f.content_hash,
        f.content_version,
        f.last_collection_run_id,
        f.is_composite_ambiguous_within_source,
        (dt.source_listing_id IS NOT NULL) AS is_direct_url_target,
        lbe.match_method AS edge_match_method,
        lbe.pair_evidence AS edge_pair_evidence
    FROM resolved_assignments ra
    INNER JOIN component_sizes cs
        ON ra.component_group_key = cs.component_group_key
    INNER JOIN features f
        ON ra.source_listing_id = f.source_listing_id
    LEFT JOIN direct_url_targets dt
        ON ra.source_listing_id = dt.source_listing_id
    LEFT JOIN listing_best_edge lbe
        ON ra.source_listing_id = lbe.source_listing_id
       AND lbe.rn = 1
),

-- Fix 5: Deterministic identity anchor strictly ordered by immutable source authority & source identity.
-- Never lets secondary URL pointer flags (is_direct_url_target) override higher source authority.
component_anchors AS (
    SELECT
        component_group_key,
        source_name || ':' || source_identity_key AS canonical_anchor_key,
        ROW_NUMBER() OVER (
            PARTITION BY component_group_key
            ORDER BY
                source_authority_rank ASC,
                source_name ASC,
                source_identity_key ASC
        ) AS anchor_rn
    FROM component_enriched
),

-- Deterministic primary-source ranking per component (source_authority_rank first, then is_direct_url_target)
primary_ranked AS (
    SELECT
        ce.*,
        ca.canonical_anchor_key,
        {{ deterministic_uuid('ca.canonical_anchor_key') }} AS opportunity_id,
        ROW_NUMBER() OVER (
            PARTITION BY ce.component_group_key
            ORDER BY
                ce.source_authority_rank ASC,
                ce.is_direct_url_target DESC,
                ce.completeness_score DESC,
                ce.first_seen_at ASC,
                ce.source_identity_key ASC,
                ce.source_listing_id::TEXT ASC
        ) AS primary_rn
    FROM component_enriched ce
    INNER JOIN component_anchors ca
        ON ce.component_group_key = ca.component_group_key
       AND ca.anchor_rn = 1
)

SELECT
    opportunity_id,
    source_listing_id,
    source_name,
    source_opportunity_id,
    source_identity_key,
    source_url,
    external_application_url_raw,
    canonical_anchor_key,
    component_size,
    (primary_rn = 1) AS is_primary_source,
    source_authority_rank,
    completeness_score,
    CASE
        WHEN component_size > 1 THEN edge_match_method
        WHEN resolution_mode = 'conflict_singleton' THEN 'singleton_transitive_conflict'
        WHEN is_composite_ambiguous_within_source THEN 'singleton_ambiguous_composite'
        ELSE 'singleton'
    END AS match_method,
    CASE
        WHEN component_size > 1 THEN
            edge_pair_evidence || JSONB_BUILD_OBJECT(
                'component_size', component_size,
                'canonical_anchor_key', canonical_anchor_key,
                'is_primary_source', (primary_rn = 1),
                'resolution_mode', resolution_mode
            )
            || CASE
                WHEN resolution_mode = 'tier1_fallback' THEN
                    JSONB_BUILD_OBJECT(
                        'full_component_conflicts',
                        JSONB_BUILD_OBJECT(
                            'same_source', violates_same_source,
                            'published_span', violates_published_span,
                            'deadline_span', violates_deadline_span,
                            'work_mode', violates_work_mode_consistency,
                            'organization', violates_organization_consistency,
                            'opportunity_type', violates_opportunity_type_consistency,
                            'geography', violates_geographic_consistency
                        )
                    )
                ELSE '{}'::JSONB
            END
        WHEN resolution_mode = 'conflict_singleton' THEN
            JSONB_BUILD_OBJECT(
                'rule', 'singleton_transitive_conflict',
                'reason', 'Transitive connected component violated component-wide invariants; retained separately conservatively.',
                'violates_same_source', (violates_same_source OR t1_violates_same_source),
                'violates_published_span', violates_published_span,
                'violates_deadline_span', violates_deadline_span,
                'violates_work_mode_consistency', violates_work_mode_consistency,
                'violates_organization_consistency',
                    (violates_organization_consistency
                     OR t1_violates_organization_consistency),
                'violates_opportunity_type_consistency',
                    (violates_opportunity_type_consistency
                     OR t1_violates_opportunity_type_consistency),
                'violates_geographic_consistency',
                    (violates_geographic_consistency
                     OR t1_violates_geographic_consistency),
                'component_size', 1,
                'canonical_anchor_key', canonical_anchor_key,
                'is_primary_source', TRUE
            )
        WHEN is_composite_ambiguous_within_source THEN
            JSONB_BUILD_OBJECT(
                'rule', 'singleton_ambiguous_composite',
                'reason', 'Multiple listings within the same source share identical Tier 2 composite signals; retained separately to avoid ambiguous merging.',
                'component_size', 1,
                'canonical_anchor_key', canonical_anchor_key,
                'is_primary_source', TRUE
            )
        ELSE
            JSONB_BUILD_OBJECT(
                'rule', 'singleton',
                'reason', 'No verified cross-source match met conservative evidence thresholds.',
                'component_size', 1,
                'canonical_anchor_key', canonical_anchor_key,
                'is_primary_source', TRUE
            )
    END AS match_evidence,
    observed_status,
    effective_status,
    first_seen_at,
    last_seen_at,
    content_hash,
    content_version,
    last_collection_run_id

FROM primary_ranked
{%- endmacro %}
