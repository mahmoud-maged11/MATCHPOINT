# Phase 4 Design Document: Cross-Source Deduplication & Canonical Opportunity Identity

This document specifies the Phase 4 Silver-layer deduplication and canonical identity design for **MATCHPOINT**, aligned with **Data Contract v3.0.0**, **ADR-003**, **ADR-004**, **ADR-018**, **ADR-026**, **ADR-042**, **ADR-043**, and **ADR-047**.

---

## 1. Architectural Overview

```text
silver_source_listings (Phase 3, 1 row per source_listing_id)
        │
        ▼
int_listing_match_features (extracts normalized signals, verified URLs, authority rank, ambiguity guard)
        │
        ▼
int_opportunity_match_pairs (Tier 1A, Tier 1B, Tier 2 cross-source edges + JSONB evidence)
        │
        ▼
int_opportunity_clusters (WITH RECURSIVE connected components, deterministic UUID, primary source)
        │
        ├──► silver_opportunity_sources  (1 row per source_listing_id -> canonical opportunity_id)
        ├──► silver_opportunities        (1 canonical row per opportunity_id + conflict transparency)
        └──► silver_opportunity_history  (1 row per Bronze history_id linked to opportunity_id)
```

- All Phase 3 models (`silver_source_listings`, `silver_listing_history`, etc.) remain **untouched**.
- No Bronze source records or Bronze history snapshots are ever deleted, rewritten, or overwritten.

---

## 2. Matching Strategy & Evidence Hierarchy

Matching is **strictly cross-source** (`a.source_name <> b.source_name`). Two distinct `source_opportunity_id`s from the **same** source are never automatically merged (`ADR-042`, `data_contract.md §5.12`).

### Generic Portal Exclusions (`seeds/generic_application_portals.csv` + `macros/normalize_url.sql`)
Per `ADR-026`, URLs are normalized symmetrically via `normalize_url_for_matching()` (lowercasing host and path and stripping trailing slashes/fragments while preserving functional query string casing). External application URLs matching generic platform homepages (`host_root_only`), social channels/shorteners (`host_any_generic_portal`), shared form/search/registration path prefixes (`path_prefix_generic`, e.g., `wuzzuf.net/jobs/egypt`, `nti.sci.eg/ereg`, `docs.google.com/forms`), exact directory pages (`path_exact_generic`, e.g., `wuzzuf.net/jobs`, `itida.gov.eg/english/programs`), or generic single-segment leaf paths (`/careers`, `/jobs`, `/apply`, `/register` with no query string) are **excluded** from strong URL matching.

### Tier 1A — `direct_cross_source_url` (Strongest Evidence)
Matches Listing A (`source_name` X) to Listing B (`source_name` Y) when Listing A's verified `raw_payload ->> 'application_url'` either:
1. Extracts a verified target `(source_name, source_opportunity_id)` matching Listing B from the case-preserved external URL (Wuzzuf `/jobs/p/<id>`, Bayt `/en/egypt/jobs/...-<id>`, UN Volunteers `/opportunities/<id>`), **or**
2. Equals Listing B's symmetrically normalized `source_url_normalized` (case-insensitive host+path, case-preserved query string, specific non-root path).

### Tier 1B — `shared_external_application_url`
Matches Listing A and Listing B across different sources when **all** hold:
- Both carry the identical verified non-generic deep `application_url`,
- `opportunity_type` matches,
- Organizations do not conflict when both are present.

### Tier 2 — `multi_signal_composite` (Conservative Structured Match)
Matches Listing A and Listing B across different sources ONLY when **all** of the following hold simultaneously:
1. **Normalized title** (`title_match_key`, length >= 4, Arabic & English preserved) matches — **never used alone**.
2. **Normalized organization** (`organization_key`) is **non-null** and matches — missing organizations never match.
3. **Opportunity type** (`opportunity_type`) matches exactly.
4. **Specific location or remote signal** (`location_match_signal`: `city:<city>:<cc>`, `gov:<gov>:<cc>`, or `remote`) is **non-null** and matches — missing or broad country-only locations (e.g., `"Egypt"`) stay `NULL` and never match.
5. **Within-source ambiguity guard:** Neither source has > 1 listing sharing the identical Tier 2 tuple (`is_composite_ambiguous_within_source = FALSE`).
6. **Work-mode compatibility:** When both listings have populated known `work_modes`, they share at least one overlapping value.
7. **Temporal compatibility:** Reliable `published_at` within **45 days**; reliable `deadline` within **14 days**; otherwise `first_seen_at` within **45 days**.

