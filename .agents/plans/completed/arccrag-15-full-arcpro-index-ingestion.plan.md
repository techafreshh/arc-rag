# Plan: ARCRAG-15 — Full ArcGIS Pro Index Ingestion (Init Container Pattern)

## Summary

Replace the manual `tmux` ingestion workflow with a Docker Compose **init container pattern**: a new one-shot `arcrag-init` service runs `build_index.py` then `load_qdrant.py` to fully populate the `arcgis_docs` Qdrant collection from the 16,419 ArcGIS Pro URLs already collected in `data/arcpro_urls.json`. A new `backend` service (FastAPI) uses `depends_on: { arcrag-init: { condition: service_completed_successfully } }` so it only starts after the index is loaded. Pre-flight hardening: add 429 retry to `build_index.py` (gap flagged in ARCRAG-06's decision log, will surface at scale) and add a "Zonal Statistics as Table" obscure-tool test to `test_search.py` (called out in ARCRAG-15's acceptance criteria). Persistent `data/` and `qdrant_data` volumes preserve the checkpoint so re-runs are resumable. A single `docker compose up` becomes the canonical full-stack deploy.

## User Story

As a developer
I want the full ArcGIS Pro documentation index to be ingested into Qdrant automatically when the system starts
So that `docker compose up` produces a fully-populated system without manual tmux/screen sessions, and re-runs can resume from the existing checkpoint

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (operational + script hardening) |
| Complexity | HIGH |
| Systems Affected | `scripts/`, `backend/`, `docker-compose.yml`, data persistence, `test_search.py` |
| Jira Issue | ARCRAG-15 |
| Blocked By | ARCRAG-07 ✅, ARCRAG-09 ✅ |

---

## Current State (verified during planning)

| Artifact | State | Implication |
|----------|-------|-------------|
| `data/arcpro_urls.json` | 16,419 URLs (from `doc.esri.com/en/arcgis-pro/3.7/`) | URL collection done (ARCRAG-05). No re-run needed. |
| `data/.checkpoint_arcpro_urls.json` | 16,419 URLs, 2 done sitemaps | Resumable. |
| `data/arcpro_index.json` | 5 pages (smoke test only) | Needs full re-run. |
| `data/.checkpoint_arcpro_index.json` | 5 done, 0 failed, 5 pages | Will be overwritten by full run. |
| Qdrant collection `arcgis_docs` | Unknown — likely empty/absent | Will be created on `--recreate` first run. |
| `backend/Dockerfile` | Does not exist | Must be created. |
| `docker-compose.yml` | Qdrant-only | Must be extended. |
| `scripts/build_index.py` | Production-ready except for 429 retry (ARCRAG-06 lesson) | Add 429 retry. |
| `scripts/load_qdrant.py` | Production-ready, has `--recreate` and `--dry-run` | No change. |
| `backend/test_search.py` | 8/10 hit-rate test exists | Add Zonal Statistics as Table test. |

---

## Patterns to Follow

### SOURCES dict + repo-root anchoring (mirrors all scripts)
```python
# SOURCE: scripts/load_qdrant.py:13-20
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
(PROJECT_DIR / "data").mkdir(exist_ok=True)
load_dotenv()
```

### Checkpoint load/save with backward-compat
```python
# SOURCE: scripts/build_index.py:143-158
def load_checkpoint(path: str) -> tuple[set[str], list[dict], set[str]]:
    p = Path(path)
    if not p.exists():
        return set(), [], set()
    data = json.loads(p.read_text())
    if isinstance(data, dict):
        return set(data.get("done_urls", [])), data.get("pages", []), set(data.get("failed_urls", []))
    return set(), [], set()
```

### Async fetch with bounded concurrency
```python
# SOURCE: scripts/build_index.py:179-202
semaphore = asyncio.Semaphore(concurrency)
async def process(url: str):
    async with semaphore:
        html = await fetch_html(client, url)
        await asyncio.sleep(delay)
        ...
async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
    await asyncio.gather(*(process(u) for u in remaining))
```

