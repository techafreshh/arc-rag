# Plan: ARCRAG-19 — End-to-End Validation & Quality Check

## Summary

Add a Python E2E test harness (`backend/test_e2e_queries.py` + `tests/e2e_queries.json`) that runs 20 representative GIS queries through the deployed agent, asserting (1) keyword relevance, (2) markdown image inclusion, (3) source citation to a real `arcgis.com` URL, (4) <10s response time, and (5) graceful handling of gibberish/non-GIS edge cases. **Fail-hard** (not skip) when Qdrant is unreachable or empty — this forces VPS-only execution and prevents false "all green" on a dev PC. Includes the ARCRAG-18 rate-limit smoke test as a permanent regression check. The report ships with a **manual review worksheet** the operator fills in for subjective quality scoring. All work happens on a new `feature/arccrag-19-e2e-validation` branch per the established pattern.

## User Story

As a developer
I want a reusable E2E test suite that runs the deployed system against a corpus of representative GIS queries and reports on answer quality (relevance, images, source citations, latency, edge cases)
So that I can confidently say the MVP meets its success criteria before declaring it done.

## Metadata

| Field | Value |
|---|---|
| Type | NEW_CAPABILITY (test harness + runbook) |
| Complexity | MEDIUM |
| Systems Affected | `tests/e2e_queries.json` (new), `backend/test_e2e_queries.py` (new), `.agents/plans/`, `.agents/reports/`, `.agents/decisions/`, `.agents/stories/` |
| Jira Issue | ARCRAG-19 |
| Branch | `feature/arccrag-19-e2e-validation` |
| Blocked By | ARCRAG-15 ⏳ (VPS run pending), ARCRAG-16 ✅ (code complete), ARCRAG-18 ✅ (code complete) |
| Blocks | None (final story in Phase 4) |

---

## Current State (verified during planning)

| Artifact | State | Implication |
|----------|-------|-------------|
| `backend/test_*.py` (5 files) | `test_fetch.py`, `test_search.py`, `test_load_qdrant.py`, `test_agent_flow.py`, `test_server.py`, `test_prod_compose.py` | Established pattern: Python `asyncio` + ad-hoc scripts, no pytest, SKIP-on-unavailable in 4 of 5 live tests. **ARCRAG-19 deliberately deviates** with fail-hard (per user direction). |
| `data/arcpro_index.json` | Smoke-test only (5 pages) | Full ingestion pending ARCRAG-15 VPS run. |
| `data/arcmap_index.json` | Not present | ARCRAG-16 code complete; VPS run pending. |
| `data/arcpro_urls.json` | 16,419 URLs collected | URL corpus done. |
| `data/arcmap_urls.json` | ArcMap URL list | URL corpus done. |
| Qdrant `arcgis_docs` collection | Empty / not yet created on VPS | ARCRAG-19's fail-hard gate exits 1 on dev PC today (by design). |
| `backend/src/agent.py` | PydanticAI agent with 3 tools (`search_index`, `fetch_page`, `lookup_url`); system prompt enforces `**Source:** [title](url)` + `![alt](url)` | Test assertions align with prompt's contract. |
| `backend/src/main.py` | FastAPI `/health` + `/ag-ui` (AGUIAdapter.dispatch_request) | `/ag-ui` endpoint available for the rate-limit smoke (HTTPS path). |
| `deploy/Caddyfile` | Rate limit: `@api path /api/*`, default 20 req/min | Rate-limit smoke targets `https://$CADDY_DOMAIN/api/copilotkit`. |
| `.opencode/plans/` | Exists, empty | Will not use — repo convention is `.agents/plans/`. |
| `examples/` | In `.gitignore` line 27 | Will not use for the query corpus. |
| `tests/` directory | Does not exist at repo root | Will be created with `tests/e2e_queries.json`. |

---

## Patterns to Follow

### Existing test suite skeleton (mirror, with deliberate fail-hard deviation)
```python
# SOURCE: backend/test_search.py
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
from src.tools.search import search_index as _search_index
# ... async test_*() functions, each prints PASS/FAIL/SKIP
async def test():
    await test_one()
    await test_two()
    ...
if __name__ == "__main__":
    asyncio.run(test())
```

### `test_agent_flow.py` response-format checks (replicate the regex)
```python
# SOURCE: backend/test_agent_flow.py:95-105
assert "![" in output, "Response does not contain markdown image syntax"
assert "**Source:**" in output, "Response missing **Source:** citation"
link_re = re.compile(r"\[.+\]\(https?://[^\)]+\)")
assert link_re.search(output), "Response missing markdown link"
```

