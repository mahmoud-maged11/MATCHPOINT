from uuid import UUID

from psycopg import Connection

from scrapers.storage.collection_runs import (
    CollectionRunError,
    RunCounters,
)

from scrapers.storage.postgres import PostgresStorage


class RunCounterRepository:

    def __init__(
        self,
        storage: PostgresStorage,
    ) -> None:

        self.storage = storage

    @staticmethod
    def _validate_conflicts(
        connection: Connection,
        run_id: UUID,
    ) -> None:

        row = connection.execute(
            """
            WITH ledger AS (

                SELECT
                    o.source_listing_id::TEXT AS listing_id,
                    s.source_opportunity_id,
                    o.observation_hash,
                    o.observed_at,
                    o.outcome

                FROM bronze.ingestion_observations AS o

                JOIN bronze.source_listings AS s
                    ON s.source_listing_id =
                       o.source_listing_id

                WHERE o.collection_run_id = %s

            ),

            rejections AS (

                SELECT
                    source_opportunity_id,

                    error_details ->> 'source_listing_id'
                        AS listing_id,

                    error_details ->> 'previous_observation_hash'
                        AS previous_hash,

                    record_payload ->> 'incoming_observation_hash'
                        AS incoming_hash,

                    record_payload ->> 'incoming_content_hash'
                        AS incoming_content_hash,

                    observed_at,
                    error_code

                FROM bronze.invalid_records

                WHERE collection_run_id = %s
                  AND failure_stage = 'ingestion'
                  AND error_code IN (
                      'SameRunObservationMismatch',
                      'EqualTimestampContentMismatch'
                  )

            ),

            expected_equal_conflicts AS (

                SELECT
                    listing_id,
                    source_opportunity_id,
                    observation_hash,
                    observed_at

                FROM ledger

                WHERE outcome = 'conflicted'

            ),

            actual_equal_conflicts AS (

                SELECT
                    listing_id,
                    source_opportunity_id,
                    incoming_hash AS observation_hash,
                    observed_at

                FROM rejections

                WHERE error_code =
                    'EqualTimestampContentMismatch'

            ),

            missing_conflicts AS (

                SELECT *
                FROM expected_equal_conflicts

                EXCEPT ALL

                SELECT *
                FROM actual_equal_conflicts

            ),

            unexpected_conflicts AS (

                SELECT *
                FROM actual_equal_conflicts

                EXCEPT ALL

                SELECT *
                FROM expected_equal_conflicts

            ),

            invalid_same_run_conflicts AS (

                SELECT r.*

                FROM rejections AS r

                LEFT JOIN ledger AS l
                    ON l.listing_id = r.listing_id

                WHERE r.error_code =
                    'SameRunObservationMismatch'

                  AND (
                      l.listing_id IS NULL

                      OR r.source_opportunity_id
                          IS DISTINCT FROM
                          l.source_opportunity_id

                      OR r.previous_hash
                          IS DISTINCT FROM
                          l.observation_hash

                      OR r.incoming_hash
                          IS NOT DISTINCT FROM
                          l.observation_hash
                  )

            ),

            malformed_conflicts AS (

                SELECT *

                FROM rejections

                WHERE listing_id IS NULL

                   OR source_opportunity_id IS NULL

                   OR observed_at IS NULL

                   OR incoming_hash IS NULL

                   OR incoming_hash !~ '^[0-9a-f]{64}$'

                   OR incoming_content_hash IS NULL

                   OR incoming_content_hash
                       !~ '^[0-9a-f]{64}$'

                   OR (
                       error_code =
                           'EqualTimestampContentMismatch'

                       AND previous_hash IS NOT NULL
                   )

            )

            SELECT

                (
                    SELECT COUNT(*)
                    FROM missing_conflicts
                ) AS missing,

                (
                    SELECT COUNT(*)
                    FROM unexpected_conflicts
                ) AS unexpected,

                (
                    SELECT COUNT(*)
                    FROM invalid_same_run_conflicts
                ) AS invalid_same_run,

                (
                    SELECT COUNT(*)
                    FROM malformed_conflicts
                ) AS malformed
            """,
            (run_id, run_id),
        ).fetchone()

        if row is None:

            raise CollectionRunError(
                "Could not validate conflict identities"
            )

        if any(row.values()):

            raise CollectionRunError(
                "Conflict identity reconciliation failed: "
                f"missing={row['missing']}, "
                f"unexpected={row['unexpected']}, "
                f"invalid_same_run={row['invalid_same_run']}, "
                f"malformed={row['malformed']}"
            )

    @staticmethod
    def calculate(
        connection: Connection,
        *,
        run_id: UUID,
        received: int,
    ) -> RunCounters:

        if not isinstance(run_id, UUID):

            raise TypeError(
                "run_id must be a UUID"
            )

        if type(received) is not int or received < 0:

            raise ValueError(
                "received must be a non-negative integer"
            )

        RunCounterRepository._validate_conflicts(
            connection,
            run_id,
        )

        row = connection.execute(
            """
            WITH observation_counts AS (

                SELECT

                    COUNT(*) FILTER (
                        WHERE outcome = 'inserted'
                    ) AS inserted,

                    COUNT(*) FILTER (
                        WHERE outcome = 'updated'
                    ) AS updated,

                    COUNT(*) FILTER (
                        WHERE outcome = 'unchanged'
                    ) AS unchanged,

                    COUNT(*) FILTER (
                        WHERE outcome = 'stale'
                    ) AS stale,

                    COUNT(*) FILTER (
                        WHERE outcome = 'conflicted'
                    ) AS ledger_conflicted

                FROM bronze.ingestion_observations

                WHERE collection_run_id = %s

            ),

            rejection_counts AS (

                SELECT

                    COUNT(*) FILTER (
                        WHERE failure_stage = 'ingestion'
                          AND error_code =
                              'SameRunObservationMismatch'
                    ) AS same_run_conflicted,

                    COUNT(*) FILTER (
                        WHERE failure_stage = 'ingestion'
                          AND error_code =
                              'EqualTimestampContentMismatch'
                    ) AS equal_timestamp_conflicted,

                    COUNT(*) FILTER (
                        WHERE NOT (
                            failure_stage = 'ingestion'
                            AND error_code IN (
                                'SameRunObservationMismatch',
                                'EqualTimestampContentMismatch'
                            )
                        )
                    ) AS invalid

                FROM bronze.invalid_records

                WHERE collection_run_id = %s

            )

            SELECT
                o.inserted,
                o.updated,
                o.unchanged,
                o.stale,
                o.ledger_conflicted,
                r.same_run_conflicted,
                r.equal_timestamp_conflicted,
                r.invalid

            FROM observation_counts AS o

            CROSS JOIN rejection_counts AS r
            """,
            (run_id, run_id),
        ).fetchone()

        if row is None:

            raise CollectionRunError(
                "Could not calculate run counters"
            )

        if (
            row["ledger_conflicted"]
            != row["equal_timestamp_conflicted"]
        ):

            raise CollectionRunError(
                "Conflict ledger and rejection counts differ"
            )

        conflicted = (
            row["ledger_conflicted"]
            + row["same_run_conflicted"]
        )

        processed = (
            row["inserted"]
            + row["updated"]
            + row["unchanged"]
            + row["stale"]
            + row["invalid"]
            + conflicted
        )

        if processed > received:

            raise CollectionRunError(
                "Persisted outcomes exceed received records: "
                f"processed={processed}, received={received}"
            )

        return RunCounters(
            received=received,
            inserted=row["inserted"],
            updated=row["updated"],
            unchanged=row["unchanged"],
            stale=row["stale"],
            invalid=row["invalid"],
            conflicted=conflicted,
        )

    def reconcile(
        self,
        *,
        run_id: UUID,
        received: int,
    ) -> RunCounters:

        with self.storage.transaction() as conn:

            run = conn.execute(
                """
                SELECT run_id

                FROM bronze.collection_runs

                WHERE run_id = %s

                FOR UPDATE
                """,
                (run_id,),
            ).fetchone()

            if run is None:

                raise CollectionRunError(
                    f"Collection run not found: {run_id}"
                )

            return self.calculate(
                conn,
                run_id=run_id,
                received=received,
            )