### Qdrant collection setup with auto-detect dimensions
```python
# SOURCE: scripts/load_qdrant.py:76-99
async def detect_vector_size(client: httpx.AsyncClient) -> int:
    vectors = await embed_batch(client, ["dimension probe"])
    return len(vectors[0])
```

### Conditional live-search test pattern
```python
# SOURCE: backend/test_search.py:82-127
async def test_live_search():
    if not api_key: print("SKIP - no API key set"); return
    ...
    assert hits >= 8, f"Expected >= 8/10 hits, got {hits}/{total}"
```

### TTLCache for fetch deduplication (apply to build_index if 429 retry)
```python
# SOURCE: backend/src/tools/fetch.py:8
_cache: TTLCache = TTLCache(maxsize=100, ttl=300)
```

### Existing Qdrant Compose service
```yaml
# SOURCE: docker-compose.yml:1-13
services:
  qdrant:
    image: qdrant/qdrant:v1.12.1
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    environment:
      - QDRANT__SERVICE__GRPC_PORT=6334

volumes:
  qdrant_data:
```

### Standard Python Dockerfile pattern (no existing pattern in repo)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir <deps>
COPY . .
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose healthcheck + depends_on with condition (standard pattern)
```yaml
services:
  arcrag-init:
    restart: "no"
  backend:
    depends_on:
      arcrag-init:
        condition: service_completed_successfully
      qdrant:
        condition: service_healthy
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/Dockerfile` | CREATE | Python 3.11 slim image; installs deps; copies `backend/src/`, `scripts/`, `data/`; CMD runs uvicorn |
| `scripts/init.sh` | CREATE | Init container entrypoint: waits for Qdrant, runs `build_index.py` then `load_qdrant.py --recreate`, exits 0 |
| `docker-compose.yml` | UPDATE | Add `arcrag-init` (one-shot) and `backend` services; add Qdrant healthcheck; add named volume `arcrag_data` for `/app/data` |
| `scripts/build_index.py` | UPDATE | Add bounded 429-retry loop in `fetch_html` (1 retry with 5s backoff) — ARCRAG-06 lesson |
| `backend/test_search.py` | UPDATE | Add `test_obscure_tool_zonal_statistics()` — calls search for "Zonal Statistics as Table" and asserts the result is in top 5 |
| `.agents/reports/arccrag-15-full-arcpro-index-ingestion-report.md` | CREATE (post-run) | Implementation report (created after run completes) |
| `.agents/decisions/arccrag-15-full-arcpro-index-ingestion.md` | CREATE (post-run) | Decision log (created after run completes) |
| `.agents/stories/stories.md` | UPDATE (post-run) | Mark ARCRAG-15 ✅ Completed, add run timestamp + vector count to summary table |

---

## Tasks

Execute in order. Each task is atomic and verifiable. Tasks 1-5 are <1h of work; Task 6 is the long-running run.

### Task 1: Add 429 retry to `build_index.py`

- **File**: `scripts/build_index.py`
- **Action**: UPDATE
- **Implement**:
  - Modify `fetch_html` (line 32-41) to check `resp.status_code == 429` and retry once after a 5s sleep; re-fetch on retry
  - Mirror the simple retry style of `scripts/parse_sitemaps.py:38-50` (which already has retry for network errors)
- **Mirror**: `scripts/parse_sitemaps.py:38-50` for retry-with-sleep pattern
- **Avoid**: Do not add exponential backoff or jitter — keep it simple per ARCRAG-06's "minimal match the spec" pattern
- **Validate**: `cd backend && uv run python -c "import importlib.util, sys; spec=importlib.util.spec_from_file_location('bi', '../scripts/build_index.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('OK')"`

### Task 2: Create `backend/Dockerfile`

- **File**: `backend/Dockerfile`
- **Action**: CREATE
- **Implement**: Single-stage image
  - Base: `python:3.11-slim`
  - `WORKDIR /app`
  - `RUN pip install --no-cache-dir "pydantic-ai[openrouter]" fastapi uvicorn httpx beautifulsoup4 qdrant-client python-dotenv cachetools`
  - Copy `backend/src/`, `scripts/`, `data/`
  - Do NOT COPY `.env` — use `env_file` in docker-compose
  - `EXPOSE 8000`
  - `CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]`
