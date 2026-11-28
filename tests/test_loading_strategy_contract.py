import json
from pathlib import Path

import pytest

from scrapers.main import build_parser, validate_arguments


ROOT = Path(__file__).resolve().parents[1]

MANIFEST = json.loads(
    (ROOT / "config" / "loading_strategies.json")
    .read_text(encoding="utf-8")
)

POLICIES = MANIFEST["sources"]

EXPECTED_SOURCES = {
    "egyincs",
    "wuzzuf",
    "forasna",
    "bayt",
    "itida",
    "nti",
    "devpost",
    "un_volunteers",
}


def test_source_inventory():

    assert set(POLICIES) == EXPECTED_SOURCES


def test_scheduler_is_not_enabled():

    assert MANIFEST["scheduler_enabled"] is False


@pytest.mark.parametrize("source", sorted(EXPECTED_SOURCES))
def test_full_load_cli_contract(source):

    policy = POLICIES[source]

    parser = build_parser()

    args = parser.parse_args([
        "--source", source,
        "--mode", policy["collection_mode"],
        "--storage", policy["storage"],
        "--load-strategy", policy["initial_load"],
    ])

    validate_arguments(parser, args)

    assert args.max_jobs is None
    assert args.max_pages is None


@pytest.mark.parametrize("scope", ["jobs", "lp_course"])
def test_egyincs_incremental_cli_contract(scope):

    policy = POLICIES["egyincs"]

    assert scope in policy["scopes"]

    parser = build_parser()

    args = parser.parse_args([
        "--source", "egyincs",
        "--mode", policy["collection_mode"],
        "--storage", policy["storage"],
        "--load-strategy", policy["recurring_load"],
        "--endpoint", scope,
    ])

    validate_arguments(parser, args)

    assert args.max_jobs is None
    assert args.max_pages is None


@pytest.mark.parametrize(
    "source",
    sorted(EXPECTED_SOURCES - {"egyincs"}),
)
def test_unsupported_incremental_rejected(source):

    policy = POLICIES[source]

    parser = build_parser()

    with pytest.raises(SystemExit):

        args = parser.parse_args([
            "--source", source,
            "--mode", policy["collection_mode"],
            "--storage", policy["storage"],
            "--load-strategy", "incremental",
        ])

        validate_arguments(parser, args)


@pytest.mark.parametrize("source", sorted(EXPECTED_SOURCES))
def test_safe_loading_policy(source):

    policy = POLICIES[source]

    assert policy["allow_partial_checkpoint"] is False
    assert policy["infer_closure_from_absence"] is False
    assert policy["recover_before_recollecting"] is True
    assert policy["require_source_lock"] is True
    assert policy["require_warehouse_write_guard"] is True
    assert policy["batch_size"] == 100
    assert policy["checkpoint_enabled"] == (
        source == "egyincs"
    )

    if source != "egyincs":
        assert policy["recurring_load"] == "full"


def test_publication_policy():

    policy = MANIFEST["publication_policy"]

    assert (ROOT / policy["runner"]).is_file()

    assert policy["require_finalized_persistence"] is True
    assert policy["require_exclusive_warehouse_lock"] is True
    assert policy["publish_partial_data_as_complete"] is False
