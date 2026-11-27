-- Validate the production surrogate key macro.
-- Returns zero rows on success.

WITH test_cases AS (

    SELECT
        'delimiter_collision' AS case_name,
        {{ deterministic_sha256_key(["'a|b'", "'c'"]) }} AS key_a,
        {{ deterministic_sha256_key(["'a'", "'b|c'"]) }} AS key_b,
        FALSE AS expected_equal

    UNION ALL

    SELECT
        'null_sentinel_collision',
        {{ deterministic_sha256_key(["NULL::TEXT"]) }},
        {{ deterministic_sha256_key(["'__NULL__'"]) }},
        FALSE

    UNION ALL

    SELECT
        'null_vs_empty',
        {{ deterministic_sha256_key(["NULL::TEXT"]) }},
        {{ deterministic_sha256_key(["''"]) }},
        FALSE

    UNION ALL

    SELECT
        'null_position',
        {{ deterministic_sha256_key(["NULL::TEXT", "'a'"]) }},
        {{ deterministic_sha256_key(["'a'", "NULL::TEXT"]) }},
        FALSE

    UNION ALL

    SELECT
        'different_order',
        {{ deterministic_sha256_key(["'a'", "'b'"]) }},
        {{ deterministic_sha256_key(["'b'", "'a'"]) }},
        FALSE

    UNION ALL

    SELECT
        'different_array_length',
        {{ deterministic_sha256_key(["'a'"]) }},
        {{ deterministic_sha256_key(["'a'", "''"]) }},
        FALSE

    UNION ALL

    SELECT
        'same_inputs',
        {{ deterministic_sha256_key(["'org'", "'matchpoint'"]) }},
        {{ deterministic_sha256_key(["'org'", "'matchpoint'"]) }},
        TRUE

    UNION ALL

    SELECT
        'different_entity_namespace',
        {{ deterministic_sha256_key(["'org'", "'python'"]) }},
        {{ deterministic_sha256_key(["'skill'", "'python'"]) }},
        FALSE

    UNION ALL

    SELECT
        'case_preservation',
        {{ deterministic_sha256_key(["'Python'"]) }},
        {{ deterministic_sha256_key(["'python'"]) }},
        FALSE

    UNION ALL

    SELECT
        'arabic_determinism',
        {{ deterministic_sha256_key(["'مهندس بيانات'"]) }},
        {{ deterministic_sha256_key(["'مهندس بيانات'"]) }},
        TRUE

    UNION ALL

    SELECT
        'different_arabic_values',
        {{ deterministic_sha256_key(["'مهندس بيانات'"]) }},
        {{ deterministic_sha256_key(["'محلل بيانات'"]) }},
        FALSE

    UNION ALL

    SELECT
        'numeric_text_equivalence',
        {{ deterministic_sha256_key(["123"]) }},
        {{ deterministic_sha256_key(["'123'"]) }},
        TRUE

    UNION ALL

    SELECT
        'json_special_characters',
        {{ deterministic_sha256_key(["'a,b'", "'c'"]) }},
        {{ deterministic_sha256_key(["'a'", "'b,c'"]) }},
        FALSE

    UNION ALL

    SELECT
        'whitespace_preservation',
        {{ deterministic_sha256_key(["'Python '"]) }},
        {{ deterministic_sha256_key(["'Python'"]) }},
        FALSE

    UNION ALL

    SELECT
        'null_determinism',
        {{ deterministic_sha256_key(["NULL::TEXT"]) }},
        {{ deterministic_sha256_key(["NULL::TEXT"]) }},
        TRUE

)

SELECT
    case_name,
    key_a,
    key_b,
    expected_equal
FROM test_cases
WHERE key_a IS NULL
   OR key_b IS NULL
   OR key_a !~ '^[0-9a-f]{64}$'
   OR key_b !~ '^[0-9a-f]{64}$'
   OR (key_a = key_b) IS DISTINCT FROM expected_equal
