-- Validate the production generic application portal classifier.
-- Returns zero rows on success.

WITH test_cases AS (

    SELECT *
    FROM (
        VALUES
            (
                'null_url',
                NULL::TEXT,
                TRUE
            ),
            (
                'invalid_url',
                'not-a-url',
                TRUE
            ),
            (
                'root_url',
                'https://company.com',
                TRUE
            ),
            (
                'root_with_query',
                'https://company.com/?id=123',
                TRUE
            ),
            (
                'generic_careers',
                'https://company.com/careers',
                TRUE
            ),
            (
                'careers_tracking_query',
                'https://company.com/careers?utm_source=facebook',
                TRUE
            ),
            (
                'generic_jobs_with_id',
                'https://company.com/jobs?id=123',
                TRUE
            ),
            (
                'generic_apply_with_query',
                'https://company.com/apply?ref=ABC',
                TRUE
            ),
            (
                'generic_uppercase_path',
                'https://company.com/CAREERS/',
                TRUE
            ),
            (
                'generic_localized_path',
                'https://company.com/en/jobs?ref=ABC',
                TRUE
            ),
            (
                'generic_arabic_locale',
                'https://company.com/ar/careers',
                TRUE
            ),
            (
                'generic_wuzzuf_directory',
                'https://wuzzuf.net/jobs',
                TRUE
            ),
            (
                'generic_wuzzuf_directory_query',
                'https://wuzzuf.net/jobs?search=python',
                TRUE
            ),
            (
                'generic_wuzzuf_egypt',
                'https://wuzzuf.net/jobs/egypt',
                TRUE
            ),
            (
                'generic_nti_registration',
                'https://www.nti.sci.eg/ereg/',
                TRUE
            ),
            (
                'generic_nti_registration_query',
                'https://www.nti.sci.eg/ereg/?id=123',
                TRUE
            ),
            (
                'generic_itida_directory',
                'https://itida.gov.eg/english/programs?ref=ABC',
                TRUE
            ),
            (
                'generic_google_forms',
                'https://docs.google.com/forms/d/e/ABC/viewform',
                TRUE
            ),
            (
                'specific_job_path',
                'https://company.com/jobs/ABC123',
                FALSE
            ),
            (
                'specific_job_with_query',
                'https://company.com/jobs/ABC123?ref=ABC',
                FALSE
            ),
            (
                'specific_careers_path',
                'https://company.com/careers/data-engineer',
                FALSE
            ),
            (
                'specific_wuzzuf_listing',
                'https://wuzzuf.net/jobs/p/ABC123-Data-Engineer',
                FALSE
            ),
            (
                'specific_prefix_boundary',
                'https://company.com/jobs-archive/ABC123',
                FALSE
            ),
            (
                'generic_fragment',
                'https://company.com/careers#apply',
                TRUE
            ),
            (
                'fragment_only_route',
                'https://company.com/#/jobs/123',
                TRUE
            ),
            (
                'credentials_rejected',
                'https://user:password@company.com/jobs/ABC',
                TRUE
            )
    ) AS t(
        case_name,
        raw_url,
        expected_generic
    )

),

evaluated AS (

    SELECT
        *,
        {{ is_generic_application_portal('raw_url') }}
            AS actual_generic
    FROM test_cases

)

SELECT
    case_name,
    raw_url,
    expected_generic,
    actual_generic
FROM evaluated
WHERE actual_generic IS DISTINCT FROM expected_generic
