import logging
import os
import sqlite3
import time

from contextlib import closing
from pathlib import Path


logger = logging.getLogger(__name__)


class CompanyCache:

    POSITIVE_TTL = 86400
    NEGATIVE_TTL = 3600

    def __init__(self, path, *, clock=time.time):

        self.path = Path(path)
        self.clock = clock
        self._initialized = False
        self._warned = False

    def _warn(self, error):

        if not self._warned:

            logger.warning(
                "Company cache unavailable; API fallback: %s",
                type(error).__name__,
            )

            self._warned = True

    def _connect(self):

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        conn = sqlite3.connect(
            self.path,
            timeout=2,
        )

        try:

            if not self._initialized:

                conn.execute(
                    "PRAGMA journal_mode=WAL"
                )

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS company_cache (
                        company_id TEXT PRIMARY KEY,
                        name TEXT,
                        expires_at REAL NOT NULL
                    )
                """)

                conn.commit()

                self._initialized = True

            return conn

        except BaseException:

            conn.close()
            raise

    def get(self, company_id):

        try:

            with closing(self._connect()) as conn:

                row = conn.execute(
                    """
                    SELECT name
                    FROM company_cache
                    WHERE company_id = ?
                      AND expires_at > ?
                    """,
                    (company_id, self.clock()),
                ).fetchone()

                if row is None:
                    return False, None

                return True, row[0]

        except (sqlite3.Error, OSError) as error:

            self._initialized = False
            self._warn(error)

            return False, None

    def put(self, company_id, name):

        if name is not None:

            if not isinstance(name, str):
                raise TypeError("Invalid company name")

            if not name.strip():
                return False

        ttl = (
            self.NEGATIVE_TTL
            if name is None
            else self.POSITIVE_TTL
        )

        try:

            with closing(self._connect()) as conn:

                with conn:

                    conn.execute(
                        """
                        INSERT INTO company_cache (
                            company_id,
                            name,
                            expires_at
                        )
                        VALUES (?, ?, ?)
                        ON CONFLICT(company_id)
                        DO UPDATE SET
                            name = excluded.name,
                            expires_at = excluded.expires_at
                        """,
                        (
                            company_id,
                            name,
                            self.clock() + ttl,
                        ),
                    )

            return True

        except (sqlite3.Error, OSError) as error:

            self._initialized = False
            self._warn(error)

            return False

    def prune(self):

        try:

            with closing(self._connect()) as conn:

                with conn:

                    cursor = conn.execute(
                        """
                        DELETE FROM company_cache
                        WHERE expires_at <= ?
                        """,
                        (self.clock(),),
                    )

                    return cursor.rowcount

        except (sqlite3.Error, OSError) as error:

            self._initialized = False
            self._warn(error)

            return 0


def create_egyincs_company_cache():

    enabled = os.getenv(
        "MATCHPOINT_COMPANY_CACHE",
        "1",
    ).strip().lower()

    if enabled in {"0", "false", "off", "no"}:
        return None

    if enabled not in {"1", "true", "on", "yes"}:

        raise ValueError(
            "Invalid MATCHPOINT_COMPANY_CACHE value"
        )

    configured = os.getenv(
        "MATCHPOINT_COMPANY_CACHE_PATH"
    )

    if configured:

        path = Path(configured)

    else:

        root = Path(
            os.getenv("LOCALAPPDATA")
            or Path.home() / ".cache"
        )

        path = (
            root
            / "MATCHPOINT"
            / "Cache"
            / "egyincs_companies.sqlite3"
        )

    cache = CompanyCache(path)

    cache.prune()

    return cache


def create_wuzzuf_company_cache():

    enabled = os.getenv(
        "MATCHPOINT_COMPANY_CACHE",
        "1",
    ).strip().lower()

    if enabled in {"0", "false", "off", "no"}:
        return None

    if enabled not in {"1", "true", "on", "yes"}:

        raise ValueError(
            "Invalid MATCHPOINT_COMPANY_CACHE value"
        )

    configured = os.getenv(
        "MATCHPOINT_WUZZUF_COMPANY_CACHE_PATH"
    )

    if configured:

        path = Path(configured)

    else:

        root = Path(
            os.getenv("LOCALAPPDATA")
            or Path.home() / ".cache"
        )

        path = (
            root
            / "MATCHPOINT"
            / "Cache"
            / "wuzzuf_companies.sqlite3"
        )

    cache = CompanyCache(path)

    cache.prune()

    return cache
