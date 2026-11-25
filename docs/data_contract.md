# MATCHPOINT Data Contract

**Version:** 2.1.0

**Status:** Implemented in collection models, Wuzzuf, Forasna and Egyincs adapters; pending team review and warehouse integration

**Owners:** Data Collection & Data Warehouse Teams

## 1. Purpose

This document defines the standardized data structure exchanged between the Data Collection, Data Transformation, Backend, and Analytics components of MATCHPOINT.

All source adapters must follow this contract when producing standardized source records.

The architecture must preserve original source data, support multiple opportunity sources, detect content changes, and prevent duplicate opportunities from appearing in the final application.

## 2. Data Schema

### 2.1 Source Identity

| Column | Data Type | Required |
|---|---|---|
| source_listing_id | UUID | Yes, generated during ingestion |
| source_name | VARCHAR | Yes |
| source_opportunity_id | TEXT | No |
| source_url | TEXT | Yes |

### 2.2 Opportunity Information

| Column | Data Type | Required |
|---|---|---|
| title | TEXT | Yes |
| organization | TEXT | No |
| description | TEXT | No |
| opportunity_type | VARCHAR | Yes |
| location | TEXT | No |
| work_modes | JSONB | No |
| employment_types | JSONB | No |
| categories | JSONB | No |

### 2.3 Qualifications and Requirements

| Column | Data Type | Required |
|---|---|---|
| experience_level | VARCHAR | No |
| experience_level_raw | TEXT | No |
| experience_years_min | NUMERIC | No |
| experience_years_max | NUMERIC | No |
| education_level | TEXT | No |
| required_skills | JSONB | No |
| requirements | TEXT | No |

### 2.4 Financial Information

| Column | Data Type | Required |
|---|---|---|
| salary_min | NUMERIC | No |
| salary_max | NUMERIC | No |
| currency | VARCHAR | No |
| salary_period | VARCHAR | No |

### 2.5 Dates and Timestamps

| Column | Data Type | Required |
|---|---|---|
| published_at | TIMESTAMPTZ | No |
| published_at_raw | TEXT | No |
| published_at_precision | VARCHAR | No |
| deadline | TIMESTAMPTZ | No |
| deadline_raw | TEXT | No |
| deadline_precision | VARCHAR | No |
| collected_at | TIMESTAMPTZ | Yes |
| last_seen_at | TIMESTAMPTZ | Yes, managed during ingestion |

### 2.6 Metadata

| Column | Data Type | Required |
|---|---|---|
| content_hash | TEXT | Yes, generated during ingestion |
| status | VARCHAR | Yes |
| source_status_raw | TEXT | No |
| raw_payload | JSONB | Yes, in Bronze |

### 2.7 Canonical Opportunity Identity

The opportunity_id field is a UUID generated for canonical opportunities during transformation.

It represents a unique business opportunity rather than an individual source listing.

Multiple source listings may reference the same canonical opportunity.

Source listings and canonical opportunities must remain independently identifiable.

## 3. Supported Sources

- wuzzuf
- forasna
- egyincs
- itida
- nti
- bayt
- amideast
- devpost
- un_volunteers

Additional sources may be introduced through documented schema and adapter updates.

## 4. Standardized Values

### 4.1 Opportunity Type

- job
- internship
- graduate_program
- training
- scholarship
- competition
- hackathon
- freelance
- volunteering
- event

### 4.2 Work Modes

- on_site
- remote
- hybrid
- unknown

Multiple values are supported.

Example:

```json
["remote", "hybrid"]
```

### 4.3 Employment Types

- full_time
- part_time
- contract
- temporary
- freelance
- unknown

Multiple values are supported.

Example:

```json
["part_time", "freelance"]
```

### 4.4 Experience Level

- entry_level
- junior
- mid_level
- senior
- lead
- manager
- executive
- unknown

Original experience labels must be preserved when available.

Ambiguous source labels must not be mapped to a specific experience level without a documented mapping rule.

