# Plan: ARCRAG-08 — `search_index` Tool (Qdrant Semantic Search)

## Summary

Build the `search_index` agent tool that semantically searches the Qdrant index produced by ARCRAG-07, returning ranked documentation matches. Extract the embedding helper from `scripts/load_qdrant.py` into a shared `backend/src/embed.py` module so both ingestion and search use a single OpenRouter embedding client. Register the new tool in `backend/src/agent.py` and update the system prompt to prefer it over the hardcoded `lookup_url` map. Keep `lookup_url` available as a fallback. Follow the same async + Pydantic + env-var patterns established in `fetch.py` and `load_qdrant.py`.

## User Story

As a student
I want the agent to find the most relevant documentation pages for my question
So that it fetches the right content to answer me

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | Backend, Scripts (light refactor) |
| Jira Issue | ARCRAG-08 |
| Blocked By | ARCRAG-07 (completed) |
| Unblocks | ARCRAG-09 |

---

## Patterns to Follow

### Pydantic tool I/O models (from fetch.py)
```python
# SOURCE: backend/src/tools/fetch.py:11-27
class ImageInfo(BaseModel):
    url: str
    alt: str

class Section(BaseModel):
    heading: str
    content: str

class PageContent(BaseModel):
    url: str
    title: str
    sections: list[Section]
    images: list[ImageInfo]
    code_blocks: list[str]
    error: str | None = None
```

### Agent tool registration with @agent.tool decorator
```python
# SOURCE: backend/src/agent.py:29-60
@agent.tool
async def fetch_page(ctx: RunContext, url: str) -> str:
    """Fetch and parse an ArcGIS documentation page. ..."""
    result = await _fetch_page(url)
    ...

@agent.tool
async def lookup_url(ctx: RunContext, topic: str) -> str:
    """Look up the ArcGIS documentation URL for a given GIS topic ..."""
    result = _lookup_url(topic)
    ...
```

### OpenRouter embeddings via httpx (from load_qdrant.py)
```python
# SOURCE: scripts/load_qdrant.py:75-90
async def embed_batch(client: httpx.AsyncClient, texts: list[str]) -> list[list[float]]:
    resp = await client.post(
        OPENROUTER_EMBEDDINGS_URL,
        json={"input": texts, "model": EMBEDDING_MODEL},
        headers={"Authorization": f"Bearer {EMBEDDING_API_KEY}"},
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return [item["embedding"] for item in data["data"]]

async def detect_vector_size(client: httpx.AsyncClient) -> int:
    vectors = await embed_batch(client, ["dimension probe"])
    return len(vectors[0])
```

### Env var loading with fallback chain
```python
# SOURCE: scripts/load_qdrant.py:30-33
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "arcgis_docs")
```

### Qdrant client and search patterns (from qdrant-client docs)
- `QdrantClient(url=QDRANT_URL)` — connect
- `client.search(collection_name=..., query_vector=..., limit=..., query_filter=...)` — search
- `models.Filter(must=[models.FieldCondition(key="source", match=models.MatchValue(value="arcmap"))])` — metadata filter
- `models.PayloadIncludeItem` — restrict returned payload fields

### Async test pattern (from test_load_qdrant.py)
```python
# SOURCE: backend/test_load_qdrant.py:181-190
async def test():
    await test_import()
    await test_flatten()
    ...
    print("\n=== ALL TESTS PASSED ===")

if __name__ == "__main__":
    asyncio.run(test())
```

