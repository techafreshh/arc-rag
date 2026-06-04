# Plan: ARCRAG-09 — Agent Search → Fetch → Answer Flow

## Summary

Tighten the agent's system prompt to mandate the `search_index` → `fetch_page` → answer flow (no `lookup_url` mention), and add a new `test_agent_flow.py` plus an expanded 10-query quality test in `test_search.py` to validate the flow end-to-end, including groundedness, no-results handling, and ≥8/10 hit rate on diverse GIS questions.

## User Story

> As a student, I want to ask any GIS question and have the agent automatically search the index, fetch the relevant page, and generate an answer, so that I get accurate documentation-grounded responses.

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (agent orchestration + test coverage) |
| Complexity | LOW |
| Systems Affected | `backend/src/agent.py`, `backend/test_search.py`, new `backend/test_agent_flow.py` |
| Jira Issue | ARCRAG-09 |
| Blocked By | ARCRAG-08 ✅, ARCRAG-03 ✅ |

---

## Decisions Locked In

- **`lookup_url`**: Prompt mention **removed entirely**; tool stays registered in `tools/lookup.py` for emergency/explicit use. (No code change to `lookup.py` or its import in `agent.py`.)
- **Test file**: New `backend/test_agent_flow.py`; existing `test_e2e.py` (ARCRAG-04) untouched.
- **Groundedness check**: Yes — assert response mentions ≥2 real Buffer-doc terms.

---

## Patterns to Follow

### Tool registration (no change needed)
```python
# SOURCE: backend/src/agent.py:33-81
@agent.tool
async def search_index(ctx: RunContext, query: str, top_k: int = 5) -> str:
    """Search the ArcGIS documentation index for pages matching a student's question..."""
    result = await _search_index(query, top_k=top_k)
    if result.error:
        return f"Search error: {result.error}"
```

### Graceful error pattern in tools
```python
# SOURCE: backend/src/tools/search.py:63-65
if not query or not query.strip():
    return SearchResults(results=[], error="Empty query")
```

### Conditional live-test skip pattern
```python
# SOURCE: backend/test_search.py:82-108
api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
if not api_key:
    print("SKIP - no API key set")
    return
```

### Agent run + result access
```python
# SOURCE: backend/test_e2e.py:19-27
result = await asyncio.wait_for(agent.run("..."), timeout=30.0)
output = result.output if hasattr(result, "output") else str(result)
# For tool-call order: result.all_messages() exposes the full transcript
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/src/agent.py` | UPDATE | Replace `instructions=` string per Task 1; no other changes |
| `backend/test_agent_flow.py` | CREATE | New E2E test (4 cases): tool order, response format, groundedness, no-results |
| `backend/test_search.py` | UPDATE | Expand `test_live_search` to 10 queries; report hit rate; assert ≥8/10 |

---

## Tasks

### Task 1: Tighten system prompt

- **File**: `backend/src/agent.py`
- **Action**: UPDATE (replace `instructions=` argument on lines 16-29 only)
- **New prompt**:
  ```
  You are a GIS documentation assistant helping students learn ArcGIS Pro and ArcMap. 
  Answer questions clearly and concisely, using technical terminology appropriate for 
  GIS students. 
  Always start by calling search_index with the student's question to find the most 
  relevant documentation pages, then call fetch_page on the best 1-2 URLs to get the 
  full content. 
  If fetch_page returns an error, try the next result or tell the student the page is 
  unavailable. 
  If search_index returns no results or all scores are very low, do not invent a page — 
  tell the student no documentation was found for that topic. 
  Always include relevant images from the fetched page using markdown ![alt](url) syntax. 
  Always end responses with a source citation: **Source:** [Page Title](url). 
  If you are unsure about something, say so rather than guessing.
  ```
- **Mirror**: `backend/src/agent.py:14-30` (replace existing string in place)
- **Validate**: `python -c "from src.agent import agent"` — must import cleanly; the 3 `@agent.tool`-decorated functions (`search_index`, `fetch_page`, `lookup_url`) stay registered

### Task 2: Create `test_agent_flow.py`

- **File**: `backend/test_agent_flow.py`
- **Action**: CREATE
- **Header**: same as `test_search.py` — `from dotenv import load_dotenv; load_dotenv()`, then imports, then `async def test(): ...` and `if __name__ == "__main__": asyncio.run(test())`
- **Skip predicate** (used by all 4 tests):
  ```python
  def _skip_no_key():
      key = os.getenv("OPENROUTER_API_KEY", "")
      if not key or key == "dummy":
          print("SKIP - OPENROUTER_API_KEY missing or 'dummy'")
          return True
      return False
  ```
- **Test 1 — `test_tool_call_order()`**:
  - Query: `"How do I create a buffer in ArcGIS Pro?"`
  - Run `agent.run(...)` with 60s timeout
  - Use `result.all_messages()` (fallback: scan `str(result)`) to confirm a `search_index` call appears **before** any `fetch_page` call
  - Assert the order; print tool call sequence
  - Skip via `_skip_no_key()`
- **Test 2 — `test_response_format()`**:
  - Same query as Test 1
  - Assert `output` contains `![`, `**Source:**`, and a markdown link matching `\[.+\]\(https?://[^\)]+\)`
  - Skip via `_skip_no_key()`
