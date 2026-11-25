# MATCHPOINT Architecture Decisions

**Related Data Contract:** v3.0.0 (proposed; pending team approval)

**Purpose:** Document architectural decisions, their rationale, and implementation requirements.

## ADR-001: Multiple Employment Types

**Status:** Implemented in collection layer; warehouse integration pending

**Problem:** A single opportunity may support multiple employment types.

**Decision:** Replace employment_type with employment_types, represented as a JSONB array.

**Reason:** Prevent information loss and support accurate opportunity filtering.

**Example:** ["part_time", "freelance"]

## ADR-002: Multiple Work Modes

**Status:** Implemented in collection layer; warehouse integration pending

**Decision:** Replace work_mode with work_modes, represented as a JSONB array.

**Reason:** Support opportunities offering multiple working arrangements.

## ADR-003: Source Listing and Canonical Opportunity Identity

**Status:** Selected, implementation pending

**Decision:** Maintain two independent identifiers:

- source_listing_id: Identifies an individual source listing.
- opportunity_id: Identifies a canonical business opportunity.

Multiple source listings may reference the same canonical opportunity.

Identifiers must remain stable across pipeline executions.

**Reason:** Prevent duplicate opportunities while preserving source attribution.

## ADR-004: Cross-source Deduplication

**Status:** Selected, implementation pending

**Decision:** Perform cross-source deduplication during Silver layer transformations.

Matching may consider:

- Normalized job titles
- Organization names
- Locations
- Descriptions
- Requirements
- Skills
- Publication information

Similarity alone must not automatically establish identity.

Original source listings must remain available after deduplication.

## ADR-005: Content Change Detection

**Status:** Hashing implemented and tested; persistent ingestion pending

**Decision:** Use SHA-256 hashing to detect changes in standardized source content.

Content hashing must exclude:

- Source identifiers
- Collection timestamps
- Ingestion metadata
- Raw payload
- Volatile relative date labels
- Derived approximate timestamps

Unordered arrays must be sorted before hashing.

Source identity and content hash must be evaluated together.

Unchanged listings must still have their last_seen_at updated.

**Remaining work:** Integrate hashing with PostgreSQL ingestion and define hash version compatibility.

## ADR-006: Date Precision and Timezones

**Status:** Implemented in collection layer; warehouse integration pending

**Decision:** Preserve original date representations and their precision.

Supported precision values:

- exact
- date_only
- relative
- unknown

Normalized timestamps must be timezone-aware and stored in UTC.

Relative dates must not be converted into precise timestamps without a reliable observation time.

Local HTML parsing time must not automatically be treated as the original observation time.

Date-only deadlines must retain their original precision.

## ADR-007: Skills and Categories Separation

**Status:** Implemented in collection layer; warehouse integration pending

**Decision:** Maintain separate fields for required_skills and categories.

Source-provided skill tags are treated as candidate skills until validated during transformation.

Broad academic disciplines and industry classifications must not automatically be classified as technical skills.

## ADR-008: Experience Normalization

**Status:** Implemented in collection layer; warehouse integration pending

**Decision:** Preserve original experience labels and extract experience ranges separately.

Fields:

- experience_level
- experience_level_raw
- experience_years_min
- experience_years_max

Ambiguous experience labels must not be mapped to specific seniority levels without documented evidence.

## ADR-009: Invalid Record Retention

**Status:** In-memory handling implemented; persistent storage pending

**Decision:** Preserve invalid source records separately for investigation and potential reprocessing.

Invalid record metadata should include:

- Source name
- Source URL, when available
- Permitted diagnostic payload
- Collection timestamp
- Validation error
- Pipeline run identifier

Invalid records must not enter validated Silver datasets until corrected.

## ADR-010: Medallion Architecture

**Status:** Selected, implementation pending

**Decision:** Use PostgreSQL for Bronze, Silver, and Gold data layers.

Bronze preserves source data and ingestion metadata.

Silver performs cleaning, normalization, validation, and deduplication.

Gold provides business-ready datasets for application integration and analytics.

ClickHouse stores analytical datasets prepared by the pipeline.

## ADR-011: Missing Information

**Status:** Selected, partially implemented

**Decision:** Missing information must be represented as null rather than fabricated values.

For arrays:

- null indicates unavailable information.
- An empty array indicates confirmed absence.

Missing deadlines must not automatically classify opportunities as expired.

## ADR-012: Currency Validation

**Status:** Implemented in collection layer; warehouse integration pending

**Decision:** Validate currency codes against ISO 4217.

Salary values must be non-negative.

Minimum salary must not exceed maximum salary.

A three-letter pattern alone is insufficient to validate a currency code.

