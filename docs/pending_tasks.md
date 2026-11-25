# MATCHPOINT Pending Tasks

**Data Contract Version:** 2.1.0

**Last Updated:** 2026-11-25

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
- [x] Pass all 30 model and hashing tests.
- [x] Prepare Data Contract v2.1.0.
- [x] Add salary_period and source_status_raw.
- [x] Update architecture decisions for Wuzzuf API collection.
- [ ] Review updated documentation against implementation.
- [ ] Obtain team approval for Data Contract v2.1.0.
- [x] Commit and push Data Contract v2.1.0 to the feature branch.
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
- [ ] Configure remaining seven sources.
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
- [x] Replace real HTML fixtures in automated tests with synthetic fixtures and exclude real source HTML from Git.
- [x] Implement and pass 15 automated Wuzzuf parser tests using synthetic HTML fixtures.
- [x] Complete bounded live adapter validation.
- [ ] Complete source-to-Bronze integration validation.


### Pending


- [x] Investigate authorized live collection methods.
- [x] Establish an alternative live collection method using the JSON API.
- [x] Implement live data collection.
- [x] Implement pagination.
- [ ] Investigate public job detail page availability if required.
- [x] Extract job descriptions.
- [x] Extract job requirements.
- [x] Extract education requirements.
- [x] Extract salary information when available.
- [x] Implement source-specific status detection.
- [x] Handle missing and malformed job cards in local HTML fixtures.
- [x] Verify that invalid records do not interrupt valid record extraction.
- [x] Preserve rejected records with raw HTML, error details, and collection run ID in memory.
### API Collection Milestone

- [x] Implement Wuzzuf API adapter.
- [x] Implement Wuzzuf API mapper.
- [x] Collect newest listings using descending postedAt.
- [x] Request active source listings.
- [x] Filter Egyptian opportunities using country code EG.
- [x] Implement company information caching.
- [x] Handle missing company responses.
- [x] Preserve hidden company and salary fields as null.
- [x] Extract salary periods.
- [x] Preserve original source status.
- [x] Validate source URLs and listing identifiers.
- [x] Implement selected source payload retention.
- [x] Handle malformed API records.
- [x] Implement collection statistics.
- [x] Implement conservative deadline evaluation.
- [x] Handle date-only deadlines.
- [x] Pass all 130 automated tests.
- [x] Collect 30 live Egyptian opportunities.
- [x] Verify zero duplicate IDs and zero invalid records in the live sample.

### Remaining Integration Work

- [ ] Integrate PostgreSQL storage after Bronze schema approval.
- [ ] Persist collection runs and invalid records.
- [ ] Implement incremental checkpoints.
- [ ] Implement content version history.
- [ ] Implement lifecycle reconciliation.
- [ ] Review source payload and URL privacy.
- [ ] Confirm production collection limits and scheduling.
- [ ] Verify API stability during scheduled execution.

**Current limitation:** Direct live HTML collection remains restricted.

**Integration dependency:** Physical Bronze schema design and migrations
must be coordinated with the Data Warehouse owner.

## 4. Additional Source Adapters

**Owner:** Mahmoud

**Priority:** P1

- [x] Forasna (collector implementation and bounded live validation)
- [x] Egyincs (collector implementation and bounded live validation)
- [x] ITIDA (collector implementation and bounded live validation)
- [x] NTI
- [ ] Bayt
- [ ] Replacement job source (TBD)
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


### Forasna Collection Milestone

- [x] Investigate website structure and robots.txt.
- [x] Verify live HTML access.
- [x] Identify search and detail page selectors.
- [x] Implement JSON-LD and HTML hybrid extraction.
- [x] Implement pagination using rel=next.
- [x] Implement source ID extraction and validation.
- [x] Implement duplicate ID detection.
- [x] Filter listings using Egyptian country code EG.
- [x] Extract descriptions, categories and requirements.
- [x] Normalize Arabic experience ranges.
- [x] Preserve original experience labels.
- [x] Normalize timezone-aware dates to UTC.
- [x] Implement salary extraction and missing salary handling.
- [x] Implement application status and deadline evaluation.
- [x] Implement internship classification.
- [x] Verify internship classification against a live listing.
- [x] Integrate Forasna with the shared CLI.
- [x] Pass 55 Forasna-specific automated tests.
- [x] Pass all 185 collection-layer automated tests.
- [x] Collect 5 live opportunities for field validation.
- [x] Collect 30 live opportunities across two search pages.
- [x] Verify zero duplicate IDs and zero invalid records.