- **Test 3 — `test_groundedness()`**:
  - Same query as Test 1
  - Assert `output.lower()` contains ≥2 of: `{"buffer", "distance", "feature class", "input features", "output feature class", "dissolve", "side type", "planar", "geodesic"}`
  - Skip via `_skip_no_key()` **and** if Qdrant unreachable (the agent can only ground if search/fetch worked)
- **Test 4 — `test_no_results_branch()`**:
  - Query: `"asdfghjkl quantum GIS dance routine"` (deliberately gibberish + off-topic)
  - Assert response does **not** contain `**Source:**` (no fabricated URL) and does **not** contain a markdown link to `pro.arcgis.com` or `desktop.arcgis.com`
  - Skip via `_skip_no_key()`
- **Mirror**: `backend/test_search.py:14-30` (test function shape), `backend/test_e2e.py:14-37` (agent.run wrapper)
- **Validate**: `python backend/test_agent_flow.py` — expected to print `SKIP` for each test in this env (dummy API key + no Qdrant); passes by exiting cleanly

### Task 3: Expand `test_live_search` to 10 queries

- **File**: `backend/test_search.py`
- **Action**: UPDATE (only the body of `test_live_search`, lines 82-108)
- **New body** (replaces the 2-query block):
  ```python
  QUERY_KEYWORDS = [
      ("How do I create a buffer in ArcGIS Pro?", "buffer"),
      ("How do I clip features?", "clip"),
      ("What is the Intersect tool?", "intersect"),
      ("What is a geodatabase?", "geodatabase"),
      ("How do I use ArcPy?", "arcpy"),
      ("How do I georeference in ArcMap?", "georeference"),
      ("How do I create a buffer in ArcMap?", "buffer"),
      ("How do I merge datasets?", "merge"),
      ("How to use ModelBuilder?", "modelbuilder"),
      ("What is a shapefile?", "shapefile"),
  ]

  hits = 0
  total = len(QUERY_KEYWORDS)
  for query, kw in QUERY_KEYWORDS:
      r = await si(query, top_k=3)
      if r.error:
          print(f"  SKIP {query!r}: {r.error}")
          continue
      if r.results and kw.lower() in r.results[0].title.lower() + r.results[0].url.lower():
          hits += 1
          print(f"  HIT  {query!r} -> {r.results[0].title}")
      else:
          top = r.results[0].title if r.results else "(no results)"
          print(f"  MISS {query!r} -> {top}")

  print(f"  Hit rate: {hits}/{total}")
  assert hits >= 8, f"Expected >= 8/10 hits, got {hits}/{total}"
  ```
- **Keep**: The existing skip block at top of `test_live_search` (no API key / no Qdrant → SKIP)
- **Validate**: `python backend/test_search.py` — skips in this env; ready to validate hit rate in deployed env

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| E2E tests need real LLM (slow, costly, non-deterministic) | All 4 tests in `test_agent_flow.py` skip when `OPENROUTER_API_KEY` missing or `"dummy"` — same pattern as `test_e2e.py` |
| PydanticAI `result.all_messages()` API surface may differ by version | Verify against installed `pydantic-ai` before Task 2; if unavailable, fall back to `str(result)` and regex for tool names |
| Hit-rate test depends on index completeness (not fully ingested yet) | Test is informational — prints ratio, only fails below 8/10. Ingesting is ARCRAG-15/16 |
| Removing `lookup_url` mention from prompt doesn't prevent agent from calling it | True — but the prompt now steers the model; this is the requested behavior |
| 10-query test is sequential (~30-60s with LLM + Qdrant round-trips) | Acceptable for a smoke test; document expected runtime in test header |
| Groundedness keyword set is Buffer-specific | Reasonable for v1; the test is parameterized on query, so future tests can add other tools' keyword sets |

---

## Out of Scope

- Removing the `lookup_url` tool itself (only the prompt mention)
- Lint/typecheck infrastructure (separate concern, flagged in ARCRAG-08)
- FastAPI server (ARCRAG-10)
- Search ranking quality improvements (separate story)
- Full index ingestion (ARCRAG-15/16)

---

## Validation

```bash
# Smoke: agent + tools still import cleanly
python -c "from src.agent import agent; from src.tools.search import search_index; from src.tools.fetch import fetch_page; print('ok')"

# New agent-flow tests (skips in this env; runs in real env)
python backend/test_agent_flow.py

# Expanded search quality test (skips in this env; runs in real env)
python backend/test_search.py

# Existing E2E test (should still pass — ARCRAG-04 path)
python backend/test_e2e.py
```

No lint/typecheck infrastructure exists in this project (per ARCRAG-08 postmortem).

---

## Acceptance Criteria (from `stories.md:259-265`)

- [ ] AC1: Agent calls `search_index` first, then `fetch_page` on top result, then answers (verified via `result.all_messages()`)
- [ ] AC2: Answer includes content from the fetched page (not hallucinated) — groundedness keyword check passes
- [ ] AC3: Answer includes markdown image references and source citation
- [ ] AC4: No/low-score results → agent states no documentation found, no fabricated URL
- [ ] AC5: 10 diverse GIS questions → ≥8/10 hit the correct documentation page in top result
