{% macro deterministic_uuid(seed_expr) -%}
    CAST(
        SUBSTRING(
            ENCODE(
                SHA256(
                    CONVERT_TO('matchpoint:canonical_opportunity:v1|' || CAST({{ seed_expr }} AS TEXT), 'UTF8')
                ),
                'hex'
            ),
            1, 8
        ) || '-' ||
        SUBSTRING(
            ENCODE(
                SHA256(
                    CONVERT_TO('matchpoint:canonical_opportunity:v1|' || CAST({{ seed_expr }} AS TEXT), 'UTF8')
                ),
                'hex'
            ),
            9, 4
        ) || '-' ||
        '5' || SUBSTRING(
            ENCODE(
                SHA256(
                    CONVERT_TO('matchpoint:canonical_opportunity:v1|' || CAST({{ seed_expr }} AS TEXT), 'UTF8')
                ),
                'hex'
            ),
            14, 3
        ) || '-' ||
        'a' || SUBSTRING(
            ENCODE(
                SHA256(
                    CONVERT_TO('matchpoint:canonical_opportunity:v1|' || CAST({{ seed_expr }} AS TEXT), 'UTF8')
                ),
                'hex'
            ),
            18, 3
        ) || '-' ||
        SUBSTRING(
            ENCODE(
                SHA256(
                    CONVERT_TO('matchpoint:canonical_opportunity:v1|' || CAST({{ seed_expr }} AS TEXT), 'UTF8')
                ),
                'hex'
            ),
            21, 12
        )
        AS UUID
    )
{%- endmacro %}
