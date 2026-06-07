# Plan: ARCRAG-16 — Full ArcMap Index Ingestion

## Summary

Apply the ARCRAG-15 init container pattern to ArcMap, parameterizing `init.sh` to accept a `SOURCE` env var so the same pipeline can ingest either documentation set on demand. Add a second compose `arcrag-init-arcmap` service that runs after `arcrag-init` (ArcGIS Pro), and a small fix to `load_qdrant.py` to add a per-source `ID_OFFSET` so the two batches don't collide on the shared `arcgis_docs` collection. Add an ArcMap-specific obscure-tool test ("georeferencing in ArcMap") to `test_search.py` as the analog of ARCRAG-15's "Zonal Statistics as Table" test. The `data/arcmap_urls.json` file already exists from ARCRAG-05 (≈10,549 lines / ~5K-10K URLs), so URL collection is a no-op — only the index build + load phases need to run. Per PRD §14 Risk 2, ArcMap docs are archived/retired; speed matters because `desktop.arcgis.com` may be taken down.

## User Story

As a developer
I want the full ArcMap documentation index to be ingested into Qdrant automatically when the system starts
So that `docker compose up` produces a system with both ArcGIS Pro and ArcMap vectors in the `arcgis_docs` collection, and re-runs of either init resume from their own checkpoint without disturbing the other source's vectors

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (operational + script hardening, mirrors ARCRAG-15) |
| Complexity | MEDIUM (lower than ARCRAG-15 because URLs already collected, plumbing exists; main work is compose wiring + ID-collision fix) |
| Systems Affected | `scripts/init.sh`, `scripts/load_qdrant.py`, `docker-compose.yml`, `backend/test_search.py`, `backend/test_load_qdrant.py` |
| Jira Issue | ARCRAG-16 |

---

## Current State (verified during planning)

| Artifact | State | Implication |
|----------|-------|-------------|
| `data/arcmap_urls.json` | 1,203,119 bytes, ~10,549 lines, paths like `http://desktop.arcgis.com/en/arcmap/latest/...` | URL collection done (ARCRAG-05). No re-run needed. |
| `data/.checkpoint_arcmap_urls.json` | Present, same byte order of magnitude | Resumable. Not relevant for this plan. |
| `data/arcmap_index.json` | Does not exist | Must be produced by the full `build_index.py --source arcmap` run. |
| `data/.checkpoint_arcmap_index.json` | Does not exist | Will be created by `build_index.py` during the run. |
| `scripts/build_index.py` | Already supports `--source arcmap` via `SOURCES["arcmap"]` dict (lines 23-28) | No code change. |
| `scripts/load_qdrant.py` | Already supports `--source arcmap` via `SOURCES["arcmap"]` (lines 27-30). **BUG:** `id=start + i` (line 153) starts at 0 for every source → IDs will collide if ArcPro and ArcMap are both upserted into the same collection. | Requires a small `ID_OFFSET` fix. |
| `scripts/init.sh` | Hardcoded `--source arcpro` (lines 30, 33), uses `--recreate` on line 33 | Needs `SOURCE` env var + drop `--recreate` for non-first runs. |
| `docker-compose.yml` | One `arcrag-init` service for ArcGIS Pro (lines 16-30) | Add `arcrag-init-arcmap` service, gated on `arcrag-init: service_completed_successfully`. |
| `backend/Dockerfile` | Exists, copies `scripts/` and `data/` | No change. |
| `backend/test_search.py` | Has 8 tests including ArcGIS Pro obscure-tool test (`test_obscure_tool_zonal_statistics`, lines 130-161). ArcMap keyword detection works (`detect_source_filter` → `ARCMAP_KEYWORDS = {"arcmap", "arc map", "arc-map"}`, `backend/src/tools/search.py:38`). | Add `test_obscure_tool_georeference_arcmap()` as analog. |
| `backend/test_load_qdrant.py` | Validates `SOURCES.keys() == ["arcpro", "arcmap"]` (line 26). Flatten/upsert path already source-agnostic. | No change unless we add an `ID_OFFSET` field, in which case update Test 1 to verify it exists. |
| Qdrant collection `arcgis_docs` | Currently empty (no successful ArcPro run yet) | First init creates it; second init merges into it. |

---

## Patterns to Follow

