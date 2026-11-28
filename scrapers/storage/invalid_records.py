

import hashlib

from contextlib import nullcontext

import json



from dataclasses import dataclass

from datetime import datetime, timezone

from typing import Literal

from uuid import UUID



from psycopg import Connection

from psycopg.pq import TransactionStatus

from psycopg.types.json import Jsonb



from scrapers.storage.postgres import PostgresStorage



from scrapers.storage.collection_runs import (

    CollectionRunError,

)



from scrapers.utils.invalid_records import InvalidRecord





FailureStage = Literal[

    "extraction",

    "mapping",

    "validation",

    "identity",

    "ingestion",

]





FAILURE_STAGES = frozenset({

    "extraction",

    "mapping",

    "validation",

    "identity",

    "ingestion",

})





@dataclass(frozen=True, slots=True)

class RejectionResult:



    invalid_record_id: UUID

    rejection_hash: str

    inserted: bool





class InvalidRecordRepository:



    def __init__(self, storage: PostgresStorage) -> None:



        self.storage = storage



    @staticmethod

    def _validate_text(

        value: str,

        field_name: str,

    ) -> None:



        if (

            not isinstance(value, str)

            or not value.strip()

            or "\x00" in value

        ):

            raise ValueError(

                f"Invalid {field_name}"

            )



    @staticmethod

    def _validate_optional_text(

        value: str | None,

        field_name: str,

    ) -> None:



        if value is not None:



            InvalidRecordRepository._validate_text(

                value,

                field_name,

            )



    @staticmethod

    def generate_rejection_hash(

        *,

        source_opportunity_id: str | None,

        source_url: str | None,

        failure_stage: FailureStage,

        error_code: str,

        record_payload,

    ) -> str:



        payload = {

            "source_opportunity_id":

                source_opportunity_id,



            "source_url":

                source_url,



            "failure_stage":

                failure_stage,



            "error_code":

                error_code,



            "record_payload":

                record_payload,

        }



        serialized = json.dumps(

            payload,

            sort_keys=True,

            ensure_ascii=False,

            separators=(",", ":"),

            allow_nan=False,

        )



        return hashlib.sha256(

            (

                "matchpoint:rejection:v1|"

                + serialized

            ).encode("utf-8")

        ).hexdigest()



    def record(

        self,

        *,

        run_id: UUID,

        source_name: str,

        failure_stage: FailureStage,

        error_code: str,

        error_message: str,

        source_opportunity_id: str | None = None,

        source_url: str | None = None,

        error_details: dict | None = None,

        record_payload=None,

        observed_at: datetime | None = None,

        connection: Connection | None = None,

    ) -> RejectionResult:



        if not isinstance(run_id, UUID):

            raise TypeError(

                "run_id must be a UUID"

            )



        if failure_stage not in FAILURE_STAGES:

            raise ValueError(

                "Unsupported failure stage"

            )



        self._validate_text(

            source_name,

            "source_name",

        )



        self._validate_text(

            error_code,

            "error_code",

        )



        self._validate_text(

            error_message,

            "error_message",

        )



        self._validate_optional_text(

            source_opportunity_id,

            "source_opportunity_id",

        )



        self._validate_optional_text(

            source_url,

            "source_url",

        )



        if error_details is None:

            error_details = {}



        if not isinstance(error_details, dict):

            raise TypeError(

                "error_details must be a dictionary"

            )



        if observed_at is not None:



            if not isinstance(observed_at, datetime):

                raise TypeError(

                    "observed_at must be a datetime"

                )



            if (

                observed_at.tzinfo is None

                or observed_at.utcoffset() is None

            ):

                raise ValueError(

                    "observed_at must be timezone-aware"

                )



            observed_at = observed_at.astimezone(

                timezone.utc

            )



        # Validate and detach JSON values before persistence.



        error_details = json.loads(

            json.dumps(

                error_details,

                ensure_ascii=False,

                allow_nan=False,

            )

        )



        record_payload = json.loads(

            json.dumps(

                record_payload,

                ensure_ascii=False,

                allow_nan=False,

            )

        )



        rejection_hash = self.generate_rejection_hash(

            source_opportunity_id=source_opportunity_id,

            source_url=source_url,

            failure_stage=failure_stage,

            error_code=error_code,

            record_payload=record_payload,

        )



        if connection is not None:



            if (
                connection.closed
                or not (
                    connection.info.transaction_status
                    == TransactionStatus.INTRANS
                    or (
                        not connection.autocommit
                        and connection.info.transaction_status
                        == TransactionStatus.IDLE
                    )
                )
            ):
                raise ValueError(

                    "Shared connection requires an active transaction"

                )



        transaction = (

            self.storage.transaction()

            if connection is None

            else nullcontext(connection)

        )



        with transaction as conn:



            run = conn.execute(

                """

                SELECT

                    source_name,

                    status

                FROM bronze.collection_runs

                WHERE run_id = %s

                FOR SHARE

                """,

                (run_id,),

            ).fetchone()



            if run is None:



                raise CollectionRunError(

                    "Collection run not found"

                )



            if run["source_name"] != source_name:



                raise CollectionRunError(

                    "Invalid record source does not match run source"

                )



            existing = conn.execute(

                """

                SELECT invalid_record_id

                FROM bronze.invalid_records

                WHERE collection_run_id = %s

                  AND rejection_hash = %s

                """,

                (

                    run_id,

                    rejection_hash,

                ),

            ).fetchone()



            if existing is not None:



                return RejectionResult(

                    invalid_record_id=existing[

                        "invalid_record_id"

                    ],

                    rejection_hash=rejection_hash,

                    inserted=False,

                )



            if run["status"] != "running":



                raise CollectionRunError(

                    "Cannot record a new rejection in a finalized run"

                )



            result = conn.execute(

                """

                INSERT INTO bronze.invalid_records (

                    collection_run_id,

                    source_opportunity_id,

                    source_url,

                    failure_stage,

                    error_code,

                    error_message,

                    error_details,

                    record_payload,

                    rejection_hash,

                    observed_at

                )

                VALUES (

                    %s, %s, %s, %s, %s,

                    %s, %s, %s, %s, %s

                )

                ON CONFLICT (

                    collection_run_id,

                    rejection_hash

                )

                DO NOTHING

                RETURNING invalid_record_id

                """,

                (

                    run_id,

                    source_opportunity_id,

                    source_url,

                    failure_stage,

                    error_code,

                    error_message,

                    Jsonb(error_details),

                    (

                        Jsonb(record_payload)

                        if record_payload is not None

                        else None

                    ),

                    rejection_hash,

                    observed_at,

                ),

            ).fetchone()



            if result is not None:



                return RejectionResult(

                    invalid_record_id=result[

                        "invalid_record_id"

                    ],

                    rejection_hash=rejection_hash,

                    inserted=True,

                )



            # Resolve a concurrent insertion of the same rejection.



            existing = conn.execute(

                """

                SELECT invalid_record_id

                FROM bronze.invalid_records

                WHERE collection_run_id = %s

                  AND rejection_hash = %s

                """,

                (

                    run_id,

                    rejection_hash,

                ),

            ).fetchone()



            if existing is None:



                raise RuntimeError(

                    "Concurrent rejection could not be resolved"

                )



            return RejectionResult(

                invalid_record_id=existing[

                    "invalid_record_id"

                ],

                rejection_hash=rejection_hash,

                inserted=False,

            )



    def record_scraper_invalid(

        self,

        record: InvalidRecord,

        *,

        failure_stage: FailureStage,

        safe_error_message: str,

        safe_payload: dict | None,

        safe_source_url: str | None = None,

        source_opportunity_id: str | None = None,

    ) -> RejectionResult:



        if not isinstance(record, InvalidRecord):



            raise TypeError(

                "Expected an InvalidRecord instance"

            )



        return self.record(

            run_id=UUID(record.run_id),

            source_name=record.source_name,

            failure_stage=failure_stage,

            error_code=record.error_type,

            error_message=safe_error_message,

            source_opportunity_id=source_opportunity_id,

            source_url=safe_source_url,

            record_payload=safe_payload,

            observed_at=record.collected_at,

        )