### Branch + commit convention
- Branch: `feature/arccrag-08-search-tool`
- Commit prefix: `feat:` (matches recent history)

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/src/embed.py` | CREATE | Shared OpenRouter embeddings client (extracted from `load_qdrant.py`) |
| `backend/src/tools/search.py` | CREATE | `search_index` tool: Pydantic models + Qdrant semantic search |
| `backend/src/agent.py` | EDIT | Register `search_index` tool; update system prompt to prefer it; keep `lookup_url` |
| `scripts/load_qdrant.py` | EDIT | Refactor to import from `backend.src.embed`; add `summary` to page-level payload |
| `scripts/__init__.py` | CREATE | Empty — allows `python -m scripts.load_qdrant` from `backend/` cwd |
| `backend/test_search.py` | CREATE | Validation: import, schema, source filter, conditional live search |
| `.agents/plans/completed/arccrag-08-search-tool.plan.md` | CREATE | This plan file |
| `.agents/reports/arccrag-08-search-tool-report.md` | CREATE | Implementation report (after merge) |
| `.agents/decisions/arccrag-08-search-tool.md` | CREATE | Postmortem decision log (after merge) |

---

## Tasks

### Task 1: Create `backend/src/embed.py` (shared embeddings client)

- **File**: `backend/src/embed.py`
- **Action**: CREATE
- **Implement**:
  - **Imports**: `os`; `httpx`; `dotenv.load_dotenv`
  - **Constants**:
    ```python
    load_dotenv()

    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
    EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"
    DEFAULT_TIMEOUT = 60.0
    ```
  - **Functions**:
    ```python
    async def embed_batch(client: httpx.AsyncClient, texts: list[str], model: str | None = None) -> list[list[float]]:
        """Embed a batch of texts via OpenRouter. Returns a list of vectors in the same order as input."""
        used_model = model or EMBEDDING_MODEL
        resp = await client.post(
            OPENROUTER_EMBEDDINGS_URL,
            json={"input": texts, "model": used_model},
            headers={"Authorization": f"Bearer {EMBEDDING_API_KEY}"},
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]

    async def embed_query(client: httpx.AsyncClient, text: str, model: str | None = None) -> list[float]:
        """Embed a single text. Returns one vector."""
        vectors = await embed_batch(client, [text], model=model)
        return vectors[0]
    ```
  - **Mirror**: `scripts/load_qdrant.py:75-90` (the `embed_batch` body is identical; `detect_vector_size` is moved out since it's only used by `load_qdrant.py`)
  - **Validate**: `uv run --directory backend python -c "from src.embed import EMBEDDING_MODEL, embed_batch, embed_query; print('OK - embed.py imports')"`

### Task 2: Refactor `scripts/load_qdrant.py` to use `embed.py`

- **File**: `scripts/load_qdrant.py`
- **Action**: EDIT
- **Implement**:
  - **Remove**: local definitions of `EMBEDDING_MODEL`, `EMBEDDING_API_KEY`, `OPENROUTER_EMBEDDINGS_URL`
  - **Add import** at top:
    ```python
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    from src.embed import EMBEDDING_MODEL, EMBEDDING_API_KEY, OPENROUTER_EMBEDDINGS_URL, embed_batch
    ```
    (The `sys.path` shim is needed because `load_qdrant.py` runs as a script, not as a module. The shim only runs when the script is executed directly.)
  - **Keep** local `QDRANT_URL` / `QDRANT_COLLECTION` constants (load_qdrant-specific)
  - **Keep** local `detect_vector_size` (load_qdrant-specific)
  - **Add `summary` to page-level payload** (one-line addition to `flatten_entries`):
    ```python
    "payload": {
        "url": page["url"],
        "title": title,
        "summary": summary,    # <-- NEW
        "section": "",
        ...
    }
    ```
  - **Validate**: `uv run --directory backend python -c "import importlib.util; spec = importlib.util.spec_from_file_location('load_qdrant', 'scripts/load_qdrant.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('OK - load_qdrant still imports')"`

### Task 3: Create `scripts/__init__.py`

- **File**: `scripts/__init__.py`
- **Action**: CREATE
- **Implement**: Empty file (allows `python -m scripts.load_qdrant` and `import scripts.load_qdrant` if needed in future)
- **Validate**: `ls scripts/__init__.py` shows the file exists

### Task 4: Create `backend/src/tools/search.py`

- **File**: `backend/src/tools/search.py`
- **Action**: CREATE
- **Implement**:
  - **Imports**: `os`; `httpx`; `qdrant_client.QdrantClient`; `qdrant_client.models` (Filter, FieldCondition, MatchValue, PayloadIncludeItem); `dotenv.load_dotenv`; `pydantic.BaseModel`
  - **Env vars** (with same fallback chain):
    ```python
    load_dotenv()

    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
    EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
    QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "arcgis_docs")

    DEFAULT_TOP_K = 5
    MAX_TOP_K = 20
    DEFAULT_MIN_SCORE = 0.0
    ```
  - **Pydantic models**:
    ```python
    class SearchResult(BaseModel):
        url: str
        title: str
        section: str
        summary: str
        breadcrumb: list[str]
        source: str
        score: float

    class SearchResults(BaseModel):
        results: list[SearchResult]
        error: str | None = None
    ```
  - **Source detection** (keyword-based per design decision):
    ```python
    ARCMAP_KEYWORDS = {"arcmap", "arc map", "arc-map"}

    def detect_source_filter(query: str) -> str | None:
        """Return 'arcmap' if the query mentions ArcMap, else None (no filter)."""
        lowered = query.lower()
        if any(kw in lowered for kw in ARCMAP_KEYWORDS):
            return "arcmap"
        return None
    ```
  - **URL deduplication** (a page and its sections share a URL — keep best score):
    ```python
    def dedupe_by_url(results: list[SearchResult]) -> list[SearchResult]:
        seen: dict[str, SearchResult] = {}
        for r in results:
            existing = seen.get(r.url)
            if existing is None or r.score > existing.score:
                seen[r.url] = r
        return sorted(seen.values(), key=lambda x: x.score, reverse=True)
    ```
  - **Main async function**:
    ```python
    async def search_index(
        query: str,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = DEFAULT_MIN_SCORE,
        source_filter: str | None = None,
    ) -> SearchResults:
        """Embed the query, search Qdrant, return top-K results deduped by URL.

        Args:
            query: Student's natural-language question.
            top_k: Max results to return (1-20, default 5).
            min_score: Minimum cosine similarity score (0.0-1.0, default 0.0).
            source_filter: Optional source filter ('arcpro' or 'arcmap'). If None, auto-detected from query.

        Returns:
            SearchResults with results list and optional error string.
        """
        if not query or not query.strip():
            return SearchResults(results=[], error="Empty query")

        top_k = max(1, min(MAX_TOP_K, top_k))

        if not EMBEDDING_API_KEY:
            return SearchResults(results=[], error="EMBEDDING_API_KEY or OPENROUTER_API_KEY not set")

        if source_filter is None:
            source_filter = detect_source_filter(query)

        try:
            qdrant = QdrantClient(url=QDRANT_URL)
            qdrant.get_collections()
        except Exception as e:
            return SearchResults(results=[], error=f"Qdrant unreachable at {QDRANT_URL}: {e}")

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                vector = await embed_query(client, query)
        except Exception as e:
            return SearchResults(results=[], error=f"Embedding failed: {e}")

        try:
            search_filter = None
            if source_filter:
                search_filter = Filter(must=[FieldCondition(key="source", match=MatchValue(value=source_filter))])

            hits = qdrant.search(
                collection_name=QDRANT_COLLECTION,
                query_vector=vector,
                limit=top_k * 2,
                score_threshold=min_score,
                query_filter=search_filter,
                with_payload=True,
            )
        except Exception as e:
            return SearchResults(results=[], error=f"Qdrant search failed: {e}")

        results = [
            SearchResult(
                url=h.payload.get("url", ""),
                title=h.payload.get("title", ""),
                section=h.payload.get("section", "") or "",
                summary=h.payload.get("summary", "") or h.payload.get("section", "") or h.payload.get("title", ""),
                breadcrumb=h.payload.get("breadcrumb", []),
                source=h.payload.get("source", ""),
                score=float(h.score),
            )
            for h in hits
        ]

        deduped = dedupe_by_url(results)[:top_k]
        return SearchResults(results=deduped)
    ```
  - **Mirror**: `backend/src/tools/fetch.py` (Pydantic + async pattern); `scripts/load_qdrant.py` (env vars + httpx pattern)
  - **Validate**: `uv run --directory backend python -c "from src.tools.search import SearchResult, SearchResults, search_index, detect_source_filter; print('OK - search.py imports')"`

### Task 5: Register `search_index` in `backend/src/agent.py` and update prompt

- **File**: `backend/src/agent.py`
- **Action**: EDIT
- **Implement**:
  - **Add import**:
    ```python
    from src.tools.search import SearchResults, search_index as _search_index
    ```
  - **Add `@agent.tool` registration** (after `lookup_url`):
    ```python
    @agent.tool
    async def search_index(ctx: RunContext, query: str, top_k: int = 5) -> str:
        """Search the ArcGIS documentation index for pages matching a student's question. Returns ranked results with URLs, titles, summaries, and relevance scores. Use this FIRST when a student asks about an ArcGIS tool, workflow, or concept — then call fetch_page on the best 1-2 URLs to get the full content. Pass the student's original question as the query."""
        result = await _search_index(query, top_k=top_k)
        if result.error:
            return f"Search error: {result.error}"
        if not result.results:
            return "No relevant documentation found for that query."
        parts = [f"Found {len(result.results)} relevant documentation pages:"]
        for i, r in enumerate(result.results, 1):
            heading = f" — {r.section}" if r.section else ""
            parts.append(f"{i}. [{r.title}{heading}]({r.url}) (source: {r.source}, score: {r.score:.2f})")
            if r.summary:
                parts.append(f"   {r.summary[:200]}")
        return "\n".join(parts)
    ```
  - **Update system prompt** to prefer `search_index` over `lookup_url`:
    ```python
    instructions=(
        "You are a GIS documentation assistant helping students learn ArcGIS Pro and ArcMap. "
        "Answer questions clearly and concisely, using technical terminology appropriate for "
        "GIS students. "
        "When asked about a specific ArcGIS tool or concept: call search_index with the student's "
        "question first to find the most relevant documentation pages, then call fetch_page on the "
        "best 1-2 URLs to get the full content. "
        "You may also call lookup_url for quick lookups of well-known tool names, but prefer "
        "search_index for any non-trivial question. "
        "Always include relevant images from the fetched page using markdown ![alt](url) syntax. "
        "Always end responses with a source citation: **Source:** [Page Title](url). "
        "If search_index returns no relevant results, tell the student you don't have "
        "documentation on that topic. If you are unsure about something, say so rather than guessing."
    ),
    ```
- **Validate**: `uv run --directory backend python -c "from src.agent import agent; tools = [t.name for t in agent.tools]; print(f'Tools: {tools}'); assert 'search_index' in tools, 'search_index not registered'; assert 'fetch_page' in tools; assert 'lookup_url' in tools; print('OK - search_index registered, lookup_url and fetch_page preserved')"`

### Task 6: Create `backend/test_search.py`

- **File**: `backend/test_search.py`
- **Action**: CREATE
- **Implement** (mirrors `test_load_qdrant.py` structure):
  ```python
  import asyncio
  import os
  from pathlib import Path
  from dotenv import load_dotenv

  load_dotenv()

  from src.tools.search import (
      SearchResult, SearchResults, search_index,
      detect_source_filter, dedupe_by_url, DEFAULT_TOP_K, MAX_TOP_K,
  )

  async def test_import():
      print("--- Test 1: Import check ---")
      assert callable(search_index)
      assert callable(detect_source_filter)
      assert callable(dedupe_by_url)
      assert DEFAULT_TOP_K == 5
      assert MAX_TOP_K == 20
      print("PASS - module imports cleanly, constants set")

  async def test_models():
      print("\n--- Test 2: Pydantic model schema ---")
      r = SearchResult(
          url="https://example.com", title="Test", section="",
          summary="A summary", breadcrumb=["a", "b"],
          source="arcpro", score=0.85,
      )
      assert r.url == "https://example.com"
      assert r.score == 0.85
      s = SearchResults(results=[r])
      assert s.error is None
      assert len(s.results) == 1
      print("PASS - SearchResult and SearchResults schemas valid")

  async def test_source_detection():
      print("\n--- Test 3: Source keyword detection ---")
      assert detect_source_filter("How do I create a buffer in ArcMap?") == "arcmap"
      assert detect_source_filter("arcmap georeferencing") == "arcmap"
      assert detect_source_filter("Arc Map tutorial") == "arcmap"
      assert detect_source_filter("How do I create a buffer in ArcGIS Pro?") is None
      assert detect_source_filter("What is a geodatabase?") is None
      assert detect_source_filter("") is None
      print("PASS - detect_source_filter works for all cases")

  async def test_dedupe():
      print("\n--- Test 4: URL deduplication ---")
      r1 = SearchResult(url="https://a", title="A", section="", summary="", breadcrumb=[], source="arcpro", score=0.9)
      r2 = SearchResult(url="https://a", title="A", section="intro", summary="intro sec", breadcrumb=[], source="arcpro", score=0.7)
      r3 = SearchResult(url="https://b", title="B", section="", summary="", breadcrumb=[], source="arcpro", score=0.8)
      deduped = dedupe_by_url([r1, r2, r3])
      assert len(deduped) == 2
      assert deduped[0].url == "https://a"
      assert deduped[0].score == 0.9
      assert deduped[1].url == "https://b"
      print("PASS - dedupe_by_url keeps best score per URL")

  async def test_empty_query():
      print("\n--- Test 5: Empty query handling ---")
      result = await search_index("")
      assert result.error is not None
      assert "Empty" in result.error
      assert result.results == []
      print("PASS - empty query returns graceful error")

  async def test_qdrant_unreachable():
      print("\n--- Test 6: Qdrant unreachable handling ---")
      result = await search_index("test", top_k=3)
      if result.error and "Qdrant" in result.error:
          print(f"PASS - Qdrant unreachable error: {result.error}")
      else:
          print("SKIP - Qdrant is reachable, can't test unreachable path")

  async def test_live_search():
      print("\n--- Test 7: Live search (conditional) ---")
      api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
      qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
      if not api_key:
          print("SKIP - no API key set")
          return
      from qdrant_client import QdrantClient
      try:
          q = QdrantClient(url=qdrant_url)
          q.get_collections()
      except Exception:
          print("SKIP - Qdrant not reachable")
          return

      from src.tools.search import search_index as si
      r = await si("buffer", top_k=3)
      assert r.error is None, f"Search error: {r.error}"
      print(f"  Query 'buffer' -> {len(r.results)} results")
      for res in r.results:
          print(f"    {res.score:.3f} {res.title} ({res.source}) -> {res.url[:60]}...")
      assert len(r.results) > 0, "Expected at least 1 result for 'buffer'"

      r2 = await si("buffer in ArcMap", top_k=3)
      print(f"  Query 'buffer in ArcMap' -> {len(r2.results)} results (source filter: {detect_source_filter('buffer in ArcMap')})")
      assert r2.error is None
      print("PASS - live search returns results for 'buffer' and 'buffer in ArcMap'")

  async def test():
      await test_import()
      await test_models()
      await test_source_detection()
      await test_dedupe()
      await test_empty_query()
      await test_qdrant_unreachable()
      await test_live_search()
      print("\n=== ALL TESTS PASSED ===")

  if __name__ == "__main__":
      asyncio.run(test())
  ```
- **Mirror**: `backend/test_load_qdrant.py:1-190` (async test pattern, print-based reporting, conditional live test)
- **Validate**: `uv run --directory backend python test_search.py` (most tests will pass; live test gracefully skips if Qdrant unavailable)

### Task 7: Validate end-to-end

- **Action**: RUN
- **Validate**:
  ```bash
  # 1. Module imports
  uv run --directory backend python -c "from src.tools.search import search_index, SearchResults; print('OK')"

  # 2. Agent registers the tool
  uv run --directory backend python -c "
  from src.agent import agent
  tool_names = [t.name for t in agent.tools]
  print(f'Agent tools: {tool_names}')
  assert 'search_index' in tool_names
  assert 'fetch_page' in tool_names
  assert 'lookup_url' in tool_names
  print('OK')
  "

  # 3. Unit tests
  uv run --directory backend python test_search.py

  # 4. E2E agent query (uses real search_index + fetch_page flow — requires Qdrant + API key)
  uv run --directory backend python test_e2e.py
  ```

### Task 8: Commit and merge

- **Action**: GIT
- **Implement**:
  ```bash
  cd /home/techafresh/projects/arcpro-docs
  git checkout -b feature/arccrag-08-search-tool
  git add backend/src/embed.py backend/src/tools/search.py backend/src/agent.py backend/test_search.py scripts/load_qdrant.py scripts/__init__.py .agents/plans/completed/arccrag-08-search-tool.plan.md
  git commit -m "feat: add ARCRAG-08 search_index tool for Qdrant semantic search