## ADR-013: Source Adapter Architecture

**Status:** Partially implemented

**Decision:** Use independent source adapters with shared infrastructure.

Shared components:

- Configuration
- Logging
- HTTP client
- Pydantic models
- Base scraper
- Content hashing
- Storage integration

Each adapter is responsible for source-specific extraction.

Parsing must remain independently testable using local HTML fixtures or equivalent source samples.

## ADR-014: Source Access and Collection

**Status:** Wuzzuf API collection verified; direct HTML access remains restricted

**Decision:** Collect data using authorized access methods and source-specific collection policies.

Prefer official APIs or feeds when available and suitable.

Respect access restrictions, rate limits, and permitted collection scope.

HTTP 403 responses must be investigated before automated collection continues.

Successful local parsing does not establish successful live collection.

**Verified collection method:** Wuzzuf JSON API.

The tested endpoints are:

- GET /api/job
- GET /api/company/{company_id}

The collector requests active listings ordered by descending postedAt.

Egyptian opportunities are selected using country code EG.

Company information is cached during each run.

Direct live HTML collection remains restricted by HTTP 403.

API availability does not establish an official or stable API contract.

Collection must remain within the approved access scope.

**Live verification on 2026-11-25:**

- 5 pages fetched.
- 37 records received.
- 30 opportunities accepted.
- 7 non-Egyptian records excluded.
- 0 duplicate IDs.
- 0 invalid records.
- 16 companies cached.
- 21 successful HTTP requests.
- Approximately 41 seconds execution time.

## ADR-015: Schema Evolution

**Status:** Selected

**Decision:** Manage data contract changes using semantic versioning and GitHub Pull Requests.

- Major: Breaking changes.
- Minor: Backward-compatible additions.
- Patch: Documentation corrections.

Architecture decisions must be documented in this file.

Outstanding implementation work must be tracked in docs/pending_tasks.md.

Affected team members must receive the updated contract before integration.

## ADR-016: Source History and Ingestion

**Status:** Detailed design pending

**Decision:** Maintain stable source listing identities and track content changes separately from collection events.

The detailed database design must define:

- First collection timestamp
- Last observation timestamp
- Content version history
- Raw observation retention
- Idempotent ingestion
- Transaction handling
- Ingestion failure recovery

The physical schema and retention policy must be documented before PostgreSQL integration.

## ADR-017: Salary Period and Original Source Status

**Status:** Implemented and tested in collection layer

**Decision:** Extend the Opportunity model with two optional fields:

- salary_period
- source_status_raw

**Reason:** Preserve salary context and distinguish original source
status from effective opportunity status.

Missing salary periods must not be inferred.

Warehouse integration requires review of Data Contract v2.1.0.


## ADR-018: Conservative Deadline Evaluation

**Status:** Implemented and tested for Wuzzuf and Forasna

**Decision:** Preserve unknown timezone information rather than
assigning an unverified timezone.

Timezone-aware timestamps are normalized to UTC.

Timezone-naive deadlines use a conservative 12-hour UTC margin.

Date-only deadlines are evaluated through the end of the stated day.

These are project-specific assumptions and must be reviewed if
the source timezone or expiration semantics become known.

Missing deadlines do not establish expiration.

Absence from a partial collection run does not establish expiration.


## ADR-019: Numeric Content Hash Normalization

**Status:** Implemented and tested

**Decision:** Normalize equivalent decimal representations
before SHA-256 hashing.

Unordered arrays remain sorted.

Collection timestamps and raw payloads remain excluded.

Hash compatibility must be managed before future schema changes.


## ADR-020: Source Payload Minimization

**Status:** Selected payload retention implemented for Wuzzuf, Forasna and Egyincs; broader privacy review pending

**Decision:** Retain selected opportunity-related source information
rather than the complete API response.

Exclude internal analytics and unrelated metadata.

Do not intentionally retain hidden salary or company metadata.

Source payloads may contain sanitized or normalized values.

Invalid API records retain limited diagnostic information.

Free-text fields and source URLs still require privacy review.


## ADR-021: Collection and Warehouse Responsibility Boundary

**Status:** Proposed for team review

**Decision:** Separate physical database design from collection integration.

Data Warehouse responsibilities:

- Design PostgreSQL schemas and tables.
- Define constraints and indexes.
- Own SQL migrations.
- Define physical history and retention structures.

Data Collection responsibilities:

- Implement source adapters and validation.
- Generate content hashes.
- Implement database connectivity.
- Implement ingestion and upsert logic against the agreed schema.
- Test source-to-Bronze integration.

Shared responsibilities:

