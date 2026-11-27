{% macro extract_source_reference(url_expr) -%}

    CASE

        WHEN LOWER(({{ url_parts(url_expr) }})[2])
            IN ('wuzzuf.net', 'www.wuzzuf.net')
            AND {{ url_path_for_matching(url_expr) }}
                ~ '^/jobs/p/[A-Za-z0-9]+(-[^/]+)?/?$'

        THEN JSONB_BUILD_OBJECT(
            'source_name', 'wuzzuf',
            'source_opportunity_id',
            (
                REGEXP_MATCH(
                    {{ url_path_for_matching(url_expr) }},
                    '^/jobs/p/([A-Za-z0-9]+)'
                )
            )[1]
        )

        WHEN LOWER(({{ url_parts(url_expr) }})[2])
            IN ('bayt.com', 'www.bayt.com')
            AND {{ url_path_for_matching(url_expr) }}
                ~ '^/([^/]+/)+jobs/[^/]+-[1-9][0-9]*/?$'

        THEN JSONB_BUILD_OBJECT(
            'source_name', 'bayt',
            'source_opportunity_id',
            (
                REGEXP_MATCH(
                    {{ url_path_for_matching(url_expr) }},
                    '-([1-9][0-9]*)/?$'
                )
            )[1]
        )

        WHEN LOWER(({{ url_parts(url_expr) }})[2])
            IN ('app.unv.org', 'www.app.unv.org')
            AND {{ url_path_for_matching(url_expr) }}
                ~ '^/opportunities/[1-9][0-9]*/?$'

        THEN JSONB_BUILD_OBJECT(
            'source_name', 'un_volunteers',
            'source_opportunity_id',
            (
                REGEXP_MATCH(
                    {{ url_path_for_matching(url_expr) }},
                    '^/opportunities/([1-9][0-9]*)/?$'
                )
            )[1]
        )

        ELSE NULL::JSONB

    END

{%- endmacro %}