### Ambiguous-Match Handling
- If a single source contains multiple listings with the same Tier 2 composite tuple, automatic Tier 2 merging is disabled (`singleton_ambiguous_composite`).
- If a transitive connected component violates component-wide invariants (same-source uniqueness, temporal span, or work-mode compatibility), it falls back to valid Tier 1 edges (`tier1_fallback`) or retains members conservatively as separate singletons (`singleton_transitive_conflict`).

---

## 3. Canonical Identity Generation (`opportunity_id`)

- Connected components across `int_opportunity_match_pairs` are resolved using PostgreSQL 16 `WITH RECURSIVE ... UNION` over symmetric undirected edges (eliminating combinatorial path enumeration, guaranteeing cycle termination, and removing artificial depth-8 truncation).
- **Component-Wide Invariant Enforcement:** Every connected component is verified across all its members (not just pairwise edges):
  1. **No same-source co-membership:** `COUNT(DISTINCT source_name) = COUNT(*)`.
  2. **Component-wide temporal and work-mode consistency (for Tier 2 components):** Reliable `published_at` span <= 45 days, reliable `deadline` span <= 14 days, and pairwise work-mode compatibility across all members with known `work_modes`.
  3. **Conservative fallback:** If a full component violates a component-wide invariant, it falls back to valid Tier 1-only components (`tier1_fallback`); if a Tier 1 component still violates same-source uniqueness, all conflicting members are retained conservatively as separate singletons (`singleton_transitive_conflict`) with full JSONB diagnostics.
- For each resolved component, a deterministic **identity anchor** (`canonical_anchor_key = source_name || ':' || source_identity_key`) is chosen strictly by **immutable source authority and identity**:
  1. `source_authority_rank ASC` (`itida=1, nti=2, un_volunteers=3, devpost=4, wuzzuf=5, forasna=6, bayt=7, egyincs=8`),
  2. `source_name ASC`,
  3. `source_identity_key ASC`.
  *(Secondary URL pointer flags never override higher source authority.)*
- `opportunity_id` is generated via `macros/deterministic_uuid.sql` using native PostgreSQL 16 `SHA256('matchpoint:canonical_opportunity:v1|' || canonical_anchor_key)` formatted as a valid RFC 4122-shaped `UUID` (zero external extensions required).

---

## 4. Primary-Source Selection & Conflict Transparency

- Exactly one `source_listing_id` per `opportunity_id` receives `is_primary_source = TRUE`, ordered deterministically by:
  1. `source_authority_rank ASC`
  2. `is_direct_url_target DESC`
  3. `completeness_score DESC`
  4. `first_seen_at ASC`
  5. `source_identity_key ASC`
  6. `source_listing_id::TEXT ASC`
- Correlated attribute bundles (`salary`, `experience`, `published_at`, `deadline`, `organization`, `location`) are selected from the highest-priority source providing that bundle so ranges and date-precision pairs never mix inconsistently across sources.
- **No silent discarding of conflicts:** `silver_opportunities` exposes:
  - `all_source_urls` (JSONB array preserving every merged source link and status),
  - `observed_effective_statuses` (all distinct statuses across merged sources),
  - `has_source_attribute_conflicts` (`BOOLEAN`) and `conflicting_attributes` (JSONB array listing differing fields: `title`, `organization`, `opportunity_type`, `location`, `effective_status`, `salary`, `employment_types`, `deadline`).
  - Salary conflict detection normalizes numeric scale via `TRIM_SCALE()` (`ADR-019`, so `10000` equals `10000.00`) and compares `(salary_min, salary_max, UPPER(currency), LOWER(salary_period))`.

---

## 5. Idempotency Guarantees & Honest Limitations

### Guaranteed by This Implementation
- Re-running dbt on unchanged Bronze data produces **bit-for-bit identical** `opportunity_id`s, clusters, and `is_primary_source` assignments.
- Adding an unrelated listing never changes any existing `opportunity_id`.
- Input row order never affects matching, clustering, or anchor selection.
- When a lower-authority aggregator listing (e.g., `egyincs`) later links to an already-existing primary source listing (e.g., `wuzzuf`), the existing `opportunity_id` is **preserved**.