### `test_agent_flow.py` no-results branch check (replicate for gibberish)
```python
# SOURCE: backend/test_agent_flow.py:140-148
assert "**Source:**" not in output, "Agent fabricated a Source: citation for nonsense query"
assert not re.search(r"\]\(https?://(pro|desktop)\.arcgis\.com/", output), (
    "Agent fabricated an arcgis.com link for nonsense query"
)
```

### ARCRAG-18 runbook rate-limit smoke (lift into permanent test)
```bash
# SOURCE: ARCRAG-18 report §VPS-Side Runbook step 7
for i in $(seq 1 25); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST https://$CADDY_DOMAIN/api/copilotkit
done
# Expected: first ~20 return 200/4xx, remainder return 429
```

### Manual review worksheet pattern (from ARCRAG-15/16/18 reports)
A markdown table with per-row scoring columns; aggregated at the bottom. Operator fills in by hand during the VPS run.

---

## Files to Create/Update

| File | Action | Purpose |
|------|--------|---------|
| `tests/e2e_queries.json` | CREATE | 20-query corpus (PRD §15 tech note) with per-query `expected_keywords`, `expected_url_pattern`, `category`, `source_hint` |
| `backend/test_e2e_queries.py` | CREATE | Static + live test suite; fail-hard on missing Qdrant/key; structured manual-review hooks |
| `.agents/plans/arccrag-19-e2e-validation.plan.md` | CREATE | This plan |
| `.agents/reports/arccrag-19-e2e-validation-report.md` | CREATE (post-VPS-run) | Implementation report + manual review worksheet + VPS runbook |
| `.agents/decisions/arccrag-19-e2e-validation.md` | CREATE (post-VPS-run) | Decision log (fail-hard rationale, edge-case handling, etc.) |
| `.agents/stories/stories.md` | UPDATE | Mark ARCRAG-19 ✅ Completed with timestamp |
| `backend/test_*.py`, app code, compose files, `deploy/Caddyfile` | NO CHANGE | Out of scope |

---

## Test Suite Design

### `tests/e2e_queries.json` schema

```json
{
  "queries": [
    {
      "id": "Q01",
      "query": "How do I create a buffer in ArcGIS Pro?",
      "category": "tool_workflow",
      "source_hint": "arcpro",
      "expected_keywords": ["buffer", "input features", "distance", "output feature class"],
      "expected_url_pattern": "buffer.htm"
    }
  ],
  "edge_cases": [
    {"id": "E01", "query": "asdfgh", "category": "gibberish"},
    {"id": "E02", "query": "what's the weather today?", "category": "non_gis"},
    {"id": "E03", "query": "buffer", "category": "single_word"},
    {"id": "E04", "query": "How do I do spatial analysis?", "category": "vague_broad"}
  ]
}
```

**Query mix** (20 total): Pro tools (5), ArcMap tools (3), Pro workflows (4), ArcMap workflows (2), conceptual (3), comparison (2), ArcPy/code (1). Suggestion pills used as a reference for phrasing.

### `backend/test_e2e_queries.py` test functions

| # | Function | Asserts |
|---|---|---|
| 1 | `test_corpus_schema` | 20 queries + 4 edge cases; each query has `expected_keywords` (list[str]) and `expected_url_pattern` (str or null); all required fields present |
| 2 | `test_prerequisites_fail_hard` | Qdrant reachable, `arcgis_docs` collection non-empty, `OPENROUTER_API_KEY` set — **sys.exit(1) if any missing** |
| 3 | `test_relevance_rate` | For each of 20 queries, run `agent.run(q, timeout=30s)`, check ≥1 expected keyword in output; require ≥16/20 (80%) |
| 4 | `test_image_inclusion_rate` | For each successful query, check `!\[` in output; require ≥12/20 (60%) |
| 5 | `test_source_citation_accuracy` | For each successful query, check `**Source:**` + regex `\[.+\]\(https?://(pro\|desktop)\.arcgis\.com/...\)`; require 20/20 (100%) |
| 6 | `test_response_latency` | For each query, measure `time.monotonic()`; require mean <10s, max <15s |
| 7 | `test_edge_case_gibberish` | "asdfgh" → no `**Source:**`, no `(pro\|desktop).arcgis.com/` link, no fabricated ArcGIS URL |
| 8 | `test_edge_case_non_gis` | "what's the weather?" → agent declines or asks for GIS context |
| 9 | `test_edge_case_single_word` | "buffer" → returns a coherent Buffer-related answer |
| 10 | `test_edge_case_vague` | "How do I do spatial analysis?" → either clarifies or returns high-level answer without fabricating a page |
| 11 | `test_rate_limit_smoke` | **ARCRAG-18 chain** — 25 sequential POSTs to `https://$CADDY_DOMAIN/api/copilotkit`; assert first ~20 return non-429, remainder return 429. **Skipped (not failed)** on dev PC where no public HTTPS endpoint exists. |
| 12 | `test_summary` | Print results table to stdout for the report |

