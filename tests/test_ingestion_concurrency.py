import os

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
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
)

from scrapers.storage.opportunities import (
    OpportunityRepository,
)


pytestmark = pytest.mark.skipif(
    os.getenv("MATCHPOINT_RUN_INGESTION_TESTS") != "1",
    reason="Requires isolated ingestion test database",
)

WORKERS = 8


@pytest.fixture
def context(monkeypatch):

    storage = PostgresStorage(
        PostgresSettings.from_config(
            host="127.0.0.1",
            database="matchpoint_ingestion_test",
        )
    )

    assert storage.health_check()["database"] == (
        "matchpoint_ingestion_test"
    )

    original_connect = storage.connect

    def bounded_connect(*, read_only=False):

        conn = original_connect(
            read_only=read_only,
        )

        try:

            conn.execute(
                "SET LOCAL lock_timeout = '10s'"
            )

            conn.execute(
                "SET LOCAL statement_timeout = '20s'"
            )

            return conn

        except BaseException:

            conn.close()

            raise

    monkeypatch.setattr(
        storage,
        "connect",
        bounded_connect,
    )

    manager = CollectionRunManager(storage)

    run_ids = []

    identifier = uuid4().hex

    opportunity = Opportunity(
        source_name="wuzzuf",
        source_opportunity_id=identifier,
        source_url=(
            f"https://wuzzuf.net/jobs/p/{identifier}"
        ),
        title="Data Engineer",
        opportunity_type="job",
        raw_payload={"id": identifier},
    )

    def start_run():

        run_id = uuid4()

        run_ids.append(run_id)

        manager.start_run(
            run_id=run_id,
            source_name="wuzzuf",
            collection_mode="api",
            collection_scope="concurrency_test",
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
                ORDER BY content_version
                """,
                (run_ids,),
            ).fetchall()

            observations = conn.execute(
                """
                SELECT *
                FROM bronze.ingestion_observations
                WHERE collection_run_id = ANY(%s::uuid[])
                ORDER BY collection_run_id
                """,
                (run_ids,),
            ).fetchall()

            invalid = conn.execute(
                """
                SELECT *
                FROM bronze.invalid_records
                WHERE collection_run_id = ANY(%s::uuid[])
                """,
                (run_ids,),
            ).fetchall()

        return {
            "listings": listings,
            "history": history,
            "observations": observations,
            "invalid": invalid,
        }

    try:

        yield {
            "storage": storage,
            "manager": manager,
            "opportunity": opportunity,
            "start_run": start_run,
            "snapshot": snapshot,
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


def concurrent_ingest(context, run_ids):

    barrier = Barrier(
        len(run_ids),
        timeout=15,
    )

    def worker(run_id):

        repository = OpportunityRepository(
            context["storage"]
        )

        opportunity = context[
            "opportunity"
        ].model_copy(deep=True)

        barrier.wait()

        return repository.ingest(
            opportunity,
            run_id,
        )

    with ThreadPoolExecutor(
        max_workers=len(run_ids)
    ) as executor:

        futures = [
            executor.submit(worker, run_id)
            for run_id in run_ids
        ]

        return [
            future.result(timeout=45)
            for future in futures
        ]


def test_concurrent_same_run_retries(context):

    run_id = context["start_run"]()

    results = concurrent_ingest(
        context,
        [run_id] * WORKERS,
    )

    outcomes = [
        result.outcome
        for result in results
    ]

    assert outcomes.count("inserted") == 1
    assert outcomes.count("duplicate") == WORKERS - 1

    assert len({
        result.source_listing_id
        for result in results
    }) == 1

    assert all(
        result.content_version == 1
        for result in results
    )

    assert all(
        result.original_outcome == "inserted"
        for result in results
        if result.outcome == "duplicate"
    )

    snapshot = context["snapshot"]()

    assert len(snapshot["listings"]) == 1
    assert len(snapshot["history"]) == 1
    assert len(snapshot["observations"]) == 1
    assert snapshot["invalid"] == []

    final = context["manager"].finish_run(
        run_id=run_id,
        status="completed",
        received=1,
    )

    assert final["records_received"] == 1
    assert final["records_inserted"] == 1
    assert final["records_conflicted"] == 0


def test_concurrent_different_runs(context):

    run_ids = [
        context["start_run"]()
        for _ in range(WORKERS)
    ]

    results = concurrent_ingest(
        context,
        run_ids,
    )

    outcomes = [
        result.outcome
        for result in results
    ]

    assert outcomes.count("inserted") == 1
    assert outcomes.count("unchanged") == WORKERS - 1

    assert len({
        result.source_listing_id
        for result in results
    }) == 1

    assert all(
        result.content_version == 1
        for result in results
    )

    snapshot = context["snapshot"]()

    assert len(snapshot["listings"]) == 1
    assert len(snapshot["history"]) == 1

    assert len(
        snapshot["observations"]
    ) == WORKERS

    assert snapshot["invalid"] == []

    finalized = [
        context["manager"].finish_run(
            run_id=run_id,
            status="completed",
            received=1,
        )
        for run_id in run_ids
    ]

    assert sum(
        run["records_inserted"]
        for run in finalized
    ) == 1

    assert sum(
        run["records_unchanged"]
        for run in finalized
    ) == WORKERS - 1

    assert sum(
        run["records_received"]
        for run in finalized
    ) == WORKERS


def concurrent_updates(context, records):

    barrier = Barrier(len(records), timeout=15)

    def worker(run_id, opportunity):

        repository = OpportunityRepository(
            context["storage"]
        )

        barrier.wait()

        return repository.ingest(
            opportunity.model_copy(deep=True),
            run_id,
        )

    with ThreadPoolExecutor(
        max_workers=len(records)
    ) as executor:

        futures = [
            executor.submit(worker, run_id, opportunity)
            for run_id, opportunity in records
        ]

        return [
            future.result(timeout=45)
            for future in futures
        ]


def seed_listing(context):

    run_id = context["start_run"]()

    repository = OpportunityRepository(
        context["storage"]
    )

    result = repository.ingest(
        context["opportunity"],
        run_id,
    )

    assert result.outcome == "inserted"

    context["manager"].finish_run(
        run_id=run_id,
        status="completed",
        received=1,
    )

    return result


def test_concurrent_identical_updates(context):

    from datetime import timedelta

    initial = seed_listing(context)

    base = context["opportunity"]

    updated = Opportunity.model_validate({
        **base.model_dump(mode="python"),
        "title": "Senior Data Engineer",
        "collected_at": (
            base.collected_at + timedelta(seconds=1)
        ),
    })

    run_ids = [
        context["start_run"]()
        for _ in range(WORKERS)
    ]

    results = concurrent_updates(
        context,
        [
            (run_id, updated)
            for run_id in run_ids
        ],
    )

    outcomes = [
        result.outcome
        for result in results
    ]

    assert outcomes.count("updated") == 1
    assert outcomes.count("unchanged") == WORKERS - 1

    assert all(
        result.source_listing_id
        == initial.source_listing_id
        for result in results
    )

    snapshot = context["snapshot"]()

    assert len(snapshot["listings"]) == 1
    assert len(snapshot["history"]) == 2
    assert len(snapshot["observations"]) == WORKERS + 1
    assert snapshot["invalid"] == []

    listing = snapshot["listings"][0]

    assert listing["content_version"] == 2
    assert listing["title"] == updated.title
    assert listing["last_seen_at"] == updated.collected_at

    assert [
        row["content_version"]
        for row in snapshot["history"]
    ] == [1, 2]

    finalized = [
        context["manager"].finish_run(
            run_id=run_id,
            status="completed",
            received=1,
        )
        for run_id in run_ids
    ]

    assert sum(
        row["records_updated"]
        for row in finalized
    ) == 1

    assert sum(
        row["records_unchanged"]
        for row in finalized
    ) == WORKERS - 1


@pytest.mark.parametrize("attempt", range(3))
def test_concurrent_out_of_order_updates(context, attempt):

    from datetime import timedelta

    from scrapers.utils.hashing import (
        generate_content_hash,
    )

    initial = seed_listing(context)

    base = context["opportunity"]

    records = []

    for index in range(1, WORKERS + 1):

        opportunity = Opportunity.model_validate({
            **base.model_dump(mode="python"),
            "title": f"Data Engineer Version {index}",
            "collected_at": (
                base.collected_at
                + timedelta(seconds=index)
            ),
            "raw_payload": {"version": index},
        })

        records.append(
            (
                context["start_run"](),
                opportunity,
            )
        )

    newest = records[-1][1]

    results = concurrent_updates(
        context,
        records,
    )

    outcomes = [
        result.outcome
        for result in results
    ]

    assert set(outcomes) <= {
        "updated",
        "stale",
    }

    updated_count = outcomes.count("updated")
    stale_count = outcomes.count("stale")

    assert updated_count >= 1

    assert updated_count + stale_count == WORKERS

    assert results[-1].outcome == "updated"

    assert all(
        result.source_listing_id
        == initial.source_listing_id
        for result in results
    )

    snapshot = context["snapshot"]()

    assert len(snapshot["listings"]) == 1

    assert len(snapshot["history"]) == (
        updated_count + 1
    )

    assert len(snapshot["observations"]) == (
        WORKERS + 1
    )

    assert snapshot["invalid"] == []

    listing = snapshot["listings"][0]

    assert listing["title"] == newest.title

    assert listing["last_seen_at"] == (
        newest.collected_at
    )

    assert listing["collected_at"] == (
        newest.collected_at
    )

    assert listing["raw_payload"] == {
        "version": WORKERS
    }

    assert listing["content_hash"] == (
        generate_content_hash(newest)
    )

    assert listing["content_version"] == (
        updated_count + 1
    )

    history = snapshot["history"]

    assert [
        row["content_version"]
        for row in history
    ] == list(
        range(1, updated_count + 2)
    )

    timestamps = [
        row["observed_at"]
        for row in history
    ]

    assert timestamps == sorted(set(timestamps))

    assert history[-1]["content_hash"] == (
        listing["content_hash"]
    )

    observations = {
        row["collection_run_id"]: row
        for row in snapshot["observations"]
    }

    for (run_id, opportunity), result in zip(
        records,
        results,
    ):

        observation = observations[run_id]

        assert observation["outcome"] == (
            result.outcome
        )

        assert observation["observed_at"] == (
            opportunity.collected_at
        )

    finalized = [
        context["manager"].finish_run(
            run_id=run_id,
            status="completed",
            received=1,
        )
        for run_id, _ in records
    ]

    assert sum(
        row["records_updated"]
        for row in finalized
    ) == updated_count

    assert sum(
        row["records_stale"]
        for row in finalized
    ) == stale_count

    print(
        f"Attempt {attempt + 1}: "
        f"updated={updated_count}, "
        f"stale={stale_count}, "
        f"versions={len(history)}"
    )


def test_concurrent_equal_timestamp_conflicts(context):

    initial = seed_listing(context)

    base = context["opportunity"]

    records = []

    for index in range(WORKERS):

        opportunity = Opportunity.model_validate({
            **base.model_dump(mode="python"),
            "title": f"Conflicting title {index}",
        })

        records.append(
            (
                context["start_run"](),
                opportunity,
            )
        )

    results = concurrent_updates(
        context,
        records,
    )

    assert all(
        result.outcome == "conflicted"
        for result in results
    )

    assert all(
        result.source_listing_id
        == initial.source_listing_id
        for result in results
    )

    snapshot = context["snapshot"]()

    assert len(snapshot["listings"]) == 1
    assert len(snapshot["history"]) == 1
    assert len(snapshot["observations"]) == WORKERS + 1
    assert len(snapshot["invalid"]) == WORKERS

    listing = snapshot["listings"][0]

    assert listing["title"] == base.title
    assert listing["content_version"] == 1

    assert all(
        row["error_code"]
        == "EqualTimestampContentMismatch"
        for row in snapshot["invalid"]
    )

    finalized = [
        context["manager"].finish_run(
            run_id=run_id,
            status="completed",
            received=1,
        )
        for run_id, _ in records
    ]

    assert sum(
        row["records_conflicted"]
        for row in finalized
    ) == WORKERS

    assert sum(
        row["records_invalid"]
        for row in finalized
    ) == 0


def test_finalization_waits_for_ingestion(
    context,
    monkeypatch,
):

    from threading import Event

    storage = context["storage"]
    manager = context["manager"]

    repository = OpportunityRepository(storage)

    run_id = context["start_run"]()

    write_ready = Event()
    release_write = Event()
    finalization_started = Event()

    original = repository._insert_observation

    def paused_observation(*args, **kwargs):

        result = original(*args, **kwargs)

        write_ready.set()

        if not release_write.wait(timeout=15):

            raise TimeoutError(
                "Timed out waiting to release ingestion"
            )

        return result

    monkeypatch.setattr(
        repository,
        "_insert_observation",
        paused_observation,
    )

    def finalize():

        finalization_started.set()

        return manager.finish_run(
            run_id=run_id,
            status="completed",
            received=1,
        )

    with ThreadPoolExecutor(
        max_workers=2
    ) as executor:

        ingestion_future = executor.submit(
            repository.ingest,
            context["opportunity"],
            run_id,
        )

        try:

            assert write_ready.wait(timeout=10)

            finalization_future = executor.submit(
                finalize,
            )

            assert finalization_started.wait(
                timeout=5
            )

            from time import monotonic, sleep

            deadline = monotonic() + 5

            waiting = False

            while monotonic() < deadline:

                with storage.transaction(
                    read_only=True
                ) as conn:

                    row = conn.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM pg_stat_activity
                            WHERE datname = current_database()
                              AND pid <> pg_backend_pid()
                              AND application_name =
                                  'matchpoint_ingestion'
                              AND wait_event_type = 'Lock'
                              AND query ILIKE
                                  '%collection_runs%'
                              AND query ILIKE
                                  '%FOR UPDATE%'
                        ) AS waiting
                        """
                    ).fetchone()

                if row["waiting"]:

                    waiting = True

                    break

                sleep(0.05)

            assert waiting, (
                "Finalization did not wait for ingestion lock"
            )

            assert not finalization_future.done()

            assert manager.get_run(
                run_id
            )["status"] == "running"

        finally:

            release_write.set()

        ingested = ingestion_future.result(
            timeout=30
        )

        finalized = finalization_future.result(
            timeout=30
        )

    assert ingested.outcome == "inserted"

    assert finalized["status"] == "completed"
    assert finalized["records_received"] == 1
    assert finalized["records_inserted"] == 1

    snapshot = context["snapshot"]()

    assert len(snapshot["listings"]) == 1
    assert len(snapshot["history"]) == 1
    assert len(snapshot["observations"]) == 1