### Forasna Remaining Integration Work

- [ ] Verify disclosed salary extraction against live samples.
- [ ] Verify freelance and remote classification against live samples.
- [ ] Review ambiguous experience and employment classifications.
- [ ] Review robots.txt wildcard and redirect handling.
- [ ] Review source payload minimization and privacy.
- [ ] Confirm production collection limits and scheduling.
- [ ] Integrate PostgreSQL storage.
- [ ] Persist collection runs and invalid records.
- [ ] Implement incremental checkpoints.
- [ ] Implement lifecycle reconciliation.
- [ ] Verify source-to-Bronze integration.


### Egyincs Collection Milestone

- [x] Investigate WordPress REST API and robots.txt.
- [x] Identify jobs and lp_course endpoints.
- [x] Identify company and taxonomy endpoints.
- [x] Implement API collector and source-specific mapper.
- [x] Implement bounded page-based pagination.
- [x] Implement company information caching.
- [x] Implement duplicate source ID detection.
- [x] Implement jobs and courses collection quotas.
- [x] Implement taxonomy-based classification.
- [x] Implement title-based classification fallback.
- [x] Recognize graduate programs.
- [x] Normalize internship and scholarship classifications.
- [x] Normalize volunteering, freelance and competition classifications.
- [x] Normalize training and event classifications.
- [x] Extract source-provided categories and candidate skills.
- [x] Normalize experience labels and numeric bounds.
- [x] Extract disclosed salary ranges.
- [x] Normalize Egyptian pound currency to EGP.
- [x] Normalize salary periods.
- [x] Reject invalid and non-finite salary amounts.
- [x] Preserve permitted selected source metadata.
- [x] Integrate Egyincs with the shared CLI.
- [x] Fix malformed JOB_FIELDS concatenation.
- [x] Add regression test for required API fields.
- [x] Pass 75 Egyincs-specific automated tests.
- [x] Pass all 260 collection-layer automated tests.
- [x] Collect 20 opportunities across three API pages.
- [x] Verify 20 unique source IDs and zero invalid records.
- [x] Verify four targeted live opportunity mappings.
- [x] Verify two disclosed monthly salaries through the list endpoint.
- [x] Validate seven special source taxonomy groups.
- [x] Map 13 special-type observations representing 12 unique listings.

### Egyincs Remaining Integration Work

**Priority:** P1/P2

- [ ] Verify application availability and effective lifecycle status.
- [ ] Investigate deadline and expiration field semantics.
- [ ] Distinguish WordPress publication status from application status.
- [ ] Review publication dates versus republished listing dates.
- [ ] Normalize valid application URLs without a scheme.
- [ ] Preserve functional application URL query parameters.
- [ ] Review external URL privacy and tracking parameters.
- [ ] Normalize placeholder values in requirements and other fields.
- [ ] Improve work mode fallback using source type taxonomies.
- [ ] Review ambiguous initiative classification.
- [ ] Review multi-label opportunity classification.
- [ ] Review conflicting experience labels and ranges.
- [ ] Review salary display modes beyond explicit ranges.
- [ ] Review embedded taxonomy terms against assigned term IDs.
- [ ] Distinguish candidate requirements from taught skills.
- [ ] Enrich course provider, duration, fees and certificate information.
- [ ] Enrich course registration URLs and delivery modes.
- [ ] Separate opportunity destination from applicant eligibility location.
- [ ] Review conflicting location taxonomies and descriptions.
- [ ] Review editorial content included in descriptions.
- [ ] Improve permitted invalid record diagnostics.
- [ ] Review cross-source application URL matching evidence.
- [ ] Improve jobs and courses quota allocation.
- [ ] Handle unused collection quota redistribution.
- [ ] Review rare opportunity type coverage.
- [ ] Review pagination when source records change during collection.
- [ ] Handle out-of-range WordPress pagination responses.
- [ ] Confirm authorized production collection limits.
- [ ] Integrate PostgreSQL storage and persistent collection runs.
- [ ] Implement incremental collection and lifecycle reconciliation.
- [ ] Verify source-to-Bronze integration.

