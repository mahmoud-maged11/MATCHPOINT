import os

from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest

from psycopg import sql

from scrapers.models import Opportunity

from scrapers.storage.postgres import (
    PostgresSettings,
    PostgresStorage,
)

from scrapers.storage.collection_runs import (
    CollectionRunManager,
    RunCounters,
)

from scrapers.storage.opportunities import (
    OpportunityRepository,
)

from scrapers.storage.counters import (
    RunCounterRepository,
)


pytestmark = pytest.mark.skipif(
    os.getenv("MATCHPOINT_RUN_INGESTION_TESTS") != "1",
    reason="Requires isolated ingestion test database",
)


class ForcedStorageFailure(Exception):
    pass


@pytest.fixture
def context():

    storage = PostgresStorage(
        PostgresSettings.from_config(
            host="127.0.0.1",
            database="matchpoint_ingestion_test",
        )
    )

    assert storage.health_check()["database"] == (
        "matchpoint_ingestion_test"
    )

    manager = CollectionRunManager(storage)
    repository = OpportunityRepository(storage)
    counter = RunCounterRepository(storage)

    run_ids = []

    identifier = uuid4().hex

    base = Opportunity(
        source_name="wuzzuf",
        source_opportunity_id=identifier,
        source_url=(
            f"https://wuzzuf.net/jobs/p/{identifier}"
        ),
        title="Data Engineer",
        opportunity_type="job",
        collected_at=(
            datetime.now(timezone.utc)
            - timedelta(hours=2)
        ),
        raw_payload={"version": 1},
    )

    def start_run():

        run_id = uuid4()

        run_ids.append(run_id)

        manager.start_run(
            run_id=run_id,
            source_name="wuzzuf",
            collection_mode="api",
            collection_scope="atomicity_test",
        )

        return run_id

    def snapshot():

        with storage.transaction(read_only=True) as conn:

            listings = conn.execute(
                """
                SELECT *
                FROM bronze.source_listings
                WHERE source_name = 'wuzzuf'
                  AND source_opportunity_id = %s
                """,
                (identifier,),
            ).fetchall()

            history = conn.execute(
                """
                SELECT *
                FROM bronze.source_listing_history
                WHERE collection_run_id = ANY(%s::uuid[])
                ORDER BY source_listing_id, content_version
                """,
                (run_ids,),
            ).fetchall()

            observations = conn.execute(
                """
                SELECT *
                FROM bronze.ingestion_observations
                WHERE collection_run_id = ANY(%s::uuid[])
                ORDER BY source_listing_id, collection_run_id
                """,
                (run_ids,),
            ).fetchall()

            invalid = conn.execute(
                """
                SELECT *
                FROM bronze.invalid_records
                WHERE collection_run_id = ANY(%s::uuid[])
                ORDER BY invalid_record_id
                """,
                (run_ids,),
            ).fetchall()

            runs = conn.execute(
                """
                SELECT *
                FROM bronze.collection_runs
                WHERE run_id = ANY(%s::uuid[])
                ORDER BY run_id
                """,
                (run_ids,),
            ).fetchall()

        return {
            "listings": listings,
            "history": history,
            "observations": observations,
            "invalid": invalid,
            "runs": runs,
        }

    def seed():

        run_id = start_run()

        result = repository.ingest(
            base,
            run_id,
        )

        assert result.outcome == "inserted"

        manager.finish_run(
            run_id=run_id,
            status="completed",
            received=1,
        )

        return result

    try:

        yield {
            "storage": storage,
            "manager": manager,
            "repository": repository,
            "counter": counter,
            "base": base,
            "start_run": start_run,
            "snapshot": snapshot,
            "seed": seed,
        }

    finally:

        with storage.transaction() as conn:

            for table in (
                "invalid_records",
                "ingestion_observations",
                "source_listing_history",
            ):

                conn.execute(
                    sql.SQL(
                        """
                        DELETE FROM bronze.{}
                        WHERE collection_run_id = ANY(%s::uuid[])
                        """
                    ).format(sql.Identifier(table)),
                    (run_ids,),
                )

            conn.execute(
                """
                DELETE FROM bronze.source_listings
                WHERE source_name = 'wuzzuf'
                  AND source_opportunity_id = %s
                """,
                (identifier,),
            )

            conn.execute(
                """
                DELETE FROM bronze.collection_runs
                WHERE run_id = ANY(%s::uuid[])
                """,
                (run_ids,),
            )


def inject_failure(
    monkeypatch,
    repository,
    method_name,
    timing,
):

    original = getattr(
        repository,
        method_name,
    )

    def fail(*args, **kwargs):

        if timing == "after":

            original(*args, **kwargs)

        raise ForcedStorageFailure(
            f"{timing}:{method_name}"
        )

    monkeypatch.setattr(
        repository,
        method_name,
        fail,
    )


