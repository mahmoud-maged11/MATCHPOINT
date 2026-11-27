
-- Validate the actual source reference extraction macro.
-- Returns zero rows on success.

WITH test_cases AS (

    SELECT *
    FROM (
        VALUES
        ('wuzzuf_basic', 'https://wuzzuf.net/jobs/p/AbC123-Engineer', 'wuzzuf', 'AbC123'),
        ('wuzzuf_case_preserved', 'HTTPS://WWW.WUZZUF.NET/jobs/p/aBc123', 'wuzzuf', 'aBc123'),
        ('wuzzuf_query', 'https://wuzzuf.net/jobs/p/AbC123?job=Other', 'wuzzuf', 'AbC123'),
        ('wuzzuf_fragment', 'https://wuzzuf.net/jobs/p/AbC123#Other', 'wuzzuf', 'AbC123'),
        ('wuzzuf_invalid_path_case', 'https://wuzzuf.net/JOBS/p/AbC123', NULL::TEXT, NULL::TEXT),
        ('wuzzuf_extra_segment', 'https://wuzzuf.net/jobs/p/AbC123/extra', NULL::TEXT, NULL::TEXT),
        ('bayt_basic', 'https://www.bayt.com/en/egypt/jobs/engineer-12345/', 'bayt', '12345'),
        ('bayt_query_numeric_suffix', 'https://www.bayt.com/en/egypt/jobs/engineer-12345/?ref=campaign-67890', 'bayt', '12345'),
        ('bayt_query_without_slash', 'https://bayt.com/en/egypt/jobs/engineer-12345?ref=campaign-67890', 'bayt', '12345'),
        ('bayt_fragment', 'https://bayt.com/en/egypt/jobs/engineer-12345#67890', 'bayt', '12345'),
        ('bayt_multiple_numbers', 'https://bayt.com/en/egypt/jobs/engineer-2026-12345/', 'bayt', '12345'),
        ('bayt_query_path_injection', 'https://bayt.com/search?next=/en/egypt/jobs/engineer-12345', NULL::TEXT, NULL::TEXT),
        ('bayt_fragment_path_injection', 'https://bayt.com/search#/en/egypt/jobs/engineer-12345', NULL::TEXT, NULL::TEXT),
        ('bayt_zero_id', 'https://bayt.com/en/egypt/jobs/engineer-0', NULL::TEXT, NULL::TEXT),
        ('bayt_leading_zero', 'https://bayt.com/en/egypt/jobs/engineer-012345', NULL::TEXT, NULL::TEXT),
        ('bayt_extra_segment', 'https://bayt.com/en/egypt/jobs/engineer-12345/extra', NULL::TEXT, NULL::TEXT),
        ('unv_basic', 'https://app.unv.org/opportunities/123456', 'un_volunteers', '123456'),
        ('unv_query', 'https://app.unv.org/opportunities/123456?ref=999', 'un_volunteers', '123456'),
        ('unv_fragment', 'https://app.unv.org/opportunities/123456/#999', 'un_volunteers', '123456'),
        ('unv_zero', 'https://app.unv.org/opportunities/0', NULL::TEXT, NULL::TEXT),
        ('unv_extra_segment', 'https://app.unv.org/opportunities/123456/extra', NULL::TEXT, NULL::TEXT),
        ('unv_wrong_host', 'https://www.unv.org/opportunities/123456', NULL::TEXT, NULL::TEXT),
        ('host_suffix_attack', 'https://bayt.com.example.org/en/egypt/jobs/engineer-12345', NULL::TEXT, NULL::TEXT),
        ('host_prefix_attack', 'https://fakebayt.com/en/egypt/jobs/engineer-12345', NULL::TEXT, NULL::TEXT),
        ('nonstandard_port', 'https://bayt.com:8443/en/egypt/jobs/engineer-12345', NULL::TEXT, NULL::TEXT),
        ('credentials', 'https://user@bayt.com/en/egypt/jobs/engineer-12345', NULL::TEXT, NULL::TEXT),
        ('unsupported_scheme', 'ftp://app.unv.org/opportunities/123456', NULL::TEXT, NULL::TEXT),
        ('relative_url', '/opportunities/123456', NULL::TEXT, NULL::TEXT),
        ('generic_portal', 'https://bayt.com/en/egypt/jobs/', NULL::TEXT, NULL::TEXT),
        ('null_url', NULL::TEXT, NULL::TEXT, NULL::TEXT),
        ('empty_url', '', NULL::TEXT, NULL::TEXT),
        ('unrelated_source', 'https://example.com/jobs/engineer-12345', NULL::TEXT, NULL::TEXT)) AS t(
        case_name,
        raw_url,
        expected_source_name,
        expected_source_id
    )

),

evaluated AS (

    SELECT
        *,
        {{ extract_source_reference('raw_url') }}
            AS actual_reference
    FROM test_cases

)

SELECT
    case_name,
    raw_url,
    expected_source_name,
    expected_source_id,
    actual_reference
FROM evaluated
WHERE
    (actual_reference ->> 'source_name')
        IS DISTINCT FROM expected_source_name
    OR
    (actual_reference ->> 'source_opportunity_id')
        IS DISTINCT FROM expected_source_id
    OR (
        expected_source_name IS NULL
        AND actual_reference IS NOT NULL
    )
