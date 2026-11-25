import argparse

from scrapers.sources.wuzzuf import WuzzufScraper
from scrapers.sources.wuzzuf_api import WuzzufAPIScraper
from scrapers.sources.forasna import ForasnaScraper
from scrapers.utils.logger import get_logger


logger = get_logger("main")


def main():

    parser = argparse.ArgumentParser(
        description="MATCHPOINT Data Collection"
    )

    parser.add_argument(
        "--source",
        required=True,
        choices=["wuzzuf", "forasna"]
    )

    parser.add_argument(
        "--mode",
        choices=["html", "api"],
        default=None
    )

    parser.add_argument("--html-path")

    parser.add_argument(
        "--max-jobs",
        type=int,
        default=20
    )

    parser.add_argument(
        "--page-size",
        type=int,
        default=20
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=10
    )

    args = parser.parse_args()

    if args.source == "wuzzuf":

        mode = args.mode or "html"

        if mode == "html":

            if not args.html_path:
                parser.error(
                    "--html-path is required in Wuzzuf HTML mode"
                )

            scraper = WuzzufScraper(args.html_path)

        else:

            scraper = WuzzufAPIScraper(
                max_jobs=args.max_jobs,
                page_size=args.page_size,
                max_pages=args.max_pages
            )

    elif args.source == "forasna":

        mode = args.mode or "html"

        if mode != "html":
            parser.error("Forasna supports HTML mode only")

        if args.html_path:
            parser.error("Forasna collects live HTML")

        scraper = ForasnaScraper(
            max_jobs=args.max_jobs,
            max_pages=args.max_pages
        )

    logger.info(
        f"Starting collection | "
        f"Source: {args.source} | "
        f"Mode: {mode}"
    )

    opportunities = scraper.run()

    logger.info(
        f"Total opportunities collected: "
        f"{len(opportunities)}"
    )

    for opportunity in opportunities:

        print(
            f"{opportunity.title} | "
            f"{opportunity.organization} | "
            f"{opportunity.location}"
        )

    return opportunities


if __name__ == "__main__":
    main()