- Data Contract review.
- Source identity rules.
- Idempotency and transaction requirements.
- Content version history.
- Opportunity lifecycle.
- Integration testing.

Physical Bronze schema approval is required before storage integration.


## ADR-022: Bounded Collection and Lifecycle

**Status:** Collection implemented; lifecycle integration pending

**Decision:** Wuzzuf collection uses bounded pagination with
source-specific filtering and duplicate ID detection.

The current collector gathers active Egyptian opportunities.

A successful bounded run does not represent a complete source snapshot.

Offset pagination may miss records when source data changes during a run.

Similar content with different source IDs remains independently identifiable.

Previously stored listings require a separate lifecycle reconciliation policy.

Expired or closed listings must not be inferred solely from absence.

Incremental checkpoints and overlap policies remain pending.


## ADR-023: Forasna Hybrid Collection

**Status:** Implemented and validated in bounded live runs;
production scheduling and storage integration pending.

**Decision:** Collect Forasna listings using HTTP requests,
BeautifulSoup and a source-specific mapper.

### Collection Method

- Discover listings through the public search page.
- Follow the source-provided rel=next pagination URL.
- Extract numeric listing identifiers from job URLs.
- Validate identifiers against JSON-LD when available.
- Fetch individual job detail pages.
- Combine JSON-LD JobPosting data with HTML fields.
- Reuse the shared HTTP client and rate limiter.
- Check robots.txt before requesting collection pages.
- Reject unexpected source hosts.
- Filter listings using country code EG.
- Exclude expired and unconfirmed active listings.
- Detect duplicate source identifiers within each run.

### Normalization Rules

- Preserve original Arabic experience labels.
- Normalize Arabic and English digits.
- Support Arabic singular and dual year expressions.
- Extract experience ranges and minimum or maximum bounds.
- Map student and fresh graduate labels to entry_level.
- Map the combined manager/supervisor label to manager.
- Preserve original values for later transformation review.
- Represent strict experience bounds approximately.
- Normalize timezone-aware timestamps to UTC.
- Treat undisclosed salary and zero-zero salary ranges as null.
- Do not infer missing salary periods.
- Separate internship classification from employment arrangements.
- Recognize INTERN and the Arabic training label as internship.
- Preserve missing internship employment arrangements as null.
- Do not infer skills from broad categories.
- Exclude dedicated age, gender and applicant statistics fields
  from selected structured payloads.

### Status Evaluation

The observed application button is used as an active status signal.
A confirmed past deadline takes precedence.

An application button does not guarantee application availability.

Missing application status is treated as unknown.

### Verification on 2026-11-25

- Initial field validation: 5 accepted opportunities.
- Initial field validation: 7 detail pages fetched.
- Pagination validation: 2 search pages.
- Pagination validation: 40 discovered listings.
- Pagination validation: 32 detail pages fetched.
- Pagination validation: 30 accepted opportunities.
- Pagination validation: 2 listings excluded by country filtering.
- Zero duplicate IDs and zero invalid records in the live samples.
- Live internship classification verified using listing 448753.
- 55 Forasna-specific automated tests passed.
- 185 total automated tests passed.

### Known Limitations

- Disclosed salary parsing requires additional live verification.
- Freelance and remote mappings require additional live samples.
- Combined experience labels may lose semantic distinctions.
- Source payloads contain selected and normalized values.
- Free-text content and source URLs require privacy review.
- Robots.txt checks do not establish comprehensive authorization.
- Redirect and wildcard handling require additional review.
- Bounded collection does not establish a complete source snapshot.
- PostgreSQL ingestion, incremental collection and lifecycle
  reconciliation remain pending.


## ADR-024: Egyincs WordPress REST API Collection

**Status:** Implemented and validated through bounded live samples;
production integration pending.

### Collection Method

- Use WordPress REST API endpoints jobs and lp_course.
- Request selected fields and embedded taxonomy terms.
- Resolve company names through the company endpoint.
- Cache company information within each collection run.
- Reuse the shared HTTP client and rate limiter.
- Check robots.txt before collection requests.
- Use bounded page-based pagination.
- Detect duplicate source identifiers within each run.
- Use a default allocation of approximately 75 percent jobs-endpoint
  records and 25 percent course-endpoint records.
- The jobs endpoint contains multiple opportunity types.
- Use comma-separated field names generated with join.
- Test required field configuration to prevent malformed requests.

### Verification on 2026-11-25

