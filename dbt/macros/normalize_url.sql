{% macro url_parts(url_expr) -%}

    REGEXP_MATCH(
        BTRIM({{ url_expr }}),
        '^(https?)://([a-z0-9.-]+(:[0-9]{1,5})?)([/?#][^[:space:]]*)?$',
        'i'
    )

{%- endmacro %}


{% macro normalize_url_for_matching(url_expr) -%}

    CASE
        WHEN {{ url_parts(url_expr) }} IS NOT NULL THEN

            LOWER(
                ({{ url_parts(url_expr) }})[1]
            )
            || '://'
            || LOWER(
                ({{ url_parts(url_expr) }})[2]
            )
            || COALESCE(
                ({{ url_parts(url_expr) }})[4],
                ''
            )

        ELSE NULL
    END

{%- endmacro %}


{% macro url_host_for_matching(url_expr) -%}

    LOWER(
        SPLIT_PART(
            ({{ url_parts(url_expr) }})[2],
            ':',
            1
        )
    )

{%- endmacro %}


{% macro url_path_for_matching(url_expr) -%}

    NULLIF(
        SPLIT_PART(
            SPLIT_PART(
                ({{ url_parts(url_expr) }})[4],
                '#',
                1
            ),
            '?',
            1
        ),
        ''
    )

{%- endmacro %}


{% macro url_reference_body(url_expr) -%}

    CASE
        WHEN {{ url_parts(url_expr) }} IS NOT NULL THEN

            REGEXP_REPLACE(
                LOWER(
                    ({{ url_parts(url_expr) }})[2]
                ),
                '^www\.',
                ''
            )
            || COALESCE(
                SPLIT_PART(
                    ({{ url_parts(url_expr) }})[4],
                    '#',
                    1
                ),
                ''
            )

        ELSE NULL
    END

{%- endmacro %}