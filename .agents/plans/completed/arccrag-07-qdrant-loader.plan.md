# Plan: ARCRAG-07 — Qdrant Loader Script (Embed & Upsert)

## Summary

Create `scripts/load_qdrant.py` — the third step of the ARCRAG ingestion pipeline. The script consumes the structured JSON index produced by ARCRAG-06 (`data/arcpro_index.json`, `data/arcmap_index.json`), flattens each page into page-level and section-level entries, generates vector embeddings via the OpenRouter embeddings API (OpenAI-compatible `/v1/embeddings` endpoint, using `httpx` directly), and upserts them into a Qdrant collection. Follows the same `SOURCES`/`argparse`/repo-root-anchoring patterns as `parse_sitemaps.py` and `build_index.py`. Supports `--recreate` (drop + recreate collection), `--dry-run` (preview without API calls), and `--source` to select which index to load.

## User Story

As a developer
I want a script that generates embeddings for index entries and upserts them into Qdrant
So that the search_index tool can query them

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | Scripts, Data |
| Jira Issue | ARCRAG-07 |
| Blocked By | ARCRAG-06 (completed) |

---

## Patterns to Follow

### Repo-root anchoring
```python
# SOURCE: scripts/build_index.py:11-14
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
(PROJECT_DIR / "data").mkdir(exist_ok=True)
```

### SOURCES dict (configuration registry)
```python
# SOURCE: scripts/build_index.py:16-29
SOURCES = {
    "arcpro": {
        "index_json": str(PROJECT_DIR / "data/arcpro_index.json"),
        "source": "arcpro",
    },
    "arcmap": {
        "index_json": str(PROJECT_DIR / "data/arcmap_index.json"),
        "source": "arcmap",
    },
}
```

### Argparse CLI with choices
```python
# SOURCE: scripts/build_index.py:209-216
def main():
    parser = argparse.ArgumentParser(description="...")
    parser.add_argument("--source", required=True, choices=["arcpro", "arcmap"])
    ...
    args = parser.parse_args()
    asyncio.run(build_index(args.source, ...))
```

### Env var loading with defaults
```python
# SOURCE: backend/src/agent.py:9-11
load_dotenv()
model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
```

### Async httpx for API calls
```python
# SOURCE: scripts/build_index.py:32-41
async def fetch_html(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        resp = await client.get(url)
    except Exception as e:
        print(f" FAILED: {e}", flush=True)
        return None
    if resp.status_code != 200:
        print(f" HTTP {resp.status_code}", flush=True)
        return None
    return resp.text
```

### Pydantic models for structured data
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
    ...