### ITIDA Collection Milestone

Status: Initial collector implemented and live validated
Date: 2026-11-25

Completed:

- [x] Investigate ITIDA website structure.
- [x] Inspect robots.txt rules.
- [x] Identify SharePoint program and event pages.
- [x] Investigate visible and hidden HTML content.
- [x] Validate ASP.NET postback pagination.
- [x] Extend shared HTTPClient with POST support.
- [x] Implement ITIDA mapper.
- [x] Implement ITIDA collector.
- [x] Implement supported program discovery.
- [x] Implement bounded event pagination.
- [x] Implement stable source identities.
- [x] Implement conservative lifecycle normalization.
- [x] Retain historical opportunities.
- [x] Integrate ITIDA into the collection CLI.
- [x] Implement mapper and collector unit tests.
- [x] Fix nested hidden HTML element handling.
- [x] Complete bounded live collection validation.

Validation results:

- Independent pagination: 3 pages and 18 unique event URLs.
- Integrated collection: 20 accepted records.
- Programs: 9.
- Event archive records: 11.
- Event listing pages: 2.
- Invalid records: 0.
- Duplicate records: 0.
- Unavailable records: 0.
- Successful HTTP requests: 24.
- Execution time: approximately 52 seconds.
- ITIDA-specific tests: 64 passed.
- Full regression suite: 334 passed.

### ITIDA Remaining Integration Work

- [ ] Validate all supported program page classifications.
- [ ] Review company-oriented Train to Hire programs.
- [ ] Distinguish permanent programs from application cohorts.
- [ ] Extract verified application URLs.
- [ ] Improve program eligibility extraction.
- [ ] Improve location normalization.
- [ ] Extract delivery and work mode information.
- [ ] Improve organizer and training-provider attribution.
- [ ] Normalize event dates using the source-local timezone.
- [ ] Validate pagination beyond the initial bounded sample.
- [ ] Improve pagination state management.
- [ ] Prevent duplicate postback requests at archive termination.
- [ ] Evaluate dynamic discovery beyond the program allowlist.
- [ ] Investigate news and press release opportunities.
- [ ] Investigate Arabic page coverage.
- [ ] Implement incremental collection and checkpointing.
- [ ] Integrate PostgreSQL persistence.
- [ ] Integrate Airflow orchestration.
- [ ] Validate production execution and monitoring.

Historical and informational records must not be presented
as currently actionable opportunities without supporting evidence.

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
- [x] Verify content hashing with 12 automated tests.
- [x] Normalize equivalent decimal representations.
- [x] Include salary period and original source status in hashing.
- [ ] Define hash version compatibility before future schema changes.
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

- [ ] Review Data Contract v2.1.0.
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

- [x] Implement collection-layer unit tests (260 passing).
- [ ] Implement unit tests for remaining components.
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
| B-001 | Wuzzuf direct HTML HTTP 403 | Mahmoud | Non-blocking for tested API collection |
| B-002 | Python models incompatible with Data Contract v2.0.0 | Mahmoud | Resolved |
| B-003 | Parser incompatible with new array fields | Mahmoud | Resolved |
| B-004 | Physical Bronze ingestion schema not implemented | Momen | Open |
| B-005 | Content history and retention policy not finalized | Mahmoud / Momen | Open |
| B-006 | Storage integration awaiting agreed Bronze schema | Mahmoud / Momen | Open |
| B-007 | Opportunity lifecycle reconciliation not implemented | Mahmoud / Momen | Open |
| B-008 | Persistent incremental checkpoints depend on ingestion design | Mahmoud / Momen / Andrew | Open |
| B-009 | Production source authorization and rate policies require confirmation | Mahmoud | Open for production |
| B-010 | Egyincs application availability cannot yet be reliably established | Mahmoud | Non-blocking for bounded collection |

