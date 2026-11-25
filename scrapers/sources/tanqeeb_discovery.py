import re

from urllib.parse import urljoin, urlsplit, unquote

from bs4 import BeautifulSoup

from scrapers.sources.tanqeeb_mapper import TanqeebMapper


class TanqeebDiscovery:

    BASE_URL = "https://egypt.tanqeeb.com"

    LISTING_PATH = "/ar/s/وظائف/وظائف-مصر"

    LISTING_URL = BASE_URL + LISTING_PATH

    @classmethod
    def parse_listing(cls, html):

        soup = BeautifulSoup(html, "html.parser")

        item_lists = TanqeebMapper.extract_structured_data(
            soup, "ItemList"
        )

        jobs = {}

        stats = {
            "discovered": 0,
            "non_egypt": 0,
            "duplicates": 0,
            "invalid_urls": 0
        }

        for item_list in item_lists:

            for entry in item_list.get(
                "itemListElement", []
            ):

                if not isinstance(entry, dict):
                    continue

                candidate = entry.get("url")

                if not candidate:
                    candidate = entry.get("item")

                if isinstance(candidate, dict):
                    candidate = (
                        candidate.get("url")
                        or candidate.get("@id")
                    )

                if not isinstance(candidate, str):
                    stats["invalid_urls"] += 1
                    continue

                url = urljoin(cls.BASE_URL, candidate)

                parsed = urlsplit(url)

                if (
                    parsed.scheme != "https"
                    or parsed.netloc != "egypt.tanqeeb.com"
                ):
                    stats["invalid_urls"] += 1
                    continue

                stats["discovered"] += 1

                if "/jobs-in-egypt/" not in parsed.path:
                    stats["non_egypt"] += 1
                    continue

                url = cls.BASE_URL + parsed.path

                try:
                    job_id = TanqeebMapper.extract_job_id(url)
                except ValueError:
                    stats["invalid_urls"] += 1
                    continue

                if job_id in jobs:
                    stats["duplicates"] += 1
                    continue

                jobs[job_id] = url

        stats["egypt_jobs"] = len(jobs)

        return list(jobs.values()), stats

    @classmethod
    def extract_next_page(cls, html, current_url):

        soup = BeautifulSoup(html, "html.parser")

        current_path = unquote(
            urlsplit(current_url).path
        ).rstrip("/")

        match = re.search(
            r"/page/(\d+)$",
            current_path
        )

        current_page = int(match.group(1)) if match else 1

        expected_path = (
            cls.LISTING_PATH
            + f"/page/{current_page + 1}"
        )

        for anchor in soup.select("a[href]"):

            if anchor.get_text(strip=True) not in (
                "التالي", "Next"
            ):
                continue

            url = urljoin(current_url, anchor["href"])

            parsed = urlsplit(url)

            if (
                parsed.scheme == "https"
                and parsed.netloc == "egypt.tanqeeb.com"
                and not parsed.query
                and not parsed.fragment
                and unquote(parsed.path) == expected_path
            ):
                return url

        return None