- Extract shared OpenRouter embeddings client into backend/src/embed.py
- Add search_index tool: embed query, search Qdrant, return ranked results
- Add URL deduplication and ArcMap keyword-based source filter
- Register search_index in agent and update system prompt to prefer it
- Refactor load_qdrant.py to use shared embed.py + add summary to page payload
- Add test_search.py with import, schema, source detection, dedupe, and conditional live tests"
  git checkout main
  git merge --no-ff feature/arccrag-08-search-tool
  git branch -d feature/arccrag-08-search-tool
  ```
- **Validate**: `git log -3 --oneline` shows new commit on main

---

## Validation

```bash
cd /home/techafresh/projects/arcpro-docs

# Module imports (read-only)
uv run --directory backend python -c "from src.embed import embed_batch, embed_query; from src.tools.search import search_index, SearchResults; print('OK')"

# Agent tools registered
uv run --directory backend python -c "
from src.agent import agent
names = [t.name for t in agent.tools]
print(names)
assert all(n in names for n in ['search_index', 'fetch_page', 'lookup_url'])
print('OK')
"

# load_qdrant.py still works after refactor
uv run --directory backend python -c "import importlib.util; spec = importlib.util.spec_from_file_location('load_qdrant', 'scripts/load_qdrant.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('OK - load_qdrant still imports')"