def test_concurrent_invalid_record_retries(context):

    from scrapers.storage.invalid_records import (
        InvalidRecordRepository,
    )

    run_id = context["start_run"]()

    barrier = Barrier(WORKERS, timeout=15)

    def worker():

        repository = InvalidRecordRepository(
            context["storage"]
        )

        barrier.wait()

        return repository.record(
            run_id=run_id,
            source_name="wuzzuf",
            failure_stage="validation",
            error_code="MissingTitle",
            error_message="Required title is missing",
            record_payload={"title": None},
        )

    with ThreadPoolExecutor(
        max_workers=WORKERS
    ) as executor:

        futures = [
            executor.submit(worker)
            for _ in range(WORKERS)
        ]

        results = [
            future.result(timeout=45)
            for future in futures
        ]

    assert sum(
        result.inserted
        for result in results
    ) == 1

    assert len({
        result.invalid_record_id
        for result in results
    }) == 1

    assert len({
        result.rejection_hash
        for result in results
    }) == 1

    snapshot = context["snapshot"]()

    assert len(snapshot["invalid"]) == 1
    assert snapshot["listings"] == []
    assert snapshot["history"] == []
    assert snapshot["observations"] == []

    finalized = context["manager"].finish_run(
        run_id=run_id,
        status="completed",
        received=1,
    )

    assert finalized["records_invalid"] == 1
    assert finalized["records_received"] == 1
    assert finalized["records_conflicted"] == 0


