import os
import sys
import subprocess

import pytest

from scrapers.source_lock import (
    LocalSourceLock,
    SourceAlreadyRunningError,
)


pytestmark = pytest.mark.skipif(
    os.name != "nt",
    reason="Windows file locking tests",
)


@pytest.fixture
def manager(tmp_path):

    return LocalSourceLock(tmp_path)


def blocked(manager, source, scope="default"):

    with pytest.raises(SourceAlreadyRunningError):

        with manager.acquire(source, scope):
            pass


def test_duplicate_source(manager):

    with manager.acquire("bayt"):

        blocked(manager, "bayt")


def test_independent_sources(manager):

    with manager.acquire("bayt"):

        with manager.acquire("wuzzuf"):
            pass


def test_independent_endpoints(manager):

    with manager.acquire("egyincs", "jobs"):

        with manager.acquire("egyincs", "lp_course"):
            pass


@pytest.mark.parametrize(
    "scope",
    ["jobs", "lp_course"],
)
def test_all_blocks_endpoint(manager, scope):

    with manager.acquire("egyincs", "all"):

        blocked(manager, "egyincs", scope)


@pytest.mark.parametrize(
    "scope",
    ["jobs", "lp_course"],
)
def test_endpoint_blocks_all(manager, scope):

    with manager.acquire("egyincs", scope):

        blocked(manager, "egyincs", "all")


def test_duplicate_all(manager):

    with manager.acquire("egyincs", "all"):

        blocked(manager, "egyincs", "all")


def test_partial_acquisition_cleanup(manager):

    with manager.acquire("egyincs", "lp_course"):

        blocked(manager, "egyincs", "all")

        with manager.acquire("egyincs", "jobs"):
            pass


def test_exception_cleanup(manager):

    with pytest.raises(RuntimeError):

        with manager.acquire("bayt"):

            raise RuntimeError("Intentional failure")

    with manager.acquire("bayt"):
        pass


def test_existing_file_is_not_active_lock(manager):

    path = manager.directory / "bayt.default.lock"

    path.write_bytes(b"\x00")

    with manager.acquire("bayt"):
        pass


@pytest.mark.parametrize(
    "source,scope",
    [
        ("unknown", "default"),
        ("bayt", "jobs"),
        ("egyincs", "invalid"),
        ("../bayt", "default"),
    ],
)
def test_invalid_scope(manager, source, scope):

    with pytest.raises(ValueError):

        with manager.acquire(source, scope):
            pass


def test_cross_process_crash_cleanup(manager):

    code = (
        "import sys,time;"
        "from scrapers.source_lock import LocalSourceLock;"
        "lock=LocalSourceLock(sys.argv[1]);"
        "ctx=lock.acquire('bayt');"
        "ctx.__enter__();"
        "print('LOCKED',flush=True);"
        "time.sleep(60)"
    )

    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            code,
            str(manager.directory),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:

        assert process.stdout.readline().strip() == "LOCKED"

        blocked(manager, "bayt")

    finally:

        process.kill()
        process.communicate(timeout=10)

    with manager.acquire("bayt"):
        pass
