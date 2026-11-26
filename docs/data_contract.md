# MATCHPOINT Data Contract

**Version:** 3.0.0 (approved; ADR-050)

**Status:** Approved contract. All eight source adapters implemented and bounded-live validated. Physical Bronze schema implemented and locally tested. Persistent ingestion and downstream integration remain pending.

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
| source_opportunity_id | TEXT | Optional in collection model; required for initial Bronze ingestion |
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
- devpost
- un_volunteers

These eight sources constitute the final project collection scope. Any future scope change requires explicit team approval and documented contract and adapter updates.

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

This mapping was originally documented under v2.1.0.

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
This mapping was originally documented under v2.1.0.

### 5.9 NTI Source Mapping

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
This mapping was originally documented under v2.1.0.

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

### 5.11 Devpost

**Source name:** `devpost`

**Opportunity type:** `hackathon`

**Collection method:** API discovery with HTML and
JSON-LD detail enrichment.

**Initial scope:** Explicitly online, public,
open or upcoming hackathons.

| Contract field | Source mapping |
|---|---|
| source_name | devpost |
| source_opportunity_id | API id converted to string |
| source_url | Validated hackathon subdomain URL |
| title | API title |
| organization | API organization_name or JSON-LD organizer |
| description | HTML challenge description or JSON-LD fallback |
| opportunity_type | hackathon |
| location | Online |
| work_modes | remote |
| categories | Deduplicated API theme names |
| requirements | HTML requirements and eligibility text |
| deadline | Normalized submission end date |
| deadline_raw | JSON-LD endDate or API date fallback |
| deadline_precision | Shared datetime normalization |
| source_status_raw | API open_state |
| status | active for open, unknown for upcoming, subject to resolver |
| collected_at | UTC observation timestamp |
| published_at | null |
| salary_min | null |
| salary_max | null |
| currency | null |
| salary_period | null |

#### Raw payload

Preserve the following source-specific evidence:

- api_id
- open_state
- displayed_location
- submission_period_dates
- time_left_to_submission
- submission_start_raw
- submission_end_raw
- deadline_kind
- registration_deadline
- registration_url
- rules_url
- prize_amount_raw
- prizes_counts
- registrations_count
- invite_only
- themes
- eligibility
- country_list_title
- listed_countries
- included_countries
- excluded_countries
- egypt_eligibility

#### Semantic constraints

- The normalized deadline represents the submission
  cutoff, not a verified registration deadline.
- Registration URLs do not prove registration is open.
- Prize amounts are not employment compensation.
- Upcoming hackathons retain unknown normalized status.
- Online delivery does not imply worldwide eligibility.
- Egyptian eligibility remains unverified.
- Aggregate registration counts are not participant
  personal records.
- Missing descriptions cause record rejection.
- Restricted country lists must be available before
  the opportunity can pass geographic filtering.

### 5.12 UN Volunteers

**Source name:** `un_volunteers`

**Opportunity type:** `volunteering`

**Collection method:** Observed JSON API listing search and assignment details.

| Contract field | Source mapping |
|---|---|
| source_opportunity_id | Validated assignment ID converted to string |
| source_url | Public assignment URL |
| title | Assignment title |
| organization | Host entity name |
| description | Cleaned task description |
| location | Source country label; may represent host country for online assignments |
| work_modes | remote for online; on_site for Egyptian onsite assignments |
| employment_types | FULLTIME to full_time; PARTTIME to part_time; missing or unrecognized arrangement to null |
| categories | Source expertise areas |
| requirements | Available skills, eligibility, education and language evidence |
| education_level | Source education evidence |
| published_at | Normalized publication timestamp when supported |
| deadline | null pending reliable closing-time semantics |
| deadline_raw | Original sourcingEndDate |
| deadline_precision | unknown when raw deadline exists; otherwise null |
| source_status_raw | Original source status evidence |
| status | active or unknown for accepted assignments under the source-specific policy |
| collected_at | UTC observation timestamp |
| raw_payload | Selected assignment metadata |

#### Geographic scope and eligibility