@pytest.mark.parametrize(
    "method_name,timing",
    [
        ("_insert_listing", "after"),
        ("_insert_history", "before"),
        ("_insert_history", "after"),
        ("_insert_observation", "before"),
        ("_insert_observation", "after"),
    ],
)
def test_new_listing_atomicity(
    context,
    monkeypatch,
    method_name,
    timing,
):

    repository = context["repository"]

    run_id = context["start_run"]()

    before = context["snapshot"]()

    with monkeypatch.context() as patch:

        inject_failure(
            patch,
            repository,
            method_name,
            timing,
        )

        with pytest.raises(ForcedStorageFailure):

            repository.ingest(
                context["base"],
                run_id,
            )

    assert context["snapshot"]() == before

    counters = context["counter"].reconcile(
        run_id=run_id,
        received=1,
    )

    assert counters == RunCounters(received=1)
    assert counters.unprocessed == 1

    result = repository.ingest(
        context["base"],
        run_id,
    )

    assert result.outcome == "inserted"
    assert result.content_version == 1

    after = context["snapshot"]()

    assert len(after["listings"]) == 1
    assert len(after["history"]) == 1
    assert len(after["observations"]) == 1

    final = context["manager"].finish_run(
        run_id=run_id,
        status="completed",
        received=1,
    )

    assert final["records_inserted"] == 1


@pytest.mark.parametrize(
    "method_name,timing",
    [
        ("_update_listing", "after"),
        ("_insert_history", "before"),
        ("_insert_history", "after"),
        ("_insert_observation", "before"),
        ("_insert_observation", "after"),
    ],
)
def test_changed_listing_atomicity(
    context,
    monkeypatch,
    method_name,
    timing,
):

    initial = context["seed"]()

    repository = context["repository"]

    run_id = context["start_run"]()

    base = context["base"]

    changed = Opportunity.model_validate({
        **base.model_dump(mode="python"),
        "title": "Senior Data Engineer",
        "collected_at": (
            base.collected_at + timedelta(hours=1)
        ),
        "raw_payload": {"version": 2},
    })

    before = context["snapshot"]()

    with monkeypatch.context() as patch:

        inject_failure(
            patch,
            repository,
            method_name,
            timing,
        )

        with pytest.raises(ForcedStorageFailure):

            repository.ingest(
                changed,
                run_id,
            )

    assert context["snapshot"]() == before

    result = repository.ingest(
        changed,
        run_id,
    )

    assert result.outcome == "updated"
    assert result.content_version == 2

    assert result.source_listing_id == (
        initial.source_listing_id
    )

    after = context["snapshot"]()

    assert len(after["listings"]) == 1
    assert len(after["history"]) == 2
    assert len(after["observations"]) == 2

    assert after["listings"][0]["title"] == (
        "Senior Data Engineer"
    )

    final = context["manager"].finish_run(
        run_id=run_id,
        status="completed",
        received=1,
    )

    assert final["records_updated"] == 1


@pytest.mark.parametrize(
    "method_name,timing",
    [
        ("_update_listing", "after"),
        ("_insert_observation", "before"),
        ("_insert_observation", "after"),
    ],
)
def test_unchanged_listing_atomicity(
    context,
    monkeypatch,
    method_name,
    timing,
):

    initial = context["seed"]()

    repository = context["repository"]

    run_id = context["start_run"]()

    base = context["base"]

    newer = Opportunity.model_validate({
        **base.model_dump(mode="python"),
        "collected_at": (
            base.collected_at + timedelta(hours=1)
        ),
        "raw_payload": {"version": 2},
    })

    before = context["snapshot"]()

    with monkeypatch.context() as patch:

        inject_failure(
            patch,
            repository,
            method_name,
            timing,
        )

        with pytest.raises(ForcedStorageFailure):

            repository.ingest(
                newer,
                run_id,
            )

    assert context["snapshot"]() == before

    result = repository.ingest(
        newer,
        run_id,
    )

    assert result.outcome == "unchanged"
    assert result.content_version == 1

    assert result.content_hash == (
        initial.content_hash
    )

    after = context["snapshot"]()

    assert len(after["listings"]) == 1
    assert len(after["history"]) == 1
    assert len(after["observations"]) == 2

    assert after["listings"][0]["raw_payload"] == {
        "version": 2
    }

    assert after["listings"][0]["last_seen_at"] == (
        newer.collected_at
    )

    final = context["manager"].finish_run(
        run_id=run_id,
        status="completed",
        received=1,
    )

    assert final["records_unchanged"] == 1


@pytest.mark.parametrize(
    "timing",
    ["before", "after"],
)
def test_stale_observation_atomicity(
    context,
    monkeypatch,
    timing,
):

    context["seed"]()

    repository = context["repository"]

    run_id = context["start_run"]()

    base = context["base"]

    older = Opportunity.model_validate({
        **base.model_dump(mode="python"),
        "title": "Older title",
        "collected_at": (
            base.collected_at - timedelta(hours=1)
        ),
    })

    before = context["snapshot"]()

    with monkeypatch.context() as patch:

        inject_failure(
            patch,
            repository,
            "_insert_observation",
            timing,
        )

        with pytest.raises(ForcedStorageFailure):

            repository.ingest(
                older,
                run_id,
            )

    assert context["snapshot"]() == before

    result = repository.ingest(
        older,
        run_id,
    )

    assert result.outcome == "stale"

    after = context["snapshot"]()

    assert after["listings"] == before["listings"]
    assert after["history"] == before["history"]

    assert len(after["observations"]) == 2

    final = context["manager"].finish_run(
        run_id=run_id,
        status="completed",
        received=1,
    )

    assert final["records_stale"] == 1