### Known Limitations & Risks
1. **Late-arriving higher-authority merge (stateless SQL limitation):** Because dbt models currently run as full-refresh stateless tables without a persistent canonical identity registry table, if a lower-authority listing (e.g., `egyincs`) is published alone first and a higher-authority listing (e.g., `wuzzuf`) arrives later and merges with it, the merged cluster switches to the higher-authority anchor's `opportunity_id`. Full cross-run immutability under late-arriving higher-authority merges would require a stateful identity registry table in a future phase.
2. **False-negative risk (intentional conservatism):** Minor title rewordings across sources without a shared external URL (e.g., `"Junior Data Engineer"` vs `"Data Engineer - Junior"`) or unmapped organization spelling variants will intentionally remain separate until stronger evidence or explicit alias mappings are added.
3. **False-positive risk (mitigated):** Two genuinely distinct openings at the same employer with identical title, city, type, and publication window on two different boards (only 1 on each board) could theoretically merge under Tier 2 if neither has distinguishing external URLs or conflicting work modes.
4. **Transitive chain depth:** Unbounded via PostgreSQL 16 `WITH RECURSIVE ... UNION` (the earlier 8-hop `UNION ALL` cap was removed in Bug 3 remediation; chains exceeding 8 edges converge cleanly without path explosion or splitting, while component-wide invariants still guard against same-source merges and temporal/work-mode drift).
5. **External URL coverage:** Only sources that retain `application_url` in `raw_payload` (currently Egyincs) participate in Tier 1 external-URL edges until other adapters expose verified external apply links.

---

## 6. Execution Commands (Once PostgreSQL 16 + dbt Are Available)

```powershell
cd dbt
dbt seed --profiles-dir .
dbt run --select +silver_opportunities +silver_opportunity_sources +silver_opportunity_history --profiles-dir .
dbt test --profiles-dir .

# Verify repeatability / idempotency by running a second time:
dbt run --select +silver_opportunities +silver_opportunity_sources +silver_opportunity_history --profiles-dir .
dbt test --profiles-dir .
```

---

## 7. Phase 4 Bug Fixes & Runtime Validation Results

**Validated Date:** 2026-11-26  
**Code Audit Fixes Status:** **ALL 7 IDENTIFIED ISSUES RESOLVED**  
**Synthetic Runtime Validation Status:** **PASS (PostgreSQL 16.16 + dbt-core 1.9.11 / dbt-postgres 1.9.1 on isolated `matchpoint_test`)**  
**Real-World Ingestion Validation Status:** **PENDING** *(Persistent Python ingestion in `scrapers/storage/postgres.py` is owned by Mahmoud and remains pending; synthetic validation does not establish live ingestion readiness.)*

### 7.1 Resolution of the Seven Identified Issues
1. **Bug 1 (URL Case Sensitivity) — Fixed:** Added `macros/normalize_url.sql` (`normalize_url_for_matching`) applied symmetrically to `source_url` and `external_application_url_raw`, lowercasing host and path while preserving query string casing; ID extraction keeps original casing for case-sensitive source IDs.
2. **Bug 2 (Transitive Connected Component Invariants) — Fixed:** `int_opportunity_clusters.sql` enforces component-wide same-source uniqueness (`COUNT(DISTINCT source_name) = COUNT(*)`), component-wide temporal spans (45d `published_at`, 14d `deadline`), and pairwise `work_modes` compatibility across Tier 2 components, with deterministic `tier1_fallback` and conservative `singleton_transitive_conflict` splitting. Added `assert_silver_no_same_source_in_canonical_opportunity.sql`.
3. **Bug 3 (Recursive Query Performance & Depth-8 Split) — Fixed:** Replaced `WITH RECURSIVE ... UNION ALL` + `visited_ids` + `depth < 8` with PostgreSQL 16 set-deduplicating `WITH RECURSIVE ... UNION` on `(start_id, current_id)` (polynomial time, automatic cycle termination, no depth-8 split).
4. **Bug 4 (Generic Non-Root Application URLs) — Fixed:** Expanded `generic_application_portals.csv` (36 patterns) with `path_exact_generic` and `path_prefix_generic` rules for directory/search/registration hubs (`wuzzuf.net/jobs/egypt`, `nti.sci.eg/ereg`, etc.) plus generic single-segment careers/apply leaf path filtering (`/careers`, `/jobs`, `/apply`, `/register` without query strings).
5. **Bug 5 (Canonical Identity Anchor Stability) — Fixed:** Removed `is_direct_url_target` from `component_anchors` so identity anchors strictly follow immutable `(source_authority_rank, source_name, source_identity_key)`; moved `source_authority_rank` ahead of `is_direct_url_target` in `primary_ranked`.
6. **Bug 6 (Salary & Employment Conflict Detection) — Fixed:** Normalized `salary_min`/`salary_max` with PostgreSQL `TRIM_SCALE()` (`ADR-019`) and included `UPPER(currency)` and `LOWER(salary_period)` in `conflict_salary`, plus added `conflict_employment_types` via precomputed `employment_types_signature`.
7. **Bug 7 (Synthetic Integration Test Coverage) — Fixed:** Added `dbt/integration_tests/` (`load_phase4_synthetic_bronze.sql`, `verify_phase4_synthetic_results.sql`, `verify_phase4_idempotency.sql`, `README.md`) testing all real Phase 4 dbt models end-to-end across 10 verification groups (covering all 12 required scenarios), plus upgraded `assert_dedup_positive_and_negative_cases.sql` to test real macros, generic portal seeds, ADR-019 salary normalization, and a 10-edge chain (> 8 edges).

