WITH
skill_expected AS (
    SELECT
        os.opportunity_id,
        ls.skill_key,
        d.skill_name
        , d.skill_group,
        COUNT(DISTINCT os.source_listing_id)
            AS supporting_source_count
    FROM {{ ref('silver_opportunity_sources') }} os
    JOIN {{ ref('silver_listing_skills') }} ls
        ON os.source_listing_id = ls.source_listing_id
    LEFT JOIN {{ ref('silver_skills') }} d
        ON ls.skill_key = d.skill_key
    GROUP BY
        os.opportunity_id,
        ls.skill_key,
        d.skill_name
        , d.skill_group
),

skill_actual AS (
    SELECT
        b.opportunity_id,
        b.skill_key,
        b.skill_name
        , b.skill_group,
        b.supporting_source_count
    FROM {{ ref('bridge_opportunity_skills') }} b
),

skill_missing AS (
    SELECT * FROM skill_expected
    EXCEPT ALL
    SELECT * FROM skill_actual
),

skill_unexpected AS (
    SELECT * FROM skill_actual
    EXCEPT ALL
    SELECT * FROM skill_expected
),

category_expected AS (
    SELECT
        os.opportunity_id,
        ls.category_key,
        d.category_name
        ,
        COUNT(DISTINCT os.source_listing_id)
            AS supporting_source_count
    FROM {{ ref('silver_opportunity_sources') }} os
    JOIN {{ ref('silver_listing_categories') }} ls
        ON os.source_listing_id = ls.source_listing_id
    LEFT JOIN {{ ref('silver_categories') }} d
        ON ls.category_key = d.category_key
    GROUP BY
        os.opportunity_id,
        ls.category_key,
        d.category_name

),

category_actual AS (
    SELECT
        b.opportunity_id,
        b.category_key,
        b.category_name
        ,
        b.supporting_source_count
    FROM {{ ref('bridge_opportunity_categories') }} b
),

category_missing AS (
    SELECT * FROM category_expected
    EXCEPT ALL
    SELECT * FROM category_actual
),

category_unexpected AS (
    SELECT * FROM category_actual
    EXCEPT ALL
    SELECT * FROM category_expected
)

SELECT
    'skill_missing' AS failure_type,
    opportunity_id::TEXT AS opportunity_id,
    skill_key::TEXT AS attribute_key
FROM skill_missing

UNION ALL

SELECT
    'skill_unexpected' AS failure_type,
    opportunity_id::TEXT AS opportunity_id,
    skill_key::TEXT AS attribute_key
FROM skill_unexpected

UNION ALL

SELECT
    'category_missing' AS failure_type,
    opportunity_id::TEXT AS opportunity_id,
    category_key::TEXT AS attribute_key
FROM category_missing

UNION ALL

SELECT
    'category_unexpected' AS failure_type,
    opportunity_id::TEXT AS opportunity_id,
    category_key::TEXT AS attribute_key
FROM category_unexpected
