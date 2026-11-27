{% macro clean_text(column_expr) -%}
    NULLIF(REGEXP_REPLACE(BTRIM({{ column_expr }}), '\s+', ' ', 'g'), '')
{%- endmacro %}

{% macro normalize_lookup_key(column_expr) -%}
    LOWER(NULLIF(REGEXP_REPLACE(BTRIM({{ column_expr }}), '\s+', ' ', 'g'), ''))
{%- endmacro %}
