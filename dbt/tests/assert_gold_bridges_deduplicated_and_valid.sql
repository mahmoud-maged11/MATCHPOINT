-- Fails if any Gold canonical bridge table has duplicate natural composite keys
-- or violates Data Contract v3.0.0 §5.2 'unknown' exclusivity for work_modes / employment_types.

WITH dup_skills AS (
    SELECT opportunity_id::TEXT AS entity_id, 'duplicate_opportunity_skill'::TEXT AS failure_reason
    FROM {{ ref('bridge_opportunity_skills') }}
    GROUP BY opportunity_id, skill_key
    HAVING COUNT(*) > 1
),

dup_categories AS (
    SELECT opportunity_id::TEXT AS entity_id, 'duplicate_opportunity_category'::TEXT AS failure_reason
    FROM {{ ref('bridge_opportunity_categories') }}
    GROUP BY opportunity_id, category_key
    HAVING COUNT(*) > 1
),

dup_work_modes AS (
    SELECT opportunity_id::TEXT AS entity_id, 'duplicate_opportunity_work_mode'::TEXT AS failure_reason
    FROM {{ ref('bridge_opportunity_work_modes') }}
    GROUP BY opportunity_id, work_mode
    HAVING COUNT(*) > 1
),

dup_employment_types AS (
    SELECT opportunity_id::TEXT AS entity_id, 'duplicate_opportunity_employment_type'::TEXT AS failure_reason
    FROM {{ ref('bridge_opportunity_employment_types') }}
    GROUP BY opportunity_id, employment_type
    HAVING COUNT(*) > 1
),

work_mode_unknown_mix AS (
    SELECT opportunity_id::TEXT AS entity_id, 'work_mode_unknown_mixed_with_known'::TEXT AS failure_reason
    FROM {{ ref('bridge_opportunity_work_modes') }}
    GROUP BY opportunity_id
    HAVING BOOL_OR(work_mode = 'unknown') AND COUNT(*) > 1
),

employment_type_unknown_mix AS (
    SELECT opportunity_id::TEXT AS entity_id, 'employment_type_unknown_mixed_with_known'::TEXT AS failure_reason
    FROM {{ ref('bridge_opportunity_employment_types') }}
    GROUP BY opportunity_id
    HAVING BOOL_OR(employment_type = 'unknown') AND COUNT(*) > 1
)

SELECT * FROM dup_skills
UNION ALL SELECT * FROM dup_categories
UNION ALL SELECT * FROM dup_work_modes
UNION ALL SELECT * FROM dup_employment_types
UNION ALL SELECT * FROM work_mode_unknown_mix
UNION ALL SELECT * FROM employment_type_unknown_mix
