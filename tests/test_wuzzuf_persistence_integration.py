
import os

from copy import deepcopy
from datetime import timedelta

import pytest

from scrapers.models import Opportunity

from scrapers.storage.reconciliation import (
    ReconciliationRepository,
)

from scrapers.utils.hashing import (
    generate_content_hash,
    generate_observation_hash,
)

from test_ingestion_atomicity import context

pytestmark = pytest.mark.skipif(
    os.getenv("MATCHPOINT_RUN_INGESTION_TESTS") != "1",
    reason="Requires isolated ingestion database",
)


@pytest.mark.parametrize(
    "scenario,expected_name,expected_version",
    [
        ("same_company", "Original Company", 1),
        ("different_company", None, 2),
        ("confidential", None, 2),
        ("access_denied", None, 2),
        ("legacy", None, 2),
        ("successful", "New Company", 2),
    ],
)
@pytest.mark.parametrize("batch", [False, True])
def test_wuzzuf_company_persistence(
    context,
    scenario,
    expected_name,
    expected_version,
    batch,
):

    storage = context["storage"]
    repository = context["repository"]
    manager = context["manager"]

    assert storage.health_check()["database"] == (
        "matchpoint_ingestion_test"
    )

    data = context["base"].model_dump(mode="python")

    data["organization"] = "Original Company"

    data["raw_payload"] = {
        "attributes": {
            "hideCompany": False,
        },
        "company_id": "123",
    }

    if scenario == "legacy":
        data["raw_payload"].pop("company_id")

    original = Opportunity.model_validate(data)

    first_run = context["start_run"]()

    first = repository.ingest(
        original,
        first_run,
    )

    assert first.outcome == "inserted"
    assert first.content_version == 1

    manager.finish_run(
        run_id=first_run,
        status="completed",
        received=1,
    )

    incoming_data = original.model_dump(
        mode="python"
    )

    incoming_data["collected_at"] = (
        original.collected_at
        + timedelta(seconds=10)
    )

    incoming_data["organization"] = None

    raw = deepcopy(
        incoming_data["raw_payload"]
    )

    raw["company_id"] = "123"

    raw["_matchpoint_company_enrichment"] = (
        "temporary_failure"
    )

    if scenario == "different_company":
        raw["company_id"] = "456"

    elif scenario == "confidential":

        raw["attributes"]["hideCompany"] = True

        raw.pop("company_id")

        raw.pop("_matchpoint_company_enrichment")

    elif scenario == "access_denied":

        raw["_matchpoint_company_enrichment"] = (
            "access_denied"
        )

    elif scenario == "successful":

        incoming_data["organization"] = "New Company"

        raw.pop("_matchpoint_company_enrichment")

    incoming_data["raw_payload"] = raw

    incoming = Opportunity.model_validate(
        incoming_data
    )

    original_observation_hash = (
        generate_observation_hash(incoming)
    )

    second_run = context["start_run"]()

    if batch:

        result, = repository.ingest_many(
            [incoming],
            second_run,
        )

    else:

        result = repository.ingest(
            incoming,
            second_run,
        )

    expected_outcome = (
        "unchanged"
        if expected_version == 1
        else "updated"
    )

    assert result.outcome == expected_outcome

    assert result.source_listing_id == (
        first.source_listing_id
    )

    assert result.content_version == expected_version

    assert result.observation_hash == (
        original_observation_hash
    )

    effective = Opportunity.model_validate({
        **incoming.model_dump(mode="python"),
        "organization": expected_name,
    })

    assert result.content_hash == (
        generate_content_hash(effective)
    )

    with storage.transaction(
        read_only=True
    ) as conn:

        listing = conn.execute(
            """
            SELECT *
            FROM bronze.source_listings
            WHERE source_listing_id = %s
            """,
            (first.source_listing_id,),
        ).fetchone()

        history = conn.execute(
            """
            SELECT *
            FROM bronze.source_listing_history
            WHERE source_listing_id = %s
            ORDER BY content_version
            """,
            (first.source_listing_id,),
        ).fetchall()

        observations = conn.execute(
            """
            SELECT *
            FROM bronze.ingestion_observations
            WHERE source_listing_id = %s
            """,
            (first.source_listing_id,),
        ).fetchall()

    assert listing["organization"] == expected_name

    assert listing["content_version"] == (
        expected_version
    )

    assert listing["content_hash"] == (
        generate_content_hash(effective)
    )

    assert listing["last_seen_at"] == (
        incoming.collected_at
    )

    assert listing["raw_payload"] == raw

    assert len(history) == expected_version
    assert len(observations) == 2

    latest_observation = next(
        row
        for row in observations
        if row["collection_run_id"] == second_run
    )

    assert latest_observation["observation_hash"] == (
        original_observation_hash
    )

    assert latest_observation["outcome"] == (
        expected_outcome
    )

    inventory = ReconciliationRepository(
        storage
    ).deferred_wuzzuf_enrichment()

    matching = [
        row
        for row in inventory
        if row["source_listing_id"] == (
            first.source_listing_id
        )
    ]

    if scenario in {"confidential", "successful"}:

        assert matching == []

    else:

        assert len(matching) == 1

        assert matching[0]["deferred_reason"] == (
            raw["_matchpoint_company_enrichment"]
        )

        assert matching[0]["organization"] == (
            expected_name
        )

    final = manager.finish_run(
        run_id=second_run,
        status="completed",
        received=1,
    )

    assert final[
        "records_" + expected_outcome
    ] == 1

    before_replay = context["snapshot"]()

    replay = repository.ingest(
        incoming,
        second_run,
    )

    assert replay.outcome == "duplicate"

    assert replay.original_outcome == (
        expected_outcome
    )

    assert context["snapshot"]() == before_replay
