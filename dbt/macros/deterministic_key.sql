{% macro deterministic_sha256_key(expressions) -%}
    ENCODE(
        SHA256(
            CONVERT_TO(
                CONCAT_WS(
                    '|',
                    {%- for expr in expressions %}
                    COALESCE(CAST({{ expr }} AS TEXT), '__NULL__'){% if not loop.last %},{% endif %}
                    {%- endfor %}
                ),
                'UTF8'
            )
        ),
        'hex'
    )
{%- endmacro %}
