import argparse
import json
import sys
import tempfile

from pathlib import Path
from uuid import UUID, uuid4

from scrapers.sources.wuzzuf import WuzzufScraper
from scrapers.sources.wuzzuf_api import WuzzufAPIScraper
from scrapers.sources.forasna import ForasnaScraper
from scrapers.sources.egyincs import EgyincsScraper
from scrapers.sources.itida import ITIDAScraper
from scrapers.sources.nti import NTIScraper
from scrapers.sources.bayt import BaytScraper
from scrapers.sources.devpost import DevpostScraper
from scrapers.sources.un_volunteers import UNVolunteersScraper


SOURCES = (
    "wuzzuf",
    "forasna",
    "egyincs",
    "itida",
    "nti",
    "bayt",
    "devpost",
    "un_volunteers",
)

API_SOURCES = {
    "egyincs": EgyincsScraper,
    "devpost": DevpostScraper,
    "un_volunteers": UNVolunteersScraper,
}

HTML_SOURCES = {
    "forasna": ForasnaScraper,
    "itida": ITIDAScraper,
    "nti": NTIScraper,
    "bayt": BaytScraper,
}

EXIT_CODES = {
    "completed": 0,
    "partial": 2,
    "failed": 1,
    "aborted": 130,
}


def positive_int(value):

    try:
        number = int(value)

    except ValueError:
        raise argparse.ArgumentTypeError(
            "Expected a positive integer"
        ) from None

    if number <= 0:
        raise argparse.ArgumentTypeError(
            "Value must be greater than zero"
        )

    return number


def parse_run_id(value):

    try:
        return UUID(value)

    except (ValueError, TypeError, AttributeError):
        raise argparse.ArgumentTypeError(
            "Expected a valid Run ID (UUID)"
        ) from None


def build_parser():

    parser = argparse.ArgumentParser(
        description="MATCHPOINT Data Collection and Recovery"
    )

    action = parser.add_mutually_exclusive_group(
        required=True
    )

    action.add_argument(
        "--source",
        choices=SOURCES,
    )

    action.add_argument(
        "--recover-run-id",
        type=parse_run_id,
        help="Resume persistence from an encrypted snapshot",
    )

    parser.add_argument(
        "--mode",
        choices=("html", "api", "live"),
    )

    parser.add_argument(
        "--storage",
        choices=("json", "postgres", "both"),
        default=None,
    )

    parser.add_argument("--html-path", type=Path)
    parser.add_argument("--details-dir", type=Path)
    parser.add_argument("--output", type=Path)

    parser.add_argument(
        "--max-jobs",
        type=positive_int,
        default=None,
    )

    parser.add_argument(
        "--page-size",
        type=positive_int,
        default=None,
    )

    parser.add_argument(
        "--max-pages",
        type=positive_int,
        default=None,
    )

    parser.add_argument(
        "--endpoint",
        choices=("all", "jobs", "lp_course"),
    )

    parser.add_argument(
        "--load-strategy",
        choices=("bounded", "full", "incremental"),
        default=None,
    )

    parser.add_argument(
        "--bootstrap",
        action="store_true",
        default=None,
        help="Initialize an absent incremental checkpoint",
    )

    parser.add_argument("--postgres-host")
    parser.add_argument("--postgres-db")

    return parser


def validate_recovery_arguments(parser, args):

    unsupported = {
        "--mode": args.mode,
        "--html-path": args.html_path,
        "--details-dir": args.details_dir,
        "--output": args.output,
        "--max-jobs": args.max_jobs,
        "--max-pages": args.max_pages,
        "--page-size": args.page_size,
        "--endpoint": args.endpoint,
        "--load-strategy": args.load_strategy,
        "--bootstrap": args.bootstrap,
    }

    for option, value in unsupported.items():

        if value is not None:
            parser.error(
                f"{option} is not supported during recovery"
            )

    if args.storage not in {None, "postgres"}:

        parser.error(
            "Recovery requires PostgreSQL storage"
        )

    args.storage = "postgres"

    return "recovery"