# Unit tests
uv run --directory backend python test_search.py

# Live tests (require Qdrant + API key)
docker compose up -d
uv run --directory backend python test_search.py    # Tests 1-6 always pass; Test 7 conditional
uv run --directory backend python test_e2e.py       # Existing E2E still works (uses lookup_url + fetch_page)

# Full CLI run (manual check)
uv run --directory backend python -m src.agent
# Then ask: "What is the Buffer tool?" — should now use search_index -> fetch_page flow
```

---

## Acceptance Criteria

- [ ] `backend/src/embed.py` exists with `embed_batch` and `embed_query` functions
- [ ] `backend/src/tools/search.py` exists with `search_index`, `SearchResult`, `SearchResults` models
- [ ] Query is embedded via the same OpenRouter model used at ingest time (`EMBEDDING_MODEL`)
- [ ] Top-K results (default 5, max 20) returned with URL, title, summary, breadcrumb, source, score
- [ ] Query containing "ArcMap" (or "Arc Map") applies a Qdrant filter `source="arcmap"`
- [ ] Exact tool name query ("Buffer") returns the matching page in top 3 (live test, conditional)
- [ ] Results are deduplicated by URL (page-level + section-level entries collapsed, best score kept)
- [ ] Qdrant unreachable -> returns `SearchResults(results=[], error="...")` with a clear message
- [ ] Empty query -> returns `SearchResults(results=[], error="Empty query")`
- [ ] `search_index` tool is registered in `backend/src/agent.py`
- [ ] System prompt updated to prefer `search_index` over `lookup_url`
- [ ] `lookup_url` is preserved (not removed) for known-tool shortcut
- [ ] `scripts/load_qdrant.py` refactored to use `src.embed` and add `summary` to page-level payload
- [ ] `scripts/__init__.py` created (empty)
- [ ] `backend/test_search.py` passes (Tests 1-6 always, Test 7 conditional)
- [ ] No comments in code (per global rule)
- [ ] Plan file written to `.agents/plans/completed/arccrag-08-search-tool.plan.md`
- [ ] Report and decision log written after merge

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `load_qdrant.py` refactor breaks existing ingestion | Add `sys.path` shim at top; keep all function bodies intact; re-run `test_load_qdrant.py` to confirm |
| Query embedding drift (different model than ingest) | Use same `EMBEDDING_MODEL` env var; document the requirement prominently in the tool's docstring |
| Section-level entries dilute results (same URL, multiple hits) | `dedupe_by_url` keeps best score; surface `section` in result for the agent to cite |
| Empty index (no data ingested yet) | Live test (Test 7) handles this gracefully; tool returns empty results without crashing |
| Source keyword filter too aggressive (e.g., user says "ArcMap and ArcGIS Pro") | Keep arcmap-only filter only when query exclusively mentions ArcMap; consider weakening to "score boost" in a future iteration if false-negatives appear |
| `summary` field in result is empty for old ingested data (pre-refactor) | Tool falls back to `section` then `title`; full summary population requires re-ingestion (ARCRAG-15) |
| `lookup_url` becomes dead code / agent ignores it | Kept for known-tool shortcut; ARCRAG-09 will refine the prompt ordering further |
| `qdrant_client` API drift (different SDK version than load_qdrant.py) | Use the same `qdrant-client` package version; same Qdrant v1.12.1 instance via docker-compose |
| Test 7 (live) requires Docker + API key — not always available | Conditional skip pattern (matches `test_load_qdrant.py`); Tests 1-6 always pass |
| `httpx` `AsyncClient` instantiation per call adds latency | Acceptable for low QPS agent; could be optimized in a future story with a shared client |

---

## Out of Scope (Deferred)

- **Hybrid search (BM25 + dense)** — story notes this as future work
- **Score threshold tuning** — `min_score` param provided but no default recommendation yet
- **Re-ingestion with full `summary` population** — requires ARCRAG-15 (Full ArcGIS Pro Index Ingestion)
- **Agent "no good results" handling** — ARCRAG-09 (Agent Search -> Fetch -> Answer Flow)
- **Per-tool keyword boost** — e.g., if query contains "Buffer", boost Buffer page results
- **Pagination / streaming of results** — top-K only for now
- **Shared `httpx.AsyncClient` lifecycle management** — fresh client per call is fine at this scale