### 4.5 Opportunity Status

- active
- expired
- closed
- unknown

### 4.6 Date Precision

- exact
- date_only
- relative
- unknown

Exact timestamps may be stored in the normalized timestamp fields.

Date-only and relative values must retain their original representation and precision.

Relative dates may be normalized when a reliable observation timestamp is available, but the resulting timestamp must be treated as approximate.

Date-only deadlines must not be interpreted as exact expiration timestamps.

### 4.7 Salary Period

- hourly
- daily
- weekly
- monthly
- yearly
- project
- unknown

Salary periods must not be inferred from salary amounts.

Missing salary periods must remain null.

Hidden salary information must not be intentionally collected
or retained in standardized records.

### 4.8 Source Status and Effective Status

source_status_raw preserves the original source status.

status represents the effective opportunity status at observation time.

Explicit closed and expired source statuses take precedence.

An active source status may be classified as expired when
the deadline has passed under the documented source-specific policy.

An active status does not guarantee that applications remain available.

Absence from a bounded collection run must not be interpreted
as evidence that a listing has expired or closed.

## 5. Data Rules

### 5.1 General Rules

- All column names must use snake_case.
- Missing information must be represented as null.
- Missing information must not be fabricated.
- Required fields must be validated before standardized ingestion.
- Empty or whitespace-only required strings are invalid.
- Preserve permitted and relevant source values in raw_payload.
- Raw payloads may be filtered or sanitized by source adapters.
- Hidden financial and organization metadata must not be intentionally retained.
- Internal analytics and unrelated source metadata must be excluded.

### 5.2 Arrays

The following fields must be represented as JSON arrays of strings when available:

- work_modes
- employment_types
- categories
- required_skills

Array values must not contain unnecessary duplicates.

Null represents unavailable information.

An empty array represents a confirmed absence of values.

Unknown must not be combined with known standardized values in the same array.

### 5.3 Date and Time Rules

- Timestamps must follow ISO 8601.
- Normalized timestamps must be timezone-aware and stored in UTC.
- Original date strings must be preserved when available.
- Relative dates must be identified as approximate.
- The observation time used for relative date normalization must be reliable.
- Missing deadlines must not automatically indicate expired opportunities.
- Unknown source timezones must not be fabricated.
- Date-only values retain date_only precision without an exact timestamp.
- Wuzzuf timezone-naive deadlines use a conservative 12-hour UTC margin.
- Wuzzuf date-only deadlines are treated as valid through the end of the stated day.
- These Wuzzuf deadline rules are project policies, not verified source guarantees.

### 5.4 Salary and Experience Rules

- Salary values must be numeric and non-negative.
- Minimum salary must not exceed maximum salary.
- Currency codes must follow ISO 4217.
- Salary periods must use standardized values when available.
- Hidden salary amounts, currency and period must remain null.
- Experience years must be numeric and non-negative.
- Minimum experience must not exceed maximum experience.
- Missing maximum experience must remain null when only a minimum is provided.

### 5.5 Skills and Categories

- Skills and opportunity categories must be represented separately.
- Source-provided skill tags are candidate skills until validated during transformation.
- Broad academic fields and industry classifications must not automatically be treated as technical skills.
- Skill normalization and taxonomy management are performed during transformation.


### 5.6 Forasna Source-Specific Implementation Notes

Forasna uses JSON-LD JobPosting metadata and HTML detail fields.

- Numeric source listing IDs are extracted from job URLs.
- JSON-LD identifiers are validated when available.
- Egyptian listings are selected using country code EG.
- Listings with missing country information are excluded.
- Timezone-aware source dates are normalized to UTC.
- Original Arabic experience labels and year expressions are retained.
- Experience bounds are normalized into numeric fields.
- Strict experience bounds are represented approximately.
- Undisclosed and zero-zero salary ranges are normalized to null.
- Missing salary periods are not inferred.
- INTERN and the Arabic training label map to internship.
- Internship is an opportunity type, not an employment arrangement.
- Missing internship employment arrangements remain null.
- Freelance and remote mappings require further live validation.
- Application buttons provide an observed active status signal.
- Confirmed past deadlines take precedence over active signals.
- Missing application status is treated as unknown.
- Selected structured payloads exclude dedicated age, gender
  and applicant statistics fields.