def validate_arguments(parser, args):

    if args.recover_run_id is not None:

        return validate_recovery_arguments(
            parser,
            args,
        )

    args.storage = args.storage or "json"

    args.load_strategy = args.load_strategy or "bounded"

    if args.bootstrap and args.load_strategy != "incremental":

        parser.error(
            "--bootstrap requires incremental collection"
        )

    if args.load_strategy == "incremental":

        if args.source != "egyincs":

            parser.error(
                "Incremental collection is currently supported only by Egyincs"
            )

        if args.storage not in {"postgres", "both"}:

            parser.error(
                "Incremental collection requires PostgreSQL storage"
            )

        if args.endpoint not in {"jobs", "lp_course"}:

            parser.error(
                "Incremental collection requires one explicit endpoint"
            )

    if args.load_strategy == "full" and args.source not in {"bayt", "devpost", "egyincs", "forasna", "itida", "nti", "un_volunteers", "wuzzuf"}:
        parser.error(
            "Full collection is not supported for this source"
        )

    if args.load_strategy == "bounded":

        if args.max_jobs is None:
            args.max_jobs = 20

        if args.max_pages is None:
            args.max_pages = 10

    if args.page_size is None:
        args.page_size = 20

    if args.source == "egyincs" and args.page_size > 20:
        parser.error("Egyincs page size must be 1-20")

    if args.source == "wuzzuf" and args.page_size > 20:
        parser.error("Wuzzuf page size must be 1-20")

    if args.source != "egyincs" and args.endpoint:

        parser.error(
            "--endpoint is only supported by Egyincs"
        )

    if args.details_dir is not None:

        parser.error(
            "--details-dir is not currently supported"
        )

    if args.storage == "both" and args.output is None:

        parser.error(
            "--output is required when storage is both"
        )

    if args.storage == "postgres" and args.output:

        parser.error(
            "Use --storage both to export JSON"
        )

    if args.storage == "json" and (
        args.postgres_host or args.postgres_db
    ):

        parser.error(
            "PostgreSQL options require persistent storage"
        )

    if args.source == "wuzzuf":

        mode = args.mode or "html"

        if args.load_strategy == "full" and mode != "api":

            parser.error(
                "Wuzzuf full collection requires API mode"
            )

        if mode == "live":

            parser.error(
                "Wuzzuf supports html or api mode"
            )

        if mode == "html":

            if args.html_path is None:
                parser.error("--html-path is required")

            if not args.html_path.is_file():
                parser.error(
                    "HTML input file does not exist"
                )

        elif args.html_path is not None:

            parser.error(
                "--html-path is not supported in API mode"
            )

        return mode

    if args.html_path is not None:

        parser.error(
            "--html-path is only supported by Wuzzuf"
        )

    if args.source in API_SOURCES:

        mode = args.mode or "api"

        if mode != "api":

            parser.error(
                f"{args.source} supports API collection only"
            )

        return mode

    mode = args.mode or "html"

    if mode not in {"html", "live"}:

        parser.error(
            f"{args.source} supports live HTML collection only"
        )

    return "live"


def build_checkpoint_intent(
    args,
    orchestrator,
    run_id,
    *,
    now=None,
):

    from datetime import datetime, timezone

    from scrapers.checkpoint_intent import CheckpointIntent
    from scrapers.incremental_window import IncrementalWindow

    from scrapers.storage.checkpoints import (
        CheckpointRepository,
    )

    if args.load_strategy != "incremental":

        return None

    current = CheckpointRepository(
        orchestrator.storage
    ).get_checkpoint(
        source_name=args.source,
        collection_scope=args.endpoint,
    )

    if current is None:

        if not args.bootstrap:

            raise ValueError(
                "No checkpoint exists; explicit bootstrap is required"
            )

        previous_run_id = None

        previous_watermark = datetime(
            1970, 1, 1,
            tzinfo=timezone.utc,
        )

    else:

        if args.bootstrap:

            raise ValueError(
                "Bootstrap cannot replace an existing checkpoint"
            )

        if current["checkpoint_type"] != "timestamp":

            raise ValueError(
                "Incremental collection requires a timestamp checkpoint"
            )

        previous_run_id = current["last_successful_run_id"]

        previous_watermark = datetime.fromisoformat(
            current["checkpoint_value"]["timestamp"]
        )

    window = IncrementalWindow.from_checkpoint(
        previous_watermark,
        now=(
            now
            if now is not None
            else datetime.now(timezone.utc)
        ),
    )

    return CheckpointIntent(
        run_id=run_id,
        source_name=args.source,
        collection_scope=args.endpoint,
        previous_run_id=previous_run_id,
        previous_watermark=previous_watermark,
        window=window,
    )


