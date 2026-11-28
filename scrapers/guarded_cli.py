from __future__ import annotations

import sys

from scrapers.source_lock import (
    LocalSourceLock,
    SourceAlreadyRunningError,
)


LOCK_CONFLICT_EXIT_CODE = 4


def resolve_scope(source, endpoint=None):

    if source == "egyincs":

        scope = endpoint or "all"

        LocalSourceLock.scopes(source, scope)

        return scope

    LocalSourceLock.scopes(source, "default")

    return "default"


def execute_guarded(
    source,
    endpoint,
    operation,
    *,
    lock_manager=None,
):

    if lock_manager is None:

        lock_manager = LocalSourceLock()

    scope = resolve_scope(source, endpoint)

    try:

        with lock_manager.acquire(source, scope):

            return operation()

    except SourceAlreadyRunningError as error:

        print(
            f"Collection blocked: {source}:{scope}. {error}",
            file=sys.stderr,
        )

        return LOCK_CONFLICT_EXIT_CODE


def main():
    from scrapers.main import main as production_main
    return production_main()


if __name__ == "__main__":

    raise SystemExit(main())