- **Validate**: `docker build -t arcrag-backend -f backend/Dockerfile .` succeeds

### Task 3: Create `scripts/init.sh` (init container entrypoint)

- **File**: `scripts/init.sh`
- **Action**: CREATE
- **Implement**: Bash script with `set -e`
  - Wait for Qdrant healthcheck (poll `wget -q -O- "$QDRANT_URL/health"` for `"status":"green"`)
  - If `arcgis_docs` collection has points, skip ingestion and exit 0 (idempotency)
  - Otherwise, run `python /app/scripts/build_index.py --source arcpro --concurrency 5 --delay 0.2`
  - Then run `python /app/scripts/load_qdrant.py --source arcpro --recreate --batch-size 100`
  - `chmod +x scripts/init.sh`
- **Mirror**: Standard Docker entrypoint pattern (no existing in repo)
- **Avoid**: Do not put secrets in script; rely on env vars passed by `docker-compose.yml`
- **Validate**: `docker compose run --rm arcrag-init sh -c "head -5 /app/scripts/init.sh && echo OK"`

### Task 4: Extend `docker-compose.yml`

- **File**: `docker-compose.yml`
- **Action**: UPDATE
- **Implement**:
  - Add Qdrant healthcheck (`test: ["CMD", "wget", "-q", "--spider", "http://localhost:6333/health"]`, `interval: 5s`, `retries: 10`)
  - Add `arcrag-init` service: build from `backend/Dockerfile`, `command: ["/app/scripts/init.sh"]`, `restart: "no"`, `env_file: backend/.env`, `volumes: [arcrag_data:/app/data]`
  - Add `backend` service: build from `backend/Dockerfile`, `depends_on: { qdrant: { condition: service_healthy }, arcrag-init: { condition: service_completed_successfully } }`, `ports: ["8000:8000"]`, `env_file: backend/.env`, `volumes: [arcrag_data:/app/data]`
  - Add volume `arcrag_data:` alongside `qdrant_data:`
- **Mirror**: Existing `qdrant` service in `docker-compose.yml:1-13`
- **Validate**: `docker compose config` parses without error

### Task 5: Add obscure-tool test to `test_search.py`

- **File**: `backend/test_search.py`
- **Action**: UPDATE
- **Implement**: Add `test_obscure_tool_zonal_statistics()` to the test module
  - Add `("What is Zonal Statistics as Table?", "zonal statistics as table")` to `QUERY_KEYWORDS`
  - Add a separate `test_obscure_tool()` that calls `search_index("Zonal Statistics as Table", top_k=5)` and asserts the top-5 results contain a URL ending in `zonal-statistics-as-table.htm` (or has "Zonal Statistics" in title)
  - Acceptance criterion: "search for obscure tools (e.g., 'Zonal Statistics as Table'), then the correct page appears in top 5 results"
- **Mirror**: `test_live_search` block at `backend/test_search.py:82-127`
- **Validate**: `cd backend && uv run python test_search.py` passes (when Qdrant is populated)

### Task 6: Pre-flight smoke test (5 min)

- **Action**: VALIDATE
- **Implement**:
  - `docker compose up -d qdrant` (just Qdrant)
  - `docker compose run --rm arcrag-init sh -c "python /app/scripts/build_index.py --source arcpro --limit 5 --concurrency 2 --delay 0.5 && python /app/scripts/load_qdrant.py --source arcpro --recreate --batch-size 100"`
  - Verify: `wget -qO- http://localhost:6333/collections/arcgis_docs | python3 -c "import json,sys; print(json.load(sys.stdin))"`
  - Verify: `cd backend && uv run python test_search.py` shows the 5-page test passes
- **Validate**: Qdrant shows the collection, 5 pages * (1 page entry + ~10 section entries) ≈ 55 points
- **Why**: Confirms the Dockerfile, init.sh, and docker-compose wiring work end-to-end at small scale before the 8-24h full run

