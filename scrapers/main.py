import argparse

from scrapers.sources.wuzzuf import WuzzufScraper
from scrapers.utils.logger import get_logger


logger = get_logger("main")


def main():
    parser = argparse.ArgumentParser(
        description="MATCHPOINT Data Collection"
    )

    parser.add_argument(
        "--source",
        required=True,
        choices=["wuzzuf"],
        help="Source to collect opportunities from"
    )

    parser.add_argument(
        "--html-path",
        required=True,
        help="Path to the local HTML fixture"
    )

    args = parser.parse_args()

    logger.info(f"Starting collection for: {args.source}")

    if args.source == "wuzzuf":
        scraper = WuzzufScraper(args.html_path)

        opportunities = scraper.run()

        logger.info(
            f"Total opportunities collected: {len(opportunities)}"
        )

        return opportunities


if __name__ == "__main__":
    main()