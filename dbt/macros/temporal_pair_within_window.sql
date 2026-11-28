{% macro temporal_pair_within_window(
    left_timestamp,
    left_calendar,
    left_precision,
    right_timestamp,
    right_calendar,
    right_precision,
    max_days
) -%}

CASE
    WHEN NOT {{ is_reliable_temporal_evidence(
        left_timestamp,
        left_calendar,
        left_precision
    ) }}
    OR NOT {{ is_reliable_temporal_evidence(
        right_timestamp,
        right_calendar,
        right_precision
    ) }}
    THEN FALSE

    WHEN {{ left_precision }} = 'exact'
     AND {{ right_precision }} = 'exact'
    THEN COALESCE(
        ABS(EXTRACT(EPOCH FROM (
            {{ left_timestamp }} - {{ right_timestamp }}
        ))) <= ({{ max_days }} * 86400),
        FALSE
    )

    ELSE ABS(
        {{ left_calendar }} - {{ right_calendar }}
    ) <= {{ max_days }}
END

{%- endmacro %}