- 75 Egyincs-specific automated tests passed.
- 260 total collection-layer automated tests passed.
- Bounded run received 25 records across three pages.
- 20 opportunities accepted, representing 20 unique IDs.
- Zero invalid records and zero duplicate IDs in that run.
- 15 records accepted from jobs and five from lp_course.
- Normalized distribution: 12 jobs, three internships and five training opportunities.
- Four targeted live mappings verified.
- B.TECH listing 193330: 6700 to 8200 EGP monthly.
- Sky listing 163611: 3600 to 7200 EGP monthly.
- Both monthly salaries verified through the corrected list endpoint.
- Seven special source taxonomy groups investigated.
- 13 successful mapping observations representing 12 unique listings.
- All 20 collected opportunities had unknown application status.

### Limitations

- The main bounded run preceded the final JOB_FIELDS correction.
- Targeted list-endpoint verification passed after that correction.
- Full collection regression after the final correction remains pending.
- Bounded collection does not represent a complete source snapshot.
- Source API stability and production collection limits are unverified.
- Successful requests do not establish comprehensive authorization.
- Collection quotas do not guarantee coverage of rare opportunity types.
- Unused endpoint quotas are not automatically redistributed.
- Course metadata enrichment remains pending.
- Persistent storage and lifecycle reconciliation remain pending.

## ADR-025: Egyincs Classification and Missing Information

**Status:** Implemented and tested for observed examples;
classification refinement pending.

### Decisions

- Use source taxonomy terms as primary classification evidence.
- Use documented title patterns to resolve selected ambiguous cases.
- Recognize graduate programs separately from internships.
- Recognize conference titles as events in selected ambiguous cases.
- Resolve observed internship and scholarship combinations using title evidence.
- Classify observed job and freelance combinations as freelance.
- Treat unclassified initiatives as training under a provisional fallback.
- Do not treat publication status publish as proof of open applications.
- Preserve unverified closing date information without inventing a deadline.
- Preserve missing or unconfirmed application status as unknown.
- Normalize explicitly disclosed salary ranges.
- Treat zero placeholder salary amounts as missing.
- Normalize recognized currency codes and salary periods.
- Preserve unknown salary periods without inferring them from amounts.
- Preserve selected external application URLs in raw_payload.
- Do not treat course categories as required technical skills.

### Remaining Work

- Review provisional initiative classification and multi-label conflicts.
- Distinguish applicant eligibility locations from opportunity destinations.
- Review course skills as learning outcomes versus prerequisites.
- Normalize scheme-less application URLs safely.
- Review salary display modes and placeholder values.
- Improve lifecycle evidence and invalid record diagnostics.

## ADR-026: Cross-source Application Link Evidence

**Status:** Proposed; implementation pending.

### Observations

- Egyincs listings may link directly to Wuzzuf opportunities.
- Egyincs and Forasna contain the same Marakez internship.
- Egyincs contains opportunities originating from NTI and ITI.
- External application URLs may contain functional query parameters.

### Proposed Decision

Use validated original application links and source identifiers
as additional cross-source matching evidence during Silver transformation.

- Preserve independent source listing identities.
- Preserve original source attribution.
- Do not automatically merge listings solely because they share
  a generic application portal.
- Do not indiscriminately remove URL query parameters.
- Review URL normalization and privacy before persistent ingestion.

## ADR-027: Incremental Collection and Checkpoint Safety

**Status:** Proposed; implementation pending.

### Proposed Decision

Separate bounded validation runs from initial backfill and
scheduled incremental collection.

- Maintain checkpoints per source and endpoint.
- Use overlap windows to accommodate changing source data.
- Define deterministic handling of equal publication timestamps.
- Advance checkpoints only after successful ingestion commits.
- Support partial runs, retries and idempotent recovery.
- Maintain first and last observation timestamps.
- Do not interpret absence from partial runs as closure.
- Coordinate checkpoint storage with the Bronze schema owner.
- Coordinate schedules and concurrent execution with the Airflow owner.

No persistent checkpoint or incremental ingestion implementation
is claimed by this decision.

## ADR-028: Collection Milestone Completion Criteria

**Status:** Proposed for team review.

Distinguish source adapter completion from production readiness.

A bounded collection milestone requires:

- Source investigation.
- Implemented extraction and normalization.
- Automated validation tests.
- Bounded live verification.
- Documented source limitations.
- Version-controlled implementation.

Production readiness additionally requires:

- Confirmed authorization and source-specific collection policies.
- Persistent storage and collection run tracking.
- Incremental collection and failure recovery.
- Lifecycle reconciliation.
- Privacy and retention review.
- Scheduled integration and deployment testing.

Completing a source adapter does not imply that these
production requirements have been completed.
---

## ADR-029: ITIDA SharePoint Collection and ASP.NET Pagination

Date: 2026-11-25
Status: Implemented and validated within bounded collection

### Context