- Categories are not automatically converted into required skills.

These implementation notes do not introduce new schema fields
or change existing standardized values.


### 5.7 Egyincs Source-Specific Implementation Notes

Egyincs uses WordPress REST API jobs and lp_course records
with selected embedded taxonomy information.

- Numeric WordPress IDs identify individual source listings.
- Source URLs preserve the original listing identity.
- Course records map to training.
- Source taxonomies provide primary opportunity classification evidence.
- Selected title patterns resolve documented classification ambiguities.
- Initiative classification uses a provisional fallback.
- Explicitly disclosed salary ranges are normalized into numeric fields.
- Invalid, non-finite and zero placeholder salary amounts are not retained
  as confirmed salary values.
- Recognized Egyptian pound labels map to EGP.
- Recognized salary periods map to standardized values.
- Salary periods are not inferred from amounts.
- Original salary metadata is retained in selected raw_payload fields.
- WordPress date_gmt provides publication timestamp evidence.
- WordPress publish status is retained as source_status_raw.
- Publication status does not establish application availability.
- Effective status remains unknown without reliable lifecycle evidence.
- Unverified closing dates are preserved without fabricating deadlines.
- External application URLs are retained in selected raw_payload fields.
- Dedicated age and gender taxonomies are excluded from structured matching fields.
- Source-provided skills remain candidate skills until validated.
- Course categories must not automatically become required skills.
- Location taxonomies may represent applicant eligibility rather than
  the actual opportunity destination.
- Scheme-less application URLs and conflicting location information
  require further normalization.

These implementation notes do not introduce new standardized
schema fields or change existing allowed values.

The Data Contract remains v2.1.0.

### 5.8 ITIDA Source-Specific Implementation Notes

ITIDA collects supported training program pages and event
archive records from the English SharePoint website.

Collection uses HTML parsing and ASP.NET postback pagination.

Source-specific rules:

- source_name is itida.
- source_opportunity_id uses program:<slug> or event:<slug>.
- URL path casing is preserved for collection.
- Identity slugs are normalized to lowercase.
- Program opportunity types use an explicit mapping.
- Event opportunity types use recognized source categories.
- Hidden page content is excluded.
- Original event start and end dates are retained in raw_payload.
- Event dates are not application deadlines.
- Missing application deadlines remain null.
- Missing salary and experience information remains null.
- Missing structured eligibility information remains null.
- Expired and closed records are retained for historical analysis.
- Unknown registration availability produces unknown status.
- Permanent program pages do not establish active enrollment.

The current implementation attributes records to ITIDA.
Specific organizers, training providers and partner organizations
require additional enrichment.

Company-oriented programs and informational pages require
eligibility review before inclusion in individual recommendations.

The current implementation does not fully distinguish program
definitions from individual application cohorts.

The initial collector was validated on 20 live records on
2026-11-25, including 9 programs and 11 event archive records.

These implementation notes do not introduce new schema fields.
The data contract remains at version 2.1.0.

## 5.9 NTI Source Mapping

NTI provides training opportunities through HireReady, Upskilling
Programs, and CREATIVA.

### Normalized Fields

| Field | Mapping |
|---|---|
| source_name | nti |
| source_opportunity_id | Initiative, track ID, and center ID where applicable |
| source_url | Public course listing URL |
| title | Course listing title |
| organization | NTI |
| opportunity_type | training |
| description | Extracted overview, scope, or module description |
| requirements | Target audience, prerequisites, and explanatory notes |
| required_skills | Required prerequisite text |
| categories | Initiative and category when available |
| location | CREATIVA center location when available |
| status | closed or unknown |
| source_status_raw | Original registration status text |

