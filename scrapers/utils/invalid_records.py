from datetime import datetime, timezone

from pydantic import BaseModel, Field

from scrapers.models import SourceName


class InvalidRecord(BaseModel):

    run_id: str

    source_name: SourceName

    source_url: str | None = None

    raw_payload: dict

    error_type: str

    error_message: str

    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )