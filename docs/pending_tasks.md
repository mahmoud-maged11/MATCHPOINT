# MATCHPOINT Pending Tasks

**Data Contract Version:** 3.0.0 (approved; ADR-050)

**Last Updated:** 2026-11-27

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
- [x] Remove AMIDEAST from the runtime source model and verify the final eight-source scope.
- [x] Resolve contract versioning for the narrowed source enumeration through ADR-050.
- [ ] Review updated documentation against implementation.
- [x] Approve Data Contract v3.0.0 through the delegated technical decision owner (ADR-050).
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
- [x] Configure all eight final sources.
- [x] Verify model and configuration source scope consistency.
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
- [x] NTI (collector implementation and bounded live validation)
- [x] Bayt (collector implementation and bounded live validation)
- [x] Devpost (collector implementation and bounded live validation)
- [x] UN Volunteers (collector implementation and bounded live validation)

Together with Wuzzuf, these constitute the final eight-source scope. AMIDEAST and the proposed replacement job source are out of scope; no additional initial collectors are planned.

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
- [x] Define stable source listing identity (ADR-042).
- [ ] Define source-specific URL identity rules.
- [ ] Generate source_listing_id.
- [ ] Track first collection timestamp.
- [ ] Track last_seen_at.
- [ ] Detect new listings.
- [ ] Detect unchanged listings.
- [ ] Detect updated listings.
- [x] Define content version history (ADR-043).
- [x] Define initial raw observation retention policy (ADR-043).
- [ ] Implement idempotent ingestion.
- [ ] Implement transaction handling.
- [ ] Implement PostgreSQL storage module.
- [ ] Test ingestion failure recovery.

## 7. Data Warehouse and Transformation

**Owner:** Momen

**Priority:** P1

- [ ] Review proposed Data Contract v3.0.0.
- [x] Design and implement the physical Bronze schema.
- [x] Design Silver and Gold transformation models.
- [x] Design and implement physical source listing tables.
- [x] Design and implement content history and observation ledger tables.
- [x] Design and implement the physical invalid record table.
- [x] Create and validate seven initial database migrations.
- [x] Initialize dbt project.
- [x] Configure dbt source definitions.
- [x] Implement staging models.
- [x] Implement intermediate models.
- [x] Implement Gold marts.
- [x] Normalize organization names.
- [x] Normalize locations.
- [x] Normalize skills.
- [x] Normalize categories.
- [x] Implement warehouse-level source listing identity preservation.
- [ ] Implement persistent ingestion-level retry deduplication.
- [x] Implement cross-source deduplication.
- [x] Define matching evidence and thresholds.
- [x] Generate deterministic canonical IDs for unchanged matching inputs.
- [ ] Implement persistent canonical identity reconciliation.
- [x] Preserve relationships between canonical opportunities and source listings.
- [x] Design fact and dimension tables.
- [x] Design skill bridge tables.
- [x] Implement data quality tests.
- [x] Document warehouse architecture.

### Warehouse Review Milestone

**Status:** Implemented and synthetic-tested.

- [x] Validate all 44 dbt models.
- [x] Pass all 483 dbt data tests.
- [x] Validate all eight supported sources using synthetic fixtures.
- [x] Preserve all 52 expanded source mappings.
- [x] Validate 44 expanded canonical opportunities.
- [x] Pass Silver integration scenarios S1-S10.
- [x] Pass Gold integration scenarios G1-G6.
- [x] Pass edge cases EC1-EC11.
- [x] Verify Silver mapping idempotency.
- [x] Verify all 20 Gold snapshots.
- [ ] Validate warehouse transformations on recorded real data.
- [ ] Validate downstream derived-key compatibility.
- [ ] Validate production-scale performance.
- [ ] Complete Phase 7 end-to-end acceptance.
- [ ] Communicate final warehouse handoff to affected team members.

See dbt/docs/warehouse_review_2026_11_27.md.

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

- [x] Implement collection-layer unit tests (665 passing as of 2026-11-25).
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
| B-004 | Physical Bronze ingestion schema | Momen | Resolved: implemented, approved and locally tested |
| B-005 | Initial content history and retention design | Mahmoud / Momen | Design approved; implementation and production retention review pending |
| B-006 | PostgreSQL storage integration | Mahmoud / Momen | Schema dependency resolved; implementation pending |
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
- [x] Complete bounded collection validation for all eight final source adapters.

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

### Next Milestone: Persistent Ingestion

- [x] Approve physical Bronze schema through ADR-050.
- [x] Approve source identity and uniqueness constraints.
- [x] Approve content version history and observation retention.
- [ ] Implement PostgreSQL connection and transaction management.
- [ ] Implement idempotent inserts and updates.
- [ ] Persist collection runs and associate observations with run IDs.
- [ ] Persist invalid records and permitted diagnostics.
- [ ] Track first_seen_at and last_seen_at.
- [ ] Detect new, unchanged and updated source listings.
- [ ] Test rollback, retries and recovery without duplicate writes.
- [ ] Integrate incremental checkpoints with committed transactions.
- [ ] Validate complete source-to-Bronze ingestion.

Initial collectors implemented and bounded live validated:

- [x] Wuzzuf
- [x] Forasna
- [x] Egyincs
- [x] ITIDA
- [x] NTI
- [x] Bayt
- [x] Devpost
- [x] UN Volunteers

**Progress:** 8/8 (100%).
**Status:** Completed.
**Regression tests:** 665 passed.

Excluded sources:
- LinkedIn
- Tanqeeb
- AMIDEAST
- Proposed replacement job source

These sources are outside the final project scope.

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

### Historical Collection Progress (NTI stage)

Initially implemented and bounded-live validated sources:

1. Wuzzuf
2. Forasna
3. Egyincs
4. ITIDA
5. NTI

Remaining initial source implementations:

None. All eight sources have been implemented
and bounded-live validated.

**Collection implementation progress:** 8/8 (100%).
**Status:** Completed.
**Next phase:** PostgreSQL Bronze ingestion and warehouse integration.

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

## Historical Source Implementation Status (Bayt stage)

**Last updated:** 2026-11-25

- Historical source implementation progress: 6/10 (60%), under the former scope.
- Completed: Wuzzuf, Forasna, Egyincs, ITIDA, NTI, Bayt.
- Regression tests at that milestone: 498 passed.
- Previously planned next source: Replacement job source (TBD).
- Previously remaining sources: Replacement job source (TBD), AMIDEAST, Devpost, UN Volunteers. Superseded by the final eight-source scope.

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

---

## UN Volunteers Collection Milestone

**Date:** 2026-11-25

**Status:** Initial collector implemented and bounded live validated.

- [x] Discover JSON search and assignment detail API endpoints.
- [x] Implement bounded POST search pagination and GET detail retrieval.
- [x] Validate response structure, source IDs and listing/detail consistency.
- [x] Filter online assignments globally and onsite assignments in Egypt only.
- [x] Exclude unsupported modalities, reserved and single-source assignments, and non-recruiting records.
- [x] Implement conservative deadline and lifecycle evaluation.
- [x] Map volunteering opportunities and retain selected source metadata.
- [x] Preserve unverified Egyptian applicant eligibility explicitly.
- [x] Integrate source configuration and CLI.
- [x] Disable automatic HTTP retries and redirects for the collector.
- [x] Validate online and Egyptian onsite collection through bounded live runs.
- [x] Verify missing or unknown employment types map to null rather than an empty array.
- [x] Verify full-time and part-time mapping.
- [x] Pass 71 UN Volunteers tests and 665 full regression tests.
- [ ] Complete architecture and data contract documentation updates.

### Live Validation Evidence

- First run: 20 accepted online active assignments; 4 listing pages, 80 discovered, 55 excluded, 5 unprocessed at the collection cap; zero duplicates, invalid records or missing details.
- Second run: 40 accepted assignments; 7 listing pages, 140 discovered, 83 excluded, 17 unprocessed at the collection cap; zero duplicates, invalid records or missing details.
- Second run modality: 39 online and 1 onsite in Egypt.
- Second run lifecycle: 39 active and 1 unknown.
- Second run: 47 successful HTTP requests, approximately 93 seconds.
- Both runs were bounded samples, not exhaustive collection. The second local JSON export predates the employment-type null correction; the correction was verified by automated tests, not a new live run.
- Distinct source IDs with identical titles were observed. Preserve both source listings pending semantic deduplication evidence.

### UN Volunteers Deferred Tasks

- [ ] Verify nationality, residency and other Egyptian applicant eligibility restrictions.
- [ ] Distinguish online host-country metadata from actual work location.
- [ ] Resolve API/UI deadline differences, source timezone and conservative expiration buffer.
- [ ] Validate experience units and normalize experience only with reliable evidence.
- [ ] Resolve conflicting hours-per-week labels and codes.
- [ ] Validate assignment duration, category and compensation metadata.
- [ ] Review raw-only metadata changes for content version tracking.
- [ ] Review free-text privacy and selected payload retention.
- [ ] Validate complete pagination coverage and changing listing boundaries.
- [ ] Confirm production authorization, request limits and scheduling.
- [ ] Implement safe retry policies, recovery and persistent checkpoints.
- [ ] Persist collection runs, invalid records and source observations.
- [ ] Integrate PostgreSQL Bronze ingestion and lifecycle reconciliation.
- [ ] Review semantic duplicate candidates with the warehouse owner.
- [ ] Integrate Airflow orchestration and production monitoring.

## Final Initial Source Implementation Status

**Last updated:** 2026-11-25

- [x] Wuzzuf
- [x] Forasna
- [x] Egyincs
- [x] ITIDA
- [x] NTI
- [x] Bayt
- [x] Devpost
- [x] UN Volunteers

**Initial collector progress:** 8/8 (100%).

**Current regression baseline:** 665 passed (2.01 seconds).

**Scope:** No additional initial sources planned. Earlier ten-source progress sections are historical snapshots, superseded by this final scope.

**Next milestone:** Complete documentation and contract version review, coordinate physical Bronze schema and ingestion design, and implement persistent ingestion before downstream integration.

Bounded live validation and passing unit tests do not establish production authorization, exhaustive coverage, complete applicant eligibility, persistent ingestion or end-to-end pipeline readiness.

---

## Bronze Physical Schema Implementation Milestone

**Date:** 2026-11-26

**Branch:** feature/data-warehouse

**Implementation:** Mahmoud

**Warehouse component owner:** Momen

**Status:** Approved, implemented and locally tested.

**Architecture references:** ADR-041 through ADR-050.

### Completed: Physical Database Infrastructure

- [x] Integrate the collection branch into the warehouse branch.
- [x] Verify PostgreSQL 16 container connectivity.
- [x] Create Bronze schema.
- [x] Create Silver schema.
- [x] Create Gold schema.
- [x] Create collection_runs table.
- [x] Create source_listings table.
- [x] Create source_listing_history table.
- [x] Create ingestion_observations table.
- [x] Create invalid_records table.
- [x] Create source_checkpoints table.
- [x] Implement primary key constraints.
- [x] Implement foreign key constraints.
- [x] Implement source identity uniqueness constraints.
- [x] Implement content history uniqueness constraints.
- [x] Implement observation ledger uniqueness constraints.
- [x] Implement invalid record uniqueness constraints.
- [x] Implement checkpoint uniqueness constraints.
- [x] Implement physical check constraints.
- [x] Create initial database indexes.
- [x] Create seven SQL migration files.
- [x] Approve Data Contract v3.0.0.
- [x] Approve initial Bronze physical design.

### Completed: Database Validation

- [x] Verify all six Bronze tables.
- [x] Verify all 96 Bronze columns.
- [x] Implement positive SQL test script.
- [x] Implement negative SQL test script.
- [x] Pass seven positive SQL checks.
- [x] Pass sixteen negative SQL checks.
- [x] Verify rollback of positive test data.
- [x] Create an isolated migration test database.
- [x] Reapply all seven migrations from scratch.
- [x] Verify reconstructed schemas and tables.
- [x] Verify reconstructed column counts.
- [x] Repeat all 23 SQL checks successfully.
- [x] Remove the temporary test database.
- [x] Verify that the primary database remains available.

### Validation Summary

| Metric | Result |
|---|---:|
| Project schemas | 3 |
| Bronze tables | 6 |
| Bronze columns | 96 |
| SQL migrations | 7 |
| SQL test files | 2 |
| Positive checks | 7 passed |
| Negative checks | 16 passed |
| Distinct SQL checks | 23 passed |
| Successful executions across both databases | 46 |
| Previous collection-layer Python regression baseline | 665 passed |

The Python regression baseline was established on
2026-11-25 and is reported separately from SQL checks.

SQL checks validate selected physical constraints.
They do not establish complete ingestion correctness.

### Next: PostgreSQL Storage Module

**Owner:** Mahmoud

**Priority:** P0

- [ ] Select and configure the PostgreSQL Python driver.
- [ ] Verify driver compatibility with the local Python version.
- [ ] Implement database connection configuration.
- [ ] Implement connection and transaction management.
- [ ] Introduce the HASH_VERSION constant.
- [ ] Define deterministic observation hashing.
- [ ] Define deterministic rejection hashing.
- [ ] Implement source identity generation.
- [ ] Reject missing or unusable source identifiers.
- [ ] Validate source consistency between listings and runs.
- [ ] Implement persistent collection run creation.
- [ ] Implement collection run finalization.
- [ ] Implement collection run failure handling.
- [ ] Define persistent run counter semantics.
- [ ] Implement new listing insertion.
- [ ] Implement initial content history creation.
- [ ] Implement changed listing detection.
- [ ] Implement content version increments.
- [ ] Implement unchanged listing handling.
- [ ] Refresh latest permitted raw payloads.
- [ ] Preserve original first_seen_at timestamps.
- [ ] Track collected_at and last_seen_at.
- [ ] Associate listings with collection run IDs.
- [ ] Implement observation ledger writes.
- [ ] Implement identical retry detection.
- [ ] Implement conflicting retry detection.
- [ ] Implement stale observation handling.
- [ ] Define equal-timestamp observation conflict rules.
- [ ] Implement equal-timestamp observation handling.
- [ ] Prevent duplicate processing counters.
- [ ] Implement row-level locking.
- [ ] Handle concurrent initial listing inserts.
- [ ] Implement atomic current/history/ledger writes.
- [ ] Integrate persistent invalid record storage.
- [ ] Sanitize retained rejection diagnostics.
- [ ] Distinguish record errors from infrastructure failures.
- [ ] Integrate storage with the shared collection CLI.
- [ ] Preserve existing JSON export functionality.

### Next: Persistent Ingestion Testing

**Owners:** Mahmoud and Momen

**Priority:** P0

- [ ] Test PostgreSQL connectivity from Python.
- [ ] Test new listing insertion.
- [ ] Test unchanged listing processing.
- [ ] Test changed listing processing.
- [ ] Test A-to-B-to-A content version history.
- [ ] Test identical retries within the same run.
- [ ] Test retries after newer runs have completed.
- [ ] Test conflicting observations within the same run.
- [ ] Test stale observations.
- [ ] Test equal-timestamp observations.
- [ ] Test missing source identifiers.
- [ ] Test source/run consistency.
- [ ] Test invalid record persistence.
- [ ] Test duplicate rejection prevention.
- [ ] Test transaction rollback.
- [ ] Test concurrent ingestion.
- [ ] Test partial failure and recovery.
- [ ] Test persistent run counters.
- [ ] Test raw payload refresh without content changes.
- [ ] Validate ingestion using the 40-record handover sample.
- [ ] Validate all eight source-to-Bronze integrations.
- [ ] Run the complete Python regression suite.
- [ ] Strengthen SQL tests to identify individual constraints.

### Next: Lifecycle and Transformation

**Owners:** Mahmoud and Momen

**Priority:** P1

- [x] Initialize dbt project.
- [x] Configure Bronze source definitions.
- [x] Implement Silver staging models.
- [x] Normalize organizations, locations and skills.
- [x] Implement effective opportunity status.
- [x] Validate reliable deadline expiration.
- [x] Handle date-only and uncertain deadlines.
- [x] Preserve explicit closure and expiration evidence.
- [ ] Prevent closure inference from bounded-run absence.
- [ ] Validate reopened opportunities.
- [ ] Define lifecycle revalidation schedules.
- [ ] Define time-dependent transformation freshness.
- [x] Implement canonical opportunity identities.
- [x] Implement evidence-based cross-source deduplication.
- [x] Implement Gold facts, dimensions and bridge tables.
- [x] Implement dbt data quality tests.

Completed transformation tasks are verified on synthetic data only.
Operational lifecycle reconciliation and real-data integration remain pending.

### Deferred: Incremental Collection

**Owners:** Mahmoud, Momen and Andrew

- [x] Implement physical source_checkpoints table.
- [ ] Define source-specific incremental strategies.
- [ ] Validate supported checkpoint representations.
- [ ] Implement independent Egyincs endpoint scopes.
- [ ] Implement checkpoint source/run/scope validation.
- [ ] Implement successful checkpoint advancement.
- [ ] Commit run finalization and checkpoint updates atomically.
- [ ] Preserve checkpoints after failed or partial runs.
- [ ] Implement overlapping collection windows.
- [ ] Handle equal timestamp boundaries.
- [ ] Implement stable pagination and recovery.
- [ ] Test incremental collection before activation.

### Deferred: Hash Version Migration

**Owners:** Mahmoud and Momen

**Architecture reference:** ADR-045

- [x] Define initial hash version compatibility.
- [x] Enforce hash_version = 1 in the initial schema.
- [x] Document future hash migration design.
- [ ] Implement hash_migrations audit table.
- [ ] Implement reconciliation_observations table.
- [ ] Implement ingestion_state singleton table.
- [ ] Add needs_reconciliation listing metadata.
- [ ] Add reconciliation_reason listing metadata.
- [ ] Add reconciliation_required_at listing metadata.
- [ ] Implement active hash version management.
- [ ] Implement current listing rehashing.
- [ ] Preserve historical hash versions.
- [ ] Prevent artificial content history creation.
- [ ] Prevent artificial collection run creation.
- [ ] Implement missing-input reconciliation.
- [ ] Preserve observations during reconciliation.
- [ ] Implement chronological observation replay.
- [ ] Implement reconciliation resolution auditing.
- [ ] Implement reconciliation retry conflict detection.
- [ ] Implement shared run coordination lock 710002.
- [ ] Implement shared write coordination lock 710001.
- [ ] Implement exclusive migration coordination.
- [ ] Enforce advisory lock acquisition order.
- [ ] Implement pinned connection management.
- [ ] Handle coordination connection loss.
- [ ] Implement abandoned migration recovery.
- [ ] Test migration rollback and audit persistence.
- [ ] Test hash migration concurrency.
- [ ] Test reconciliation and recovery.

### Deferred: Production Database Readiness

- [ ] Implement persistent migration execution tracking.
- [ ] Define database schema upgrade procedures.
- [ ] Review database roles and permissions.
- [ ] Review historical record write protection.
- [ ] Define raw payload retention periods.
- [ ] Define invalid record retention periods.
- [ ] Implement approved retention and purge procedures.
- [ ] Review source-specific raw-only content changes.
- [ ] Review payload and free-text privacy.
- [ ] Implement controlled invalid record reprocessing.
- [ ] Validate persistent Docker volume behavior.
- [ ] Implement backup and restore procedures.
- [ ] Review indexes using representative query workloads.
- [ ] Configure automated database integration tests.
- [ ] Configure database monitoring.

### Documentation and Repository Integration

- [x] Document Bronze architecture decisions.
- [x] Record technical design approval in ADR-050.
- [ ] Synchronize Data Contract documentation.
- [ ] Synchronize README instructions.
- [ ] Synchronize final project documentation.
- [ ] Review staged migration and test files.
- [ ] Commit Bronze implementation milestone.
- [ ] Push the warehouse feature branch.
- [ ] Communicate the approved design to team members.
- [ ] Coordinate downstream component integration.

### Current Milestone Boundaries

The physical Bronze schema is implemented, approved
and locally tested.

Persistent Python ingestion is not yet implemented.

Silver and Gold transformations are implemented and
synthetic-tested. Real-data integration remains pending.

Incremental collection is not activated.

Future hash migration and reconciliation structures
are intentionally deferred.

Production authorization, exhaustive source coverage,
privacy review and end-to-end pipeline readiness
remain separate requirements.

Existing team component ownership remains unchanged.