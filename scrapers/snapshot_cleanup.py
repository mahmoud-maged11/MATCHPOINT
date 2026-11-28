import argparse
import json
import sys

from scrapers.storage.postgres import (
    PostgresSettings,
    PostgresStorage,
)

from scrapers.storage.snapshot_config import (
    create_snapshot_store,
)

from scrapers.storage.snapshot_retention import (
    DEFAULT_RETENTION_DAYS,
    SnapshotRetentionManager,
)


EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_PARTIAL = 2


def positive_integer(value):

    try:

        number = int(value)

    except ValueError:

        raise argparse.ArgumentTypeError(
            "Expected a positive integer"
        ) from None

    if number < 1:

        raise argparse.ArgumentTypeError(
            "Expected a positive integer"
        )

    return number


def parse_args(argv=None):

    parser = argparse.ArgumentParser(
        description="MATCHPOINT snapshot retention and cleanup"
    )

    parser.add_argument(
        "--postgres-host",
        default=None,
    )

    parser.add_argument(
        "--postgres-db",
        default=None,
    )

    parser.add_argument(
        "--retention-days",
        type=positive_integer,
        default=DEFAULT_RETENTION_DAYS,
    )

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview eligible snapshots without deleting",
    )

    mode.add_argument(
        "--apply",
        action="store_true",
        help="Delete eligible expired snapshots",
    )

    return parser.parse_args(argv)


def create_manager(args):

    settings = PostgresSettings.from_config(
        host=args.postgres_host,
        database=args.postgres_db,
    )

    storage = PostgresStorage(settings)

    storage.health_check()

    store = create_snapshot_store(
        settings=settings,
    )

    return SnapshotRetentionManager(
        storage,
        store,
        retention_days=args.retention_days,
    )


def build_summary(result):

    return {
        "operation": "snapshot_cleanup",
        "status": (
            "partial"
            if result.errors
            else "completed"
        ),
        "dry_run": result.dry_run,
        "retention_days": result.retention_days,
        "cutoff": result.cutoff.isoformat(),
        "scanned": result.scanned,
        "eligible": result.eligible,
        "deleted": result.deleted,
        "retained": result.retained,
        "skipped": result.skipped,
        "errors": result.errors,
        "eligible_bytes": result.eligible_bytes,
        "reclaimed_bytes": result.reclaimed_bytes,
        "decisions": [
            {
                "run_id": (
                    str(item.run_id)
                    if item.run_id is not None
                    else None
                ),
                "filename": item.filename,
                "action": item.action,
                "reason": item.reason,
                "size_bytes": item.size_bytes,
            }
            for item in result.decisions
        ],
    }


def main(argv=None):

    args = parse_args(argv)

    stage = "initialization"

    try:

        manager = create_manager(args)

        stage = "cleanup"

        result = manager.cleanup(
            dry_run=not args.apply,
        )

        print(
            json.dumps(
                build_summary(result),
                ensure_ascii=False,
            )
        )

        if result.errors:

            return EXIT_PARTIAL

        return EXIT_SUCCESS

    except Exception as error:

        print(
            json.dumps({
                "operation": "snapshot_cleanup",
                "status": "failed",
                "stage": stage,
                "error_type": type(error).__name__,
                "dry_run": not args.apply,
            })
        )

        return EXIT_FAILURE


if __name__ == "__main__":

    sys.exit(main())
