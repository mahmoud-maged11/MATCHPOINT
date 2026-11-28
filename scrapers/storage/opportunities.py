from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from psycopg import sql
from psycopg.types.json import Jsonb

from scrapers.models import Opportunity

from scrapers.storage.postgres import PostgresStorage

from scrapers.storage.identity import SourceIdentity

from scrapers.storage.invalid_records import (
    InvalidRecordRepository,
)

from scrapers.storage.collection_runs import (
    CONTRACT_VERSION,
    CollectionRunError,
)

from scrapers.utils.hashing import (
    HASH_VERSION,
    generate_content_hash,
    generate_observation_hash,
)


IngestionOutcome = Literal[
    "inserted",
    "updated",
    "unchanged",
    "stale",
    "conflicted",
    "duplicate",
]


OPPORTUNITY_COLUMNS = (
    "source_name",
    "source_opportunity_id",
    "source_url",
    "title",
    "organization",
    "description",
    "opportunity_type",
    "location",
    "work_modes",
    "employment_types",
    "categories",
    "experience_level",
    "experience_level_raw",
    "experience_years_min",
    "experience_years_max",
    "education_level",
    "required_skills",
    "requirements",
    "salary_min",
    "salary_max",
    "currency",
    "salary_period",
    "published_at",
    "published_at_raw",
    "published_at_precision",
    "deadline",
    "deadline_raw",
    "deadline_precision",
    "collected_at",
    "status",
    "source_status_raw",
    "raw_payload",
)


JSON_COLUMNS = frozenset({
    "work_modes",
    "employment_types",
    "categories",
    "required_skills",
    "raw_payload",
})


IDENTITY_COLUMNS = frozenset({
    "source_name",
    "source_opportunity_id",
})


@dataclass(frozen=True, slots=True)
class IngestionResult:

    source_listing_id: UUID
    outcome: IngestionOutcome
    content_version: int
    content_hash: str
    observation_hash: str
    original_outcome: str | None = None
    reason: str | None = None



def preserve_egyincs_organization(opportunity, existing):

    if opportunity.source_name != "egyincs":
        return opportunity

    if opportunity.organization is not None:
        return opportunity

    incoming = opportunity.raw_payload
    previous = existing.get("raw_payload")

    if not isinstance(incoming, dict):
        return opportunity

    if not isinstance(previous, dict):
        return opportunity

    if incoming.get(
        "_matchpoint_company_enrichment"
    ) != "access_denied":
        return opportunity

    incoming_id = str(
        incoming.get("company_id")
    ).strip()

    previous_id = str(
        previous.get("company_id")
    ).strip()

    if (
        not incoming_id.isascii()
        or not incoming_id.isdigit()
        or int(incoming_id) <= 0
        or incoming_id != previous_id
    ):
        return opportunity

    organization = existing.get("organization")

    if not isinstance(organization, str):
        return opportunity

    if not organization.strip():
        return opportunity

    return Opportunity.model_validate({
        **opportunity.model_dump(mode="python"),
        "organization": organization,
    })



def preserve_wuzzuf_organization(opportunity, existing):

    if opportunity.source_name != "wuzzuf":
        return opportunity

    if opportunity.organization is not None:
        return opportunity

    incoming = opportunity.raw_payload
    previous = existing.get("raw_payload")

    if not isinstance(incoming, dict):
        return opportunity

    if not isinstance(previous, dict):
        return opportunity

    if incoming.get(
        "_matchpoint_company_enrichment"
    ) != "temporary_failure":
        return opportunity

    incoming_attributes = incoming.get("attributes")
    previous_attributes = previous.get("attributes")

    if not isinstance(incoming_attributes, dict):
        return opportunity

    if not isinstance(previous_attributes, dict):
        return opportunity

    if incoming_attributes.get("hideCompany") is not False:
        return opportunity

    if previous_attributes.get("hideCompany") is not False:
        return opportunity

    incoming_id = incoming.get("company_id")
    previous_id = previous.get("company_id")

    if not isinstance(incoming_id, str):
        return opportunity

    if not isinstance(previous_id, str):
        return opportunity

    if (
        not incoming_id.isascii()
        or not incoming_id.isdigit()
        or not incoming_id.strip("0")
        or incoming_id != previous_id
    ):
        return opportunity

    organization = existing.get("organization")

    if not isinstance(organization, str):
        return opportunity

    if not organization.strip():
        return opportunity

    return Opportunity.model_validate({
        **opportunity.model_dump(mode="python"),
        "organization": organization,
    })