ITIDA uses SharePoint pages and ASP.NET server-side pagination
for its English events archive.

The archive does not expose conventional page-number URLs
for navigating between event listing pages.

### Collection Method

- Use Requests and BeautifulSoup.
- Discover supported programs from the programs listing.
- Discover event detail URLs from the events archive.
- Use a configurable allowlist for supported program pages.
- Preserve the HTTP session and cookies during pagination.
- Extract postback targets and arguments dynamically.
- Reconstruct the ASP.NET form using current form values.
- Preserve VIEWSTATE and EVENTVALIDATION during pagination.
- Do not hardcode session-specific form values.
- Apply robots.txt checks and source-level request pacing.
- Enforce configurable collection and pagination limits.
- Exclude hidden HTML content from normalized descriptions.

### Source Identity

Use page type and normalized URL slug as source identity:

- program:<slug>
- event:<slug>

Preserve the original URL path casing for HTTP requests.

Normalize identity casing to prevent duplicate records caused
by SharePoint URL variations.

### Verification on 2026-11-25

Independent pagination validation:

- 3 event listing pages.
- 18 unique event URLs.
- 0 overlapping event URLs.
- Successful HTTP GET and POST requests.

Integrated collector validation:

- 9 program records.
- 11 event archive records.
- 20 accepted records.
- 2 event listing pages processed.
- 24 successful HTTP requests.
- 0 duplicate records.
- 0 unavailable records.
- 0 invalid records.
- Approximately 52 seconds execution time.

Automated verification:

- 64 ITIDA-specific tests passed.
- 16 HTTPClient tests passed.
- 334 total regression tests passed.

### Limitations

- Full archive coverage has not been validated.
- Integrated pagination beyond two pages remains unverified.
- English pages only.
- Program discovery is limited to the configured allowlist.
- News and press release discovery are deferred.
- GET redirects are not prevented before destination checks.
- Persistent storage and scheduled execution remain pending.

---

## ADR-030: ITIDA Program and Event Lifecycle

Date: 2026-11-25
Status: Initial implementation

### Decisions

- Retain expired events and closed programs for historical analysis.
- Do not interpret a permanent program page as an active application.
- Use unknown status when registration availability is unverified.
- Mark Summer Training as closed when both observed registration
  tracks explicitly report closed registration.
- Evaluate event expiration using the observed event end date.
- Do not interpret event dates as application deadlines.
- Preserve original event date strings in raw_payload.
- Leave unsupported or unavailable normalized fields null.
- Keep event categories separate from required skills.

### Live Status Distribution

- Active: 0
- Closed: 1
- Expired: 11
- Unknown: 8

### Remaining Work

- Distinguish permanent programs from individual cohorts.
- Review company-oriented programs for individual eligibility.
- Exclude informational records from actionable recommendations.
- Extract verified application URLs.
- Improve program eligibility and location extraction.
- Normalize online and in-person delivery information.
- Evaluate event dates using the source-local timezone.
- Validate historical and current registration states separately.
- Improve organizer and training-provider attribution.

The initial collector milestone does not establish that all
collected program pages are actionable individual opportunities.

---

## ADR-031: Shared HTTPClient POST Support

Date: 2026-11-25
Status: Implemented with reliability limitations

### Decision

Extend the shared HTTPClient with POST support for public
listing pagination that requires server-side form submission.

The implementation:

- Reuses the existing requests.Session.
- Reuses the configured request timeout.
- Reuses source-level request pacing.
- Respects disabled source configuration.
- Rejects POST redirects.
- Propagates HTTP and network errors.
- Does not intentionally log submitted form payloads.

### Retry Policy

Automatic status retries remain restricted to GET.

Connection and other retry categories are currently disabled
to reduce unintended POST replay.

This temporary policy also disables connection retries for GET.

### Verification

- POST request configuration.
- Disabled source enforcement.
- Redirect rejection.
- HTTP error propagation.
- Timeout propagation.
- Retry configuration.
- Successful live ITIDA postback requests.

### Remaining Work

- Separate GET and POST retry policies without losing session state.
- Verify non-idempotent POST replay prevention at transport level.
- Restore safe GET connection retries.
- Apply request pacing to internal retry attempts.
- Improve redirect handling and destination validation.
- Review robots.txt handling across all source adapters.

---

## ADR-032: NTI Hybrid HTML Collection

**Status:** Accepted

**Date:** 2026-11-25

### Context

NTI publishes training opportunities through multiple initiatives.
Course listings contain dynamic detail references rather than
standalone course detail links.

### Decision

Implement a Requests and BeautifulSoup collector covering:

- HireReady.
- Upskilling Programs.
- CREATIVA training centers.

