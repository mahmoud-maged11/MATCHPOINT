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
| Automated testing | pytest | Implemented |
| Data storage | PostgreSQL 16 | Infrastructure configured and tested; ingestion pending |
| Data transformation | Python, SQL, dbt | Warehouse implementation pending |
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

Airflow is planned to orchestrate collection, ingestion, dbt transformations and analytical loading. Collection, mapping, validation and shared content hashing are implemented; persistent ingestion and downstream integration remain pending. Bronze must preserve permitted source evidence and ingestion metadata. Silver must preserve source attribution while identifying canonical opportunities.

## Current Project Status

As of 2026-11-25, on the `feature/data-collection` branch:

- Eight of eight source adapters implemented and bounded-live validated.
- Shared collection utilities, standardized models, content hashing and in-memory invalid-record handling implemented.
- Latest regression result: **665 tests passed**, including 71 UN Volunteers tests.
- UN Volunteers expanded live sample: 40 accepted assignments (39 online, one onsite in Egypt), with zero duplicate IDs, invalid records or missing details. The subsequent employment arrangement correction was verified by automated tests, not a new live run.
- Data Contract 3.0.0 is proposed, pending team approval; the previous version is 2.1.0.
- PostgreSQL and ClickHouse infrastructure configured and tested; persistent storage configured. End-to-end pipeline integration has not been demonstrated.
- Warehouse schema, persistent ingestion, lifecycle management, incremental collection, orchestration, backend, frontend and analytics remain pending implementation or integration review.

These statements describe the collection branch, not a completed application or a merged release on `main`.

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

Use the appropriate feature branch for development. The collection implementation is currently on `feature/data-collection`.

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

### 4. Install collection dependencies

From the repository root in Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r scrapers/requirements.txt
.\.venv\Scripts\python.exe -m pip install pytest
```

If a virtual environment already exists, reuse it. Install any additional browser dependencies required by the relevant adapter before using browser-based collection.

### 5. Run collectors and tests

```powershell
.\.venv\Scripts\python.exe -m scrapers.main --help
.\.venv\Scripts\python.exe -m pytest -q
```

Example bounded API collection, subject to applicable source access policies:

```powershell
.\.venv\Scripts\python.exe -m scrapers.main --source un_volunteers --mode api --max-jobs 20 --page-size 20 --max-pages 10 --output "$env:TEMP\unv_sample.json"
```

Use the CLI help and adapter documentation to select supported modes and limits for each source. Collection output is not evidence of persistent Bronze ingestion. Keep generated datasets and sensitive data out of Git.

### 6. Stop database services

```bash
docker compose down
```

Do not use `docker compose down -v` unless you intentionally want to delete stored database data.

## Repository Structure

```text
MATCHPOINT/
├── scrapers/
│   ├── sources/             # Eight collectors and source mappers
│   ├── storage/             # Storage integration area
│   ├── utils/               # Shared collection utilities
│   ├── main.py
│   ├── models.py
│   ├── source_config.py
│   ├── base_scraper.py
│   ├── config.py
│   └── requirements.txt
├── tests/
│   └── fixtures/
├── database/
│   └── migrations/
├── dbt/
├── airflow/
│   └── dags/
├── clickhouse/
├── analytics/
├── backend/
├── frontend/
├── docs/
│   ├── data_contract.md
│   ├── architecture_decisions.md
│   ├── pending_tasks.md
│   └── MATCHPOINT_Project_Documentation_Final.docx
├── .env.example
├── .gitignore
├── docker-compose.yml
└── README.md
```

Several downstream directories are currently scaffolding; their presence does not imply completed implementation.

## Team Responsibilities

| Member | Responsibility |
|---|---|
| Mahmoud | Data collection, validation, hashing, PostgreSQL ingestion and backend |
| Momen | PostgreSQL warehouse design, dbt, Silver/Gold, deduplication and data quality |
| Andrew | Airflow orchestration, monitoring and ClickHouse analytical loading |
| Ramadan | SQL analytics and Power BI dashboards |
| Abdel Rahman | React frontend |

Mahmoud and Momen must coordinate the contract, physical Bronze schema, source identity, history, idempotency, transaction boundaries and lifecycle handling before persistent integration. Responsibilities remain subject to team review.

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

- Review and approve the proposed contract with the team.
- Agree on the physical Bronze schema and persistent ingestion interface.
- Implement source identity, content history, invalid-record retention, idempotency and incremental checkpoints.
- Integrate Silver and Gold transformations, orchestration and analytical loading.
- Implement backend, matching, frontend and dashboards.
- Complete integration tests, deployment documentation and end-to-end validation.

The detailed outstanding work remains in `docs/pending_tasks.md`.
