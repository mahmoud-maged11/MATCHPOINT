{% macro deadline_has_passed(timestamp_expr, calendar_expr, precision_expr, evaluated_at_expr) %}

    CASE
        WHEN {{ calendar_expr }} IS NULL
        THEN FALSE

        WHEN {{ precision_expr }} = 'exact'
             AND {{ timestamp_expr }} IS NOT NULL
        THEN COALESCE(
            {{ timestamp_expr }} < {{ evaluated_at_expr }},
            FALSE
        )

        WHEN {{ precision_expr }} = 'date_only'
        THEN COALESCE(
            (
                (
                    {{ calendar_expr }}::TIMESTAMP
                    + INTERVAL '36 hours'
                ) AT TIME ZONE 'UTC'
            ) < {{ evaluated_at_expr }},
            FALSE
        )

        ELSE FALSE
    END

{% endmacro %}