Discover category and center listing URLs dynamically.

Extract course identifiers from data-target attributes and retrieve
the corresponding public HTML detail fragments.

Reuse the shared HireReady career development fragment.

Cache course details by track ID within each collection run.

Use center-based discovery for CREATIVA to preserve location-specific
opportunities and avoid overlapping category-based discovery.

### Identity

- HireReady: hire_ready:{track_id}
- Upskilling: upskilling:{track_id}
- CREATIVA: creativa:{track_id}:center:{center_id}

### Validation

Two bounded live collection runs each returned:

- 3 discovery pages.
- 3 listing pages.
- 31 discovered courses.
- 20 accepted opportunities.
- 20 unique source identifiers.
- 2 HireReady opportunities.
- 16 Upskilling opportunities.
- 2 CREATIVA opportunities.
- 0 duplicate records.
- 0 invalid records.
- 0 unavailable detail pages.
- 27 successful HTTP requests.
- Approximately 54 seconds execution time.

The robots.txt endpoint returned HTTP 404.

Cache behavior was validated through unit tests, but no live cache
hits occurred in the bounded collection runs.

Full source coverage has not yet been validated.

---

## ADR-033: NTI Training Metadata and Lifecycle

**Status:** Accepted

**Date:** 2026-11-25

### Decision

Map NTI courses to the training opportunity type.

Preserve explicitly closed registrations as closed.

Use unknown when registration availability cannot be confirmed.

Do not infer active registration from the absence of a closed label.

Preserve training duration components in raw_payload:

- total_hours
- technical_hours
- career_hours
- business_hours
- freelance_hours

Separate prerequisites into:

- Required prerequisites.
- Optional or recommended prerequisites.
- Explanatory notes.
- Explicit statements of no prerequisites.

Do not treat curriculum contents as required skills.

Preserve target audiences with their associated program parts.

Do not invent salary, publication dates, deadlines, or locations.

### Data Quality Results

The bounded 20-record sample contained:

- 100% unique source identifiers.
- 85% description coverage.
- 90% requirements coverage.
- 95% total duration coverage.
- 18 closed registrations.
- 2 unknown registrations.

Targeted live validation confirmed that:

- CCNA explanatory prerequisite text is excluded from required skills.
- Recommended Motion Graphics knowledge is classified as optional.
- Original prerequisite notes remain available.

### Limitations

Prerequisite classification is heuristic and does not constitute
canonical skill normalization.

Explicit no-prerequisite statements may coexist with expected skills.

Missing descriptions, requirements, and durations require further
source-level investigation.

Duration inference requires additional validation across all programs.

Raw-only duration changes are not currently captured by the
normalized opportunity content hash.

### Testing

- 66 NTI-specific tests passed.
- 400 total regression tests passed.
- CLI integration validated.
- Targeted live mapper validation passed.

NTI is considered initially implemented and bounded-live validated,
not production-complete.

---

## ADR-034: Bayt Hybrid HTML and JSON-LD Collection

**Date:** 2026-11-25

**Status:** Accepted

### Context

Bayt provides Egyptian job listings through public HTML
pages. JSON-LD ItemList data was observed on the first
listing page but was absent on subsequent sampled pages.

### Decision

- Use HTML job links as the primary discovery mechanism.
- Use JSON-LD ItemList as a supplementary discovery mechanism.
- Extract job details from JSON-LD JobPosting and visible
  HTML fields.
- Follow validated sequential pagination links.
- Use the numeric job ID in the canonical URL as source identity.
- Preserve the JSON-LD identifier separately in raw_payload.
- Deduplicate by source opportunity ID.
- Restrict collection to validated Egyptian job URLs.
- Check robots.txt before collection.
- Retain bounded collection limits for development runs.

### Validation

- 35 unique opportunities collected.
- 2 listing pages processed.
- 60 job appearances discovered.
- 35 detail pages fetched.
- 38 successful HTTP responses.
- Zero invalid records and duplicate IDs.
- All 35 collected opportunities were active jobs.
- Approximately 74 seconds of execution time.

### Consequences

Full production coverage, incremental collection,
redirect prevention, robots wildcard support and
authorization scope remain subject to further work.

---

## ADR-035: Bayt Conservative Field Normalization

**Date:** 2026-11-25

**Status:** Accepted

### Decision

- Normalize HTML entities in textual fields.
- Map Fresh graduate and Fresh graduates to entry_level.
- Preserve confidential organizations as null.
- Use explicit structured employment types.
- Map structured TELECOMMUTE to remote.
- Preserve experience and education evidence.
- Use currency as the canonical salary currency field.
- Preserve date-only publication values without inventing
  timestamps.
