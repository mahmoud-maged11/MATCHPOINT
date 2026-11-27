{% macro normalize_url_for_matching(url_expr) -%}
    CASE
        WHEN {{ url_expr }} ~* '^https?://' THEN
            NULLIF(
                CASE
                    WHEN POSITION('?' IN SPLIT_PART(REGEXP_REPLACE(BTRIM({{ url_expr }}), '^https?://(www\.)?', '', 'i'), '#', 1)) > 0 THEN
                        RTRIM(
                            LOWER(
                                SPLIT_PART(
                                    SPLIT_PART(REGEXP_REPLACE(BTRIM({{ url_expr }}), '^https?://(www\.)?', '', 'i'), '#', 1),
                                    '?',
                                    1
                                )
                            ),
                            '/'
                        )
                        || '?'
                        || SUBSTRING(
                            SPLIT_PART(REGEXP_REPLACE(BTRIM({{ url_expr }}), '^https?://(www\.)?', '', 'i'), '#', 1)
                            FROM POSITION('?' IN SPLIT_PART(REGEXP_REPLACE(BTRIM({{ url_expr }}), '^https?://(www\.)?', '', 'i'), '#', 1)) + 1
                        )
                    ELSE
                        RTRIM(
                            LOWER(
                                SPLIT_PART(REGEXP_REPLACE(BTRIM({{ url_expr }}), '^https?://(www\.)?', '', 'i'), '#', 1)
                            ),
                            '/'
                        )
                END,
                ''
            )
        ELSE NULL
    END
{%- endmacro %}
