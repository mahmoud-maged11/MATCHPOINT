# MATCHPOINT Architecture Decisions

**Related Data Contract:** v2.1.0

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

**Status:** Implemented and tested for Wuzzuf

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

**Status:** Implemented for Wuzzuf; broader review pending

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