### Fail-hard vs skip policy (locked decision)

- **Qdrant unreachable OR `arcgis_docs` empty OR `OPENROUTER_API_KEY` missing → `sys.exit(1)`** with a clear message ("E2E tests require a populated Qdrant and a valid API key. Run on the VPS after ARCRAG-15/16 ingestion.").
- This is a **deliberate departure** from the skip-on-unavailable pattern in `test_search.py` / `test_load_qdrant.py` / `test_agent_flow.py` / `test_server.py`. Rationale: E2E is the final gate; a "SKIP" on dev PC would create a false sense of "all green".
- **Rate-limit smoke** is the only test that skips cleanly on dev PC (no public HTTPS endpoint there).

---

## Manual Review Worksheet (in the report)

```markdown
## Manual Review Worksheet

Reviewer: __________  Date: __________  VPS run timestamp: __________

| Query ID | Query (truncated) | Relevant (1-5) | Image helpful? | Source accurate? | Notes |
|---|---|---|---|---|---|
| Q01 | "How do I create a buffer..." | | | | |
| Q02 | ... | | | | |
... 20 rows ...
| **Average** | | ___/5 | __/20 yes | __/20 yes | |
```

Acceptance gate: average relevance ≥ 4.0/5.

---

## VPS Runbook (in the report)

```bash
# 0. On VPS, after ARCRAG-15/16/18 are confirmed running
cd /opt/arcpro-docs && git pull origin feature/arccrag-19-e2e-validation

# 1. Verify prerequisites
docker compose -f docker-compose.prod.yml ps        # all 4 services running
docker compose -f docker-compose.prod.yml exec backend wget -qO- http://qdrant:6333/collections/arcgis_docs
# Expect: > 0 points across both source:arcpro and source:arcmap

# 2. Run the E2E suite
cd backend && python3 test_e2e_queries.py
# Expect: 20/20 queries answered, ≥80% relevance, ≥60% images, 100% sources, <10s mean

# 3. Run the rate-limit smoke (requires $CADDY_DOMAIN to be set in env)
export CADDY_DOMAIN=arcgis-docs.your-domain.com
python3 -c "import asyncio; from backend.test_e2e_queries import test_rate_limit_smoke; asyncio.run(test_rate_limit_smoke())"
# Expect: first 20 requests 200/4xx, remainder 429

# 4. Manual review: open 20 queries in the browser, fill in the worksheet

# 5. Capture results, write report, update stories.md, merge
```

---

## Tasks (executed sequentially after plan approval)

1. Create branch `feature/arccrag-19-e2e-validation` from `main`
2. Author `tests/e2e_queries.json` with 20 diverse queries + 4 edge cases
3. Author `backend/test_e2e_queries.py` with the 12 test functions
4. Write the plan file (this file, already done)
5. Static validation: `python3 -c "import json; json.load(open('tests/e2e_queries.json'))"` and `python3 -m py_compile backend/test_e2e_queries.py`
6. Commit on the branch (no push, no PR per repo convention)
7. Write the report + decision log + update `stories.md` (post-VPS-run, but the report skeleton can be created now with the runbook + worksheet + placeholder for results)
8. Stop short of the VPS run itself (operator-driven, per ARCRAG-15/16/17/18 precedent)

---

## Validation Block

