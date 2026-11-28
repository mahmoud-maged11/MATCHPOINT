{% macro temporal_component_exceeds_window(
    timestamp_expr,
    calendar_expr,
    precision_expr,
    max_days
) -%}

{% set reliable %}
    {{ is_reliable_temporal_evidence(
        timestamp_expr,
        calendar_expr,
        precision_expr
    ) }}
{% endset %}

(
    COALESCE(
        MAX({{ calendar_expr }})
            FILTER (WHERE {{ reliable }})
        -
        MIN({{ calendar_expr }})
            FILTER (WHERE {{ reliable }})
        > {{ max_days }},
        FALSE
    )

    OR COALESCE(
        EXTRACT(EPOCH FROM (
            MAX({{ timestamp_expr }}) FILTER (
                WHERE {{ precision_expr }} = 'exact'
                  AND {{ reliable }}
            )
            -
            MIN({{ timestamp_expr }}) FILTER (
                WHERE {{ precision_expr }} = 'exact'
                  AND {{ reliable }}
            )
        )) > ({{ max_days }} * 86400),
        FALSE
    )
)

{%- endmacro %}
