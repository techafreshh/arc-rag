# Implementation Report

**Plan**: `.agents/plans/arccrag-09-agent-search-fetch-answer-flow.plan.md`
**Branch**: `feature/arccrag-09-agent-search-fetch-answer-flow`
**Status**: COMPLETE

## Summary

Tightened the agent's system prompt to mandate the `search_index` → `fetch_page` → answer flow (no `lookup_url` mention in the prompt), and added a new `test_agent_flow.py` with 4 E2E tests plus an expanded 10-query quality test in `test_search.py` to validate the flow end-to-end, including groundedness, no-results handling, and ≥8/10 hit rate on diverse GIS questions.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Tighten system prompt — remove `lookup_url` mention; add "no-results → don't invent" branch | `backend/src/agent.py` | ✅ |
| 2 | Create new E2E test file with 4 tests (tool order, response format, groundedness, no-results) | `backend/test_agent_flow.py` | ✅ |
| 3 | Expand `test_live_search` from 2 to 10 queries with hit-rate assertion (≥8/10) | `backend/test_search.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `python -c "from src.agent import agent; from src.tools.search import search_index; from src.tools.fetch import fetch_page; print('ok')"` | ✅ `ok` |
| All 3 tools registered (`search_index`, `fetch_page`, `lookup_url`) | ✅ verified via `agent.toolsets[0].tools.keys()` |
| `python backend/test_search.py` | ✅ Tests 1–6 PASS, Test 7 SKIP (Qdrant unreachable, expected in this env) |
| `python backend/test_agent_flow.py` | ✅ All 4 tests SKIP cleanly (dummy `OPENROUTER_API_KEY`, expected) |
| `python backend/test_e2e.py` | ⚠️ Pre-existing 401 (dummy key in `.env`); confirmed pre-existing on main, unrelated to ARCRAG-09 |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `backend/src/agent.py` | UPDATE | +8/-7 |
| `backend/test_agent_flow.py` | CREATE | +160 |
| `backend/test_search.py` | UPDATE | +31/-10 |

## Deviations from Plan

None. The plan was implemented exactly as specified:

- **Task 1**: The new prompt text matches the plan verbatim (no `lookup_url` mention, with the new "if scores are very low, do not invent" branch). The `lookup_url` tool remains registered via `@agent.tool` (per the locked decision).
- **Task 2**: `test_agent_flow.py` follows the plan structure — `_skip_no_key()` helper, 4 async tests in the order specified, same `dotenv` + `asyncio.run` footer as `test_search.py`. A small helper `_qdrant_reachable()` was added for Test 3 (the plan said "skip if Qdrant unreachable" — implemented by attempting a low-cost `search_index("test")` call). Tool-order parsing uses `result.all_messages()` (verified available on pydantic-ai 1.104.0's `AgentRunResult`) with a `str(result)` regex fallback.
- **Task 3**: The new `QUERY_KEYWORDS` block in `test_search.py` matches the plan exactly (10 entries, hit counter, ≥8/10 assertion). The pre-existing skip block (no API key / no Qdrant) is preserved verbatim.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `backend/test_agent_flow.py` | `test_tool_call_order` — verifies `search_index` called before `fetch_page` via `result.all_messages()`<br>`test_response_format` — asserts `![`, `**Source:**`, and a markdown link `[…](http…)` in the output<br>`test_groundedness` — asserts ≥2 of 9 Buffer-doc terms (`buffer`, `distance`, `feature class`, `input features`, `output feature class`, `dissolve`, `side type`, `planar`, `geodesic`) appear in the response; SKIPs if Qdrant unreachable<br>`test_no_results_branch` — gibberish query; asserts no `**Source:**` and no `pro.arcgis.com` / `desktop.arcgis.com` link |
| `backend/test_search.py` (`test_live_search`) | 10 diverse GIS queries (buffer Pro, clip, intersect, geodatabase, ArcPy, georeference ArcMap, buffer ArcMap, merge, ModelBuilder, shapefile); reports HIT/MISS/SKIP per query; asserts ≥8/10 hit rate |

## Notes for Deployment

- The 4 tests in `test_agent_flow.py` and the 10-query test in `test_search.py` SKIP locally because `OPENROUTER_API_KEY=dummy` in `backend/.env` and Qdrant is not running. Run them in a real environment (real API key + Qdrant with ≥8/10 of the listed pages ingested) to validate the full flow end-to-end.
- The 10-query hit rate depends on index completeness — flagged in the plan as ARCRAG-15/16 (ingestion is out of scope here).
- Tool-call-order parsing via `result.all_messages()` is robust in pydantic-ai 1.104.0; the `str(result)` regex fallback handles the case where the API surface differs.
