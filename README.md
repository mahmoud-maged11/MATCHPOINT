# MATCHPOINT

*Your Next Opportunity Starts Here.*

## Project Overview

MATCHPOINT is a youth opportunity discovery and recommendation platform designed to help students, fresh graduates, job seekers and career changers in Egypt find opportunities matching their skills, interests, education and career goals.

## Project Objectives and Planned Features

- Centralize opportunities from permitted sources.
- Provide opportunity discovery, search and personalized recommendations.
- Identify skill gaps between user profiles and opportunity requirements.
- Support saved opportunities, deadline notifications and application tracking.
- Analyze market trends and in-demand skills.

Target users include university students, fresh graduates, job seekers, professionals seeking career development and career changers. User-facing features remain planned.

## Final Data Collection Scope

| Source | CLI identifier | Collection approach |
|---|---|---|
| Wuzzuf | `wuzzuf` | API |
| Forasna | `forasna` | HTML and JSON-LD |
| Egyincs | `egyincs` | WordPress REST API |
| ITIDA | `itida` | SharePoint HTML and ASP.NET pagination |
| NTI | `nti` | HTML and dynamic course discovery |
| Bayt | `bayt` | HTML and JSON-LD |
| Devpost | `devpost` | API and HTML detail enrichment |
| UN Volunteers | `un_volunteers` | JSON API search and details |

All eight adapters have been implemented and tested with bounded live samples. This does not establish complete coverage, production authorization or applicant eligibility. Online opportunities may have international host locations; geographic filtering does not guarantee Egyptian applicant eligibility. UN Volunteers accepts explicitly online assignments and onsite assignments in Egypt. No additional sources are planned within the current scope.

## Technology Stack

| Component | Technologies | Status |
|---|---|---|
| Data collection and validation | Python, Requests, Beautiful Soup, Pydantic | Implemented |
| Automated testing | pytest, PostgreSQL SQL tests | Collection and physical Bronze tests implemented |
| Data storage | PostgreSQL 16 | Physical Bronze schema implemented and locally tested; Python ingestion pending |
| Data transformation | Python, SQL, dbt | Silver and Gold schemas created; transformation models pending |
| Workflow orchestration | Apache Airflow | Planned |
| Analytics database | ClickHouse 25.8 | Infrastructure configured and tested; analytical loading pending |
| Backend | Python, FastAPI | Planned |
| Frontend | React, Vite | Planned |
| Processing and matching | pandas, spaCy, scikit-learn | Proposed |
| Visualization | Power BI | Planned |
| Version control and infrastructure | Git, GitHub, Docker Compose | Configured |

## Architecture

```text
Eight opportunity sources
    -> Source adapters / collection
    -> Mapping, normalization and contract validation
    -> PostgreSQL Bronze (persistent ingestion and source history)
    -> Silver (cleaning, enrichment, deduplication, canonical identity)
    -> Gold (business-ready datasets)
         -> FastAPI -> React
         -> ClickHouse -> Power BI
```

Airflow is planned to orchestrate collection, ingestion, dbt transformations and analytical loading. Collection, mapping, validation, shared content hashing and the physical Bronze schema are implemented. Persistent Python ingestion and downstream integration remain pending. Bronze must preserve permitted source evidence and ingestion metadata. Silver must preserve source attribution while identifying canonical opportunities.

## Current Project Status

As of 2026-11-26, on the `feature/data-warehouse` branch:

### Data Collection

- Eight of eight source adapters implemented and bounded-live validated.
- Shared collection utilities, standardized models, content hashing and in-memory invalid-record handling implemented.
- Collection regression baseline: **665 Python tests passed** on 2026-11-25, including 71 UN Volunteers tests.
- UN Volunteers expanded live sample: 40 accepted assignments (39 online, one onsite in Egypt), with zero duplicate IDs, invalid records or missing details.
- The subsequent employment arrangement correction was verified by automated tests, not a new live run.
- A separate handover sample contains 40 validated records, five per source.

### Data Contract and Technical Design

- Data Contract v3.0.0 approved under ADR-050.
- Initial Bronze physical design approved.
- Source identity, content history, idempotency, hash versioning, invalid-record retention, lifecycle and checkpoint designs documented.
- Technical design approval no longer blocks persistent ingestion implementation.
- Team communication and integration validation remain pending.

### PostgreSQL Warehouse

- PostgreSQL 16 connectivity verified.
- Bronze, Silver and Gold schemas created.
- Six physical Bronze tables implemented.
- Seven SQL migrations created and successfully applied.
- Primary keys, foreign keys, unique constraints, check constraints and indexes implemented.
- Fresh database reconstruction successfully verified.

| Bronze table | Columns |
|---|---:|
| collection_runs | 18 |
| source_listings | 42 |
| source_listing_history | 10 |
| ingestion_observations | 6 |
| invalid_records | 12 |
| source_checkpoints | 8 |
| **Total** | **96** |

### Database Testing

