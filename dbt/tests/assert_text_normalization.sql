-- Validate production text normalization macros.
-- Returns zero rows on success.

WITH test_cases AS (

    SELECT *
    FROM (
        VALUES
            (
                'null_input',
                NULL::TEXT,
                NULL::TEXT,
                NULL::TEXT
            ),
            (
                'empty_input',
                '',
                NULL,
                NULL
            ),
            (
                'spaces_only',
                '    ',
                NULL,
                NULL
            ),
            (
                'tabs_only',
                E'\t\t',
                NULL,
                NULL
            ),
            (
                'mixed_whitespace_only',
                E' \t\n\r ',
                NULL,
                NULL
            ),
            (
                'leading_trailing_whitespace',
                E'\t Data Engineer \n',
                'Data Engineer',
                'data engineer'
            ),
            (
                'internal_whitespace',
                E'Data\t\n  Engineer',
                'Data Engineer',
                'data engineer'
            ),
            (
                'preserve_display_case',
                'Power BI',
                'Power BI',
                'power bi'
            ),
            (
                'preserve_arabic',
                E'\tمهندس   بيانات\n',
                'مهندس بيانات',
                'مهندس بيانات'
            ),
            (
                'preserve_mixed_language',
                E'  Python\tلتحليل البيانات  ',
                'Python لتحليل البيانات',
                'python لتحليل البيانات'
            ),
            (
                'preserve_skill_punctuation',
                'C++',
                'C++',
                'c++'
            ),
            (
                'preserve_dotnet',
                '.NET',
                '.NET',
                '.net'
            ),
            (
                'preserve_delimiter',
                'Data | Engineering',
                'Data | Engineering',
                'data | engineering'
            ),
            (
                'already_normalized',
                'data engineering',
                'data engineering',
                'data engineering'
            )
    ) AS t(
        case_name,
        raw_value,
        expected_clean,
        expected_lookup
    )

),

evaluated AS (

    SELECT
        *,
        {{ clean_text('raw_value') }} AS actual_clean,
        {{ normalize_lookup_key('raw_value') }} AS actual_lookup
    FROM test_cases

)

SELECT
    case_name,
    raw_value,
    expected_clean,
    actual_clean,
    expected_lookup,
    actual_lookup
FROM evaluated
WHERE actual_clean IS DISTINCT FROM expected_clean
   OR actual_lookup IS DISTINCT FROM expected_lookup