import logging
from scrapers.config import LOG_LEVEL


def get_logger(name: str) -> logging.Logger:

    logger = logging.getLogger(name)

    logger.setLevel(LOG_LEVEL.upper())

    if not logger.handlers:

        handler = logging.StreamHandler()

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        handler.setFormatter(formatter)

        logger.addHandler(handler)

    logger.propagate = False

    return logger