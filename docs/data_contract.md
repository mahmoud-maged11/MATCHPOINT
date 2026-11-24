\# MATCHPOINT Data Contract



\*\*Version:\*\* 1.0.0  

\*\*Status:\*\* Initial approved specification  

\*\*Owners:\*\* Data Collection \& Data Warehouse Teams



\## 1. Purpose



This document defines the standardized data structure exchanged between the Data Collection and Data Transformation components of MATCHPOINT.



All source adapters must follow this contract before loading standardized records into the data pipeline.



\## 2. Data Schema



| Column | Data Type | Required |

|---|---|---|

| opportunity\_id | UUID | Yes, generated internally |

| source\_name | VARCHAR | Yes |

| source\_opportunity\_id | TEXT | No |

| source\_url | TEXT | Yes |

| title | TEXT | Yes |

| organization | TEXT | No |

| description | TEXT | No |

| opportunity\_type | VARCHAR | Yes |

| location | TEXT | No |

| work\_mode | VARCHAR | No |

| employment\_type | VARCHAR | No |

| experience\_level | VARCHAR | No |

| education\_level | TEXT | No |

| required\_skills | JSONB | No |

| requirements | TEXT | No |

| salary\_min | NUMERIC | No |

| salary\_max | NUMERIC | No |

| currency | VARCHAR | No |

| published\_at | TIMESTAMPTZ | No |

| deadline | TIMESTAMPTZ | No |

| collected\_at | TIMESTAMPTZ | Yes |

| last\_seen\_at | TIMESTAMPTZ | Yes, managed during ingestion |

| content\_hash | TEXT | Yes, generated during ingestion |

| status | VARCHAR | Yes |

| raw\_payload | JSONB | Yes, in Bronze |



\## 3. Supported Sources



\- wuzzuf

\- forasna

\- egyincs

\- itida

\- nti

\- bayt

\- linkedin

\- amideast

\- devpost

\- un\_volunteers



\## 4. Standardized Values



\### Opportunity Type



\- job

\- internship

\- graduate\_program

\- training

\- scholarship

\- competition

\- hackathon

\- freelance

\- volunteering

\- event



\### Work Mode



\- on\_site

\- remote

\- hybrid

\- unknown



\### Employment Type



\- full\_time

\- part\_time

\- contract

\- temporary

\- freelance

\- unknown



\### Experience Level



\- entry\_level

\- junior

\- mid\_level

\- senior

\- lead

\- manager

\- executive

\- unknown



\### Opportunity Status



\- active

\- expired

\- closed

\- unknown



\## 5. Data Rules



\- All column names must use snake\_case.

\- Missing information must be represented as null.

\- Missing information must not be fabricated.

\- Timestamps must follow ISO 8601 and use UTC.

\- Date-only deadlines must retain their original precision.

\- Required skills must be represented as an array of strings when available.

\- Salary values must be numeric and non-negative.

\- Currency codes must follow ISO 4217.

\- Original source URLs must be preserved.

\- Raw source data must be preserved in the Bronze layer.

\- Duplicate opportunities must be identified during transformation.

\- Source attribution must be preserved after deduplication.

\- Missing deadlines must not automatically indicate expired opportunities.

\- Content hashes must use a consistent hashing strategy.



\## 6. Data Architecture



\### Bronze Layer



Stores raw source records, original payloads, collection timestamps, and source metadata.



\### Silver Layer



Stores cleaned, validated, standardized, and deduplicated opportunities.



\### Gold Layer



Stores business-ready datasets for application integration, matching, reporting, and analytical consumption.



\## 7. Responsibilities



\### Mahmoud: Data Collection \& Backend



\- Collect data from approved sources.

\- Implement source adapters.

\- Preserve raw source data.

\- Load collected records into PostgreSQL.

\- Integrate curated opportunities with the backend.



\### Momen: Data Warehouse \& Transformation



\- Design PostgreSQL schemas and tables.

\- Implement dbt transformation models.

\- Develop Silver and Gold layers.

\- Implement deduplication and data quality tests.

\- Maintain warehouse documentation.



\### Andrew: Pipeline \& Orchestration



\- Automate pipeline execution using Apache Airflow.

\- Manage scheduling, dependencies, and monitoring.

\- Load analytical datasets into ClickHouse.



\### Ramadan: Analytics



\- Consume analytical datasets from ClickHouse.

\- Develop SQL analytics and Power BI dashboards.



\### Abdel Rahman: Frontend



\- Consume opportunity data through backend APIs.

\- Display opportunities and personalized recommendations.



\## 8. Schema Evolution



Changes to the data contract must be documented and reviewed through GitHub Pull Requests.



Breaking changes must be communicated to all affected team members before implementation.



The contract will be refined as real source data becomes available.

