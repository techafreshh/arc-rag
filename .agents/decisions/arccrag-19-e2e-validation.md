# Decision Log & Implementation Postmortem: arccrag-19-e2e-validation

- **Date**: 2026-06-07
- **Branch**: `feature/arccrag-19-e2e-validation`
- **Report Path**: `.agents/reports/arccrag-19-e2e-validation-report.md`

## 1. Summary of Implementation

Created an end-to-end validation suite for the ArcGIS Documentation RAG
agent consisting of two files:

1. **`tests/e2e_queries.json`** — a structured 20-query corpus with 4 edge
   cases, each query tagged with `id`, `query`, `category`, `source_hint`,
   `expected_keywords` (list[str]), and `expected_url_pattern` (str).
2. **`backend/test_e2e_queries.py`** — 12 test functions following the
   existing `test_agent_flow.py` async pattern: corpus schema check,
   fail-hard prerequisites, relevance rate (≥80%), image inclusion (≥60%),
   source citation (100%), latency (mean <10s, max <15s), 4 edge-case
   handlers (gibberish, non-GIS, single-word, vague), an ARCRAG-18
   rate-limit smoke regression test, and a summary printer.

Key design decisions: **fail-hard** (not SKIP) when Qdrant is unreachable,
the collection is empty, or `OPENROUTER_API_KEY` is missing — this forces
VPS-only execution and prevents false "all green" reports from dev PC.
Rate-limit smoke is the only test that skips cleanly on dev PC (no public
HTTPS endpoint there).

## 2. Key Decisions & Rationale

### 2.1 Fail-hard on prerequisites (not SKIP)

**Decision**: `test_prerequisites_fail_hard` calls `sys.exit(1)` with a
clear error message if Qdrant is unreachable, the `arcgis_docs` collection
is empty, or `OPENROUTER_API_KEY` is missing/dummy.

**Rationale**: All existing live tests (`test_search.py`, `test_load_qdrant.py`,
`test_agent_flow.py`, `test_server.py`) use SKIP-on-unavailable. But E2E is
the final gate — a SKIP on a dev PC would create a false sense of "all
green" and potentially merge without ever having run on the VPS. Fail-hard
makes the absence of a live Qdrant + valid API key a loud failure that the
operator cannot ignore.

**Consequence**: The suite cannot run on a developer's PC. This is by design.
It runs exclusively on the VPS after ingestion (ARCRAG-15/16) and proxy
(ARCRAG-18) are operational.

### 2.2 Rate-limit smoke skips cleanly on dev PC (only exception)

**Decision**: `test_rate_limit_smoke` returns early with a printed "SKIP -
CADDY_DOMAIN not set" message when the env var is absent.

**Rationale**: Unlike the E2E execution tests, the rate-limit smoke needs an
HTTPS endpoint behind Caddy's rate limiter — which only exists on the VPS.
It cannot be exercised on a dev PC where there's no public domain and no
Caddy. The ARCRAG-18 report already documented this as "deferred to VPS run."
This single exception to the fail-hard policy is documented in the plan's
"Fail-hard vs skip policy" table.

### 2.3 Source citation regex broadened to cover `doc.esri.com`

**Decision**: The regex for source citation accuracy uses
`(?:[a-z0-9-]+\.)?(?:arcgis\.com|esri\.com)` instead of the plan's
`(pro|desktop)\.arcgis\.com`.

**Rationale**: The plan assumed ArcGIS Pro URLs live at `pro.arcgis.com`,
but the actual indexed URLs (from ARCRAG-15/16 ingestion) are at
`doc.esri.com/en/arcgis-pro/3.7/...`. ArcMap URLs are correctly at
`desktop.arcgis.com/en/arcmap/latest/...`. Broadening the regex to match
both `arcgis.com` and `esri.com` subdomains covers both sources without
false negatives. See Deviation §1 in the report.

### 2.4 Corpus at repo root (`tests/`) not `backend/`

**Decision**: `tests/e2e_queries.json` lives at repo root, not in `backend/`.

**Rationale**: Per the plan's Open Questions §1: "`tests/` is at repo root,
not `backend/` — keeps the corpus engine-agnostic and easy for non-engineers
to edit. Mirrors PRD §15 tech note verbatim."

### 2.5 Query categories use `source_hint` to differentiate

**Decision**: Pro tools and ArcMap tools share the `"tool_workflow"` category
but are differentiated by the `source_hint` field (`"arcpro"` vs `"arcmap"`).

