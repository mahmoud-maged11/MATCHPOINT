from __future__ import annotations

import os
import errno
import msvcrt

from pathlib import Path
from contextlib import contextmanager, ExitStack


SUPPORTED_SOURCES = frozenset({
    "egyincs",
    "wuzzuf",
    "forasna",
    "devpost",
    "un_volunteers",
    "itida",
    "nti",
    "bayt",
})


class SourceAlreadyRunningError(RuntimeError):
    pass


class LocalSourceLock:

    def __init__(self, directory=None):

        if directory is None:

            directory = (
                Path(os.environ["LOCALAPPDATA"])
                / "MATCHPOINT"
                / "Locks"
            )

        self.directory = Path(directory).resolve()

        self.directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    @staticmethod
    def scopes(source, scope):

        if source not in SUPPORTED_SOURCES:

            raise ValueError(
                f"Unsupported source: {source}"
            )

        if source == "egyincs":

            if scope == "all":
                return ("jobs", "lp_course")

            if scope in ("jobs", "lp_course"):
                return (scope,)

            raise ValueError(
                f"Invalid scope: {scope}"
            )

        if scope != "default":

            raise ValueError(
                f"Invalid scope: {scope}"
            )

        return ("default",)

    @contextmanager
    def _acquire(self, path):

        handle = path.open("a+b")

        acquired = False

        try:

            if path.stat().st_size == 0:

                handle.write(b"\x00")
                handle.flush()

            handle.seek(0)

            try:

                msvcrt.locking(
                    handle.fileno(),
                    msvcrt.LK_NBLCK,
                    1,
                )

                acquired = True

            except OSError as error:

                if (
                    error.errno in (
                        errno.EACCES,
                        errno.EAGAIN,
                        errno.EDEADLK,
                    )
                    or getattr(
                        error, "winerror", None
                    ) in (32, 33)
                ):

                    raise SourceAlreadyRunningError(
                        f"Source lock unavailable: {path.name}"
                    ) from error

                raise

            yield

        finally:

            try:

                if acquired:

                    handle.seek(0)

                    msvcrt.locking(
                        handle.fileno(),
                        msvcrt.LK_UNLCK,
                        1,
                    )

            finally:

                handle.close()

    @contextmanager
    def acquire(self, source, scope="default"):

        scopes = self.scopes(source, scope)

        with ExitStack() as stack:

            for endpoint in sorted(scopes):

                path = self.directory / (
                    f"{source}.{endpoint}.lock"
                )

                stack.enter_context(
                    self._acquire(path)
                )

            yield