| Validation | Result |
|---|---:|
| Positive SQL checks | 7 passed |
| Negative SQL checks | 16 passed |
| Distinct SQL checks | 23 passed |
| Successful executions across two databases | 46 |
| Fresh migration reconstruction | Passed |

SQL checks are reported separately from the Python regression baseline.

### Remaining Implementation

- PostgreSQL Python storage module and persistent ingestion.
- Application-level transaction management and idempotency.
- Persistent collection run and invalid-record integration.
- Observation and rejection hashing.
- Lifecycle reconciliation.
- Incremental collection and checkpoint integration.
- Silver and Gold transformation models.
- Airflow orchestration and ClickHouse analytical loading.
- Backend, matching, frontend and analytics.
- Production authorization, privacy review and operational readiness.

The physical database schema is implemented, but end-to-end ingestion has not yet been demonstrated.

These statements describe the warehouse feature branch, not a completed application or a merged release on `main`.


## Getting Started

### Prerequisites

- Git
- Docker Desktop and Docker Compose
- Python 3.12 (recommended)
- DBeaver (recommended)

### 1. Clone the repository

```bash
git clone https://github.com/mahmoud-maged11/MATCHPOINT.git
cd MATCHPOINT
```

Use the appropriate feature branch for development. The collection implementation is on `feature/data-collection`. The Bronze implementation integrates that collection baseline on `feature/data-warehouse`.

### 2. Configure environment variables

PowerShell:

```powershell
Copy-Item .env.example .env
```

Git Bash:

```bash
cp .env.example .env
```

Update `.env` with local credentials. Never commit credentials or the `.env` file.

### 3. Start and verify database services

```bash
docker compose up -d
docker compose ps
```

| Setting | PostgreSQL | ClickHouse |
|---|---|---|
| Host | localhost | localhost |
| Port | 5432 | 8123 |
| Database | matchpoint | matchpoint_analytics |
| Username | matchpoint | matchpoint |
| Password | From .env | From .env |

For container-to-container communication, use the service names `postgres` and `clickhouse` instead of `localhost`.

### 4. Initialize the PostgreSQL warehouse

Switch to the warehouse feature branch when working
with the physical Bronze implementation:

```powershell
git switch feature/data-warehouse
```

Start PostgreSQL and verify connectivity:

```powershell
docker compose up -d postgres

docker compose exec postgres psql -U matchpoint -d matchpoint -c "SELECT current_database(), current_user;"
```

The following commands assume the default local
database and username from the project configuration.
Adjust them if your local configuration differs.

Inspect existing schemas before initialization:

```powershell
docker compose exec postgres psql -U matchpoint -d matchpoint -c "\dn"
```

Apply the migrations only to a fresh project database
where the Bronze tables have not already been created.

From the repository root in Windows PowerShell:

```powershell
$migrations = Get-ChildItem database/migrations -Filter "*.sql" -File | Sort-Object Name

foreach ($migration in $migrations) {
    Write-Host "Applying $($migration.Name)"

    Get-Content $migration.FullName -Raw |
        docker compose exec -T postgres psql -U matchpoint -d matchpoint -v ON_ERROR_STOP=1

    if ($LASTEXITCODE -ne 0) {
        throw "Migration failed: $($migration.Name)"
    }
}
```

Verify the resulting database structure:

```powershell
docker compose exec postgres psql -U matchpoint -d matchpoint -c "\dn"

docker compose exec postgres psql -U matchpoint -d matchpoint -c "\dt bronze.*"
```

Expected project schemas:

- bronze
- silver
- gold

Expected Bronze tables: six.

The public schema may also be present.

The initial migration sequence is intended for fresh
database construction. Persistent migration tracking
and upgrade procedures remain pending.

Do not blindly rerun the complete migration sequence
against an existing initialized database.

If a migration fails, investigate the database state
before attempting recovery. Previously committed
migration files may already have been applied.

### 5. Run Bronze database integrity tests

Use a local development or isolated test database.

Run the positive SQL checks:

```powershell
Get-Content tests/sql/test_bronze_valid_records.sql -Raw |
    docker compose exec -T postgres psql -U matchpoint -d matchpoint -v ON_ERROR_STOP=1
```

Run the negative SQL checks:

```powershell
Get-Content tests/sql/test_bronze_invalid_records.sql -Raw |
    docker compose exec -T postgres psql -U matchpoint -d matchpoint -v ON_ERROR_STOP=1
```

Expected results:

- Seven positive checks pass.
- Sixteen negative checks pass.
- Both scripts complete with ROLLBACK.

The scripts use synthetic records and transaction
rollback to avoid retaining test data.

These tests validate selected physical database
constraints. They do not establish complete Python
ingestion correctness or concurrent processing safety.

Persistent ingestion is not yet available through
the collection CLI.


### 6. Install collection dependencies