- Normalize timezone-aware deadlines to UTC.
- Resolve lifecycle status using application evidence
  and deadline information.
- Preserve aggregated and external listing flags as
  source metadata without assuming application destination.
- Do not treat preferred skills as mandatory skills.
- Retain selected source metadata rather than complete HTML.

### Validation

98 Bayt unit tests and 498 total regression tests passed.

HTML entity and fresh graduate normalization fixes were
validated through unit tests after the live collection.

### Consequences

Free-text experience extraction, work-mode reconciliation,
semantic deduplication and skill classification remain
deferred to subsequent enrichment work.

## ADR-036: Devpost API and HTML Hybrid Collection

**Status:** Accepted

**Date:** 2026-11-25

### Context

Devpost provides hackathon discovery through a JSON API
and detailed opportunity information through individual
hackathon subdomains.

The listing API provides stable identifiers, titles,
organizations, themes, submission periods, location
information, invitation status, and prize information.

Individual detail pages provide descriptions,
requirements, eligibility restrictions, registration
links, rules links, and structured JSON-LD event dates.

### Decision

- Use the Devpost hackathons API for discovery.
- Use HTML and JSON-LD for detail enrichment.
- Collect open and upcoming hackathons.
- Use round-robin collection across both statuses.
- Restrict the initial adapter to explicitly online
  and non-invitation-only opportunities.
- Apply bounded pagination independently per status.
- Deduplicate using source identifiers and canonical URLs.
- Validate source URLs and disable HTTP redirects.
- Check and cache robots.txt independently per host.
- Reuse the shared HTTP session, retry configuration,
  and rate limiter.
- Reject records without a usable description.
- Skip missing detail pages returning HTTP 404 or 410.
- Propagate other HTTP failures after configured retries.

### Consequences

Browser automation and additional dependencies are
not required for the validated collection flow.

The adapter depends on an observed public-facing API
and HTML structures without a guaranteed stability
contract.

The initial scope excludes physical and hybrid
hackathons, including potentially relevant Egyptian
events.

### Validation

Final live validation on 2026-11-25:

- Listing pages: 4
- Discovered records: 27
- Detail pages fetched: 23
- Accepted opportunities: 20
- Excluded opportunities: 6
- Invalid records: 1
- Duplicate records: 0
- Missing detail pages: 0
- Open opportunities: 12
- Upcoming opportunities: 8
- Approximate runtime: 104 seconds
- Devpost unit tests: 82 passed
- Full project tests: 580 passed

The rejected invalid record lacked a usable description.
The run completed without an unhandled HTTP failure.

## ADR-037: Devpost Eligibility and Lifecycle Semantics

**Status:** Accepted

**Date:** 2026-11-25

### Decision

Country eligibility is evaluated conservatively using
the available detail-page evidence.

- Reject explicit exclusions of Egypt.
- Reject country allowlists that do not include Egypt.
- Reject restricted opportunities when the required
  country list cannot be extracted.
- Preserve eligibility text and extracted country lists.
- Do not infer full Egyptian eligibility from the
  absence of Egypt in an exclusion list.
- Preserve age, student, team, and organization
  restrictions as source evidence.

Map open hackathons to active status subject to
the shared deadline resolver.

Map upcoming hackathons to unknown status while
preserving the original source status.

Store submission deadlines separately from the
meaning of registration deadlines through raw metadata.

Store prize information in raw_payload rather than
salary fields.

### Consequences

Conservative geographic filtering may reduce recall.

Official rules are linked but are not fully parsed.
Individual eligibility and registration availability
remain unverified.

Upcoming opportunities are distinguishable through
source_status_raw without changing the shared
status enumeration.

### Validation

The final live run excluded:

- QNX Global Hackathon: unavailable country blocklist.
- Pico Space Program: Egypt absent from the extracted
  country allowlist.

The collection still reached its target of 20 unique
opportunities after applying these restrictions.

## ADR-038: UN Volunteers API Collection

**Date:** 2026-11-25

**Status:** Implemented and bounded-live validated; production integration pending.

### Decision

- Use the observed JSON API at app.unv.org: POST /api/doa/doa/SearchDoaAsyncByAzureCognitive for discovery and GET /api/doa/doa/{id} for details.
- Use bounded skip/take pagination and validate response structure and pagination metadata.
- Use positive numeric assignment IDs as source opportunity identifiers; deduplicate within each run.
- Filter listing scope before detail retrieval and validate identity and modality again during mapping.
- Apply configured request pacing and timeouts; disable automatic retries and redirects for this adapter.
- Skip detail responses with HTTP 404 or 410; propagate other HTTP failures.
- Retain selected opportunity metadata and limited invalid-record diagnostics, not complete API responses or dedicated recruitment contact fields.

