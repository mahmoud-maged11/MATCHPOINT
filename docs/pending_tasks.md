# MATCHPOINT Pending Tasks

**Data Contract Version:** 2.0.0

**Last Updated:** 2026-11-24

## Priority Definitions

- P0: Blocking task.
- P1: Required for core functionality.
- P2: Required for production readiness.
- P3: Future improvement.

## 1. Data Contract and Documentation

**Owner:** Mahmoud

**Priority:** P0

- [x] Define initial Data Contract v1.0.0.
- [x] Identify limitations using real source samples.
- [x] Prepare Data Contract v2.0.0.
- [x] Document architecture decisions.
- [x] Update Pydantic models.
- [x] Update Wuzzuf parser.
- [x] Pass all 20 Pydantic model tests.
- [x] Verify updated parser against four local job cards.
- [x] Update content hashing implementation.
- [x] Pass all 10 content hashing tests.
- [x] Pass all 30 model and hashing tests.- [ ] Verify consistency between documentation and code.
- [ ] Commit and push updated specification.
- [ ] Communicate updated contract to all team members.

## 2. Data Collection Infrastructure

**Owner:** Mahmoud

**Priority:** P1

- [x] Create scraper directory structure.
- [x] Configure Python virtual environment.
- [x] Install initial dependencies.
- [x] Implement configuration module.
- [x] Implement logging module.
- [x] Implement HTTP client.
- [x] Implement initial Pydantic model.
- [x] Implement abstract BaseScraper.
- [x] Implement initial SHA-256 content hashing.
- [x] Confirm HTTP client connectivity test (HTTP 200 from example.com).
- [x] Verify content hashing test results.
- [x] Implement and verify main scraper execution module using CLI arguments and local HTML fixtures.
- [x] Implement source-specific collection settings.
- [x] Implement source configuration registry.
- [x] Integrate source configuration with BaseScraper.
- [x] Integrate source configuration with HTTPClient.
- [x] Centralize source base URLs.
- [x] Pass 5 source configuration tests.
- [x] Pass 4 HTTPClient tests.
- [x] Pass all 62 automated tests.
- [x] Enforce live collection enabled flag.
- [x] Block HTTP requests for disabled sources.
- [x] Allow HTTP requests for enabled sources.
- [x] Preserve local HTML parsing for disabled sources.
- [x] Pass 6 HTTPClient automated tests.
- [x] Pass all 69 automated tests.
- [ ] Configure remaining sources.
- [x] Implement per-client rate limiting.
- [x] Use monotonic clock for request interval calculation.
- [x] Protect rate limiter state using thread locks.
- [x] Integrate RateLimiter with HTTPClient.
- [x] Pass 5 rate limiter automated tests.
- [x] Pass all 67 automated tests.
- [ ] Enforce rate limits for internal HTTP retries.
- [ ] Coordinate rate limits across concurrent collection processes.
- [ ] Configure authorized rate limits for each source.
- [x] Implement in-memory invalid record handling.
- [x] Verify invalid record handling with 8 automated tests.
- [x] Pass all 53 automated tests.
- [ ] Implement persistent invalid record storage in PostgreSQL.
- [x] Implement and verify collection run identifiers using UUID4 and scraper lifecycle logging.
- [ ] Associate collection run identifiers with stored opportunities and invalid records.
## 3. Wuzzuf Source Adapter

**Owner:** Mahmoud

**Priority:** P0

### Completed

- [x] Investigate website structure.
- [x] Confirm job data exists in HTML.
- [x] Identify job card selectors.
- [x] Implement initial HTML parser.
- [x] Successfully parse one local job card.
- [x] Successfully parse four local job cards.
- [x] Extract source identifiers.
- [x] Extract job titles and URLs.
- [x] Extract organizations and locations.
- [x] Extract work modes.
- [x] Extract candidate skill tags.
- [x] Identify multiple employment types issue.
- [x] Support multiple employment types.
- [x] Support multiple work modes.
- [x] Investigate alternative publication date selectors.
- [x] Extract original publication dates.
- [x] Preserve publication date precision.
- [x] Extract original experience labels.
- [x] Extract minimum and maximum experience years.
- [x] Extract opportunity categories.
- [x] Replace real HTML fixtures in automated tests with synthetic fixtures and exclude real source HTML from Git.- [x] Implement and pass 15 automated Wuzzuf parser tests using synthetic HTML fixtures.- [ ] Complete final adapter validation.


