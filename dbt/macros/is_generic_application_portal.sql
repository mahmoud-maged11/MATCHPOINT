{% macro is_generic_application_portal(url_expr) -%}

    (
        SELECT
            CASE
                WHEN p.host_name IS NULL THEN TRUE

                WHEN p.path_name = '' THEN TRUE

                WHEN p.path_name IN (
                    'careers',
                    'career',
                    'jobs',
                    'apply',
                    'register',
                    'registration',
                    'opportunities',
                    'internships',
                    'vacancies',
                    'join-us',
                    'work-with-us',
                    'en/careers',
                    'en/jobs',
                    'ar/careers',
                    'ar/jobs'
                ) THEN TRUE

                ELSE EXISTS (
                    SELECT 1
                    FROM {{ ref('generic_application_portals') }} gp
                    WHERE

                        (
                            gp.match_scope = 'host_any_generic_portal'
                            AND (
                                p.host_name = LOWER(gp.portal_pattern)
                                OR RIGHT(
                                    p.host_name,
                                    LENGTH(gp.portal_pattern) + 1
                                ) = '.' || LOWER(gp.portal_pattern)
                            )
                        )

                        OR (
                            gp.match_scope = 'host_root_only'
                            AND (
                                p.host_name = LOWER(gp.portal_pattern)
                                OR RIGHT(
                                    p.host_name,
                                    LENGTH(gp.portal_pattern) + 1
                                ) = '.' || LOWER(gp.portal_pattern)
                            )
                            AND p.path_name = ''
                        )

                        OR (
                            gp.match_scope = 'path_exact_generic'
                            AND p.host_and_path = LOWER(gp.portal_pattern)
                        )

                        OR (
                            gp.match_scope = 'path_prefix_generic'
                            AND (
                                p.host_and_path = LOWER(gp.portal_pattern)
                                OR LEFT(
                                    p.host_and_path,
                                    LENGTH(gp.portal_pattern) + 1
                                ) = LOWER(gp.portal_pattern) || '/'
                            )
                        )
                )
            END

        FROM (
            SELECT
                u.host_name,
                u.path_name,
                u.host_name ||
                    CASE
                        WHEN u.path_name = '' THEN ''
                        ELSE '/' || u.path_name
                    END AS host_and_path

            FROM (
                SELECT
                    REGEXP_REPLACE(
                        {{ url_host_for_matching(url_expr) }},
                        '^www\.',
                        ''
                    ) AS host_name,

                    LOWER(
                        BTRIM(
                            COALESCE(
                                {{ url_path_for_matching(url_expr) }},
                                ''
                            ),
                            '/'
                        )
                    ) AS path_name
            ) u
        ) p
    )

{%- endmacro %}
