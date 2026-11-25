from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup

from scrapers.sources.tanqeeb import TanqeebSource
from scrapers.sources.tanqeeb_mapper import TanqeebMapper


class TanqeebOfflineSource(TanqeebSource):

    def __init__(
        self,
        listings_dir,
        details_dir=None,
        max_jobs=20,
        max_pages=5
    ):

        self.listings_dir = Path(listings_dir)

        self.details_dir = Path(
            details_dir or listings_dir
        )

        if not self.listings_dir.is_dir():
            raise FileNotFoundError(self.listings_dir)

        if not self.details_dir.is_dir():
            raise FileNotFoundError(self.details_dir)

        self.details = self.load_details()

        super().__init__(
            fetch_listing=self.read_listing,
            fetch_detail=self.read_detail,
            max_jobs=max_jobs,
            max_pages=max_pages
        )

    def load_details(self):

        details = {}

        for path in sorted(
            self.details_dir.glob("detail_*.html")
        ):

            html = path.read_text(encoding="utf-8")

            soup = BeautifulSoup(html, "html.parser")

            canonical = soup.select_one(
                'link[rel="canonical"][href]'
            )

            if canonical is None:
                continue

            try:
                job_id = TanqeebMapper.extract_job_id(
                    canonical["href"]
                )
            except ValueError:
                continue

            details[job_id] = html

        return details

    def read_listing(self, url):

        path = unquote(urlsplit(url).path)

        page = 1

        if "/page/" in path:
            page = int(path.rsplit("/", 1)[-1])

        file_path = (
            self.listings_dir / f"egypt_page_{page}.html"
        )

        return file_path.read_text(encoding="utf-8")

    def read_detail(self, url):

        job_id = TanqeebMapper.extract_job_id(url)

        return self.details.get(job_id)