def create_scraper(args, mode, *, incremental_window=None):

    from scrapers.company_cache import (
        create_egyincs_company_cache,
        create_wuzzuf_company_cache,
    )

    limits = {
        "max_jobs": args.max_jobs,
        "max_pages": args.max_pages,
    }

    if args.source == "wuzzuf":

        if mode == "html":

            return WuzzufScraper(
                html_path=str(args.html_path)
            )

        return WuzzufAPIScraper(
            **limits,
            page_size=args.page_size,
            persistent_company_cache=create_wuzzuf_company_cache(),
        )

    if args.source in HTML_SOURCES:

        return HTML_SOURCES[args.source](**limits)

    if args.source == "devpost":

        return DevpostScraper(**limits)

    if args.source == "egyincs":

        if (
            args.load_strategy == "incremental"
            and incremental_window is None
        ):

            raise ValueError(
                "Incremental collection requires a fixed window"
            )

        return EgyincsScraper(
            **limits,
            page_size=args.page_size,
            endpoint=args.endpoint or "all",
            incremental_window=incremental_window,
            persistent_company_cache=create_egyincs_company_cache(),
        )

    return UNVolunteersScraper(
        **limits,
        page_size=args.page_size,
    )


def write_json_atomic(path, opportunities):

    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = [
        opportunity.model_dump(mode="json")
        for opportunity in opportunities
    ]

    temporary_path = None

    try:

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:

            temporary_path = Path(
                temporary_file.name
            )

            json.dump(
                payload,
                temporary_file,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )

            temporary_file.write("\n")

        temporary_path.replace(path)

    finally:

        if temporary_path is not None:

            temporary_path.unlink(
                missing_ok=True
            )


def create_orchestrator(args):

    from scrapers.config import (
        REJECTION_FINGERPRINT_KEY,
    )

    from scrapers.storage.postgres import (
        PostgresSettings,
        PostgresStorage,
    )

    from scrapers.storage.rejection_policy import (
        RejectionPolicy,
    )

    from scrapers.storage.orchestrator import (
        IngestionOrchestrator,
    )

    from scrapers.storage.snapshot_config import (
        create_snapshot_store,
    )

    from scrapers.storage.recovery_lock import (
        RecoveryLockManager,
    )

    if not REJECTION_FINGERPRINT_KEY:

        raise RuntimeError(
            "REJECTION_FINGERPRINT_KEY is required"
        )

    policy = RejectionPolicy(
        REJECTION_FINGERPRINT_KEY.encode("utf-8")
    )

    settings = PostgresSettings.from_config(
        host=args.postgres_host,
        database=args.postgres_db,
    )

    storage = PostgresStorage(settings)

    storage.health_check()

    snapshot_store = create_snapshot_store(
        settings=settings,
    )

    recovery_lock = RecoveryLockManager(
        storage
    )

    return IngestionOrchestrator(
        storage,
        rejection_policy=policy,
        snapshot_store=snapshot_store,
        recovery_lock=recovery_lock,
        batch_size=100,
    )


def extract_counters(execution):

    return {
        key: value
        for key, value in execution.finalized_run.items()
        if key.startswith("records_")
    }


def checkpoint_summary(finalized_run):

    metadata = finalized_run.get("metadata") or {}

    if "checkpoint_intent" not in metadata:

        return None

    receipt = metadata.get("checkpoint_finalization")

    if receipt is not None:

        return receipt

    return {
        "outcome": "not_advanced",
    }


def collection_exit_code(status, checkpoint=None):

    if status == "completed" and checkpoint is not None:

        if checkpoint.get("outcome") != "advanced":

            return 2

    return EXIT_CODES[status]


def print_summary(
    *,
    run_id,
    source,
    status,
    stop_reason,
    accepted,
    rejected,
    counters=None,
    export_status="not_requested",
    persistence_status="not_requested",
    operation="collection",
    already_finalized=None,
    snapshot_available=None,
    checkpoint=None,
):

    summary = {
        "run_id": str(run_id),
        "source": source,
        "operation": operation,
        "status": status,
        "stop_reason": stop_reason,
        "accepted": accepted,
        "rejected": rejected,
        "export_status": export_status,
        "persistence_status": persistence_status,
        "export_scope": "collected_opportunities",
    }

    if already_finalized is not None:
        summary["already_finalized"] = already_finalized

    if snapshot_available is not None:
        summary["snapshot_available"] = snapshot_available

    if counters is not None:

        summary["counters"] = counters

    if checkpoint is not None:

        summary["checkpoint"] = checkpoint

    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            default=str,
        )
    )


