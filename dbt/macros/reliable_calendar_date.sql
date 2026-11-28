{% macro reliable_calendar_date(timestamp_expr, raw_expr, precision_expr) %}

    CASE
        WHEN {{ precision_expr }} = 'exact'
             AND {{ timestamp_expr }} IS NOT NULL
             AND ISFINITE({{ timestamp_expr }})
        THEN
            CASE
                WHEN ({{ timestamp_expr }} AT TIME ZONE 'UTC')::DATE
                     BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'
                THEN ({{ timestamp_expr }} AT TIME ZONE 'UTC')::DATE
                ELSE NULL::DATE
            END

        WHEN {{ precision_expr }} = 'date_only'
        THEN
            CASE
                WHEN BTRIM({{ raw_expr }}) ~
                     '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                THEN
                    CASE
                        WHEN PG_INPUT_IS_VALID(
                            BTRIM({{ raw_expr }}),
                            'date'
                        )
                        THEN BTRIM({{ raw_expr }})::DATE
                        ELSE NULL::DATE
                    END
                ELSE NULL::DATE
            END

        ELSE NULL::DATE
    END

{% endmacro %}