### Live validation

| Metric | First run | Second run |
|---|---:|---:|
| Listing pages | 4 | 7 |
| Discovered | 80 | 140 |
| Excluded | 55 | 83 |
| Accepted | 20 | 40 |
| Online | 20 | 39 |
| On-site in Egypt | 0 | 1 |
| Active | 20 | 39 |
| Unknown status | 0 | 1 |
| Invalid / duplicate / missing details | 0 / 0 / 0 | 0 / 0 / 0 |
| Unprocessed after acceptance cap | 5 | 17 |
| Approximate runtime (seconds) | 54 | 93 |

The second run used max_jobs=40, page_size=20 and max_pages=10, with 47 successful HTTP requests. Both runs reported 167 available search results; neither establishes full coverage.

The second run verified an Egyptian on-site assignment and preserved two distinct assignment IDs sharing a title. Similarity is candidate deduplication evidence, not proof of identity.

Initial UN Volunteers integration: 66 source tests and 646 total tests passed. After the employment mapping correction and source scope tests, 71 source tests and 665 total tests passed. The live samples preceded that correction.

### Remaining work

Confirm production authorization, API stability, rate policies, full coverage, retry and recovery policies, privacy, persistent run tracking, checkpoints, PostgreSQL ingestion and Airflow scheduling.

## ADR-039: UN Volunteers Eligibility and Lifecycle

**Date:** 2026-11-25

**Status:** Initial mapping implemented and tested; eligibility and lifecycle refinement pending.

### Decision

- Map assignments to volunteering. Accept explicitly online assignments globally and explicitly on-site assignments only when country code is EGY. Reject unknown modality.
- Geographic filtering does not establish individual Egyptian eligibility. Preserve eligibility evidence and mark egypt_eligibility as unverified.
- For online assignments, the country label represents the source-reported host country, not a required physical work location.
- Require recruiting status (DOA_SOURCING), active sourcing, and explicit non-reserved and non-single-source flags.
- Preserve original sourcing deadline in raw date fields; leave normalized deadline null with unknown precision when a raw deadline exists because closing-time semantics are unverified.
- For parseable deadline dates, use the current UTC observation date: before the deadline date is active; from the deadline date through two days afterward is unknown; later dates are excluded. Missing or unparseable deadlines produce unknown status. This conservative buffer is provisional, not a verified source timezone rule.
- Map explicit FULLTIME and PARTTIME arrangement codes to full_time and part_time. Missing or unrecognized arrangements are null, not an empty array, consistent with ADR-011.
- Preserve experience values and units, duration, hours, volunteer category, nationality category, education and language evidence without inventing normalized experience or salary values.
- Record online compensation as unpaid in selected raw metadata; on-site compensation remains unverified. Do not treat volunteering allowances as salary without evidence.

### Remaining work

Verify nationality and individual eligibility, application availability, deadline timezone and buffer, experience units, conflicting hours labels and codes, duration semantics, and category metadata. Review host versus execution location semantics before downstream filtering. Define version tracking for meaningful raw-only metadata changes and review free-text privacy. Preserve distinct source IDs until deduplication evidence is sufficient. Persistent lifecycle reconciliation remains pending; absence from a bounded run is not proof of closure.

## ADR-040: Final Data Source Scope

**Date:** 2026-11-25

**Status:** Final collection scope selected by project collection owner; code and automated scope tests verified locally; documentation synchronization and team contract review pending.

### Decision

The initial project collection scope is closed at eight sources:

- wuzzuf
- forasna
- egyincs
- itida
- nti
- bayt
- devpost
- un_volunteers

AMIDEAST, LinkedIn, Tanqeeb and the proposed replacement job source are outside the active scope. No additional source implementation is planned for this milestone.

All eight adapters are implemented and bounded-live validated. SourceName and SOURCE_CONFIGS now agree on the eight sources; all are enabled. Automated tests verify registry and model consistency and reject out-of-scope configuration requests. The full regression baseline is 665 passing tests.

### Contract compatibility

Removing amideast from SourceName narrows the accepted enumeration and is a breaking change relative to the documented v2.1.0 contract under ADR-015. Data Contract v3.0.0 is proposed to reflect this change, pending team review and confirmation of compatibility requirements. The previous contract version remains a historical reference.

### Consequences

The next milestone is persistent ingestion design and integration with the Data Warehouse owner, including identity, raw observation retention, content history, transactions, invalid records, checkpoints and lifecycle. Production authorization, coverage, orchestration and end-to-end validation remain pending. Historical milestones retain their original test counts and scope context.