### SOURCES dict + repo-root anchoring (mirrors all scripts)
```python
# SOURCE: scripts/load_qdrant.py:13-31
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
(PROJECT_DIR / "data").mkdir(exist_ok=True)
SOURCES = {
    "arcpro": {"index_json": ".../arcpro_index.json", "source": "arcpro"},
    "arcmap": {"index_json": ".../arcmap_index.json", "source": "arcmap"},
}
```

### ARCGIS-15 init.sh structure (parameterize, don't rewrite)
```bash
# SOURCE: scripts/init.sh:1-35
#!/bin/bash
set -e
QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-arcgis_docs}"
# ... waits for Qdrant, checks collection, runs build_index then load_qdrant
```

### ARCRAG-15 compose init service (mirror and add second)
```yaml
# SOURCE: docker-compose.yml:16-30
arcrag-init:
  build:
    context: .
    dockerfile: backend/Dockerfile
  command: ["/app/scripts/init.sh"]
  restart: "no"
  env_file: backend/.env
  environment:
    - QDRANT_URL=http://qdrant:6333
    - QDRANT_COLLECTION=arcgis_docs
  volumes:
    - arcrag_data:/app/data
  depends_on:
    qdrant:
      condition: service_healthy
```

### ARCRAG-15 backend gate on init success
```yaml
# SOURCE: docker-compose.yml:32-49
backend:
  depends_on:
    qdrant:
      condition: service_healthy
    arcrag-init:
      condition: service_completed_successfully
```

### Conditional live-search test pattern (Test 7/8 template)
```python
# SOURCE: backend/test_search.py:82-127
async def test_live_search():
    api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    if not api_key:
        print("SKIP - no API key set"); return
    from qdrant_client import QdrantClient
    try:
        q = QdrantClient(url=qdrant_url)
        q.get_collections()
    except Exception:
        print("SKIP - Qdrant not reachable"); return
    # ... run queries, assert hit rate
```

### Obscure-tool test pattern (Test 8 template)
```python
# SOURCE: backend/test_search.py:130-161
async def test_obscure_tool_zonal_statistics():
    # Skip-gate identical to test_live_search
    r = await search_index("Zonal Statistics as Table", top_k=5)
    # ...
    target_suffix = "zonal-statistics-as-table.htm"
    found = any(
        target_suffix in result.url.lower() or "zonal statistics" in result.title.lower()
        for result in r.results
    )
    assert found, f"Expected Zonal Statistics as Table page in top 5, got: ..."
```

### ArcMap source detection (already works in search tool)
```python
# SOURCE: backend/src/tools/search.py:38-45
ARCMAP_KEYWORDS = {"arcmap", "arc map", "arc-map"}
def detect_source_filter(query: str) -> str | None:
    lowered = query.lower()
    if any(kw in lowered for kw in ARCMAP_KEYWORDS):
        return "arcmap"
    return None
```

### 429-retry pattern in `build_index.py` (no change needed)
```python
# SOURCE: scripts/build_index.py:32-47
async def fetch_html(client, url):
    for attempt in range(2):
        try:
            resp = await client.get(url)
        except Exception as e:
            print(f" FAILED: {e}", flush=True); return None
        if resp.status_code == 429 and attempt == 0:
            print(f" HTTP 429, sleeping 5s and retrying", flush=True)
            await asyncio.sleep(5); continue
        # ...
```

---

## Key Design Decisions

### 1. Parameterize `init.sh` with `SOURCE` env var (don't duplicate)

**Decision:** Read `SOURCE` from env (default `arcpro` for backward compat), use it in both `build_index.py` and `load_qdrant.py` invocations. One script, two calls.

**Rationale:** ARCRAG-15's `init.sh` is hardcoded to `--source arcpro`. We have two options:
- (a) Parameterize the existing script
- (b) Add a second `init-arcmap.sh` (copy of init.sh with different source)

(a) is cleaner — single source of truth, easier to maintain, and the script's body doesn't need to know about a specific source. The default `arcpro` preserves ARCRAG-15's existing behavior with no diff needed for the ARCRAG-15 service block.

### 2. Drop `--recreate` from the non-first init run

**Decision:** `init.sh` runs `load_qdrant.py` **without** `--recreate`. The first init to run (ArcGIS Pro) creates the collection; the second (ArcMap) upserts into it.

**Rationale:** If both inits use `--recreate`, the second would wipe the first's vectors. The order in `docker-compose.yml` is: `arcrag-init` (ArcPro) runs first, `arcrag-init-arcmap` waits on it. ArcPro `--recreate` creates the collection; ArcMap just appends.