Salary, publication dates, deadlines, and other unsupported fields
remain null.

### Source-Specific Raw Payload

- initiative
- track_id
- center_id
- category
- location
- detail_url
- detail_title
- durations
- prerequisites
- target_audience
- status_raw

The durations object preserves total, technical, career, business,
and freelance training hours.

The prerequisites object preserves required, optional, notes,
and explicit_none values.

Prerequisite text requires downstream skill normalization.

The explicit_none flag records source evidence and does not
necessarily imply an empty required_skills list.

No normalized schema changes are introduced by this source mapping.
The existing data contract version remains 2.1.0.

---

### 5.10 Bayt

**Source name:** `bayt`

**Collection method:** Hybrid HTML and JSON-LD.

**Base URL:** `https://www.bayt.com`

**Listing URL:** `https://www.bayt.com/en/egypt/jobs/`

| Canonical field | Source mapping |
|---|---|
| source_opportunity_id | Numeric ID in canonical job URL |
| source_url | Validated job detail URL |
| title | JobPosting.title with HTML entity normalization |
| organization | JobPosting.hiringOrganization; confidential becomes null |
| opportunity_type | Structured internship evidence or explicit internship title; otherwise job |
| description | Visible description with JSON-LD fallback |
| requirements | Visible skills, major and preferred residence |
| required_skills | Null pending reliable skill classification |
| location | Egyptian JobPosting address |
| employment_types | Structured employmentType |
| work_modes | Structured TELECOMMUTE mapped to remote |
| experience_level | Normalized visible career level |
| experience_level_raw | Original visible career level |
| experience_years_min | Explicit experience field or structured months |
| experience_years_max | Explicit experience range |
| education_level | Visible degree or structured credential category |
| salary_min | Valid structured salary minimum or fixed value |
| salary_max | Valid structured salary maximum or fixed value |
| currency | Valid ISO 4217 currency |
| salary_period | Normalized structured salary unit |
| published_at | Timezone-aware datePosted when available |
| published_at_raw | Original datePosted |
| published_at_precision | Exact, date_only or unknown |
| deadline | Timezone-aware validThrough when available |
| deadline_raw | Original validThrough |
| deadline_precision | Exact, date_only or unknown |
| status | Application evidence and shared deadline resolution |
| source_status_raw | Original application status evidence |
| raw_payload | Selected source-specific metadata |

#### Source-specific rules

- URL identity takes precedence over JSON-LD identifier.
- Missing or unconfirmed Egyptian location is excluded.
- Date-only publication values retain raw text and precision.
- Missing salary information remains null.
- External and aggregated flags are not application status.
- directApply=false does not imply a closed opportunity.
- Free-text requirements are not automatically mandatory skills.
- Fresh graduate career levels map to entry_level.
- Collection limits are development controls, not evidence
  of complete source coverage.

#### Validation

- 98 source-specific unit tests passed.
- 498 total regression tests passed.
- Live sample: 35 unique active jobs across two listing pages.
- Zero invalid records in the live sample.
- Structured salary fields were populated in the live sample.
- Live internship and closed/expired cases remain unverified.

## 6. Source Identity and Deduplication

### 6.1 Source Listing Identity

Each individual source listing must have a stable source_listing_id.

When a reliable source_opportunity_id is available, the combination of source_name and source_opportunity_id identifies the listing.

When a source identifier is unavailable, a documented source-specific URL identity strategy must be used.

Original source URLs must be preserved.

### 6.2 Content Change Detection

SHA-256 must be used for standardized content hashing.

Content serialization must be deterministic.

Collection timestamps, ingestion metadata, source identifiers, and volatile raw payload fields must not affect the content hash.

Relative date labels and derived approximate timestamps must not trigger false content changes.

Unordered arrays must be normalized before hashing.

Equivalent numeric representations must produce identical hashes.

For example, 5000 and 5000.00 represent the same numeric value.

Salary period and source status participate in standardized content hashing.

Changes to hashing rules must be coordinated before persistent ingestion.

