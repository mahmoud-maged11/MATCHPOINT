from scrapers.storage.postgres import PostgresStorage


class ReconciliationRepository:

    def __init__(self, storage: PostgresStorage):
        self.storage = storage

    def deferred_enrichment(self):

        with self.storage.transaction(
            read_only=True
        ) as conn:

            return conn.execute(
                """
                SELECT
                    source_listing_id,
                    source_opportunity_id,
                    source_url,
                    organization,
                    raw_payload ->> 'company_id'
                        AS company_id,
                    first_seen_at,
                    last_seen_at,
                    last_collection_run_id,
                    content_version
                FROM bronze.source_listings
                WHERE source_name = 'egyincs'
                  AND raw_payload ->>
                      '_matchpoint_company_enrichment'
                      = 'access_denied'
                ORDER BY source_opportunity_id
                """
            ).fetchall()


    def deferred_wuzzuf_enrichment(self):

        with self.storage.transaction(
            read_only=True
        ) as conn:

            return conn.execute(
                """
                SELECT
                    source_listing_id,
                    source_opportunity_id,
                    source_url,
                    organization,
                    raw_payload ->> 'company_id'
                        AS company_id,
                    raw_payload ->>
                        '_matchpoint_company_enrichment'
                        AS deferred_reason,
                    first_seen_at,
                    last_seen_at,
                    last_collection_run_id,
                    content_version
                FROM bronze.source_listings
                WHERE source_name = 'wuzzuf'
                  AND raw_payload ->>
                      '_matchpoint_company_enrichment'
                      IN (
                          'temporary_failure',
                          'access_denied'
                      )
                  AND raw_payload -> 'attributes'
                      -> 'hideCompany' = 'false'::jsonb
                ORDER BY source_opportunity_id
                """
            ).fetchall()

    def rejected_records(self):

        with self.storage.transaction(
            read_only=True
        ) as conn:

            return conn.execute(
                """
                SELECT
                    i.invalid_record_id,
                    i.collection_run_id,
                    i.source_opportunity_id,
                    i.source_url,
                    i.failure_stage,
                    i.error_code,
                    i.error_message,
                    i.record_payload,
                    i.observed_at,
                    r.collection_scope,
                    r.status AS run_status
                FROM bronze.invalid_records AS i
                JOIN bronze.collection_runs AS r
                  ON r.run_id = i.collection_run_id
                WHERE r.source_name = 'egyincs'
                ORDER BY i.observed_at,
                         i.invalid_record_id
                """
            ).fetchall()


    def unresolved_rejections(self):

        with self.storage.transaction(
            read_only=True
        ) as conn:

            return conn.execute(
                """
                SELECT
                    i.invalid_record_id,
                    i.collection_run_id,
                    i.source_opportunity_id,
                    i.source_url,
                    i.failure_stage,
                    i.error_code,
                    i.error_message,
                    i.observed_at,
                    r.collection_scope
                FROM bronze.invalid_records AS i
                JOIN bronze.collection_runs AS r
                  ON r.run_id = i.collection_run_id
                WHERE r.source_name = 'egyincs'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM bronze.source_listings AS s
                      WHERE s.source_name = r.source_name
                        AND s.source_opportunity_id =
                            i.source_opportunity_id
                        AND s.last_seen_at > i.observed_at
                        AND s.raw_payload ->> 'endpoint' =
                            r.collection_scope
                  )
                ORDER BY i.observed_at,
                         i.invalid_record_id
                """
            ).fetchall()