- Accept explicitly online assignments regardless of host country and onsite assignments only when the country code is EGY.
- Reject unknown modality and inconsistent listing/detail identities or modalities.
- Geographic filtering does not establish Egyptian applicant eligibility. Preserve nationality and other eligibility evidence; egypt_eligibility remains unverified.
- Online host location must not be interpreted as a required physical work location.

#### Lifecycle and normalization

- Require DOA_SOURCING, active sourcing, and explicitly false reserved and single-source flags.
- Preserve sourcingEndDate without inventing a normalized deadline or timezone.
- Missing or unparseable deadline evidence produces unknown status. Before the raw deadline date, qualifying assignments are active; from that date through two days afterward, status is unknown; later observations are excluded. This is a conservative project policy, not a verified source guarantee.
- Preserve distinct source IDs even when titles match; semantic deduplication requires downstream evidence.
- Missing or unrecognized employment arrangements remain null, not an empty array.
- Do not infer normalized experience years from unverified experience units or salary from volunteering metadata. Normalized salary and experience fields remain null.
- Preserve selected duration, hours, experience, category, nationality, language, eligibility and status metadata. Do not intentionally retain recruitment contact fields or the complete API response.

#### Validation and limitations

- Initial bounded live run: 20 online active assignments accepted.
- Expanded bounded live run: 40 accepted (39 online, one onsite in Egypt), 39 active and one unknown; zero duplicate IDs, invalid records or missing details. Seven listing pages and 40 detail requests returned HTTP 200.
- The live runs preceded the final employment_types correction. The correction was verified by automated tests: 71 UN Volunteers tests and 665 full regression tests passed.
- Full coverage, applicant eligibility, exact closing times, source authorization for production, persistent ingestion and lifecycle reconciliation remain pending.

## 6. Source Identity and Deduplication

### 6.1 Source Listing Identity

Each individual source listing must have a stable source_listing_id.

When a reliable source_opportunity_id is available, the combination of source_name and source_opportunity_id identifies the listing.

For initial Bronze ingestion, a non-empty source_opportunity_id is mandatory. Records without a usable source identifier must be rejected. URL-based fallback identity and identity promotion are deferred under ADR-042.

Original source URLs must be preserved.

### 6.2 Content Change Detection

SHA-256 must be used for standardized content hashing.

Content serialization must be deterministic.

Collection timestamps, ingestion metadata, source identifiers, source URLs and the entire raw_payload must not affect the initial content hash.

Relative date labels and derived approximate timestamps must not trigger false content changes.

Unordered arrays must be normalized before hashing.

Equivalent numeric representations must produce identical hashes.

For example, 5000 and 5000.00 represent the same numeric value.

Salary period and source status participate in standardized content hashing.

The initial Bronze schema supports hash_version = 1. Future hashing changes require an explicit migration and reconciliation strategy under ADR-045.

Observed status changes participate in content hashing. Downstream effective status changes caused solely by passage of time must not create Bronze content versions.

The source listing identity and content hash must be used together to detect content changes.

Newer unchanged observations must refresh collected_at, last_seen_at, last_collection_run_id and the latest permitted raw_payload without incrementing content_version. Stale observations and identical retries must not overwrite newer state.

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

#### 7.1.1 Physical Bronze Implementation

The initial PostgreSQL 16 implementation contains
six Bronze tables:

| Table | Purpose | Columns |
|---|---|---:|
| collection_runs | Collection execution metadata and counters | 18 |
| source_listings | Latest accepted standardized source records | 42 |
| source_listing_history | Content-version snapshots | 10 |
| ingestion_observations | Observation identity and processing outcomes | 6 |
| invalid_records | Rejected records and permitted diagnostics | 12 |
| source_checkpoints | Persistent incremental collection state | 8 |

Seven SQL migrations create the three project schemas
and six Bronze tables.

The physical schema is implemented and locally tested.

Persistent ingestion behavior remains pending.

#### 7.1.2 Collection Model and Storage Fields

The standardized Data Contract defines 35 fields.

The Pydantic Opportunity collection model contains
32 fields.

The following three contract fields are generated
or managed during ingestion:

- source_listing_id
- content_hash
- last_seen_at

The physical source_listings table adds seven
storage-specific fields:

