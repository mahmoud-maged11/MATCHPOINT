-- Validate conservative URL normalization.
-- Returns zero rows on success.

WITH test_cases AS (

    SELECT *
    FROM (
        VALUES
            (
                'host_case',
                'HTTPS://Company.COM/jobs/ABC',
                'https://company.com/jobs/ABC'
            ),
            (
                'path_case_upper',
                'https://company.com/jobs/ABC',
                'https://company.com/jobs/ABC'
            ),
            (
                'path_case_lower',
                'https://company.com/jobs/abc',
                'https://company.com/jobs/abc'
            ),
            (
                'query_case',
                'https://company.com/jobs?id=AbC',
                'https://company.com/jobs?id=AbC'
            ),
            (
                'query_order',
                'https://company.com/jobs?b=2&a=1',
                'https://company.com/jobs?b=2&a=1'
            ),
            (
                'fragment_preservation',
                'https://company.com/#/jobs/123',
                'https://company.com/#/jobs/123'
            ),
            (
                'trailing_slash',
                'https://company.com/jobs/ABC/',
                'https://company.com/jobs/ABC/'
            ),
            (
                'www_preservation',
                'https://www.Company.com/jobs/ABC',
                'https://www.company.com/jobs/ABC'
            ),
            (
                'http_preservation',
                'http://Company.com/jobs/ABC',
                'http://company.com/jobs/ABC'
            ),
            (
                'port_preservation',
                'https://Company.com:8443/jobs/ABC',
                'https://company.com:8443/jobs/ABC'
            ),
            (
                'encoded_path',
                'https://company.com/jobs/A%2FB',
                'https://company.com/jobs/A%2FB'
            ),
            (
                'outer_spaces',
                '  https://Company.com/jobs/ABC  ',
                'https://company.com/jobs/ABC'
            ),
            (
                'null_input',
                NULL::TEXT,
                NULL::TEXT
            ),
            (
                'empty_input',
                '',
                NULL
            ),
            (
                'unsupported_scheme',
                'ftp://company.com/jobs/ABC',
                NULL
            ),
            (
                'missing_host',
                'https:///jobs/ABC',
                NULL
            ),
            (
                'credentials_rejected',
                'https://user:password@company.com/jobs/ABC',
                NULL
            ),
            (
                'embedded_whitespace',
                'https://company.com/jobs/Data Engineer',
                NULL
            ),
            (
                'relative_url',
                '/jobs/ABC',
                NULL
            ),
            (
                'root_url',
                'https://Company.com',
                'https://company.com'
            )
    ) AS t(case_name, raw_url, expected_url)

),

evaluated AS (

    SELECT
        *,
        {{ normalize_url_for_matching('raw_url') }} AS actual_url
    FROM test_cases

)

SELECT
    case_name,
    raw_url,
    expected_url,
    actual_url
FROM evaluated
WHERE actual_url IS DISTINCT FROM expected_url
