{{
    config(
        indexes=[
            {'columns': ['opportunity_employment_type_id'], 'unique': True},
            {'columns': ['opportunity_id']},
            {'columns': ['employment_type']}
        ]
    )
}}

-- Canonical opportunity-to-employment-type bridge expanded from silver_opportunities.employment_types
-- (which already enforces Data Contract v3.0.0 §5.2 'unknown' exclusivity across merged sources).

WITH expanded AS (
    SELECT DISTINCT
        o.opportunity_id,
        LOWER(BTRIM(elem.val)) AS employment_type
    FROM {{ ref('silver_opportunities') }} o
    CROSS JOIN LATERAL JSONB_ARRAY_ELEMENTS_TEXT(
        CASE
            WHEN JSONB_TYPEOF(o.employment_types) = 'array'
            THEN o.employment_types
            ELSE '[]'::JSONB
        END
    ) AS elem(val)
    WHERE NULLIF(BTRIM(elem.val), '') IS NOT NULL
)

SELECT
    {{ deterministic_sha256_key(["opportunity_id", "employment_type"]) }} AS opportunity_employment_type_id,
    opportunity_id,
    employment_type
FROM expanded