## 15. Task Management Rules

- Every unresolved technical issue must be recorded in this document.
- Every architectural decision must be recorded in architecture_decisions.md.
- Tasks must only be marked complete after implementation and verification.
- Blocking issues must be addressed before dependent components are integrated.
- Data contract changes must be communicated to affected team members.
- Documentation must remain synchronized with implementation.
- Update this document before completing each development milestone.

## 16. Retrospective Infrastructure Review

### Status Definitions

- Completed and tested: implemented and verified within the stated scope.
- Implemented, needs validation: implementation exists but additional verification is required.
- Deferred: intentionally postponed until a later development milestone.
- Blocked: depends on an unresolved external or architectural dependency.

### Completed and Tested

- [x] Initialize GitHub repository and project directory structure.
- [x] Merge initial project setup pull request.
- [x] Create component-specific feature branches.
- [x] Configure initial Docker Compose infrastructure.
- [x] Verify local PostgreSQL and ClickHouse connectivity during initial setup.
- [x] Implement environment variable configuration.
- [x] Exclude local credentials and real source HTML fixtures from Git.
- [x] Implement shared browser client and automated tests.
- [x] Verify shared collection CLI for implemented adapters.
- [x] Implement shared date normalization utilities.
- [x] Implement deterministic numeric and array hashing.
- [x] Implement and test in-memory invalid record handling.
- [x] Complete bounded collection validation for three source adapters.

### Implemented, Needs Validation

- [ ] Revalidate database containers and persistent volumes before ingestion.
- [ ] Validate dependency compatibility with the target deployment Python version.
- [ ] Validate browser client behavior against permitted live sources.
- [ ] Verify logging timezone configuration.
- [ ] Review retry behavior under real transient failures.
- [ ] Review source-specific HTTP timeouts and collection budgets.
- [ ] Verify date precision and timezone assumptions across all sources.
- [ ] Review hashing behavior for relative dates and effective status changes.
- [ ] Verify Forasna internship mapping for array-based employmentType values.
- [ ] Verify Forasna malformed salary handling and hidden salary payload retention.
- [ ] Review Wuzzuf hidden organization information in URLs and free text.
- [ ] Review Wuzzuf raw employment and work mode metadata retention.
- [ ] Revalidate Egyincs end-to-end collection after final field configuration fix.

### Deferred: Shared Collection Reliability

- [ ] Separate GET and POST retry policies.
- [ ] Restore safe GET connection retries.
- [ ] Verify transport-level POST replay prevention.
- [ ] Validate redirect destinations before following redirects.
- [ ] Improve ASP.NET pagination session-state isolation.
- [ ] Validate source-local timezone handling.
- [ ] Review hidden HTML removal across all HTML mappers.
- [ ] Implement retry-aware and redirect-aware request pacing.
- [ ] Coordinate rate limits across concurrent workers.
- [ ] Review robots.txt wildcard matching and crawl-delay policies.
- [ ] Validate redirect destinations before following requests.
- [ ] Establish documented authorization and collection policies for every source.
- [ ] Handle HTTP 429 and Retry-After consistently.
- [ ] Define source-specific circuit breaking and failure isolation.
- [ ] Define full initial collection versus incremental collection policies.
- [ ] Implement persistent per-source and per-endpoint checkpoints.
- [ ] Implement overlapping incremental collection windows.
- [ ] Handle equal timestamps and stable pagination boundaries.
- [ ] Advance checkpoints only after successful persistent ingestion.
- [ ] Support partial runs and safe recovery after failures.
- [ ] Define stale listing revalidation schedules.
- [ ] Never infer closure solely from absence in bounded collection.
- [ ] Implement persistent collection metrics and data quality reporting.
- [ ] Define raw payload retention and privacy policies.
- [ ] Exclude sensitive attributes from opportunity matching.
- [ ] Review free-text descriptions for unnecessary personal information.
- [ ] Implement controlled invalid record reprocessing.
- [ ] Implement automated collection integration tests.

### Deferred: Repository and Deployment