**Idempotency:** The `load_qdrant.py` code path without `--recreate` is already handled (line 92-99: "Collection already exists" branch), it just calls `qdrant.upsert(...)` on the existing collection.

### 3. Add `ID_OFFSET` per source to prevent ID collisions

**Decision:** Add `id_offset` to each `SOURCES` entry in `load_qdrant.py`. Use `id=start + i + id_offset` instead of `id=start + i`. ArcGIS Pro: 0. ArcMap: 1_000_000.

**Rationale:** Both sources upsert into the same `arcgis_docs` collection. With the current code (`load_qdrant.py:147-159`):
```python
for start in range(0, total, batch_size):  # start = 0, 100, 200, ...
    points = [PointStruct(id=start + i, ...) for i in range(len(batch))]
```
If ArcPro ingests first, IDs 0..N_pro are used. When ArcMap's `load_qdrant.py` runs without `--recreate`, it would try to write IDs 0..N_map, overwriting ArcPro vectors with ArcMap content.

Fix: per-source offset large enough to never collide. ArcPro = 0 (existing behavior, no diff for ARCRAG-15's already-merged code). ArcMap = 1_000_000 (plenty of headroom for 5K-10K page entries + 10K-30K section entries). This is a 1-line change to `load_qdrant.py` plus a SOURCES dict update.

Alternative considered: use `uuid.uuid4()` for IDs. Rejected because it would change the existing ARCRAG-15 behavior and break the plan's "mirror prior patterns" directive.

### 4. Idempotency guard: check per-source, not collection-wide

**Decision:** `init.sh` checks if Qdrant collection has any points **with `source=<this_source>` payload**, not just `points_count > 0`. If yes, skip ingestion for this source.

**Rationale:** With the current ARCRAG-15 init.sh, the check is `points_count > 0` (line 24 of init.sh). With two sources sharing a collection, that check would always be true after the first run, so the second source's `arcrag-init-arcmap` would skip every time. We need a per-source check: filter by `source` field.

**Implementation:** Use Qdrant's count API with a filter, e.g.:
```bash
count=$(wget -q -O- "${QDRANT_URL}/collections/${QDRANT_COLLECTION}" 2>/dev/null | \
    python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('result', {}).get('points_count', 0))" 2>/dev/null || echo "0")
```
becomes:
```bash
filter='{"filter":{"must":[{"key":"source","match":{"value":"'$SOURCE'"}}]}}'
count=$(wget -q -O- --post-data="$filter" --header="Content-Type: application/json" \
    "${QDRANT_URL}/collections/${QDRANT_COLLECTION}/points/count" 2>/dev/null | \
    python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('result', {}).get('count', 0))" 2>/dev/null || echo "0")
```

Alternative: use Qdrant's scroll API to check the first point. Rejected — `/points/count` with filter is the idiomatic Qdrant way and is one HTTP call.

### 5. Two init services, not one service run twice

**Decision:** Add `arcrag-init-arcmap` as a separate compose service that runs after `arcrag-init` completes.

**Rationale:** ARCRAG-15's pattern uses a single init container gated on Qdrant. For ArcMap we add a second service gated on **both** Qdrant AND the first init's success:
```yaml
arcrag-init-arcmap:
  # ... same body as arcrag-init except:
  environment:
    - SOURCE=arcmap  # passed to init.sh
  depends_on:
    qdrant:
      condition: service_healthy
    arcrag-init:
      condition: service_completed_successfully
```

The `backend` service needs to gate on BOTH inits:
```yaml
backend:
  depends_on:
    qdrant: { condition: service_healthy }
    arcrag-init: { condition: service_completed_successfully }
    arcrag-init-arcmap: { condition: service_completed_successfully }
```

### 6. Add ArcMap-specific obscure-tool test, source-filter validation test

**Decision:** Add `test_obscure_tool_georeference_arcmap()` to `backend/test_search.py` (analog of `test_obscure_tool_zonal_statistics`). Also add `test_source_filter_no_leakage()` to verify that an "ArcMap" query does NOT return ArcGIS Pro results even when both sources are loaded.

**Rationale:** ARCRAG-15's "Zonal Statistics as Table" test asserts a specific tool name. The ArcMap analog is "georeferencing in ArcMap" — a workflow that's well-documented in the archived docs. The second test catches the common bug where the source filter is missing or wrong after merging two sources into one collection.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `scripts/init.sh` | UPDATE | Read `SOURCE` env var (default `arcpro`); use it in `build_index.py` and `load_qdrant.py` calls; drop `--recreate`; per-source idempotency check (filter by `source` payload) |
| `scripts/load_qdrant.py` | UPDATE | Add `id_offset` field to each `SOURCES` entry (arcpro=0, arcmap=1_000_000); use `id=start + i + id_offset` in upsert loop |
| `docker-compose.yml` | UPDATE | Add `arcrag-init-arcmap` service (mirror of `arcrag-init` with `SOURCE=arcmap`, gated on both `qdrant` and `arcrag-init`); update `backend` to depend on both inits |
| `backend/test_search.py` | UPDATE | Add `test_obscure_tool_georeference_arcmap()` and `test_source_filter_no_leakage()` |
| `backend/test_load_qdrant.py` | UPDATE (minor) | In Test 1, assert `ID_OFFSET` (or whatever the field is called) exists per source and is an int |
| `.agents/reports/arccrag-16-full-arcmap-index-ingestion-report.md` | CREATE (post-run) | Implementation report (created after run completes on VPS) |
| `.agents/decisions/arccrag-16-full-arcmap-index-ingestion.md` | CREATE (post-run) | Decision log (postmortem) |
| `.agents/stories/stories.md` | UPDATE (post-run) | Mark ARCRAG-16 ✅ Completed with vector count + runtime |

---

## Tasks

Execute in order. Each task is atomic and verifiable. Tasks 1-4 are <1h of work; Task 5 is the long-running run on VPS.

### Task 1: Parameterize `init.sh` with `SOURCE` env var

- **File**: `scripts/init.sh`
- **Action**: UPDATE
- **Implement**:
  - Add `SOURCE="${SOURCE:-arcpro}"` near the top (preserves ARCRAG-15's default)
  - Replace `build_index.py --source arcpro ...` with `build_index.py --source "$SOURCE" ...`
  - Replace `load_qdrant.py --source arcpro --recreate ...` with `load_qdrant.py --source "$SOURCE" ...` (drop `--recreate`)
  - Replace `points_count > 0` idempotency check with a per-source filter (use Qdrant `/points/count` with `{"filter":{"must":[{"key":"source","match":{"value":"'$SOURCE'"}}]}}`)
  - Log `[init] (source=$SOURCE)` in startup line for clarity
- **Mirror**: `scripts/init.sh:1-35` — keep the existing structure (wait-for-Qdrant poll loop, idempotency guard, sequential build+load)
- **Avoid**: Don't put `SOURCE` in `env_file: backend/.env`; pass it via the compose `environment:` block (same pattern as `QDRANT_URL` and `QDRANT_COLLECTION` already do)
- **Validate**: `bash -n scripts/init.sh` (syntax check), then `SOURCE=arcmap bash scripts/init.sh` locally (will fail at Qdrant connection or API key, but proves the env var plumbing works)

### Task 2: Add `id_offset` to `load_qdrant.py` SOURCES

- **File**: `scripts/load_qdrant.py`
- **Action**: UPDATE
- **Implement**:
  - Add `"id_offset": 0` to `SOURCES["arcpro"]` and `"id_offset": 1_000_000` to `SOURCES["arcmap"]` (line 22-31)
  - In `load_qdrant()` function (line 102), read `id_offset = config["id_offset"]`
  - In the upsert loop (line 147-159), change `id=start + i` to `id=start + i + id_offset`
- **Mirror**: Existing `SOURCES` dict structure at `scripts/load_qdrant.py:22-31`
- **Avoid**: Don't change the rest of the embedding/upsert flow; minimal diff
- **Validate**: `cd backend && uv run python -c "import importlib.util; spec=importlib.util.spec_from_file_location('lq', '../scripts/load_qdrant.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print(m.SOURCES['arcmap']['id_offset'])"` → should print `1000000`

### Task 3: Add `arcrag-init-arcmap` service to `docker-compose.yml`

- **File**: `docker-compose.yml`
- **Action**: UPDATE
- **Implement**:
  - Copy the existing `arcrag-init` service block (lines 16-30) as `arcrag-init-arcmap`
  - Add `SOURCE: arcmap` to the new service's `environment:` block
  - Change the new service's `depends_on` to include both `qdrant: { condition: service_healthy }` and `arcrag-init: { condition: service_completed_successfully }`
  - Update the `backend` service's `depends_on` (lines 45-49) to add `arcrag-init-arcmap: { condition: service_completed_successfully }`
- **Mirror**: Existing `arcrag-init` block at `docker-compose.yml:16-30`
- **Avoid**: Don't change the `arcrag-init` (ArcPro) service — it must keep `--recreate` (passed via init.sh's hardcoded default behavior, which is fine because ArcPro is first)
- **Validate**: `docker compose config` parses without error; the output shows 4 services (qdrant, arcrag-init, arcrag-init-arcmap, backend) and the dependency graph is correct

### Task 4: Add ArcMap-specific tests to `backend/test_search.py` and `backend/test_load_qdrant.py`

- **File**: `backend/test_search.py`
- **Action**: UPDATE
- **Implement**:
  - Add `test_obscure_tool_georeference_arcmap()` — mirror of `test_obscure_tool_zonal_statistics` (lines 130-161). Search "How do I georeference in ArcMap?" with `top_k=5`. Assert any result's URL ends in `georeferencing.htm` or has "georeference" in title.
  - Add `test_source_filter_no_leakage()` — searches for "buffer ArcMap" with `top_k=10`. Asserts ALL returned results have `source == "arcmap"` (no ArcGIS Pro leakage). Skip-gate identical to Test 7/8.
  - Wire both into `test()` (line 164-173)
- **Mirror**: `test_obscure_tool_zonal_statistics` at `backend/test_search.py:130-161`
- **Avoid**: Don't change the existing 8 tests
- **Validate**: `cd backend && uv run python test_search.py` — new tests skip gracefully when Qdrant/keys are absent, pass when ArcMap data is loaded

- **File**: `backend/test_load_qdrant.py`
- **Action**: UPDATE (minor, 1-line addition)
- **Implement**: In `test_import()` (line 22-32), after the `SOURCES` assertion, add:
  ```python
  assert all("id_offset" in s for s in m.SOURCES.values()), "id_offset missing in SOURCES"
  assert isinstance(m.SOURCES["arcmap"]["id_offset"], int), "arcmap id_offset must be int"
  ```
- **Validate**: `cd backend && uv run python test_load_qdrant.py` — Test 1 passes

### Task 5: Pre-flight smoke test on VPS (5 min)

- **Action**: VALIDATE
- **Implement**:
  - On VPS: `cd /home/.../arcpro-docs && git pull origin <branch>`
  - Ensure `backend/.env` has a real `OPENROUTER_API_KEY` (per ARCRAG-15's lesson)
  - `docker compose up -d qdrant`
  - `docker compose run --rm arcrag-init sh -c "python /app/scripts/build_index.py --source arcpro --limit 5 --concurrency 2 --delay 0.5"` (5-page smoke test for ArcPro, confirm ID_OFFSET=0 works)
  - `docker compose run --rm arcrag-init sh -c "python /app/scripts/build_index.py --source arcmap --limit 5 --concurrency 2 --delay 0.5"` (5-page smoke test for ArcMap, confirm ID_OFFSET=1_000_000 works)
  - Verify: `wget -qO- http://localhost:6333/collections/arcgis_docs/points/count -O- --post-data='{"filter":{"must":[{"key":"source","match":{"value":"arcmap"}}]}}' --header='Content-Type: application/json'` returns a count (should be ≈ 55 = 5 pages * (1 page entry + ~10 section entries))
  - `docker compose run --rm arcrag-init sh -c "python /app/scripts/load_qdrant.py --source arcpro --recreate --batch-size 100 && python /app/scripts/load_qdrant.py --source arcmap --batch-size 100"` (load both, verify IDs don't collide)
  - Verify: `wget -qO- http://localhost:6333/collections/arcgis_docs` shows the full point count
- **Validate**: Qdrant collection has both `source: arcpro` and `source: arcmap` points; `test_search.py` runs all 10 tests; 2 new tests skip cleanly because the 5-page data is too sparse to satisfy the assertion

### Task 6: Full ingestion run on VPS (4-12h)

- **Action**: VALIDATE
- **Implement**:
  - On VPS, clean the partial data: `docker compose run --rm arcrag-init rm -f /app/data/arcpro_index.json /app/data/.checkpoint_arcpro_index.json /app/data/arcmap_index.json /app/data/.checkpoint_arcmap_index.json` (Note: the `arcmap_urls.json` and `.checkpoint_arcmap_urls.json` are kept — ARCRAG-05's URL collection is reused as-is)
  - `docker compose up -d` (starts qdrant + arcrag-init + arcrag-init-arcmap + backend)
  - Monitor: `docker compose logs -f arcrag-init arcrag-init-arcmap` (build progress prints every 25 pages via `print` flush=True)
  - First watch `arcrag-init` complete (ArcPro, 8-24h per ARCRAG-15), then `arcrag-init-arcmap` start (ArcMap, 4-12h estimated, smaller URL count)
  - Spot-check: `wget -qO- http://localhost:6333/collections/arcgis_docs/points/count -O- --post-data='{"filter":{"must":[{"key":"source","match":{"value":"arcmap"}}]}}' --header='Content-Type: application/json'` — should grow over time
- **Validate**:
  - `arcrag-init` exits 0 → `arcrag-init-arcmap` starts
  - `arcrag-init-arcmap` exits 0 → `backend` auto-starts
  - `curl http://localhost:8000/health` returns `{"status":"ok","qdrant":"connected","model":"..."}`
  - Expected final Qdrant counts: ArcPro ≈ 45K-65K points (from ARCRAG-15 plan §Task 7); ArcMap ≈ 15K-30K points (estimated, 5K-10K pages × 1 + ~3-5 sections per page)

### Task 7: Quality validation on VPS

- **Action**: VALIDATE
- **Implement**:
  - `cd backend && uv run python test_search.py` — all 10 tests pass (8 existing + 2 new ArcMap tests)
  - Manually invoke ArcMap-specific queries:
    - `python -c "import asyncio; from src.tools.search import search_index; r=asyncio.run(search_index('How do I georeference in ArcMap?', top_k=5)); [print(x.title, x.url, x.source) for x in r.results]"` — should return ArcMap results
    - Same for "ArcMap buffer", "ArcMap clip", "ArcMap intersect"
  - `python -c "...search_index('buffer ArcMap', top_k=10)..."` — verify `source` field is `arcmap` on ALL results (no leakage)
  - Spot-check via the running backend UI: ask the chat "How do I georeference a raster in ArcMap?" and confirm a grounded answer with image + source link
- **Validate**:
  - ≥8/10 hit rate on the existing 10-query `QUERY_KEYWORDS` (ArcPro tests still pass)
  - New `test_obscure_tool_georeference_arcmap` passes
  - New `test_source_filter_no_leakage` passes
  - Both source-specific hit rates (ArcPro ≥80%, ArcMap ≥70% on a 5-query spot check)

### Task 8: Documentation

- **Action**: DOCUMENT
- **Implement**:
  - Create `.agents/reports/arccrag-16-full-arcmap-index-ingestion-report.md` following the ARCRAG-15 template (summary, files changed, validation results, deviations, acceptance criteria checklist, vector count, runtime, costs)
  - Create `.agents/decisions/arccrag-16-full-arcmap-index-ingestion.md` (summary, key decisions, errors, lessons learned) — focus on the new design decisions (id_offset, per-source idempotency, second init service)
  - Update `.agents/stories/stories.md`: mark ARCRAG-16 ✅ Completed with vector count, runtime, and timestamp
- **Mirror**: `.agents/reports/arccrag-15-full-arcpro-index-ingestion-report.md` and `.agents/decisions/arccrag-15-full-arcpro-index-ingestion.md` for format
- **Validate**: Files exist; all 5 acceptance criteria from the story are checked off

---

## Validation Block

```bash
# After Tasks 1-4 (code complete, before Task 5)
cd /home/techafresh/projects/arcpro-docs
docker compose config                          # parses without error, 4 services
bash -n scripts/init.sh                        # init.sh syntax check
cd backend
uv run python -c "import importlib.util; spec=importlib.util.spec_from_file_location('lq', '../scripts/load_qdrant.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('arcmap id_offset:', m.SOURCES['arcmap']['id_offset'])"
uv run python test_search.py                   # 8 existing + 2 new skip cleanly
uv run python test_load_qdrant.py              # Test 1 asserts id_offset exists

# Pre-flight on VPS (Task 5)
docker compose up -d qdrant
docker compose run --rm arcrag-init sh -c "python /app/scripts/build_index.py --source arcpro --limit 5 && python /app/scripts/build_index.py --source arcmap --limit 5 && python /app/scripts/load_qdrant.py --source arcpro --recreate --batch-size 100 && python /app/scripts/load_qdrant.py --source arcmap --batch-size 100"
wget -qO- http://localhost:6333/collections/arcgis_docs | python3 -c "import json,sys; d=json.load(sys.stdin); print('Total points:', d['result']['points_count'])"

# Full run on VPS (Task 6) - 12-36h total
docker compose up -d
docker compose logs -f arcrag-init arcrag-init-arcmap

# Final verification on VPS (Task 7)
curl http://localhost:8000/health
wget -qO- http://localhost:6333/collections/arcgis_docs | python3 -c "import json,sys; d=json.load(sys.stdin); print('Total points:', d['result']['points_count'])"
cd backend && uv run python test_search.py     # all 10 tests pass
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `desktop.arcgis.com` is taken down mid-run (PRD §14 Risk 2) | The 5-page pre-flight (Task 5) catches this immediately. If pre-flight fails for ArcMap URLs, abort and either (a) accept that ArcMap is gone, (b) find an archive (Wayback Machine), (c) use a local mirror. Document the failure in the report. |
| `load_qdrant.py --source arcmap` collides with ArcPro IDs | **The `id_offset` field in SOURCES prevents this.** Verified by Task 5's 5-page smoke test on both sources; IDs 0..N_pro and 1_000_000..1_000_000+N_map. |
| `arcrag-init-arcmap` runs before `arcrag-init` (race condition) | Compose's `depends_on: { arcrag-init: { condition: service_completed_successfully } }` guarantees sequential start. Compose will not start the second service until the first exits 0. |
| `arcrag-init-arcmap` runs without ArcPro data (if user removes the first service) | The per-source idempotency check is independent per source. If ArcPro data is missing but ArcMap data exists, the second init's check still works. If both are missing, both inits run sequentially. |
| `init.sh`'s per-source idempotency check is wrong (filters by wrong field) | The Qdrant `/points/count` with `{"filter":{"must":[{"key":"source","match":{"value":"arcmap"}}]}}` is a standard Qdrant REST pattern. Pre-flight (Task 5) verifies it works. |
| ArcMap DOM is different from ArcPro DOM (legacy Esri template) | `build_index.py`'s extraction functions (`extract_title`, `extract_summary`, `extract_sections`, `extract_breadcrumb`, `extract_images` at `scripts/build_index.py:50-127`) use generic selectors (`<h1>`, `<article id="main">`, `<main>`, etc.) and fallback paths. The 5-page pre-flight will surface any major extraction failures. |
| ArcMap docs have lower-quality summaries (legacy pages) | Won't be a correctness issue for embedding (the page still gets vectorized). May reduce search quality; out of scope for ARCRAG-16 — the search tool already returns `summary` and `section` so the LLM can work with what's there. |
| Embedding cost overrun (~$3-10 budget for ArcMap) | Use `openai/text-embedding-3-small` (already in `.env.example`); `load_qdrant.py --batch-size 100` keeps requests under control; abortable mid-run via checkpoint (`.checkpoint_arcmap_index.json` resumes). |
| `docker build` heavy on dev PC (ARCRAG-15 lesson) | Do NOT build on the dev PC. The user explicitly deferred ARCRAG-15's build to VPS. Mirror that here. |
| `backend/.env` `OPENROUTER_API_KEY=dummy` breaks embedding | Documented in ARCRAG-15's report. The runbook in Task 6 step 2 explicitly sets a real key. |
| ArcMap URL `path_filter` mismatch if Esri changes sitemap structure | `parse_sitemaps.py:28-35` has the filter `/en/arcmap/latest/`. If the live `data/arcmap_urls.json` (already collected) has URLs outside this filter, `build_index.py` will still process them (no filter on the build side). |
| `arcrag_data` volume wiped by `docker compose down -v` (ARCRAG-15 lesson) | Document prominently in the report. Re-running `arcrag-init-arcmap` after a `down -v` will redo both sources from scratch. |
| Second init's wait-for-Qdrant is redundant after first init's wait | Acceptable redundancy. Belt-and-suspenders. Each init is independent; one could be removed via compose override without breaking the other. |

---

## Acceptance Criteria

- [ ] `scripts/init.sh` reads `SOURCE` env var (default `arcpro`); idempotency check filters by `source` payload
- [ ] `scripts/init.sh` does NOT pass `--recreate` to `load_qdrant.py` (so the second source doesn't wipe the first)
- [ ] `scripts/load_qdrant.py` SOURCES has `id_offset` (arcpro=0, arcmap=1_000_000); upsert loop uses `id=start + i + id_offset`
- [ ] `docker compose config` parses with 4 services: qdrant, arcrag-init, arcrag-init-arcmap, backend
- [ ] `arcrag-init-arcmap` service is gated on `arcrag-init: service_completed_successfully` and `qdrant: service_healthy`
- [ ] `backend` service is gated on `arcrag-init-arcmap: service_completed_successfully` (in addition to existing gates)
- [ ] `backend/test_search.py` has new `test_obscure_tool_georeference_arcmap()` (analog of Test 8 for ArcMap)
- [ ] `backend/test_search.py` has new `test_source_filter_no_leakage()` (asserts `source=arcmap` filter works after both sources loaded)
- [ ] `backend/test_load_qdrant.py` Test 1 asserts `id_offset` field exists and is int
- [ ] Pre-flight: 5-page run for both ArcPro and ArcMap completes, Qdrant shows both source:arcpro and source:arcmap points with no ID collision
- [ ] Full run: `data/arcmap_index.json` contains entries for all ~5K-10K accessible ArcMap pages
- [ ] Qdrant collection `arcgis_docs` has ArcPro points + ArcMap points (combined ≈ 60K-95K points)
- [ ] `curl http://localhost:8000/health` returns `{"status":"ok","qdrant":"connected","model":"..."}`
- [ ] `cd backend && uv run python test_search.py` passes all 10 tests
- [ ] Obscure ArcMap test: searching for "How do I georeference in ArcMap?" returns a georeferencing page in top 5
- [ ] Source-filter test: searching for "buffer ArcMap" returns only `source=arcmap` results
- [ ] Re-running `docker compose up arcrag-init-arcmap` resumes from `.checkpoint_arcmap_index.json` without re-ingesting ArcPro data
- [ ] `.agents/reports/arccrag-16-*.md` and `.agents/decisions/arccrag-16-*.md` are written
- [ ] `.agents/stories/stories.md` marks ARCRAG-16 ✅ Completed with vector count + runtime

---

## Open Questions / Assumptions

1. **ArcMap URLs file is complete and accurate**: Verified by `wc -l data/arcmap_urls.json` (~10,549 lines, 1.2MB) and spot-checked first/last entries (`http://desktop.arcgis.com/en/arcmap/latest/...`). No re-run of `parse_sitemaps.py` needed.
2. **Qdrant filter API is stable**: The `/points/count` endpoint with `{"filter":{"must":[{"key":"source","match":{"value":"..."}}]}}` is a documented Qdrant REST pattern. If the Qdrant version is too old, the alternative is to scroll + count client-side. Tested with Qdrant v1.12.1 (per `docker-compose.yml:3`).
3. **ID offset of 1,000,000 is sufficient**: ArcMap has ~5K-10K pages × 1 page entry + ~3-5 section entries ≈ 20K-60K total entries. 1,000,000 is comfortable headroom. If we ever ingest a third source, it'd need 2,000,000+ or we'd switch to UUIDs.
4. **ArcMap URLs' response size**: The `httpx.AsyncClient(timeout=10.0)` in `build_index.py:207` matches ARCRAG-15's setting. If ArcMap pages are larger, we may need to bump timeout. Pre-flight (Task 5) catches this.
5. **Production hardening (ARCRAG-17) handles the dual-init pattern**: This plan stops at "both inits run, backend starts, tests pass". ARCRAG-17 (production Docker Compose) will extend with HTTPS, frontend service, Caddy, rate limits, memory limits. The dual-init pattern is compatible with that future work.
6. **Embedding cost**: ArcMap = ~20K-60K entries × `openai/text-embedding-3-small` (~$0.02/1M tokens, ~500 tokens/entry) = ~$0.20-$0.60. Negligible.
7. **No separate ArcMap `Dockerfile` needed**: ARCRAG-15's `backend/Dockerfile` already installs `httpx`, `bs4`, `qdrant-client` — everything `build_index.py` and `load_qdrant.py` need for ArcMap.
8. **The 5-page smoke test for ArcMap may fail if the first 5 URLs in `arcmap_urls.json` are non-content pages** (e.g., redirects or error pages). The smoke test is for pipeline validation, not content validation. If it fails, switch to `--limit 20` and spot-check that any 5 pages succeed.
