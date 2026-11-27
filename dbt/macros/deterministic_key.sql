{% macro deterministic_sha256_key(expressions) -%}

    {%- if expressions | length == 0 -%}
        {{ exceptions.raise_compiler_error(
            "deterministic_sha256_key requires at least one expression"
        ) }}
    {%- endif -%}

    ENCODE(
        SHA256(
            CONVERT_TO(
                'matchpoint:surrogate_key:v2|' ||
                JSONB_BUILD_ARRAY(
                    {%- for expr in expressions %}
                    CAST({{ expr }} AS TEXT)
                    {%- if not loop.last %},{% endif %}
                    {%- endfor %}
                )::TEXT,
                'UTF8'
            )
        ),
        'hex'
    )

{%- endmacro %}