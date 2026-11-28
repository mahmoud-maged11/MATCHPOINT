from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from scrapers import config


@dataclass(frozen=True, slots=True)
class PostgresSettings:
    host: str
    port: int
    database: str
    user: str
    password: str = field(repr=False)
    connect_timeout: int = 10

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ValueError("PostgreSQL host is required")

        if not 1 <= self.port <= 65535:
            raise ValueError("Invalid PostgreSQL port")

        if not self.database.strip():
            raise ValueError("PostgreSQL database is required")

        if not self.user.strip():
            raise ValueError("PostgreSQL user is required")

        if not self.password:
            raise ValueError("PostgreSQL password is required")

        if self.connect_timeout <= 0:
            raise ValueError("Connection timeout must be positive")

    @classmethod
    def from_config(
        cls,
        *,
        host: str | None = None,
        database: str | None = None,
    ) -> "PostgresSettings":

        return cls(
            host=host if host is not None else config.POSTGRES_HOST,
            port=config.POSTGRES_PORT,
            database=(
                database
                if database is not None
                else config.POSTGRES_DB
            ),
            user=config.POSTGRES_USER,
            password=config.POSTGRES_PASSWORD or "",
        )


class PostgresStorage:

    def __init__(self, settings: PostgresSettings) -> None:
        self.settings = settings

    def connect(
        self,
        *,
        read_only: bool = False,
    ) -> psycopg.Connection:

        connection = psycopg.connect(
            host=self.settings.host,
            port=self.settings.port,
            dbname=self.settings.database,
            user=self.settings.user,
            password=self.settings.password,
            connect_timeout=self.settings.connect_timeout,
            application_name="matchpoint_ingestion",
            autocommit=False,
            row_factory=dict_row,
        )

        try:
            connection.read_only = read_only
            return connection

        except BaseException:
            connection.close()
            raise

    @contextmanager
    def transaction(
        self,
        *,
        read_only: bool = False,
    ) -> Iterator[psycopg.Connection]:

        from scrapers.storage.connection_context import (
            get_protected_connection,
            ProtectedConnectionError,
            ProtectedConnectionLostError,
        )

        from scrapers.storage.concurrency import (
            WAREHOUSE_KEY,
        )

        def acquire_write_guard(connection):

            if not read_only:

                previous_timeout = connection.execute(
                    "SHOW lock_timeout"
                ).fetchone()["lock_timeout"]

                connection.execute(
                    "SELECT set_config('lock_timeout', %s, true)",
                    ("30s",),
                )

                connection.execute(
                    "SELECT pg_advisory_xact_lock_shared(%s::bigint)",
                    (WAREHOUSE_KEY,),
                )

                connection.execute(
                    "SELECT set_config('lock_timeout', %s, true)",
                    (previous_timeout,),
                )

        protected = get_protected_connection()

        if protected is None:

            with self.connect(read_only=read_only) as connection:

                acquire_write_guard(connection)

                yield connection

            return

        if protected.storage is not self:

            raise ProtectedConnectionError(
                "Protected storage identity mismatch"
            )

        connection = protected.connection

        if connection.closed or connection.broken:

            raise ProtectedConnectionLostError(
                "Protected database connection was lost"
            )

        with connection.transaction():

            if read_only:

                connection.execute(
                    "SET TRANSACTION READ ONLY"
                )

            acquire_write_guard(connection)

            yield connection

    def health_check(self) -> dict:

        with self.transaction(read_only=True) as connection:

            result = connection.execute(
                """
                SELECT
                    current_database() AS database,
                    current_user AS username,
                    current_setting('server_version')
                        AS server_version,
                    current_setting('transaction_read_only')
                        AS read_only
                """
            ).fetchone()

            if result is None:
                raise RuntimeError(
                    "PostgreSQL health check returned no result"
                )

            return result