```bash
# After Tasks 1-5 (code complete, before commit)
cd /home/techafresh/projects/arcpro-docs

# Task 5a: corpus is valid JSON with required shape
python3 -c "
import json
data = json.load(open('tests/e2e_queries.json'))
assert len(data['queries']) == 20, f'Expected 20 queries, got {len(data[\"queries\"])}'
assert len(data['edge_cases']) == 4, f'Expected 4 edge cases, got {len(data[\"edge_cases\"])}'
for q in data['queries']:
    for k in ('id', 'query', 'category', 'expected_keywords', 'expected_url_pattern'):
        assert k in q, f'Missing key {k} in {q.get(\"id\", \"?\")}'
    assert isinstance(q['expected_keywords'], list)
print('OK: corpus schema valid')
"

# Task 5b: test file compiles
python3 -m py_compile backend/test_e2e_queries.py && echo "OK: test_e2e_queries.py compiles"

# Task 5c: pre-flight (dev PC) — fail-hard gate fires
cd backend && python3 test_e2e_queries.py
# Expected on dev PC: exit 1 with "Qdrant unreachable" or "arcgis_docs collection is empty" message
# This is the CORRECT behavior — it proves the fail-hard gate works.

# Task 5d (VPS only, deferred): full live run
# See VPS Runbook above
```

---

## Acceptance Criteria

- [ ] `tests/e2e_queries.json` exists with exactly 20 queries + 4 edge cases
- [ ] Each query has `id`, `query`, `category`, `expected_keywords` (list), `expected_url_pattern` (str or null)
- [ ] `backend/test_e2e_queries.py` exists and `python3 -m py_compile` succeeds
- [ ] On dev PC, `python3 backend/test_e2e_queries.py` exits 1 (fail-hard gate fires)
- [ ] On VPS (deferred), the suite reports 20/20 queries answered with the threshold check (≥80% relevance, ≥60% images, 100% sources, <10s mean latency)
- [ ] On VPS, edge cases (gibberish, non-GIS, single-word, vague) are handled without fabricated citations
- [ ] On VPS, rate-limit smoke: 21st POST to `/api/copilotkit` from same IP within a minute returns 429
- [ ] Manual review worksheet in the report is filled in with average relevance ≥ 4.0/5
- [ ] `.agents/reports/arccrag-19-*.md` and `.agents/decisions/arccrag-19-*.md` are written
- [ ] `.agents/stories/stories.md` marks ARCRAG-19 ✅ Completed with timestamp

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Qdrant is empty on VPS (ARCRAG-15 not yet run) → fail-hard exits | The fail-hard gate explicitly tells the operator to run after ARCRAG-15/16. Document in runbook. |
| 20-query corpus is a moving target as the index changes | Use the full index snapshot for the run; re-baseline expectations on each major ingest update |
| Subjective thresholds (80% relevance, 60% images) are hard to define objectively | Manual review worksheet provides the auditable "is this actually good?" check; the automated checks are the floor, not the ceiling |
| Rate-limit smoke test on dev PC silently passes (no Caddy in front) | Explicit SKIP message when `CADDY_DOMAIN` env var is unset |
| LLM non-determinism causes test flakiness | Run each query once, document the model + temperature in the report; consider adding a re-run capability if flakiness is observed |
| OPENROUTER_API_KEY leakage in CI logs | Use `dotenv` + env var; never print the key; existing `test_agent_flow.py` pattern |
| Test file takes >5 minutes on VPS (20 × ~10s + overhead) | Acceptable; operator runs once. Document expected runtime in runbook |
| Edge case "buffer" (single word) confuses the agent | Test asserts "coherent Buffer-related answer" (lenient); if it fails, document as a known gap and add to the system's edge-case handling backlog |

---

## Open Questions / Assumptions

1. **`tests/e` is at repo root, not `backend/`** — keeps the corpus engine-agnostic and easy for non-engineers to edit. Mirrors PRD §15 tech note verbatim.
2. **20 queries will be hand-crafted** to span: Pro tools (5), ArcMap tools (3), Pro workflows (4), ArcMap workflows (2), conceptual (3), comparison (2), ArcPy/code (1). Suggestion pills used as a reference for phrasing.
3. **The rate-limit smoke is the only test that can run on dev PC in a degraded form** (POST to `http://localhost:8000/api/copilotkit` from a test client, then send >20 more — the Caddy 429 won't fire on dev, so this is a SKIP unless `CADDY_DOMAIN` is set in env).
4. **No new dependencies** — pure stdlib + existing `httpx`, `pydantic-ai`, `dotenv`. Matches repo convention.
5. **Manual review worksheet is a markdown table in the report**, not a separate file (single source of truth, easy to copy/paste into Jira).
6. **No app code, compose, or Caddyfile changes** — this is purely a test harness + runbook story.
7. **VPS run is operator-driven** (per ARCRAG-15/16/17/18 precedent); the report is written with placeholder results and filled in post-run.
8. **The 4 created files in the repo (test, corpus, plan, report skeleton) are essentially a VPS operator's runbook in executable form.**
