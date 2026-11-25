# MATCHPOINT Architecture Decisions

**Related Data Contract:** v2.0.0

**Purpose:** Document architectural decisions, their rationale, and implementation requirements.

## ADR-001: Multiple Employment Types

**Status:** Selected, implementation pending

**Problem:** A single opportunity may support multiple employment types.

**Decision:** Replace employment_type with employment_types, represented as a JSONB array.

**Reason:** Prevent information loss and support accurate opportunity filtering.

**Example:** ["part_time", "freelance"]

## ADR-002: Multiple Work Modes

**Status:** Selected, implementation pending

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

**Status:** Partially implemented

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

**Remaining work:** Update the existing hashing implementation to comply with Data Contract v2.0.0.

## ADR-006: Date Precision and Timezones

**Status:** Selected, implementation pending

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

**Status:** Selected, implementation pending

**Decision:** Maintain separate fields for required_skills and categories.

Source-provided skill tags are treated as candidate skills until validated during transformation.

Broad academic disciplines and industry classifications must not automatically be classified as technical skills.

## ADR-008: Experience Normalization

**Status:** Selected, implementation pending

**Decision:** Preserve original experience labels and extract experience ranges separately.

Fields:

- experience_level
- experience_level_raw
- experience_years_min
- experience_years_max

Ambiguous experience labels must not be mapped to specific seniority levels without documented evidence.

## ADR-009: Invalid Record Retention

**Status:** Selected, implementation pending

**Decision:** Preserve invalid source records separately for investigation and potential reprocessing.

Invalid record metadata should include:

- Source name
- Source URL, when available
- Original payload
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

**Status:** Selected, implementation pending

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

**Status:** Live collection blocked for Wuzzuf

**Decision:** Collect data using authorized access methods and source-specific collection policies.

Prefer official APIs or feeds when available and suitable.

Respect access restrictions, rate limits, and permitted collection scope.

HTTP 403 responses must be investigated before automated collection continues.

Successful local parsing does not establish successful live collection.

**Current limitation:** Wuzzuf returns HTTP 403 to the current HTTP client. Local parsing has successfully extracted four listings.

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