### Pending


- [ ] Investigate authorized live collection methods.
- [ ] Resolve HTTP 403 through an authorized access method.
- [ ] Implement live data collection.
- [ ] Implement pagination.
- [ ] Investigate job details page structure.
- [ ] Extract job descriptions.
- [ ] Extract job requirements.
- [ ] Extract education requirements.
- [ ] Extract salary information when available.
- [ ] Implement source-specific status detection.
- [x] Handle missing and malformed job cards in local HTML fixtures.
- [x] Verify that invalid records do not interrupt valid record extraction.
- [x] Preserve rejected records with raw HTML, error details, and collection run ID in memory.
**Current blocker:** HTTP 403 Forbidden during direct HTTP requests. Local HTML parsing is functional, but automated live collection has not been established.

## 4. Additional Source Adapters

**Owner:** Mahmoud

**Priority:** P1

- [ ] Forasna
- [ ] Egyincs
- [ ] ITIDA
- [ ] NTI
- [ ] Bayt
- [ ] LinkedIn
- [ ] AMIDEAST
- [ ] Devpost
- [ ] UN Volunteers

For each source:

- Confirm authorized collection method.
- Investigate source structure.
- Implement source adapter.
- Map fields to the latest Data Contract.
- Test missing and malformed values.
- Implement pagination where applicable.
- Validate extracted records.
- Document source-specific limitations.

## 5. Data Validation and Normalization

**Owners:** Mahmoud and Momen

**Priority:** P1

- [x] Validate multiple employment types.
- [x] Validate multiple work modes.
- [x] Remove duplicate array values.
- [x] Reject empty required strings.
- [x] Validate timezone-aware timestamps.
- [x] Normalize timestamps to UTC.
- [x] Preserve original date values.
- [x] Handle relative date precision.
- [x] Handle date-only deadlines.
- [x] Validate ISO 4217 currency codes.
- [x] Validate salary ranges.
- [x] Validate experience ranges.
- [x] Reject unsupported legacy fields.
- [x] Retain invalid records in memory during collection runs.
- [x] Preserve raw payload, error details, source information, UTC timestamp, and run ID.
- [ ] Persist invalid records in PostgreSQL Bronze Layer.
- [ ] Separate skills from categories across all sources.
- [ ] Define experience-level mapping rules across all sources.
- [ ] Preserve ambiguous source values across all sources.

## 6. Content Hashing and Ingestion

**Owner:** Mahmoud

**Priority:** P1

- [x] Update hashing for Data Contract v2.0.0.
- [x] Normalize unordered arrays before hashing.
- [x] Exclude volatile relative date values.
- [x] Exclude collection timestamps.
- [x] Verify content hashing with 10 automated tests.
- [ ] Exclude future ingestion metadata from content hashing.
- [ ] Define stable source listing identity.
- [ ] Define source-specific URL identity rules.
- [ ] Generate source_listing_id.
- [ ] Track first collection timestamp.
- [ ] Track last_seen_at.
- [ ] Detect new listings.
- [ ] Detect unchanged listings.
- [ ] Detect updated listings.
- [ ] Define content version history.
- [ ] Define raw observation retention policy.
- [ ] Implement idempotent ingestion.
- [ ] Implement transaction handling.
- [ ] Implement PostgreSQL storage module.
- [ ] Test ingestion failure recovery.

## 7. Data Warehouse and Transformation

**Owner:** Momen

**Priority:** P1

- [ ] Review Data Contract v2.0.0.
- [ ] Design Bronze, Silver, and Gold schemas.
- [ ] Design physical source listing tables.
- [ ] Design raw observation and content history tables.
- [ ] Design invalid record storage.
- [ ] Create database migrations.
- [ ] Initialize dbt project.
- [ ] Configure dbt source definitions.
- [ ] Implement staging models.
- [ ] Implement intermediate models.
- [ ] Implement Gold marts.
- [ ] Normalize organization names.
- [ ] Normalize locations.
- [ ] Normalize skills.
- [ ] Normalize categories.
- [ ] Implement source listing deduplication.
- [ ] Implement cross-source deduplication.
- [ ] Define matching evidence and thresholds.
- [ ] Generate stable canonical opportunity IDs.
- [ ] Preserve relationships between canonical opportunities and source listings.
- [ ] Design fact and dimension tables.
- [ ] Design skill bridge tables.
- [ ] Implement data quality tests.
- [ ] Document warehouse architecture.

