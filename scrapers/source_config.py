from dataclasses import dataclass

from scrapers.config import (
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    REQUEST_DELAY
)


@dataclass(frozen=True)
class SourceConfig:

    base_url: str

    request_timeout: int = REQUEST_TIMEOUT

    max_retries: int = MAX_RETRIES

    request_delay: float = REQUEST_DELAY

    enabled: bool = False



SOURCE_CONFIGS = {
    "wuzzuf": SourceConfig(
        base_url="https://wuzzuf.net",
        enabled=True,
    ),

    "forasna": SourceConfig(
        base_url="https://forasna.com",
        enabled=True,
    ),

    "egyincs": SourceConfig(
        base_url="https://egyincs.com",
        enabled=True,
    ),
}


def get_source_config(source_name: str) -> SourceConfig:

    if source_name not in SOURCE_CONFIGS:
        raise ValueError(
            f"No configuration found for source: {source_name}"
        )

    return SOURCE_CONFIGS[source_name]