{{
    config(
        indexes=[
            {'columns': ['opportunity_work_mode_id'], 'unique': True},
            {'columns': ['opportunity_id']},
            {'columns': ['work_mode']}
        ]
    )
}}

-- Canonical opportunity-to-work-mode bridge expanded from silver_opportunities.work_modes
-- (which already enforces Data Contract v3.0.0 §5.2 'unknown' exclusivity across merged sources).

WITH expanded AS (
    SELECT DISTINCT
        o.opportunity_id,
        LOWER(BTRIM(elem.val)) AS work_mode
    FROM {{ ref('silver_opportunities') }} o
    CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS_TEXT(o.work_modes) AS elem(val)
    WHERE o.work_modes IS NOT NULL
      AND JSONB_TYPEOF(o.work_modes) = 'array'
      AND JSONB_ARRAY_LENGTH(o.work_modes) > 0
      AND NULLIF(BTRIM(elem.val), '') IS NOT NULL
)

SELECT
    {{ deterministic_sha256_key(["opportunity_id", "work_mode"]) }} AS opportunity_work_mode_id,
    opportunity_id,
    work_mode
FROM expanded
