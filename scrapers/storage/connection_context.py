from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID


class ProtectedConnectionError(RuntimeError):
    pass


class ProtectedConnectionLostError(ProtectedConnectionError):
    pass


@dataclass(frozen=True, slots=True)
class ProtectedConnection:
    storage: object
    connection: object
    run_id: UUID


_active_connection: ContextVar[
    ProtectedConnection | None
] = ContextVar(
    "matchpoint_protected_connection",
    default=None,
)


def get_protected_connection():
    return _active_connection.get()


@contextmanager
def bind_protected_connection(
    *,
    storage,
    connection,
    run_id: UUID,
):
    if get_protected_connection() is not None:
        raise ProtectedConnectionError(
            "A protected connection is already active"
        )

    token = _active_connection.set(
        ProtectedConnection(
            storage=storage,
            connection=connection,
            run_id=run_id,
        )
    )

    try:
        yield
    finally:
        _active_connection.reset(token)