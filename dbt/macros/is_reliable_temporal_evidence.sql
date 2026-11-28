{% macro is_reliable_temporal_evidence(
    timestamp_expr,
    calendar_expr,
    precision_expr
) -%}

COALESCE(
    CASE
        WHEN {{ calendar_expr }} IS NULL
        THEN FALSE

        WHEN NOT ISFINITE({{ calendar_expr }})
        THEN FALSE

        WHEN {{ calendar_expr }} NOT BETWEEN
            DATE '0001-01-01' AND DATE '9999-12-31'
        THEN FALSE

        WHEN {{ precision_expr }} = 'exact'
        THEN CASE
            WHEN {{ timestamp_expr }} IS NOT NULL
             AND ISFINITE({{ timestamp_expr }})
            THEN
                ({{ timestamp_expr }} AT TIME ZONE 'UTC')::DATE
                = {{ calendar_expr }}
            ELSE FALSE
        END

        WHEN {{ precision_expr }} = 'date_only'
        THEN ISFINITE({{ calendar_expr }})

        ELSE FALSE
    END,
    FALSE
)

{%- endmacro %}
