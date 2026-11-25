# MATCHPOINT Data Contract

**Version:** 2.1.0

**Status:** Implemented in collection models and Wuzzuf adapter; pending team review and warehouse integration

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
- linkedin
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
