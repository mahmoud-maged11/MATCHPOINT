import pytest

from scrapers.source_lock import LocalSourceLock

from scrapers.guarded_cli import (
    execute_guarded,
    resolve_scope,
    LOCK_CONFLICT_EXIT_CODE,
)


@pytest.fixture
def manager(tmp_path):

    return LocalSourceLock(tmp_path)


def test_operation_executes_once(manager):

    calls = []

    def operation():

        calls.append(1)

        return 0

    result = execute_guarded(
        "bayt",
        None,
        operation,
        lock_manager=manager,
    )

    assert result == 0
    assert calls == [1]


def test_duplicate_never_calls_operation(manager):

    def operation():

        pytest.fail("Duplicate operation executed")

    with manager.acquire("bayt"):

        result = execute_guarded(
            "bayt",
            None,
            operation,
            lock_manager=manager,
        )

    assert result == LOCK_CONFLICT_EXIT_CODE


def test_different_source_allowed(manager):

    with manager.acquire("bayt"):

        result = execute_guarded(
            "wuzzuf",
            None,
            lambda: 0,
            lock_manager=manager,
        )

    assert result == 0


@pytest.mark.parametrize(
    "endpoint",
    ["jobs", "lp_course"],
)
def test_all_blocks_endpoint(manager, endpoint):

    with manager.acquire("egyincs", "all"):

        result = execute_guarded(
            "egyincs",
            endpoint,
            lambda: pytest.fail("Overlap executed"),
            lock_manager=manager,
        )

    assert result == LOCK_CONFLICT_EXIT_CODE


def test_independent_endpoints(manager):

    with manager.acquire("egyincs", "jobs"):

        result = execute_guarded(
            "egyincs",
            "lp_course",
            lambda: 0,
            lock_manager=manager,
        )

    assert result == 0


def test_endpoint_blocks_all(manager):

    with manager.acquire("egyincs", "jobs"):

        result = execute_guarded(
            "egyincs",
            None,
            lambda: pytest.fail("Overlap executed"),
            lock_manager=manager,
        )

    assert result == LOCK_CONFLICT_EXIT_CODE


@pytest.mark.parametrize(
    "exit_code",
    [0, 1, 2, 3],
)
def test_original_exit_code_preserved(
    manager,
    exit_code,
):

    result = execute_guarded(
        "bayt",
        None,
        lambda: exit_code,
        lock_manager=manager,
    )

    assert result == exit_code


def test_exception_releases_lock(manager):

    def operation():

        raise RuntimeError("Intentional failure")

    with pytest.raises(
        RuntimeError,
        match="Intentional failure",
    ):

        execute_guarded(
            "bayt",
            None,
            operation,
            lock_manager=manager,
        )

    with manager.acquire("bayt"):
        pass


def test_system_exit_releases_lock(manager):

    def operation():

        raise SystemExit(2)

    with pytest.raises(SystemExit) as error:

        execute_guarded(
            "bayt",
            None,
            operation,
            lock_manager=manager,
        )

    assert error.value.code == 2

    with manager.acquire("bayt"):
        pass


@pytest.mark.parametrize(
    "source,endpoint,expected",
    [
        ("egyincs", None, "all"),
        ("egyincs", "all", "all"),
        ("egyincs", "jobs", "jobs"),
        ("egyincs", "lp_course", "lp_course"),
        ("bayt", None, "default"),
        ("wuzzuf", None, "default"),
        ("forasna", None, "default"),
        ("itida", None, "default"),
        ("nti", None, "default"),
        ("devpost", None, "default"),
        ("un_volunteers", None, "default"),
    ],
)
def test_scope_resolution(
    source,
    endpoint,
    expected,
):

    assert resolve_scope(
        source,
        endpoint,
    ) == expected


def test_invalid_source():

    with pytest.raises(ValueError):

        resolve_scope("invalid")


def test_invalid_endpoint():

    with pytest.raises(ValueError):

        resolve_scope("egyincs", "invalid")


def test_lock_held_during_operation(manager):

    def operation():

        result = execute_guarded(
            "bayt",
            None,
            lambda: pytest.fail("Nested run executed"),
            lock_manager=manager,
        )

        assert result == LOCK_CONFLICT_EXIT_CODE

        return 0

    assert execute_guarded(
        "bayt",
        None,
        operation,
        lock_manager=manager,
    ) == 0