### 7.2 Actual PostgreSQL 16.16 Runtime Validation Record (`matchpoint_test`)

Executed on an isolated PostgreSQL 16.16 test database (`current_database() = matchpoint_test`) initialized cleanly with approved migrations `database/migrations/001` through `007` (6 Bronze tables, 96 columns):

| Check | Actual Result |
|---|---|
| `dbt debug --target test --profiles-dir .` | **PASS** (`Connection test: [OK connection ok]`, `All checks passed!`) |
| `dbt parse --target test --profiles-dir .` | **PASS** (Exit 0; 24 models, 290 data tests, 4 seeds, 6 sources) |
| `dbt seed --target test --profiles-dir .` | **PASS** (`4/4` seeds loaded into `silver.*`: 36 + 89 + 17 + 71 rows) |
| `dbt run` (empty Bronze sanity check) | **PASS** (`24/24` models in 2.85s, 0 errors, 0 warnings) |
| `load_phase4_synthetic_bronze.sql` | **PASS** (41 synthetic listings, 9 runs, 2 Bronze history rows) |
| `dbt run` (**Run 1** on synthetic Bronze) | **PASS** (`24/24` models in 3.31s; **41 source listings → 32 canonical opportunities**, 2 history rows) |
| `verify_phase4_synthetic_results.sql` | **PASS** (All 10 scenario groups `PASS S1` through `PASS S10` verified against materialized tables) |
| `dbt test --target test --profiles-dir .` | **PASS** (**290/290 passed**, 0 failures, 0 errors, 0 warnings, 0 skipped — 278 generic YAML + 12 singular SQL tests in 15.00s) |
| `dbt run` (**Run 2**) + `verify_phase4_idempotency.sql` | **PASS** (`24/24` models in 3.29s; **0 row/ID diffs** — bit-for-bit identical canonical UUIDs for all 41 listings / 32 opportunities) |
| Same-source co-membership invariant | **PASS** (`same_source_violations = 0`) |

### 7.3 Observed Synthetic Outcome Breakdown (41 Listings → 32 Canonical Opportunities)
- `direct_cross_source_url`: 6 listings → 3 opportunities (including mixed-case SharePoint URL & 4-source chain anchor stability)
- `multi_signal_composite`: 8 listings → 4 opportunities (including English/Arabic Cairo & ADR-019 salary equivalence vs real `salary`/`employment_types` conflicts)
- `shared_external_application_url`: 2 listings → 1 opportunity
- `singleton`: 15 listings → 15 opportunities
- `singleton_ambiguous_composite`: 4 listings → 4 opportunities
- `singleton_transitive_conflict`: 6 listings → 6 opportunities (same-source transitive bridge & 78-day temporal drift split conservatively)

> **Distinction Between Synthetic and Live Validation:** The results above verify SQL correctness, deduplication invariants, conflict transparency, and repeatability using controlled synthetic fixtures in `matchpoint_test`. End-to-end validation with live collected data from all eight sources remains pending completion of persistent Python ingestion (`scrapers/storage/postgres.py`, owned by Mahmoud).

