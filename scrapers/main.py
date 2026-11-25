import argparse
import json
from pathlib import Path
from scrapers.sources.wuzzuf import WuzzufScraper
from scrapers.sources.wuzzuf_api import WuzzufAPIScraper
from scrapers.sources.forasna import ForasnaScraper
from scrapers.sources.egyincs import EgyincsScraper
from scrapers.sources.itida import ITIDAScraper
from scrapers.sources.nti import NTIScraper
from scrapers.sources.bayt import BaytScraper
from pathlib import Path


def main():

    parser = argparse.ArgumentParser(
        description="MATCHPOINT Data Collection"
    )

    parser.add_argument(
        "--source",
        required=True,
        choices=[
            "wuzzuf",
            "forasna",
            "egyincs",
            "itida",
            "nti",
            "bayt",
        ],    )

    parser.add_argument(
        "--mode",
        choices=["html", "api", "live"],
        default=None,
    )

    parser.add_argument("--html-path")
    parser.add_argument("--details-dir")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-jobs", type=int, default=20)
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--max-pages", type=int, default=10)

    parser.add_argument(
        "--endpoint",
        choices=["all", "jobs", "lp_course"],
        default=None,
    )

    args = parser.parse_args()

    if args.source != "egyincs" and args.endpoint is not None:
        parser.error("--endpoint is only supported by Egyincs")

    if args.source == "wuzzuf":

        mode = args.mode or "html"

        if mode == "html":

            if not args.html_path:
                parser.error("--html-path is required")

            scraper = WuzzufScraper(
                html_path=args.html_path
            )

        else:

            if args.html_path:
                parser.error("--html-path is not supported in API mode")

            scraper = WuzzufAPIScraper(
                max_jobs=args.max_jobs,
                page_size=args.page_size,
                max_pages=args.max_pages,
            )

    elif args.source == "forasna":

        mode = args.mode or "html"

        if mode != "html" or args.html_path:
            parser.error("Forasna supports live HTML collection only")

        scraper = ForasnaScraper(
            max_jobs=args.max_jobs,
            max_pages=args.max_pages,
        )

    elif args.source == "egyincs":

        mode = args.mode or "api"

        if mode != "api" or args.html_path:
            parser.error("Egyincs supports API collection only")

        scraper = EgyincsScraper(
            max_jobs=args.max_jobs,
            page_size=args.page_size,
            max_pages=args.max_pages,
            endpoint=args.endpoint or "all",
        )

    elif args.source == "itida":

        mode = args.mode or "html"

        if mode != "html" or args.html_path is not None:
            parser.error("ITIDA supports live HTML collection only")

        scraper = ITIDAScraper(
            max_jobs=args.max_jobs,
            max_pages=args.max_pages,

        )

    elif args.source == "nti":

        mode = args.mode or "html"

        if mode != "html" or args.html_path is not None:
            parser.error("NTI supports live HTML collection only")

        scraper = NTIScraper(
            max_jobs=args.max_jobs,
            max_pages=args.max_pages,
        )

    elif args.source == "bayt":

        mode = args.mode or "html"

        if mode != "html" or args.html_path is not None:
            parser.error("Bayt supports live HTML collection only")

        scraper = BaytScraper(
            max_jobs=args.max_jobs,
            max_pages=args.max_pages,
        )




    opportunities = scraper.run()
    if args.output:

        args.output.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        payload = [
            opportunity.model_dump(mode="json")
            for opportunity in opportunities
        ]

        args.output.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        print(f"Results saved to: {args.output}")


    print(f"\nTotal opportunities: {len(opportunities)}\n")

    for opportunity in opportunities:

        print(
            f"{opportunity.title} | "
            f"{opportunity.organization} | "
            f"{opportunity.location} | "
            f"{opportunity.opportunity_type} | "
            f"{opportunity.status}"
        )

    return opportunities


if __name__ == "__main__":
    main()