**Rationale**: The plan's split mentions "Pro tools (5), ArcMap tools (3)"
but the schema example only shows one `category` value. Using `source_hint`
to differentiate is cleaner than creating redundant category values like
`pro_tool` and `arcmap_tool`. The actual counts match the plan exactly.

### 2.6 Single-word "buffer" edge case has lenient assertion

**Decision**: `test_edge_case_single_word` asserts "buffer is mentioned in
the response" and "**Source:** citation is present" — no requirement for
keyword hit count or specific tool documentation.

**Rationale**: Per the plan's Risk table: "Edge case 'buffer' (single word)
confuses the agent — test asserts 'coherent Buffer-related answer' (lenient);
if it fails, document as a known gap." The implementation follows this
precisely.

### 2.7 No new Python dependencies

**Decision**: The test file uses only stdlib + existing dependencies
(`httpx`, `dotenv`, `qdrant-client`, `pydantic-ai`).

**Rationale**: Per the plan's Open Questions §4. All dependencies are
already present in `pyproject.toml` from earlier stories. No `requirements.txt`
or `pyproject.toml` changes needed.

### 2.8 Manual review worksheet in the report (not a separate file)

**Decision**: The 20-row manual review table is embedded in the report
at `.agents/reports/arccrag-19-e2e-validation-report.md`.

**Rationale**: Per the plan's Open Questions §5: "Manual review worksheet is
a markdown table in the report, not a separate file (single source of truth,
easy to copy/paste into Jira)."

### 2.9 No app code, compose, or Caddyfile changes

**Decision**: Zero changes to `backend/src/`, `docker-compose*.yml`,
`deploy/Caddyfile`, or `frontend/`.

**Rationale**: The plan's "Files to Create/Update" table explicitly marks
these as "NO CHANGE — Out of scope." This is purely a test harness + runbook
story.

## 3. Errors & Roadblocks Encountered

### 3.1 Source citation regex mismatch with actual indexed URLs

**Error**: The plan specified `\[.+\]\(https?://(pro|desktop)\.arcgis\.com/...`
for source citation verification. But the actual indexed ArcGIS Pro URLs live
at `doc.esri.com/en/arcgis-pro/3.7/...` — not `pro.arcgis.com`.

**Resolution**: Broadened the regex to match both `arcgis.com` and
`esri.com` subdomains. Documented as Deviation §1 in the report and as
Decision §2.3 in this log.

**Root cause**: The plan was written before ARCRAG-15/16 detailed the
actual URL structure. The `doc.esri.com` domain was discovered during the
sitemap parsing (ARCRAG-05). This is a known gap in the plan's assumptions
about the index URL format.

### 3.2 `pnpm run build` is not applicable

**Issue**: The implementer's protocol says to run `pnpm run build` after each
task. This repo has no `pnpm` or `package.json` at root — it's a Python +
Docker project.

**Resolution**: Used the plan's own Validation Block commands instead:
`python3 -c "import json; json.load(open('tests/e2e_queries.json'))"` and
`python3 -m py_compile backend/test_e2e_queries.py`. These are the correct
static checks for this project.

### 3.3 No `tests/` directory existed at repo root

**Issue**: The plan notes "`tests/` directory does not exist at repo root"
in the Current State table.

**Resolution**: Created `tests/` as part of writing `tests/e2e_queries.json`.
The directory is trivial (no `__init__.py` needed — it's a JSON resource, not
a Python package).

### 3.4 Atlassian MCP / `gh` / `jira` not available

**Issue**: Same as ARCRAG-17/18 — no MCP tools, no `gh`, no `jira` CLI in
session. Cannot automate Jira transition + comment.

**Resolution**: Documented manual Jira steps. The operator will need to
transition and comment manually after VPS run.

## 4. Workarounds & Resolutions

| # | Issue | Workaround |
|---|-------|-----------|
| 1 | Plan regex assumes `pro.arcgis.com` but URLs are at `doc.esri.com` | Broadened regex to match both `arcgis.com` and `esri.com` subdomains (Decision §2.3) |
| 2 | `pnpm run build` N/A for this project | Used plan's own static checks (JSON parse + py_compile) |
| 3 | `tests/` directory didn't exist | Created it as part of writing the corpus file |
| 4 | No Atlassian MCP / Jira CLI | Documented manual Jira-update steps in the report's "Jira Update" section |

## 5. What Went Right & What Went Wrong

### 5.1 What Went Right

- **Plan adherence was high.** Every "Patterns to Follow" item was respected
  (async ad-hoc-script pattern from `test_search.py`, response-format regex
  from `test_agent_flow.py`, no-results branch check, ARCRAG-18 rate-limit
  smoke, manual review worksheet pattern from prior reports).
