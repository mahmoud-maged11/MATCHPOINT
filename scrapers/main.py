import argparse

from scrapers.sources.wuzzuf import WuzzufScraper
from scrapers.sources.wuzzuf_api import WuzzufAPIScraper
from scrapers.utils.logger import get_logger


logger = get_logger("main")


def main():

    parser = argparse.ArgumentParser(
        description="MATCHPOINT Data Collection"
    )

    parser.add_argument(
        "--source",
        required=True,
        choices=["wuzzuf"]
    )

    parser.add_argument(
        "--mode",
        choices=["html", "api"],
        default="html"
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

    logger.info(
        f"Starting collection | "
        f"Source: {args.source} | "
        f"Mode: {args.mode}"
    )

    if args.mode == "html":

        if not args.html_path:
            parser.error(
                "--html-path is required in HTML mode"
            )

        scraper = WuzzufScraper(args.html_path)

    else:

        scraper = WuzzufAPIScraper(
            max_jobs=args.max_jobs,
            page_size=args.page_size,
            max_pages=args.max_pages
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