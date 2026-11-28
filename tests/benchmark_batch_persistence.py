import gc
import statistics
import time
import tracemalloc

from uuid import uuid4

import pytest

from test_incremental_pipeline import (
    pipeline,
    make_scraper,
)

from scrapers.models import Opportunity
from scrapers.storage.opportunities import (
    OpportunityRepository,
)


RECORD_COUNT = 1000

BATCH_SIZES = (
    1,
    25,
    50,
    100,
    250,
    500,
)


def cleanup(storage, run_id):

    with storage.transaction() as conn:

        for table, column in (
            (
                "source_checkpoints",
                "last_successful_run_id",
            ),
            (
                "ingestion_observations",
                "collection_run_id",
            ),
            (
                "source_listing_history",
                "collection_run_id",
            ),
            (
                "invalid_records",
                "collection_run_id",
            ),
            (
                "source_listings",
                "last_collection_run_id",
            ),
            (
                "collection_runs",
                "run_id",
            ),
        ):

            conn.execute(
                f"DELETE FROM bronze.{table} "
                f"WHERE {column} = %s",
                (run_id,),
            )


def verify(storage, run_id):

    with storage.transaction(
        read_only=True
    ) as conn:

        for table, column in (
            (
                "source_listings",
                "last_collection_run_id",
            ),
            (
                "source_listing_history",
                "collection_run_id",
            ),
            (
                "ingestion_observations",
                "collection_run_id",
            ),
        ):

            count = conn.execute(
                f"SELECT COUNT(*) AS n "
                f"FROM bronze.{table} "
                f"WHERE {column} = %s",
                (run_id,),
            ).fetchone()["n"]

            assert count == RECORD_COUNT, (
                table,
                count,
            )

        rows = conn.execute(
            """
            SELECT
                source_opportunity_id,
                content_hash,
                content_version
            FROM bronze.source_listings
            WHERE last_collection_run_id = %s
            ORDER BY source_opportunity_id
            """,
            (run_id,),
        ).fetchall()

        assert all(
            row["content_version"] == 1
            for row in rows
        )

        return rows


def test_batch_performance(pipeline):

    orchestrator = pipeline["orchestrator"]
    storage = orchestrator.storage

    scraper = make_scraper()

    sample = scraper.run_with_result(
        run_id=uuid4()
    )

    assert sample.accepted_count == 3

    template = sample.opportunities[0]

    records = []

    for index in range(RECORD_COUNT):

        payload = template.model_dump(
            mode="python"
        )

        payload.update({
            "source_opportunity_id":
                f"benchmark-{index:06d}",
            "source_url":
                f"https://egyincs.com/benchmark/{index}",
        })

        records.append(
            Opportunity.model_validate(payload)
        )

    repository = OpportunityRepository(storage)

    results = []
    expected = None

    for batch_size in BATCH_SIZES:

        run_id = uuid4()

        try:

            orchestrator.start_collection(
                scraper=scraper,
                collection_mode="api",
                collection_scope="benchmark",
                run_id=run_id,
            )

            gc.collect()

            tracemalloc.start()

            started = time.perf_counter()

            try:

                with orchestrator._acquire_run_lock(
                    run_id
                ):

                    for offset in range(
                        0,
                        RECORD_COUNT,
                        batch_size,
                    ):

                        batch = records[
                            offset:offset + batch_size
                        ]

                        if batch_size == 1:

                            outcomes = (
                                repository.ingest(
                                    batch[0],
                                    run_id,
                                ),
                            )

                        else:

                            outcomes = (
                                repository.ingest_many(
                                    batch,
                                    run_id,
                                )
                            )

                        assert len(outcomes) == len(batch)

                        assert all(
                            item.outcome == "inserted"
                            for item in outcomes
                        )

                elapsed = (
                    time.perf_counter() - started
                )

                _, peak = (
                    tracemalloc.get_traced_memory()
                )

            finally:

                tracemalloc.stop()

            rows = verify(storage, run_id)

            if expected is None:

                expected = rows

            else:

                assert rows == expected

            results.append({
                "batch_size": batch_size,
                "seconds": elapsed,
                "records_per_second":
                    RECORD_COUNT / elapsed,
                "peak_mib":
                    peak / (1024 ** 2),
                "transactions":
                    (
                        RECORD_COUNT
                        + batch_size - 1
                    ) // batch_size,
            })

        finally:

            cleanup(storage, run_id)

    baseline = results[0]["seconds"]

    print("\n========== BATCH BENCHMARK ==========")

    print(
        f"{'Batch':>8}"
        f"{'Seconds':>12}"
        f"{'Rows/sec':>14}"
        f"{'Peak MiB':>12}"
        f"{'Txns':>10}"
        f"{'Speedup':>12}"
    )

    for row in results:

        print(
            f"{row['batch_size']:>8}"
            f"{row['seconds']:>12.3f}"
            f"{row['records_per_second']:>14.2f}"
            f"{row['peak_mib']:>12.3f}"
            f"{row['transactions']:>10}"
            f"{baseline / row['seconds']:>11.2f}x"
        )

    fastest = min(
        results,
        key=lambda row: row["seconds"],
    )

    print(
        "\nFastest batch size:",
        fastest["batch_size"],
    )

    print(
        "Maximum observed speedup:",
        round(
            baseline / fastest["seconds"],
            2,
        ),
    )

    print("PASS: Identical persistence results")
    print("PASS: Benchmark cleanup")
