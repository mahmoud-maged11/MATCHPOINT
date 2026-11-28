from contextlib import contextmanager
from unittest.mock import Mock
from uuid import uuid4

import pytest

from scrapers.storage.opportunities import (
    OpportunityRepository,
)


@pytest.fixture
def context(monkeypatch):

    storage = Mock()
    connection = Mock()

    events = []

    @contextmanager
    def transaction():

        events.append("begin")

        try:

            yield connection

        except BaseException:

            events.append("rollback")
            raise

        else:

            events.append("commit")

    storage.transaction.side_effect = transaction

    repository = OpportunityRepository(storage)

    prepare = Mock(
        side_effect=lambda opportunity, run_id: opportunity
    )

    run = {"status": "running"}

    get_run = Mock(return_value=run)

    persist = Mock(
        side_effect=lambda conn, run, run_id, item: item
    )

    monkeypatch.setattr(
        repository,
        "_prepare_ingestion",
        prepare,
    )

    monkeypatch.setattr(
        repository,
        "_get_run",
        get_run,
    )

    monkeypatch.setattr(
        repository,
        "_ingest_prepared",
        persist,
    )

    return {
        "repository": repository,
        "storage": storage,
        "connection": connection,
        "events": events,
        "prepare": prepare,
        "get_run": get_run,
        "persist": persist,
        "run": run,
        "run_id": uuid4(),
    }


@pytest.mark.parametrize("size", [1, 10, 100, 1000])
def test_batch_uses_one_transaction(context, size):

    records = list(range(size))

    result = context["repository"].ingest_many(
        records,
        context["run_id"],
    )

    assert result == tuple(records)

    assert context["events"] == [
        "begin",
        "commit",
    ]

    assert context["prepare"].call_count == size

    context["get_run"].assert_called_once_with(
        context["connection"],
        context["run_id"],
    )

    assert context["persist"].call_count == size

    assert [
        call.args[-1]
        for call in context["persist"].call_args_list
    ] == records


def test_empty_batch_does_not_open_transaction(context):

    result = context["repository"].ingest_many(
        [],
        context["run_id"],
    )

    assert result == ()

    context["storage"].transaction.assert_not_called()

    context["get_run"].assert_not_called()


def test_tuple_batch_supported(context):

    assert context["repository"].ingest_many(
        (1, 2, 3),
        context["run_id"],
    ) == (1, 2, 3)


def test_batch_preserves_input_order(context):

    records = [3, 1, 3, 2]

    result = context["repository"].ingest_many(
        records,
        context["run_id"],
    )

    assert result == tuple(records)


def test_invalid_run_id_rejected(context):

    with pytest.raises(TypeError, match="UUID"):

        context["repository"].ingest_many(
            [1],
            "invalid",
        )

    assert context["events"] == []


@pytest.mark.parametrize(
    "records",
    [
        None,
        "invalid",
        {},
        100,
        iter([1, 2]),
    ],
)
def test_invalid_batch_type(context, records):

    with pytest.raises(TypeError, match="list or tuple"):

        context["repository"].ingest_many(
            records,
            context["run_id"],
        )

    assert context["events"] == []


def test_oversized_batch_rejected(context):

    with pytest.raises(ValueError, match="1000"):

        context["repository"].ingest_many(
            list(range(1001)),
            context["run_id"],
        )

    assert context["events"] == []

    context["prepare"].assert_not_called()


def test_preparation_failure_prevents_writes(context):

    context["prepare"].side_effect = [
        1,
        ValueError("Invalid opportunity"),
    ]

    with pytest.raises(
        ValueError,
        match="Invalid opportunity",
    ):

        context["repository"].ingest_many(
            [1, 2, 3],
            context["run_id"],
        )

    assert context["events"] == []

    context["persist"].assert_not_called()


def test_batch_failure_rolls_back(context):

    context["persist"].side_effect = [
        1,
        RuntimeError("Persistence failure"),
    ]

    with pytest.raises(
        RuntimeError,
        match="Persistence failure",
    ):

        context["repository"].ingest_many(
            [1, 2, 3],
            context["run_id"],
        )

    assert context["events"] == [
        "begin",
        "rollback",
    ]

    assert context["persist"].call_count == 2


def test_single_ingest_uses_shared_engine(context):

    result = context["repository"].ingest(
        1,
        context["run_id"],
    )

    assert result == 1

    assert context["events"] == [
        "begin",
        "commit",
    ]

    context["persist"].assert_called_once_with(
        context["connection"],
        context["run"],
        context["run_id"],
        1,
    )


def test_run_lookup_failure_rolls_back(context):

    context["get_run"].side_effect = RuntimeError(
        "Run lookup failed"
    )

    with pytest.raises(
        RuntimeError,
        match="Run lookup failed",
    ):

        context["repository"].ingest_many(
            [1, 2],
            context["run_id"],
        )

    assert context["events"] == [
        "begin",
        "rollback",
    ]

    context["persist"].assert_not_called()