### Task 7: Full ingestion run (8-24h)

- **Action**: VALIDATE
- **Implement**:
  - Delete the partial data: `docker compose run --rm arcrag-init rm -f /app/data/arcpro_index.json /app/data/.checkpoint_arcpro_index.json`
  - `docker compose up -d` (Qdrant + arcrag-init + backend)
  - Monitor: `docker compose logs -f arcrag-init` (build progress prints every 25 pages via `print` flush=True)
  - Check Qdrant count: `wget -qO- http://localhost:6333/collections/arcgis_docs | python3 -c "import json,sys; d=json.load(sys.stdin); print('Points:', d['result']['points_count'])"`
  - Expected final count: 16,419 page entries + ~30K-50K section entries ≈ 45K-65K points
- **Validate**: After init exits 0, backend auto-starts; `curl http://localhost:8000/health` returns `{"status":"ok","qdrant":"connected","model":"..."}`
- **If interrupted**: Re-run `docker compose up arcrag-init` — checkpoint resumes from `.checkpoint_arcpro_index.json` in the `arcrag_data` volume

### Task 8: Quality validation

- **Action**: VALIDATE
- **Implement**:
  - `cd backend && uv run python test_search.py` — all 7 tests pass (6 existing + new Zonal Statistics obscure test)
  - Manually invoke 5-10 diverse queries (e.g., "How do I create a buffer?", "What is a geodatabase?", "How do I export a map to PDF?") via `python -c "import asyncio; from src.agent import agent; print(asyncio.run(agent.run('YOUR QUERY')).output)"`
  - Spot-check: each answer should reference a real ArcGIS Pro URL and include at least one image
- **Validate**: ≥8/10 hit rate; obscure-tool test passes; spot-checked queries return grounded answers

### Task 9: Documentation

- **Action**: DOCUMENT
- **Implement**:
  - Create `.agents/reports/arccrag-15-full-arcpro-index-ingestion-report.md` following the ARCRAG-06/07/14 template: summary, files changed, validation results, deviations, acceptance criteria checklist, vector count, runtime, costs
  - Create `.agents/decisions/arccrag-15-full-arcpro-index-ingestion.md`: summary, key decisions, errors encountered, what went right/wrong, lessons learned
  - Update `.agents/stories/stories.md`: mark ARCRAG-15 ✅ Completed with vector count, runtime, and timestamp
- **Mirror**: `.agents/reports/arccrag-06-index-builder-report.md` and `.agents/decisions/arccrag-06-index-builder.md` for format
- **Validate**: Files exist; all 5 acceptance criteria from the story are checked off

---

## Validation Block