Effective status changes may affect the content hash.

The source listing identity and content hash must be used together to detect content changes.

Unchanged listings must still have their last_seen_at updated.

### 6.3 Cross-source Deduplication

Cross-source deduplication is performed during transformation.

Potential matching attributes include:

- Normalized title
- Normalized organization
- Location
- Description
- Requirements
- Skills
- Publication information

Exact matching and similarity-based matching may be used.

Similar listings must not automatically be merged without sufficient matching evidence.

### 6.4 Source Attribution

A canonical opportunity may be linked to multiple source listings.

Original source identifiers and URLs must remain available after deduplication.

The application may display one canonical opportunity with multiple source links.

## 7. Data Architecture

### 7.1 Bronze Layer

Stores standardized source records, permitted source payloads, collection timestamps, source metadata, and ingestion information.

Responsibilities include:

- Raw data preservation
- Source listing identification
- Collection metadata
- Content change detection
- Invalid record retention
- Ingestion error tracking

Invalid records must be retained separately for investigation rather than silently discarded.

### 7.2 Silver Layer

Stores cleaned, validated, standardized, and deduplicated data.

Responsibilities include:

- Data cleaning
- Type normalization
- Date normalization
- Skill normalization
- Category classification
- Source listing deduplication
- Cross-source matching
- Canonical opportunity identification
- Data quality testing

### 7.3 Gold Layer

Stores business-ready datasets for application integration, matching, reporting, and analytical consumption.

Responsibilities include:

- Canonical opportunities
- Opportunity matching datasets
- Skill gap analysis datasets
- Analytical facts and dimensions
- Business metrics
- Reporting datasets

### 7.4 Analytical Storage

ClickHouse consumes analytical datasets prepared by the data pipeline.

Analytical datasets must preserve consistent business definitions and avoid counting duplicate source listings as unique opportunities.

## 8. Responsibilities

### Mahmoud: Data Collection & Backend

- Collect data from approved sources.
- Implement source adapters.
- Validate standardized records.
- Preserve permitted source data and sanitized payloads.
- Implement content hashing.
- Load collected records into PostgreSQL.
- Integrate curated opportunities with the backend.
- Maintain source adapter documentation.

### Momen: Data Warehouse & Transformation

- Design PostgreSQL schemas and tables.
- Implement dbt transformation models.
- Develop Silver and Gold layers.
- Implement deduplication and canonical opportunity identification.
- Preserve source attribution.
- Implement data quality tests.
- Maintain warehouse documentation.

### Andrew: Pipeline & Orchestration

- Automate pipeline execution using Apache Airflow.
- Manage scheduling, dependencies, and monitoring.
- Manage pipeline retries and failure handling.
- Load analytical datasets into ClickHouse.

### Ramadan: Analytics

- Consume analytical datasets from ClickHouse.
- Develop SQL analytics and Power BI dashboards.
- Use canonical opportunity definitions for opportunity-level metrics.

### Abdel Rahman: Frontend

- Consume opportunity data through backend APIs.
- Display opportunities and personalized recommendations.
- Support multiple employment types and work modes.
- Display available source links for canonical opportunities.

## 9. Schema Evolution

Changes to the data contract must be documented and reviewed through GitHub Pull Requests.

Breaking changes require a major version increment.

Backward-compatible additions require a minor version increment.

Documentation corrections that do not change the contract require a patch version increment.

Breaking changes must be communicated to all affected team members before integration.

Architecture decisions must be recorded in docs/architecture_decisions.md.

Outstanding implementation tasks must be recorded in docs/pending_tasks.md.

## 10. Version History

| Version | Description |
|---|---|
| 1.0.0 | Initial data contract |
| 2.0.0 | Multiple employment types and work modes, source listing identity, canonical opportunities, date precision, experience ranges, category separation, content hashing, and deduplication rules |
| 2.1.0 | Added salary period, original source status, conservative deadline handling, numeric hash normalization, and source payload minimization |