## 8. Pipeline and Orchestration

**Owner:** Andrew

**Priority:** P1

- [ ] Configure Apache Airflow.
- [ ] Define scraper execution DAGs.
- [ ] Define source-specific schedules.
- [ ] Configure task dependencies.
- [ ] Configure retries and timeouts.
- [ ] Implement pipeline monitoring.
- [ ] Integrate PostgreSQL ingestion.
- [ ] Integrate dbt transformations.
- [ ] Design ClickHouse analytical tables.
- [ ] Implement analytical data loading.
- [ ] Implement failure notifications.
- [ ] Test complete pipeline execution.

## 9. Backend and Matching

**Owner:** Mahmoud

**Priority:** P1

- [ ] Initialize FastAPI backend.
- [ ] Configure database connections.
- [ ] Implement authentication.
- [ ] Implement user profiles.
- [ ] Implement user skills.
- [ ] Implement opportunity APIs.
- [ ] Support multiple employment types.
- [ ] Support multiple work modes.
- [ ] Support canonical opportunities.
- [ ] Expose original source links.
- [ ] Implement opportunity matching.
- [ ] Implement explainable recommendations.
- [ ] Implement skill gap analysis.
- [ ] Implement saved opportunities.
- [ ] Implement application tracking.
- [ ] Implement API validation and testing.
- [ ] Generate API documentation.

## 10. Analytics and Visualization

**Owner:** Ramadan

**Priority:** P1

- [ ] Connect to ClickHouse.
- [ ] Define analytical KPIs.
- [ ] Define canonical opportunity counting rules.
- [ ] Analyze opportunity trends.
- [ ] Analyze skill demand.
- [ ] Analyze location distributions.
- [ ] Analyze experience requirements.
- [ ] Analyze employment types.
- [ ] Analyze work modes.
- [ ] Prevent duplicate opportunity counts.
- [ ] Develop Power BI dashboards.
- [ ] Validate analytical results.

## 11. Frontend

**Owner:** Abdel Rahman

**Priority:** P1

- [ ] Initialize React and Vite project.
- [ ] Design application interface.
- [ ] Implement registration and login.
- [ ] Implement user profiles.
- [ ] Implement opportunity listing pages.
- [ ] Implement opportunity details pages.
- [ ] Implement filtering and search.
- [ ] Support multiple employment types.
- [ ] Support multiple work modes.
- [ ] Display personalized recommendations.
- [ ] Display skill gaps.
- [ ] Display original source links.
- [ ] Implement saved opportunities.
- [ ] Implement application tracking.
- [ ] Integrate backend APIs.
- [ ] Test frontend functionality.

## 12. Testing and Deployment

**Owners:** All Team Members

**Priority:** P2

- [ ] Implement unit tests.
- [ ] Implement integration tests.
- [ ] Implement end-to-end pipeline tests.
- [ ] Validate data contract consistency.
- [ ] Configure GitHub CI checks.
- [ ] Verify main branch protection.
- [ ] Configure team repository access.
- [ ] Review environment variables.
- [ ] Review credential security.
- [ ] Complete Docker integration.
- [ ] Test deployment environment.
- [ ] Complete project documentation.
- [ ] Prepare final project demonstration.

## 13. Future Improvements

**Priority:** P3

- [ ] Batch-based collection for large datasets.
- [ ] Advanced skill extraction.
- [ ] Advanced similarity-based matching.
- [ ] Email notifications.
- [ ] Telegram notifications.
- [ ] Incremental collection optimization.
- [ ] Advanced pipeline observability.

## 14. Current Blockers

| ID | Blocker | Owner | Status |
|---|---|---|---|
| B-001 | Wuzzuf HTTP 403 | Mahmoud | Open |
| B-002 | Python models incompatible with Data Contract v2.0.0 | Mahmoud | Resolved |
| B-003 | Parser incompatible with new array fields | Mahmoud | Resolved |
| B-004 | Physical Bronze ingestion schema not implemented | Momen | Open |
| B-005 | Content history and retention policy not finalized | Mahmoud / Momen | Open |

## 15. Task Management Rules

- Every unresolved technical issue must be recorded in this document.
- Every architectural decision must be recorded in architecture_decisions.md.
- Tasks must only be marked complete after implementation and verification.
- Blocking issues must be addressed before dependent components are integrated.
- Data contract changes must be communicated to affected team members.
- Documentation must remain synchronized with implementation.
- Update this document before completing each development milestone.