From the repository root in Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r scrapers/requirements.txt
.\.venv\Scripts\python.exe -m pip install pytest
```

If a virtual environment already exists, reuse it. Install any additional browser dependencies required by the relevant adapter before using browser-based collection.

### 7. Run collectors and Python tests

```powershell
.\.venv\Scripts\python.exe -m scrapers.main --help
.\.venv\Scripts\python.exe -m pytest -q
```

Example bounded API collection, subject to applicable source access policies:

```powershell
.\.venv\Scripts\python.exe -m scrapers.main --source un_volunteers --mode api --max-jobs 20 --page-size 20 --max-pages 10 --output "$env:TEMP\unv_sample.json"
```

Use the CLI help and adapter documentation to select supported modes and limits for each source. Collection output is not evidence of persistent Bronze ingestion. Keep generated datasets and sensitive data out of Git.

### 8. Stop database services

```bash
docker compose down
```

Do not use `docker compose down -v` unless you intentionally want to delete stored database data.

## Repository Structure

```text
MATCHPOINT/
|-- scrapers/
|   |-- sources/             # Eight collectors and source mappers
|   |-- storage/             # Persistent ingestion pending
|   |-- utils/               # Shared collection utilities
|   |-- main.py
|   |-- models.py
|   |-- source_config.py
|   |-- base_scraper.py
|   |-- config.py
|   `-- requirements.txt
|-- tests/
|   |-- fixtures/
|   `-- sql/
|       |-- test_bronze_valid_records.sql
|       `-- test_bronze_invalid_records.sql
|-- database/
|   `-- migrations/
|       |-- 001_create_schemas.sql
|       |-- 002_create_collection_runs.sql
|       |-- 003_create_source_listings.sql
|       |-- 004_create_source_listing_history.sql
|       |-- 005_create_ingestion_observations.sql
|       |-- 006_create_invalid_records.sql
|       `-- 007_create_source_checkpoints.sql
|-- dbt/
|-- airflow/
|   `-- dags/
|-- clickhouse/
|-- analytics/
|-- backend/
|-- frontend/
|-- docs/
|   |-- data_contract.md
|   |-- architecture_decisions.md
|   |-- pending_tasks.md
|   `-- MATCHPOINT_Project_Documentation_Final.docx
|-- .env.example
|-- .gitignore
|-- docker-compose.yml
`-- README.md
```

Several downstream directories remain scaffolding.
Their presence does not imply completed implementation.


## Team Responsibilities

| Member | Responsibility |
|---|---|
| Mahmoud | Data collection, validation, hashing, PostgreSQL ingestion and backend |
| Momen | PostgreSQL warehouse design, dbt, Silver/Gold, deduplication and data quality |
| Andrew | Airflow orchestration, monitoring and ClickHouse analytical loading |
| Ramadan | SQL analytics and Power BI dashboards |
| Abdel Rahman | React frontend |

The initial Data Contract and Bronze technical design are approved under ADR-050. Mahmoud and Momen must coordinate persistent ingestion, transformation integration, testing and remaining implementation details. Existing component responsibilities remain unchanged.

## Project Documentation

- [Data Contract](docs/data_contract.md): standardized schema and source mapping rules.
- [Architecture Decisions](docs/architecture_decisions.md): technical decisions and rationale.
- [Pending Tasks](docs/pending_tasks.md): outstanding tasks, blockers and validation milestones.
- [Project Documentation](docs/MATCHPOINT_Project_Documentation_Final.docx): project-level documentation, pending alignment with the latest implementation.

## Development Workflow

1. Fetch and review the latest changes from `main`.
2. Work on the appropriate feature branch.
3. Implement and test changes.
4. Update the contract, architecture decisions and pending tasks where relevant.
5. Commit with descriptive messages and push the feature branch.
6. Open a Pull Request for review.
7. Merge approved changes into `main`.

Communicate contract changes to affected team members before integration.

## Responsible Data Collection

Use only permitted collection methods and respect applicable terms, access restrictions and rate limits. Do not bypass access controls. Retain only relevant and permitted source evidence; avoid hidden financial or organization information and unnecessary personal data. Live HTTP success does not establish production permission. Do not infer closure from absence in a bounded run or infer applicant eligibility from online delivery alone.

## Next Development Milestones

1. Implement PostgreSQL Python connectivity and transaction management.
2. Implement persistent collection runs and source listing identity.
3. Implement content history, observation hashing and idempotent ingestion.
4. Integrate persistent invalid-record handling.
5. Validate persistent ingestion using the 40-record handover sample.
6. Integrate all eight source adapters with Bronze.
7. Implement Silver and Gold transformation models.
8. Implement lifecycle reconciliation and validated incremental strategies.
9. Integrate Airflow orchestration and ClickHouse analytical loading.
10. Implement backend, matching, frontend and dashboards.
11. Complete integration tests, deployment documentation and end-to-end validation.

Future hash migration and reconciliation infrastructure
remain intentionally deferred.

Production authorization, privacy review, retention
policies, migration tracking and operational readiness
remain separate requirements.

The detailed outstanding work remains in `docs/pending_tasks.md`.