- **All 12 test functions from the plan exist and match the spec.** Function
  names, assertions, and thresholds are implemented exactly as documented
  in the plan's "`backend/test_e2e_queries.py` test functions" table.
- **Fail-hard gate works on dev PC.** Confirmed: missing `OPENROUTER_API_KEY`
  → exit 1 with clear message; Qdrant unreachable → exit 1 with clear
  message. The plan's core design intent is verified.
- **Corpus schema validated programmatically.** `test_corpus_schema()` checks
  all 20 queries + 4 edge cases have all required fields, types, and
  non-empty keyword lists.
- **Edge cases match the plan exactly.** E01 (gibberish), E02 (non-GIS),
  E03 (single-word), E04 (vague/broad) — all four are present with the
  exact queries from the plan.
- **No app code changes.** Zero risk of regression on runtime behavior.
- **Zero new dependencies.** All imports are from stdlib or existing deps.
- **Existing tests untouched.** `git diff --stat backend/test_*.py` shows
  zero changes to any existing test file.

### 5.2 What Went Wrong

- **Source citation regex had to be adapted** from the plan's `(pro|desktop).arcgis.com`
  to cover `doc.esri.com` URLs. This is a minor deviation reflecting that the
  plan was written before the full URL structure was known. The spirit of the
  test (esri.com-domain citations) is preserved.
- **Jira update could not be automated** (same as ARCRAG-17/18 — known
  environment limitation). Operator must transition + comment manually.
- **VPS validation is fully deferred.** Per plan, this is intentional, but it
  means the report's "Complete" status applies only to the dev-PC scope;
  the VPS scope remains an open task for the operator before merging.

## 6. Lessons Learned & Recommendations

### 6.1 Lessons Learned

1. **Fail-hard is better than SKIP for E2E gates.** The existing SKIP-on-
   unavailable pattern in 4/5 live tests was appropriate for unit-level
   checks but would have let a dev-PC "pass" through. For E2E, fail-hard
   makes the requirement to run on VPS undeniable. This pattern should be
   standard for any "final gate" tests in future phases.
2. **Source citation regex must match the actual index.** The plan assumed
   `pro.arcgis.com` URLs, but ARCRAG-15/16 ingested from `doc.esri.com`.
   Plans should verify URL domains before specifying regex patterns. A
   cross-reference between the plan and the actual data directory
   (`data/arcpro_urls.json`, `data/arcmap_urls.json`) would catch this.
3. **`source_hint` is a cleaner discriminator than separate categories.**
   Using a single `category` + `source_hint` makes schema validation
   simpler and avoids combinatorial explosion. It's also easier for
   non-engineers editing the JSON to understand.
4. **Embed the runbook + worksheet + placeholder results in the report.**
   This gives the operator a single document to work from during the VPS
   run. Prior reports did this; continuing the pattern is good practice.
5. **Existing tests are cheap regression insurance.** Running `git diff`
   against all existing test and source files after the implementation
   confirmed zero unintended changes. This is a good habit to continue.

### 6.2 Recommendations

1. **Operator must run the VPS runbook** (Steps 0-5 in the report) before
   merging. All 20 queries + 4 edge cases + rate-limit smoke must pass
   on the VPS for this story to be truly "Done."
2. **If `doc.esri.com` URLs change or are redirected in the future**, the
   regex in `CITATION_LINK_RE` may need updating. The current pattern
   (`(?:[a-z0-9-]+\.)?(?:arcgis\.com|esri\.com)`) is broad enough to
   cover foreseeable Esri documentation domains, but a future move to a
   different domain would require a regex update.
3. **Consider adding a `--vps` flag** to the test script that would
   automatically skip VPS-only tests on dev PC (currently, only the
   rate-limit smoke has this behavior; everything else fail-hards). This
   would make it easier for developers to run the corpus schema and
   structure validation locally without needing a VPS setup.
4. **Add the corpus schema validation as a pre-commit hook** or CI step
   to catch invalid `e2e_queries.json` edits early. The existing
   `test_corpus_schema()` function can be reused for this.
5. **For future E2E stories**, consider adding a `test_re_run` function
   that retries flaky queries once (with a configurable retry limit) to
   mitigate LLM non-determinism — as noted in the plan's Risk table.
6. **Document the `tests/` directory** in a future top-level README, so
   future contributors know it's the home for test resources that are
   engine-agnostic (JSON corpora, test configs, etc.).