def test_concurrent_finalization_attempts(context):

    from scrapers.storage.collection_runs import (
        CollectionRunError,
    )

    run_id = context["start_run"]()

    repository = OpportunityRepository(
        context["storage"]
    )

    result = repository.ingest(
        context["opportunity"],
        run_id,
    )

    assert result.outcome == "inserted"

    barrier = Barrier(WORKERS, timeout=15)

    def worker():

        barrier.wait()

        try:

            result = context["manager"].finish_run(
                run_id=run_id,
                status="completed",
                received=1,
            )

            return ("completed", result)

        except CollectionRunError as error:

            return ("rejected", str(error))

    with ThreadPoolExecutor(
        max_workers=WORKERS
    ) as executor:

        futures = [
            executor.submit(worker)
            for _ in range(WORKERS)
        ]

        results = [
            future.result(timeout=45)
            for future in futures
        ]

    outcomes = [
        outcome
        for outcome, _ in results
    ]

    assert outcomes.count("completed") == 1
    assert outcomes.count("rejected") == WORKERS - 1

    final = context["manager"].get_run(run_id)

    assert final["status"] == "completed"
    assert final["records_received"] == 1
    assert final["records_inserted"] == 1

    successful = [
        result
        for outcome, result in results
        if outcome == "completed"
    ][0]

    assert final == successful

    snapshot = context["snapshot"]()

    assert len(snapshot["listings"]) == 1
    assert len(snapshot["history"]) == 1
    assert len(snapshot["observations"]) == 1
    assert snapshot["invalid"] == []
