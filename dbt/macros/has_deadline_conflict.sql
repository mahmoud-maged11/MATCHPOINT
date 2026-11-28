{% macro has_deadline_conflict(timestamp_expr, calendar_expr, precision_expr) %}

    (
        COUNT(DISTINCT {{ calendar_expr }})
        FILTER (
            WHERE {{ precision_expr }} IN ('exact', 'date_only')
        ) > 1

        OR

        COUNT(DISTINCT {{ timestamp_expr }})
        FILTER (
            WHERE {{ precision_expr }} = 'exact'
              AND {{ calendar_expr }} IS NOT NULL
              AND {{ timestamp_expr }} IS NOT NULL
        ) > 1
    )

{% endmacro %}