```

### Index JSON entry schema (input format)
```python
# SOURCE: data/arcpro_index.json (produced by build_index.py)
{
    "url": "https://doc.esri.com/en/arcgis-pro/...",
    "source": "arcpro",
    "title": "Box",
    "summary": "",
    "breadcrumb": ["arcgis-pro", "arcpy", "charts", "box.html"],
    "sections": [{"heading": "Summary", "level": 2, "brief_text": "..."}],
    "images": [{"url": "https://...", "alt": "..."}],
    "scraped_at": "2026-06-04T..."
}
```

### Branch + commit convention
- Branch: `feature/arccrag-07-qdrant-loader`
- Commit prefix: `feat:` (matches recent history)

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `scripts/load_qdrant.py` | CREATE | Embed index entries and upsert into Qdrant collection |
| `backend/test_load_qdrant.py` | CREATE | Validation: dry-run, schema check, embed+upsert subset |
| `.agents/plans/completed/arccrag-07-qdrant-loader.plan.md` | CREATE | This plan file (moved on completion) |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Create load_qdrant.py with config, flattener, embedder, and Qdrant upserter

- **File**: `scripts/load_qdrant.py`
- **Action**: CREATE
- **Implement**:
  - **Imports**: `argparse`, `asyncio`, `json`, `os`, `sys` from stdlib; `httpx`; `qdrant_client.QdrantClient`; `qdrant_client.models` (PointStruct, VectorParams, Distance, CollectionParams); `pathlib.Path`; `dotenv.load_dotenv`
  - **Constants & config**:
    ```python
    SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_DIR = SCRIPT_DIR.parent
    (PROJECT_DIR / "data").mkdir(exist_ok=True)

    load_dotenv()

    SOURCES = {
        "arcpro": {
            "index_json": str(PROJECT_DIR / "data/arcpro_index.json"),
            "source": "arcpro",
        },
        "arcmap": {
            "index_json": str(PROJECT_DIR / "data/arcmap_index.json"),
            "source": "arcmap",
        },
    }

    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
    EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
    QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "arcgis_docs")
    OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"
    ```
  - **Entry flattener** — converts each index page dict into page-level + section-level entry dicts:
    ```python
    def flatten_entries(pages: list[dict]) -> list[dict]:
        entries = []
        for page in pages:
            title = page["title"]
            summary = page.get("summary", "")
            # Page-level entry
            if title:
                embed_text = f"{title} - {summary}".strip(" -")
                entries.append({
                    "embed_text": embed_text,
                    "payload": {
                        "url": page["url"],
                        "title": title,
                        "section": "",
                        "breadcrumb": page.get("breadcrumb", []),
                        "source": page["source"],
                        "type": "page",
                        "images": page.get("images", []),
                    },
                })
            # Section-level entries
            for sec in page.get("sections", []):
                heading = sec["heading"]
                brief = sec.get("brief_text", "")
                embed_text = f"{title} > {heading} - {brief}".strip(" -")
                entries.append({
                    "embed_text": embed_text,
                    "payload": {
                        "url": page["url"],
                        "title": title,
                        "section": heading,
                        "breadcrumb": page.get("breadcrumb", []),
                        "source": page["source"],
                        "type": "section",
                        "images": page.get("images", []),
                    },
                })
        return entries
    ```
  - **Embedding function** — calls OpenRouter's `/v1/embeddings` endpoint (OpenAI-compatible) via httpx:
    ```python
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
    ```
  - **Vector size detection** — embed a single text first, measure the dimension:
    ```python
    async def detect_vector_size(client: httpx.AsyncClient) -> int:
        vectors = await embed_batch(client, ["dimension probe"])
        return len(vectors[0])
    ```
  - **Qdrant setup** — create or recreate collection:
    ```python
    def setup_collection(client: QdrantClient, collection_name: str, vector_size: int, recreate: bool):
        if recreate:
            if client.collection_exists(collection_name):
                client.delete_collection(collection_name)
                print(f"Deleted existing collection: {collection_name}")
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            print(f"Created collection: {collection_name} (dim={vector_size})")
        else:
            if client.collection_exists(collection_name):
                print(f"Collection {collection_name} already exists")
                return
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            print(f"Created collection: {collection_name} (dim={vector_size})")
    ```
  - **Main orchestrator** — `load_qdrant(source, recreate, dry_run, batch_size)`:
    - Load index JSON from `SOURCES[source]["index_json"]`
    - Flatten entries via `flatten_entries()`
    - If `--dry-run`: print first 5 entries and stats, return
    - Connect to Qdrant via `QdrantClient(url=QDRANT_URL)`
    - Detect vector size by embedding a probe text
    - Setup collection (create or recreate)
    - Batch entries in groups of `batch_size` (default 100)
    - For each batch: embed via `embed_batch()`, create `PointStruct` list with sequential IDs, upsert via `client.upsert()`
    - Print progress every batch
    - Final summary: total upserted, collection count
  - **CLI**:
    ```python
    def main():
        parser = argparse.ArgumentParser(description="Load documentation index into Qdrant with embeddings")
        parser.add_argument("--source", required=True, choices=["arcpro", "arcmap"])
        parser.add_argument("--recreate", action="store_true", help="Drop and recreate the collection")
        parser.add_argument("--dry-run", action="store_true", help="Show what would be upserted without calling APIs")
        parser.add_argument("--batch-size", type=int, default=100, help="Embedding/upsert batch size")
        args = parser.parse_args()
        asyncio.run(load_qdrant(args.source, args.recreate, args.dry_run, args.batch_size))
    ```
- **Mirror**: `scripts/build_index.py:11-216` (SOURCES, argparse, async orchestrator, repo-root anchoring); `backend/src/tools/fetch.py:30-38` (async httpx pattern)
- **Validate**: `uv run --directory backend python -c "import importlib.util; spec = importlib.util.spec_from_file_location('load_qdrant', 'scripts/load_qdrant.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('OK - load_qdrant imports'); print(f'SOURCES: {list(m.SOURCES.keys())}')"` 

### Task 2: Validate dry-run mode

- **File**: `(none — run directly)`
- **Action**: RUN
- **Implement**:
  - Run `--dry-run --source arcpro` to verify the script reads the index, flattens entries, and prints stats without calling any APIs
  - Expected output: entry counts (page-level vs section-level), first 5 entries preview, no HTTP calls
- **Validate**: `uv run --directory backend python scripts/load_qdrant.py --source arcpro --dry-run`

### Task 3: Validate embed + upsert with subset

- **File**: `(none — run directly)`
- **Action**: RUN
- **Implement**:
  - Requires: Qdrant running (`docker compose up -d`), `EMBEDDING_API_KEY` or `OPENROUTER_API_KEY` set in `.env`
  - Run with `--source arcpro --recreate` (the current index has only 5 entries, so this is already a subset)
  - Verify: collection created, points upserted, `qdrant_client.count()` returns expected count
  - Then run again WITHOUT `--recreate` — verify it prints "already exists" and appends (or use `--dry-run` to skip)
- **Validate**:
  ```bash
  uv run --directory backend python scripts/load_qdrant.py --source arcpro --recreate
  # Should print: Created collection, 5 pages + N sections upserted
  ```

### Task 4: Write test_load_qdrant.py

- **File**: `backend/test_load_qdrant.py`
- **Action**: CREATE
- **Implement**:
  - Follow the `test_fetch.py` / `test_e2e.py` pattern: `async def test()` + `asyncio.run()` + `__main__`
  - Test 1: Import check — verify module loads, SOURCES dict has expected keys
  - Test 2: Flatten check — load a sample index entry, call `flatten_entries()`, assert page-level and section-level entries are produced with correct `embed_text` format
  - Test 3: Dry-run check — run the script with `--dry-run`, capture output, assert it mentions entry counts
  - Test 4 (conditional): If `OPENROUTER_API_KEY` is set and Qdrant is running, do a live embed+upsert of 2 entries and verify collection count
- **Mirror**: `backend/test_fetch.py:1-20` (async test pattern, assertions, print-based reporting)
- **Validate**: `uv run --directory backend python test_load_qdrant.py`

### Task 5: Commit and merge

- **Action**: GIT
- **Implement**:
  ```bash
  cd /home/techafresh/projects/arcpro-docs
  git checkout -b feature/arccrag-07-qdrant-loader
  git add scripts/load_qdrant.py backend/test_load_qdrant.py .agents/plans/completed/arccrag-07-qdrant-loader.plan.md
  git commit -m "feat: add ARCRAG-07 Qdrant loader script for embedding and upserting index entries"
  git checkout main
  git merge --no-ff feature/arccrag-07-qdrant-loader
  git branch -d feature/arccrag-07-qdrant-loader
  ```
- **Validate**: `git log -3 --oneline` shows new commit on main

---

## Validation

```bash
# Module import check (read-only)
cd /home/techafresh/projects/arcpro-docs
uv run --directory backend python -c "
import importlib.util
spec = importlib.util.spec_from_file_location('load_qdrant', 'scripts/load_qdrant.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print('OK - load_qdrant module imports cleanly')
print(f'SOURCES: {list(m.SOURCES.keys())}')
print(f'EMBEDDING_MODEL: {m.EMBEDDING_MODEL}')
print(f'QDRANT_URL: {m.QDRANT_URL}')
"

# Flatten check
uv run --directory backend python -c "
import json, importlib.util
spec = importlib.util.spec_from_file_location('load_qdrant', 'scripts/load_qdrant.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
data = json.load(open('data/arcpro_index.json'))
entries = m.flatten_entries(data)
pages = [e for e in entries if e['payload']['type'] == 'page']
sections = [e for e in entries if e['payload']['type'] == 'section']
print(f'Total entries: {len(entries)} ({len(pages)} pages, {len(sections)} sections)')
assert len(pages) > 0, 'No page entries'
assert all(e['embed_text'] for e in entries), 'Empty embed_text'
assert all(e['payload']['url'] for e in entries), 'Missing url in payload'
print('PASS - flatten schema OK')
"

# Dry-run check
uv run --directory backend python scripts/load_qdrant.py --source arcpro --dry-run

# Live embed + upsert (requires Qdrant + API key)
docker compose up -d
uv run --directory backend python scripts/load_qdrant.py --source arcpro --recreate

# Test file
uv run --directory backend python test_load_qdrant.py

# Full runs (deferred — run when ready for full index)
# uv run --directory backend python scripts/load_qdrant.py --source arcpro --recreate
# uv run --directory backend python scripts/load_qdrant.py --source arcmap
```

---

## Acceptance Criteria

- [ ] `scripts/load_qdrant.py` exists with `--source arcpro|arcmap`, `--recreate`, `--dry-run`, `--batch-size` CLI flags
- [ ] Page-level entries embedded as `"{title} - {summary}"`
- [ ] Section-level entries embedded as `"{title} > {heading} - {brief_text}"`
- [ ] Qdrant collection `arcgis_docs` created with cosine distance and auto-detected vector dimensions
- [ ] Payload includes: `url`, `title`, `section`, `breadcrumb`, `source`, `type`, `images`
- [ ] Embedding calls batched at 100 texts per request (configurable via `--batch-size`)
- [ ] `--recreate` drops and recreates the collection
- [ ] `--dry-run` prints entry stats and first 5 entries without API calls
- [ ] Env vars: `EMBEDDING_MODEL`, `EMBEDDING_API_KEY` (falls back to `OPENROUTER_API_KEY`), `QDRANT_URL`, `QDRANT_COLLECTION`
- [ ] `backend/test_load_qdrant.py` passes
- [ ] No comments in code (per global rule)
- [ ] Plan file written to `.agents/plans/completed/arccrag-07-qdrant-loader.plan.md`

---

### Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| OpenRouter embeddings API rate limiting on large batches | Configurable `--batch-size`; default 100 matches the story spec; add delay between batches if needed |
| `EMBEDDING_API_KEY` not set (falls back to `OPENROUTER_API_KEY` which is for chat) | Both may use the same key on OpenRouter; fallback chain is `EMBEDDING_API_KEY` → `OPENROUTER_API_KEY`; fail with clear error if neither set |
| Vector dimension mismatch between runs (different embedding models) | `--recreate` flag forces fresh collection; detect dimension from first embedding call; document that changing `EMBEDDING_MODEL` requires `--recreate` |
| `openai` SDK is transitive (through `pydantic-ai`), not direct | Use `httpx` directly for embeddings API (already a direct dependency); avoids fragile transitive dependency |
| Qdrant not running when script executes | `QdrantClient` will raise a connection error; document `docker compose up -d` as prerequisite |
| Empty titles in some index entries | `flatten_entries()` skips page-level entry if title is empty (section entries still created since they use parent title) |