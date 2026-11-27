{% macro clean_text(column_expr) -%}
    NULLIF(
        BTRIM(
            REGEXP_REPLACE(
                {{ column_expr }},
                '[[:space:]]+',
                ' ',
                'g'
            )
        ),
        ''
    )
{%- endmacro %}


{% macro normalize_lookup_key(column_expr) -%}
    LOWER({{ clean_text(column_expr) }})
{%- endmacro %}