```bash
# After Tasks 1-5 (code complete, before Task 6)
cd /home/techafresh/projects/arcpro-docs
docker compose config                          # parses without error

# Pre-flight (Task 6)
docker compose up -d qdrant
docker compose run --rm arcrag-init sh -c "python /app/scripts/build_index.py --source arcpro --limit 5 && python /app/scripts/load_qdrant.py --source arcpro --recreate"
wget -qO- http://localhost:6333/collections/arcgis_docs
cd backend && uv run python test_search.py    # all tests pass

# Full run (Task 7) - 8-24h
docker compose up -d
docker compose logs -f arcrag-init            # monitor

# Final verification (Task 8)
curl http://localhost:8000/health
wget -qO- http://localhost:6333/collections/arcgis_docs
cd backend && uv run python test_search.py
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Init container takes 8-24h; user expects "up and running" | Document the long runtime in `init.sh` output and the report; checkpoint persistence means re-runs are fast |
| `doc.esri.com` rate-limits (429) during the 8-24h run | Task 1 adds bounded retry (1 retry, 5s backoff) preemptively per ARCRAG-06's flagged gap |
| OpenRouter API cost overrun (~$5-15 budget) | Use `openai/text-embedding-3-small` (already in `.env.example`); `load_qdrant.py --batch-size 100` keeps requests under control; abortable mid-run via checkpoint |
| Container's `data/` volume loses checkpoint on `docker compose down -v` | Document explicitly: `docker compose down` (no `-v`) preserves `arcrag_data`; re-running init resumes |
| `arcrag-init` succeeds but `backend` can't connect to Qdrant | Use `depends_on: { qdrant: { condition: service_healthy } }`; Qdrant healthcheck returns 200 only when fully ready |
| `backend/Dockerfile` doesn't have `httpx`/`bs4` (script dependencies) | Install full Python deps in the image, not just `src/main.py`'s direct imports — init container runs `build_index.py` which needs `bs4` |
| Qdrant snapshot not preserved across container restarts | Existing `qdrant_data` named volume already handles this; document in plan |
| `arcrag-init` re-runs and re-embeds on every `docker compose up` | Idempotency guard in `init.sh`: skip if `arcgis_docs` collection already has points |
| Backend fails to start because of missing `.env` | `docker-compose.yml` uses `env_file: backend/.env` (already exists); document that this file must contain valid `OPENROUTER_API_KEY` |
| The 16K URLs are version 3.7 specifically; future versions need re-run | Add a doc note in the report that the ingestion is version-specific and should be re-run when Esri releases a new major version |

---

## Acceptance Criteria

- [ ] `scripts/build_index.py` `fetch_html` has 429-retry (1 retry, 5s backoff)
- [ ] `backend/Dockerfile` exists; `docker build -t arcrag-backend -f backend/Dockerfile .` succeeds
- [ ] `scripts/init.sh` exists, is executable, runs `build_index.py` then `load_qdrant.py --recreate` after Qdrant is ready
- [ ] `docker-compose.yml` has `qdrant` (healthy) + `arcrag-init` (one-shot) + `backend` (depends on both) services
- [ ] Named volume `arcrag_data` is mounted at `/app/data` in both init and backend
- [ ] `docker compose config` parses without error
- [ ] Pre-flight: 5-page run completes, Qdrant shows the collection with the expected point count
- [ ] Full run: `data/arcpro_index.json` contains entries for all 16,419 accessible pages
- [ ] Qdrant collection `arcgis_docs` has ~15K-20K page-level + section-level vectors (estimate ~45K-65K points after flatten)
- [ ] `curl http://localhost:8000/health` returns `{"status":"ok","qdrant":"connected","model":"..."}`
- [ ] `cd backend && uv run python test_search.py` passes all 7 tests (6 existing + new Zonal Statistics test)
- [ ] Obscure-tool test: searching for "Zonal Statistics as Table" returns the correct page in top 5
- [ ] Re-running `docker compose up arcrag-init` resumes from checkpoint (verified by log timestamps)
- [ ] `.agents/reports/arccrag-15-*.md` and `.agents/decisions/arccrag-15-*.md` are written
- [ ] `.agents/stories/stories.md` marks ARCRAG-15 ✅ Completed with vector count + runtime

---

## Open Questions / Assumptions

1. **Backend `.env` file exists**: Verified by `ls backend/.env` (24 bytes). Assumes it contains `OPENROUTER_API_KEY`. The `env_file: backend/.env` directive in `docker-compose.yml` will pick it up. If not present at runtime, the init container will fail at the embedding step with a clear error.
2. **Single init container is sufficient**: The plan runs the entire ArcGIS Pro ingestion in one container. No parallelization across multiple init containers — the bottleneck is doc.esri.com rate limits, not local compute, so parallel containers would just multiply the rate-limit hits.
3. **ArcMap (ARCRAG-16) is out of scope here**: This plan is ArcGIS Pro only. ARCRAG-16 will be a separate ticket with a similar init container pattern; can reuse `init.sh` by parameterizing `--source arcmap` later.
4. **Production Docker Compose (ARCRAG-17) is partially addressed**: The `backend` service added here overlaps with ARCRAG-17. ARCRAG-17 will extend this further (HTTPS, frontend service, Caddy/Nginx, rate limiting, memory limits).
5. **The 5-page smoke-test entries in `data/arcpro_index.json` will be overwritten** on the full run. The pre-flight test (Task 6) uses `--limit 5` to verify the pipeline; the full run (Task 7) deletes the partial index first.