def execute_recovery(args, orchestrator):

    run_id = args.recover_run_id

    recovery = orchestrator.recover_with_retry(
        run_id=run_id
    )

    result = recovery.collection_result

    status = recovery.collection_status.value

    snapshot_available = result is not None

    if snapshot_available:

        source = result.source_name

        accepted = result.accepted_count

        rejected = result.rejected_count

    else:

        source = recovery.finalized_run[
            "source_name"
        ]

        accepted = None

        rejected = None

    stop_reason = (
        recovery.stop_reason.value
        if recovery.stop_reason is not None
        else None
    )

    checkpoint = checkpoint_summary(
        recovery.finalized_run
    )

    print_summary(
        run_id=run_id,
        source=source,
        status=status,
        stop_reason=stop_reason,
        accepted=accepted,
        rejected=rejected,
        counters=extract_counters(recovery),
        export_status="not_requested",
        persistence_status="finalized",
        operation="recovery",
        already_finalized=recovery.already_finalized,
        snapshot_available=snapshot_available,
        checkpoint=checkpoint,
    )

    return collection_exit_code(
        status,
        checkpoint,
    )


def main(argv=None):

    parser = build_parser()

    args = parser.parse_args(argv)

    mode = validate_arguments(
        parser,
        args,
    )

    if args.source is not None:
        from scrapers.guarded_cli import execute_guarded

        return execute_guarded(
            args.source,
            args.endpoint,
            lambda: _execute_validated(args, mode),
        )

    return _execute_validated(args, mode)


def _execute_validated(args, mode):

    run_id = (
        args.recover_run_id
        if args.recover_run_id is not None
        else uuid4()
    )

    operation = (
        "recovery"
        if args.recover_run_id is not None
        else "collection"
    )

    try:

        orchestrator = None
        counters = None
        checkpoint = None
        checkpoint_intent = None
        persistence_status = "not_requested"

        if args.storage in {"postgres", "both"}:

            orchestrator = create_orchestrator(
                args
            )

        if operation == "recovery":

            return execute_recovery(
                args,
                orchestrator,
            )

        if args.load_strategy == "incremental":

            checkpoint_intent = build_checkpoint_intent(
                args,
                orchestrator,
                run_id,
            )

            scraper = create_scraper(
                args,
                mode,
                incremental_window=checkpoint_intent.window,
            )

        else:

            scraper = create_scraper(
                args,
                mode,
            )

        if orchestrator is None:

            result = scraper.run_with_result(
                run_id=run_id
            )

            status = result.status.value

            stop_reason = result.stop_reason.value

            opportunities = result.opportunities

        else:

            checkpoint_arguments = {}

            if checkpoint_intent is not None:

                checkpoint_arguments["checkpoint_intent"] = (
                    checkpoint_intent
                )

            execution = orchestrator.execute_with_recovery(
                scraper=scraper,
                collection_mode=mode,
                collection_scope=(
                    args.endpoint or "all"
                    if args.source == "egyincs"
                    else "default"
                ),
                metadata={
                    "max_jobs": args.max_jobs,
                    "max_pages": args.max_pages,
                    "page_size": args.page_size,
                    "storage": args.storage,
                    "load_strategy": args.load_strategy,
                },
                run_id=run_id,
                **checkpoint_arguments,
            )

            checkpoint = checkpoint_summary(
                execution.finalized_run
            )

            status = execution.collection_status.value

            stop_reason = execution.stop_reason.value

            result = scraper.last_result

            opportunities = result.opportunities

            counters = extract_counters(
                execution
            )

            persistence_status = "finalized"

        export_status = "not_requested"

        if args.output is not None:

            try:

                write_json_atomic(
                    args.output,
                    opportunities,
                )

                export_status = "completed"

            except Exception as error:

                export_status = "failed"

                print(
                    f"JSON export failed: "
                    f"{type(error).__name__}. "
                    f"Run ID: {run_id}",
                    file=sys.stderr,
                )

        print_summary(
            run_id=run_id,
            source=args.source,
            status=status,
            stop_reason=stop_reason,
            accepted=result.accepted_count,
            rejected=result.rejected_count,
            counters=counters,
            export_status=export_status,
            persistence_status=persistence_status,
            operation=operation,
            checkpoint=checkpoint,
        )

        if (
            export_status == "failed"
            and status == "completed"
        ):

            return 3

        return collection_exit_code(
            status,
            checkpoint,
        )

    except KeyboardInterrupt:

        print(
            f"{operation.capitalize()} interrupted. "
            f"Run ID: {run_id}",
            file=sys.stderr,
        )

        return 130

    except Exception as error:

        from scrapers.storage.orchestrator import (
            IngestionExecutionError,
        )

        stage = (
            f" Stage: {error.stage}."
            if isinstance(
                error,
                IngestionExecutionError,
            )
            else ""
        )

        print(
            f"Execution failed: "
            f"{type(error).__name__}."
            f"{stage} Run ID: {run_id}",
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":

    sys.exit(main())