| Field | Data Type | Purpose |
|---|---|---|
| source_identity_key | TEXT | Deterministic source identity key |
| first_seen_at | TIMESTAMPTZ | Initial accepted observation timestamp |
| created_at | TIMESTAMPTZ | Database row creation timestamp |
| updated_at | TIMESTAMPTZ | Database row modification timestamp |
| hash_version | INTEGER | Content hashing algorithm version |
| content_version | INTEGER | Current content revision number |
| last_collection_run_id | UUID | Most recent accepted observation run |

These seven fields are managed by persistent
ingestion and database storage.

They are not required fields in the Pydantic
collection model.

The physical source_listings table therefore
contains 42 columns.

#### 7.1.3 Storage Admission and Identity

Initial Bronze ingestion requires a valid,
non-empty source_opportunity_id.

Generate the source identity key as:

source_identity_key = "id:" + source_opportunity_id

Enforce uniqueness of source_name and
source_identity_key.

Generate a stable UUID for source_listing_id
when a new source identity is inserted.

Preserve the UUID across subsequent observations
and content changes.

Source IDs remain optional at the collection model
level, but records without usable IDs cannot enter
the initial source_listings table.

The URL fallback strategy remains deferred.

Detailed source identity rules are documented
in ADR-042.

#### 7.1.4 Content History and Observation Semantics

Create an initial content history snapshot for
each new source listing.

Create subsequent snapshots only when standardized
content changes.

Keep content_version independent of hash_version.

A repeated historical content hash does not imply
that the new content revision is a duplicate.

Maintain one observation ledger entry per source
listing and logical collection run.

Use a dedicated observation hash for retry detection.

Identical retries must not duplicate writes.

Stale observations must not overwrite newer state.

Conflicting observations must preserve the original
accepted observation and retain permitted diagnostics.

Current listing, history and observation ledger
changes must be committed atomically.

Retain the latest permitted raw payload in the
current listing and the permitted payload associated
with each historical content version.

The initial design does not retain a full raw
snapshot for every unchanged observation.

Detailed rules are documented in ADR-043 and ADR-044.

#### 7.1.5 Hash Version Compatibility

The initial physical schema supports hash_version = 1.

Future hashing changes must preserve historical
hashes and original hash versions.

A hashing algorithm change must not automatically
create a new content version.

Future hash migration and reconciliation structures
are deferred under ADR-045.

#### 7.1.6 Invalid Records and Checkpoints

Invalid records are stored separately from accepted
source listings and associated with collection runs.

A deterministic rejection hash prevents duplicate
rejections within the same logical run.

Sensitive information must be removed before
persistent rejection storage.

Checkpoints are maintained per source and
collection scope.

Checkpoint advancement requires successful
persistent processing of the covered records.

Failed or partial runs must not advance the
previous successful checkpoint.

Incremental collection is not activated in
the initial implementation.

Detailed rules are documented in ADR-046 and ADR-048.

#### 7.1.7 Lifecycle Boundaries

Bronze preserves the opportunity status evaluated
at observation time.

Silver derives the downstream effective status
using reliable source and deadline evidence.

Passage of time alone must not create a new
Bronze content version.

Absence from a bounded collection run must not
be interpreted as closure or expiration.

Lifecycle reconciliation remains pending
under ADR-047.

#### 7.1.8 Validation and Implementation Status

Physical database validation completed on 2026-11-26:

- Three project schemas created.
- Six Bronze tables created.
- 96 Bronze columns verified.
- Seven SQL migrations applied successfully.
- Seven positive SQL checks passed.
- Sixteen negative SQL checks passed.
- All migrations reproduced in an isolated database.
- All 23 SQL checks repeated successfully.

These checks validate selected physical database
constraints, not complete application-level
Data Contract enforcement.

The previous collection-layer regression baseline
is 665 passing Python tests.

Persistent Python ingestion, transaction handling,
observation hashing, rejection hashing, lifecycle
reconciliation and checkpoint integration remain
pending.

Architecture decisions ADR-041 through ADR-050
define the approved implementation baseline.

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
| 3.0.0 | Final eight-source scope; UN Volunteers mapping; missing employment arrangement semantics; approved initial Bronze storage admission policy and physical storage design. Standardized collection fields and data types remain unchanged. Approved under ADR-050. |