- [ ] Confirm team repository permissions and branch protection.
- [ ] Configure automated CI tests for pull requests.
- [ ] Review dependency pinning and reproducible builds.
- [ ] Align local Python dependencies with Airflow and dbt runtimes.
- [ ] Build production scraper container.
- [ ] Configure Docker networking and service health checks.
- [ ] Verify credential management and environment isolation.
- [ ] Implement database backup and restore procedures.
- [ ] Validate complete scheduled execution through Airflow.
- [ ] Review remaining team component status before integration.

### Blocked: Persistent Ingestion

- [ ] Approve physical Bronze schema with the Data Warehouse owner.
- [ ] Approve source identity and uniqueness constraints.
- [ ] Approve content version history and observation retention.
- [ ] Implement PostgreSQL connection and transaction management.
- [ ] Implement idempotent inserts and updates.
- [ ] Persist collection runs and associate observations with run IDs.
- [ ] Persist invalid records and permitted diagnostics.
- [ ] Track first_seen_at and last_seen_at.
- [ ] Detect new, unchanged and updated source listings.
- [ ] Test rollback, retries and recovery without duplicate writes.
- [ ] Integrate incremental checkpoints with committed transactions.
- [ ] Validate complete source-to-Bronze ingestion.

### Current Collection Milestone

Initial collectors implemented and bounded live validated:

- [x] Wuzzuf
- [x] Forasna
- [x] Egyincs
- [x] ITIDA
- [x] NTI
- [ ] Bayt
- [ ] Replacement job source (TBD)
- [ ] AMIDEAST
- [ ] Devpost
- [ ] UN Volunteers

Progress: 5 of 10 initial source collectors (50%).

Current automated regression baseline: 400 passed.

Next source: Bayt.

Collector completion does not imply production readiness,
persistent ingestion, full source coverage, verified active
opportunities or completed warehouse integration.

---

## NTI Implementation Milestone

**Date:** 2026-11-25

- [x] Discover initiative and category endpoints.
- [x] Discover dynamic course detail fragments.
- [x] Implement NTI mapper.
- [x] Implement NTI collector.
- [x] Implement course detail caching.
- [x] Implement shared career development fragment caching.
- [x] Register NTI source configuration.
- [x] Integrate NTI with CLI.
- [x] Validate bounded live collection.
- [x] Review representative normalized records.
- [x] Fix prerequisite classification issues.
- [x] Fix duration heading classification.
- [x] Pass targeted live mapper validation.
- [x] Pass 66 NTI-specific tests.
- [x] Pass 400 total regression tests.

### Remaining NTI Tasks

- [ ] Validate full category and center coverage.
- [ ] Implement coverage reporting and resumable collection.
- [ ] Improve initiative fairness during bounded collection.
- [ ] Investigate missing descriptions and requirements.
- [ ] Investigate missing CCNA duration metadata.
- [ ] Validate duration inference across all training programs.
- [ ] Preserve and validate initiative-level eligibility conditions.
- [ ] Normalize delivery modes and training locations.
- [ ] Verify positive registration availability evidence.
- [ ] Investigate application URL mapping.
- [ ] Validate live cache reuse across multiple centers.
- [ ] Validate track identity and center identifier consistency.
- [ ] Investigate diploma and additional training program coverage.
- [ ] Investigate CREATIVA category enrichment without duplicates.
- [ ] Improve prerequisite classification and skill normalization.
- [ ] Include meaningful training metadata changes in version tracking.
- [ ] Review source access conditions and authorization scope.

### Shared Production Tasks

- [ ] Prevent unvalidated HTTP redirects before following them.
- [ ] Improve retry pacing and request policy enforcement.
- [ ] Standardize source access policy handling.
- [ ] Implement full-load collection across bounded batches.
- [ ] Implement incremental collection and checkpoints.
- [ ] Implement persistent run tracking.
- [ ] Integrate PostgreSQL storage with the agreed warehouse schema.
- [ ] Implement idempotent writes and opportunity version history.
- [ ] Integrate collectors with Airflow.
- [ ] Validate production data coverage for every source.

### Current Collection Progress

Initially implemented and bounded-live validated sources:

1. Wuzzuf
2. Forasna
3. Egyincs
4. ITIDA
5. NTI

