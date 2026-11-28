from unittest.mock import Mock
from uuid import UUID, uuid4
from scrapers.models import Opportunity

from scrapers.collection_result import (
    CollectionStatus,
    StopReason,
)
import pytest

from scrapers.base_scraper import BaseScraper


class DummyScraper(BaseScraper):

    def __init__(self):

        super().__init__("wuzzuf")

        self.client = Mock()
        self.logger = Mock()
        self.action = Mock(return_value=[])

    def scrape(self):

        return self.action()


@pytest.fixture
def scraper():

    return DummyScraper()


def test_automatic_run_id(scraper):

    result = scraper.run()

    assert result == []
    assert isinstance(UUID(scraper.run_id), UUID)
    assert scraper._running is False

    scraper.client.close.assert_called_once()


@pytest.mark.parametrize("as_string", [False, True])
def test_external_run_id(scraper, as_string):

    identifier = uuid4()

    supplied = (
        str(identifier)
        if as_string
        else identifier
    )

    scraper.run(run_id=supplied)

    assert scraper.run_id == str(identifier)


def test_invalid_record_uses_external_run_id(scraper):

    identifier = uuid4()

    def collect():

        scraper.record_invalid(
            raw_payload={"title": None},
            error_type="MissingTitle",
            error_message="Title is required",
        )

        return []

    scraper.action.side_effect = collect

    scraper.run(run_id=identifier)

    assert len(scraper.invalid_records) == 1

    record = scraper.invalid_records[0]

    assert record.run_id == str(identifier)
    assert record.source_name == "wuzzuf"


def test_invalid_records_reset_between_runs(scraper):

    def collect():

        scraper.record_invalid(
            raw_payload={},
            error_type="InvalidRecord",
            error_message="Invalid data",
        )

        return []

    scraper.action.side_effect = collect

    scraper.run()

    first_run = scraper.run_id

    assert len(scraper.invalid_records) == 1

    scraper.action.side_effect = None

    scraper.run()

    assert scraper.run_id != first_run
    assert scraper.invalid_records == []


@pytest.mark.parametrize(
    "invalid",
    ["", "invalid-uuid", "123"],
)
def test_invalid_uuid_rejected(scraper, invalid):

    with pytest.raises(ValueError):

        scraper.run(run_id=invalid)

    scraper.action.assert_not_called()
    assert scraper._running is False


@pytest.mark.parametrize(
    "invalid",
    [123, True, [], {}],
)
def test_invalid_run_id_type(scraper, invalid):

    with pytest.raises(TypeError):

        scraper.run(run_id=invalid)

    scraper.action.assert_not_called()


def test_record_invalid_before_run(scraper):

    with pytest.raises(
        RuntimeError,
        match="Collection run has not been initialized",
    ):

        scraper.record_invalid(
            raw_payload={},
            error_type="InvalidRecord",
            error_message="Invalid data",
        )


def test_scraping_failure_closes_client(scraper):

    identifier = uuid4()

    scraper.action.side_effect = RuntimeError(
        "Simulated collection failure"
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated collection failure",
    ):

        scraper.run(run_id=identifier)

    assert scraper.run_id == str(identifier)
    assert scraper._running is False

    scraper.client.close.assert_called_once()


def test_invalid_records_preserved_after_failure(scraper):

    identifier = uuid4()

    def collect():

        scraper.record_invalid(
            raw_payload={},
            error_type="InvalidRecord",
            error_message="Invalid data",
        )

        raise RuntimeError("Collection interrupted")

    scraper.action.side_effect = collect

    with pytest.raises(
        RuntimeError,
        match="Collection interrupted",
    ):

        scraper.run(run_id=identifier)

    assert len(scraper.invalid_records) == 1

    assert scraper.invalid_records[0].run_id == (
        str(identifier)
    )

    assert scraper._running is False


def test_client_close_failure_resets_state(scraper):

    scraper.client.close.side_effect = RuntimeError(
        "Client close failed"
    )

    with pytest.raises(
        RuntimeError,
        match="Client close failed",
    ):

        scraper.run()

    assert scraper._running is False


def test_reentrant_run_rejected(scraper):

    identifier = uuid4()

    def collect():

        with pytest.raises(
            RuntimeError,
            match="Scraper is already running",
        ):

            scraper.run(run_id=uuid4())

        assert scraper.run_id == str(identifier)
        assert scraper._running is True

        return []

    scraper.action.side_effect = collect

    scraper.run(run_id=identifier)

    assert scraper.run_id == str(identifier)
    assert scraper._running is False

    scraper.client.close.assert_called_once()
def test_opportunities_preserved_after_post_scrape_failure(scraper):

    opportunity = Opportunity(
        source_name="wuzzuf",
        source_opportunity_id="12345",
        source_url="https://wuzzuf.net/jobs/p/12345",
        title="Data Engineer",
        opportunity_type="job",
        raw_payload={"id": "12345"},
    )

    scraper.action.return_value = [opportunity]

    def fail_after_scrape(message):

        if message.startswith("Collected"):

            raise RuntimeError(
                "Post-scrape processing failed"
            )

    scraper.logger.info.side_effect = fail_after_scrape

    with pytest.raises(
        RuntimeError,
        match="Post-scrape processing failed",
    ):

        scraper.run()

    assert scraper.last_result is not None

    assert scraper.last_result.status == (
        CollectionStatus.PARTIAL
    )

    assert scraper.last_result.stop_reason == (
        StopReason.UNKNOWN
    )

    assert scraper.last_result.opportunities == (
        opportunity,
    )

    assert scraper._running is False

    scraper.client.close.assert_called_once()