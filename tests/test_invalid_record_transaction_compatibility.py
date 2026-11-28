
import ast
import inspect
from types import SimpleNamespace

import pytest

from psycopg.pq import TransactionStatus

from scrapers.storage import invalid_records


def load_transaction_guard():

    tree = ast.parse(
        inspect.getsource(invalid_records)
    )

    matches = []

    for node in ast.walk(tree):

        if not isinstance(node, ast.If):
            continue

        for statement in node.body:

            if (
                isinstance(statement, ast.Raise)
                and statement.exc is not None
                and "Shared connection requires an active transaction"
                in ast.unparse(statement.exc)
            ):
                matches.append(node.test)

    assert len(matches) == 1

    expression = ast.Expression(
        body=matches[0]
    )

    return compile(
        ast.fix_missing_locations(expression),
        "<transaction_guard>",
        "eval",
    )


@pytest.mark.parametrize(
    "autocommit,status,closed,allowed",
    [
        (False, TransactionStatus.IDLE, False, True),
        (False, TransactionStatus.INTRANS, False, True),
        (True, TransactionStatus.INTRANS, False, True),
        (True, TransactionStatus.IDLE, False, False),
        (False, TransactionStatus.INERROR, False, False),
        (True, TransactionStatus.INERROR, False, False),
        (False, TransactionStatus.ACTIVE, False, False),
        (True, TransactionStatus.ACTIVE, False, False),
        (False, TransactionStatus.UNKNOWN, False, False),
        (True, TransactionStatus.UNKNOWN, False, False),
        (False, TransactionStatus.IDLE, True, False),
        (True, TransactionStatus.INTRANS, True, False),
    ],
)
def test_shared_transaction_guard(
    autocommit,
    status,
    closed,
    allowed,
):

    connection = SimpleNamespace(
        autocommit=autocommit,
        closed=closed,
        info=SimpleNamespace(
            transaction_status=status,
        ),
    )

    rejected = eval(
        load_transaction_guard(),
        {
            "connection": connection,
            "TransactionStatus": TransactionStatus,
        },
    )

    assert (not rejected) == allowed