Remaining initial source implementations:

6. Bayt
7. Replacement job source (TBD)
8. AMIDEAST
9. Devpost
10. UN Volunteers

Current milestone: 5 of 10 initial collectors implemented.

Regression baseline: 400 passing tests.

This milestone does not represent full production readiness.

---

## Bayt Implementation Milestone

**Date:** 2026-11-25

**Implementation status:** Completed and validated locally.

- Hybrid listing discovery implemented.
- JSON-LD and HTML detail mapping implemented.
- Source configuration and CLI integration implemented.
- Pagination and source ID deduplication implemented.
- 98 Bayt unit tests passed.
- 498 total regression tests passed.
- Live collection returned 35 unique active jobs.
- Two listing pages validated.
- Zero invalid records in the live sample.

### Bayt Deferred Tasks

- [ ] Validate authorization scope for production collection.
- [ ] Implement complete source coverage and pagination checkpoints.
- [ ] Implement incremental collection and recovery.
- [ ] Support robots.txt wildcard rules consistently.
- [ ] Align actual HTTP User-Agent with robots evaluation.
- [ ] Prevent unauthorized redirects before following them.
- [ ] Improve handling of empty listings and terminal pages.
- [ ] Validate remote eligibility when jobLocation is missing.
- [ ] Reconcile structured work modes with explicit prose.
- [ ] Improve free-text experience and education extraction.
- [ ] Separate mandatory skills from preferred skills.
- [ ] Validate live internship and closed/expired records.
- [ ] Review salary range and period accuracy across more samples.
- [ ] Investigate external and aggregated flag semantics.
- [ ] Implement semantic deduplication across distinct source IDs.
- [ ] Integrate persistent storage after warehouse schema agreement.

---

## Current Source Implementation Status

**Last updated:** 2026-11-25

- Completed source implementations: 6/10 (60%).
- Completed: Wuzzuf, Forasna, Egyincs, ITIDA, NTI, Bayt.
- Total regression tests: 498 passed.
- Next source: Replacement job source (TBD).
- Remaining: Replacement job source (TBD), AMIDEAST, Devpost, UN Volunteers.

Production coverage, incremental collection, persistent
storage and orchestration integration remain pending.

## Devpost Collection Milestone

**Status:** Implemented and live validated

**Validation date:** 2026-11-25

- [x] API investigation
- [x] Pagination investigation
- [x] HTML and JSON-LD investigation
- [x] Mapper implementation
- [x] Collector implementation
- [x] Source configuration
- [x] CLI integration
- [x] Offline mapping validation
- [x] Unit tests
- [x] Initial live collection
- [x] Country allowlist and blocklist handling
- [x] Final live validation
- [x] Architecture documentation
- [x] Data contract documentation

### Deferred improvements

- [ ] Full official rules parsing.
- [ ] Structured age and student eligibility.
- [ ] Structured team-size restrictions.
- [ ] Complete country-name normalization.
- [ ] Support for Egyptian physical and hybrid events.
- [ ] Verification of registration availability.
- [ ] Separate normalized registration and submission dates.
- [ ] Structured prize amount and currency extraction.
- [ ] Validation of unusually distant submission deadlines.
- [ ] Explicit stale-deadline checks for upcoming events.
- [ ] Improved extraction for missing country lists.
- [ ] Additional HTML layout fallback coverage.
- [ ] Verification of API filter semantics and full coverage.
- [ ] Incremental collection checkpoints.
- [ ] Persistent invalid-record storage.
- [ ] Cross-process rate limiting and retry pacing.
- [ ] Automated source structure change detection.
- [ ] Airflow scheduling and PostgreSQL integration.
- [ ] Confirm production authorization scope and limits.

### Known limitations

The final sample contains 20 unique online hackathons.

Country filtering reduces known geographic conflicts,
but does not establish complete participant eligibility.

The API and HTML structures may change without notice.

Collection is bounded and does not guarantee exhaustive
coverage.

The final validation checked the collector output in
memory. The earlier local JSON export predates the
country eligibility fix and is not a final dataset.

Database persistence and orchestration remain pending.