class OpportunityRepository:

    def __init__(self, storage: PostgresStorage) -> None:
        self.storage = storage
        self.invalid_repository = InvalidRecordRepository(
            storage
        )

    @staticmethod
    def _prepare_values(
        opportunity: Opportunity,
    ) -> dict:

        payload = opportunity.model_dump(mode="python")

        if set(payload) != set(OPPORTUNITY_COLUMNS):
            raise RuntimeError(
                "Opportunity model and persistence columns differ"
            )

        values = {}

        for column in OPPORTUNITY_COLUMNS:

            value = payload[column]

            if column == "source_url":
                value = str(value)

            elif column in JSON_COLUMNS:

                if value is not None:
                    value = Jsonb(value)

            values[column] = value

        return values

    @staticmethod
    def _get_run(conn, run_id: UUID) -> dict:

        run = conn.execute(
            """
            SELECT
                run_id,
                source_name,
                status,
                contract_version,
                hash_version
            FROM bronze.collection_runs
            WHERE run_id = %s
            FOR SHARE
            """,
            (run_id,),
        ).fetchone()

        if run is None:
            raise CollectionRunError(
                f"Collection run not found: {run_id}"
            )

        return run

    @staticmethod
    def _get_listing(
        conn,
        identity: SourceIdentity,
    ) -> dict | None:

        return conn.execute(
            """
            SELECT *
            FROM bronze.source_listings
            WHERE source_name = %s
              AND source_identity_key = %s
            FOR UPDATE
            """,
            (
                identity.source_name,
                identity.source_identity_key,
            ),
        ).fetchone()

    @staticmethod
    def _get_observation(
        conn,
        listing_id: UUID,
        run_id: UUID,
    ) -> dict | None:

        return conn.execute(
            """
            SELECT *
            FROM bronze.ingestion_observations
            WHERE source_listing_id = %s
              AND collection_run_id = %s
            """,
            (listing_id, run_id),
        ).fetchone()

    @staticmethod
    def _insert_listing(
        conn,
        opportunity: Opportunity,
        identity: SourceIdentity,
        run_id: UUID,
        content_hash: str,
    ) -> dict | None:

        values = OpportunityRepository._prepare_values(
            opportunity
        )

        values.update({
            "source_identity_key":
                identity.source_identity_key,

            "first_seen_at":
                opportunity.collected_at,

            "last_seen_at":
                opportunity.collected_at,

            "content_hash":
                content_hash,

            "hash_version":
                HASH_VERSION,

            "content_version":
                1,

            "last_collection_run_id":
                run_id,
        })

        columns = tuple(values)

        statement = sql.SQL("""
            INSERT INTO bronze.source_listings ({})
            VALUES ({})
            ON CONFLICT (
                source_name,
                source_identity_key
            )
            DO NOTHING
            RETURNING *
        """).format(
            sql.SQL(", ").join(
                sql.Identifier(column)
                for column in columns
            ),
            sql.SQL(", ").join(
                sql.Placeholder()
                for _ in columns
            ),
        )

        return conn.execute(
            statement,
            tuple(values.values()),
        ).fetchone()

    @staticmethod
    def _update_listing(
        conn,
        existing: dict,
        opportunity: Opportunity,
        run_id: UUID,
        content_hash: str,
        *,
        content_changed: bool,
    ) -> dict:

        values = OpportunityRepository._prepare_values(
            opportunity
        )

        for column in IDENTITY_COLUMNS:
            values.pop(column)

        values.update({
            "last_seen_at":
                opportunity.collected_at,

            "last_collection_run_id":
                run_id,

            "content_hash":
                content_hash,

            "hash_version":
                HASH_VERSION,

            "content_version":
                existing["content_version"]
                + int(content_changed),
        })

        assignments = [
            sql.SQL("{} = {}").format(
                sql.Identifier(column),
                sql.Placeholder(),
            )
            for column in values
        ]

        assignments.append(
            sql.SQL("""
                updated_at = GREATEST(
                    clock_timestamp(),
                    updated_at
                )
            """)
        )

        statement = sql.SQL("""
            UPDATE bronze.source_listings
            SET {}
            WHERE source_listing_id = %s
            RETURNING *
        """).format(
            sql.SQL(", ").join(assignments)
        )

        result = conn.execute(
            statement,
            (
                *values.values(),
                existing["source_listing_id"],
            ),
        ).fetchone()

        if result is None:
            raise RuntimeError(
                "Source listing update failed"
            )

        return result

    @staticmethod
    def _insert_history(
        conn,
        listing: dict,
        opportunity: Opportunity,
        run_id: UUID,
    ) -> None:

        conn.execute(
            """
            INSERT INTO bronze.source_listing_history (
                source_listing_id,
                content_version,
                content_hash,
                hash_version,
                contract_version,
                collection_run_id,
                standardized_payload,
                observed_at
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            (
                listing["source_listing_id"],
                listing["content_version"],
                listing["content_hash"],
                HASH_VERSION,
                CONTRACT_VERSION,
                run_id,
                Jsonb(
                    opportunity.model_dump(mode="json")
                ),
                opportunity.collected_at,
            ),
        )

    @staticmethod
    def _insert_observation(
        conn,
        listing_id: UUID,
        run_id: UUID,
        observation_hash: str,
        opportunity: Opportunity,
        outcome: str,
    ) -> None:

        conn.execute(
            """
            INSERT INTO bronze.ingestion_observations (
                source_listing_id,
                collection_run_id,
                observation_hash,
                observed_at,
                outcome
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                listing_id,
                run_id,
                observation_hash,
                opportunity.collected_at,
                outcome,
            ),
        )

    @staticmethod
    def _result(
        listing: dict,
        outcome: IngestionOutcome,
        observation_hash: str,
        *,
        original_outcome: str | None = None,
        reason: str | None = None,
    ) -> IngestionResult:

        return IngestionResult(
            source_listing_id=listing["source_listing_id"],
            outcome=outcome,
            content_version=listing["content_version"],
            content_hash=listing["content_hash"],
            observation_hash=observation_hash,
            original_outcome=original_outcome,
            reason=reason,
        )

    def _record_conflict(
        self,
        conn,
        *,
        run_id: UUID,
        opportunity: Opportunity,
        existing: dict,
        observation_hash: str,
        content_hash: str,
        reason: str,
        previous_observation_hash: str | None = None,
    ) -> None:

        error_codes = {
            "same_run_observation_mismatch":
                "SameRunObservationMismatch",

            "equal_timestamp_content_mismatch":
                "EqualTimestampContentMismatch",
        }

        self.invalid_repository.record(
            connection=conn,
            run_id=run_id,
            source_name=opportunity.source_name,
            source_opportunity_id=(
                opportunity.source_opportunity_id
            ),
            failure_stage="ingestion",
            error_code=error_codes[reason],
            error_message=reason,
            error_details={
                "source_listing_id": str(
                    existing["source_listing_id"]
                ),
                "current_content_version":
                    existing["content_version"],
                "current_content_hash":
                    existing["content_hash"],
                "previous_observation_hash":
                    previous_observation_hash,
            },
            record_payload={
                "incoming_observation_hash":
                    observation_hash,
                "incoming_content_hash":
                    content_hash,
            },
            observed_at=opportunity.collected_at,
        )

    @staticmethod
    def _prepare_ingestion(
        opportunity: Opportunity,
        run_id: UUID,
    ):

        if not isinstance(opportunity, Opportunity):
            raise TypeError(
                "Expected an Opportunity instance"
            )

        if not isinstance(run_id, UUID):
            raise TypeError(
                "run_id must be a UUID"
            )

        # Revalidate to protect against unvalidated model updates.

        opportunity = Opportunity.model_validate(
            opportunity.model_dump(mode="python")
        )

        identity = SourceIdentity.from_opportunity(
            opportunity
        )

        content_hash = generate_content_hash(
            opportunity
        )

        observation_hash = generate_observation_hash(
            opportunity
        )

        return (
            opportunity,
            identity,
            content_hash,
            observation_hash,
        )

    def _ingest_prepared(
        self,
        conn,
        run,
        run_id: UUID,
        prepared,
    ) -> IngestionResult:

        (
            opportunity,
            identity,
            content_hash,
            observation_hash,
        ) = prepared

        if run["source_name"] != identity.source_name:
            raise CollectionRunError(
                "Opportunity source does not match run source"
            )

        if run["contract_version"] != CONTRACT_VERSION:
            raise CollectionRunError(
                "Unsupported run contract version"
            )

        if run["hash_version"] != HASH_VERSION:
            raise CollectionRunError(
                "Unsupported run hash version"
            )

        existing = self._get_listing(
            conn,
            identity,
        )

        if existing is None:

            if run["status"] != "running":
                raise CollectionRunError(
                    "Cannot ingest into a finalized run"
                )

            inserted = self._insert_listing(
                conn,
                opportunity,
                identity,
                run_id,
                content_hash,
            )

            if inserted is not None:

                self._insert_history(
                    conn,
                    inserted,
                    opportunity,
                    run_id,
                )

                self._insert_observation(
                    conn,
                    inserted["source_listing_id"],
                    run_id,
                    observation_hash,
                    opportunity,
                    "inserted",
                )

                return self._result(
                    inserted,
                    "inserted",
                    observation_hash,
                )

            # Another transaction inserted this identity.

            existing = self._get_listing(
                conn,
                identity,
            )

            if existing is None:
                raise RuntimeError(
                    "Concurrent listing could not be resolved"
                )

        listing_id = existing["source_listing_id"]

        if existing["hash_version"] != HASH_VERSION:
            raise RuntimeError(
                "Unsupported listing hash version"
            )

        previous = self._get_observation(
            conn,
            listing_id,
            run_id,
        )

        if previous is not None:

            if (
                previous["observation_hash"]
                == observation_hash
            ):

                return self._result(
                    existing,
                    "duplicate",
                    observation_hash,
                    original_outcome=previous["outcome"],
                )

            self._record_conflict(
                conn,
                run_id=run_id,
                opportunity=opportunity,
                existing=existing,
                observation_hash=observation_hash,
                content_hash=content_hash,
                reason="same_run_observation_mismatch",
                previous_observation_hash=(
                    previous["observation_hash"]
                ),
            )

            return self._result(
                existing,
                "conflicted",
                observation_hash,
                original_outcome=previous["outcome"],
                reason="same_run_observation_mismatch",
            )

        if run["status"] != "running":
            raise CollectionRunError(
                "Cannot ingest into a finalized run"
            )

        observed_at = opportunity.collected_at
        last_seen_at = existing["last_seen_at"]

        # Keep the incoming observation hash unchanged.
        # Only the effective stored content is enriched.
        if observed_at > last_seen_at:

            effective = preserve_egyincs_organization(
                opportunity,
                existing,
            )

            effective = preserve_wuzzuf_organization(
                effective,
                existing,
            )

            if effective is not opportunity:

                opportunity = effective

                content_hash = generate_content_hash(
                    opportunity
                )

        content_changed = (
            existing["content_hash"] != content_hash
        )

        if observed_at < last_seen_at:

            outcome = "stale"

            self._insert_observation(
                conn,
                listing_id,
                run_id,
                observation_hash,
                opportunity,
                outcome,
            )

            return self._result(
                existing,
                outcome,
                observation_hash,
                reason="older_observation",
            )

        if observed_at == last_seen_at:

            if content_changed:

                outcome = "conflicted"
                reason = "equal_timestamp_content_mismatch"

                self._record_conflict(
                    conn,
                    run_id=run_id,
                    opportunity=opportunity,
                    existing=existing,
                    observation_hash=observation_hash,
                    content_hash=content_hash,
                    reason=reason,
                )

            else:

                outcome = "unchanged"
                reason = "equal_timestamp_same_content"

            self._insert_observation(
                conn,
                listing_id,
                run_id,
                observation_hash,
                opportunity,
                outcome,
            )

            return self._result(
                existing,
                outcome,
                observation_hash,
                reason=reason,
            )

        updated = self._update_listing(
            conn,
            existing,
            opportunity,
            run_id,
            content_hash,
            content_changed=content_changed,
        )

        outcome = (
            "updated"
            if content_changed
            else "unchanged"
        )

        if content_changed:

            self._insert_history(
                conn,
                updated,
                opportunity,
                run_id,
            )

        self._insert_observation(
            conn,
            listing_id,
            run_id,
            observation_hash,
            opportunity,
            outcome,
        )

        return self._result(
            updated,
            outcome,
            observation_hash,
        )

    def ingest(
        self,
        opportunity: Opportunity,
        run_id: UUID,
    ) -> IngestionResult:

        prepared = self._prepare_ingestion(
            opportunity,
            run_id,
        )

        with self.storage.transaction() as conn:

            run = self._get_run(conn, run_id)

            return self._ingest_prepared(
                conn,
                run,
                run_id,
                prepared,
            )

    def ingest_many(
        self,
        opportunities,
        run_id: UUID,
    ) -> tuple[IngestionResult, ...]:

        if not isinstance(run_id, UUID):

            raise TypeError(
                "run_id must be a UUID"
            )

        if not isinstance(opportunities, (list, tuple)):

            raise TypeError(
                "Batch must be a list or tuple"
            )

        if len(opportunities) > 1000:

            raise ValueError(
                "Batch cannot exceed 1000 opportunities"
            )

        if not opportunities:

            return ()

        prepared = tuple(
            self._prepare_ingestion(
                opportunity,
                run_id,
            )
            for opportunity in opportunities
        )

        with self.storage.transaction() as conn:

            run = self._get_run(conn, run_id)

            return tuple(
                self._ingest_prepared(
                    conn,
                    run,
                    run_id,
                    item,
                )
                for item in prepared
            )
