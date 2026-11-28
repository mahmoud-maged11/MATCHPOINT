from dataclasses import dataclass

from scrapers.models import Opportunity
from scrapers.source_config import get_source_config


MAX_SOURCE_ID_BYTES = 512


class SourceIdentityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SourceIdentity:

    source_name: str
    source_opportunity_id: str

    def __post_init__(self) -> None:

        try:
            source_config = get_source_config(
                self.source_name
            )
        except ValueError as exc:
            raise SourceIdentityError(
                "Unsupported source"
            ) from exc

        if not source_config.enabled:
            raise SourceIdentityError(
                "Source is disabled"
            )

        identifier = self.source_opportunity_id

        if not isinstance(identifier, str):
            raise SourceIdentityError(
                "Source opportunity ID must be a string"
            )

        if not identifier.strip():
            raise SourceIdentityError(
                "Source opportunity ID cannot be empty"
            )

        if identifier != identifier.strip():
            raise SourceIdentityError(
                "Source opportunity ID contains surrounding whitespace"
            )

        if "\x00" in identifier:
            raise SourceIdentityError(
                "Source opportunity ID contains a null character"
            )

        try:
            encoded_identifier = identifier.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise SourceIdentityError(
                "Source opportunity ID contains invalid Unicode"
            ) from exc

        if len(encoded_identifier) > MAX_SOURCE_ID_BYTES:
            raise SourceIdentityError(
                f"Source opportunity ID exceeds "
                f"{MAX_SOURCE_ID_BYTES} UTF-8 bytes"
            )

    @property
    def source_identity_key(self) -> str:

        return f"id:{self.source_opportunity_id}"

    @classmethod
    def from_opportunity(
        cls,
        opportunity: Opportunity,
    ) -> "SourceIdentity":

        identifier = opportunity.source_opportunity_id

        if identifier is None:
            raise SourceIdentityError(
                "Source opportunity ID is required for Bronze ingestion"
            )

        return cls(
            source_name=opportunity.source_name,
            source_opportunity_id=identifier,
        )
