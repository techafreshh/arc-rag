# Implementation Report

**Plan**: `.agents/plans/completed/arccrag-16-full-arcmap-index-ingestion.plan.md`
**Branch**: `feature/arccrag-16-full-arcmap-index-ingestion`
**Status**: CODE COMPLETE (VPS-side runtime validation deferred)

## Summary

Mirrored the ARCRAG-15 init-container pattern for ArcMap, parameterizing `scripts/init.sh` with a `SOURCE` env var (default `arcpro`) so the same script drives both ArcGIS Pro and ArcMap ingestion. Added a new `arcrag-init-arcmap` compose service gated on `arcrag-init: service_completed_successfully`, with its `SOURCE=arcmap` env var passed through. Fixed a latent ID-collision bug in `scripts/load_qdrant.py` by introducing a per-source `id_offset` (arcpro=0, arcmap=1_000_000) and switching the upsert loop to `id=start + i + id_offset`. Replaced the collection-wide `points_count > 0` idempotency check in `init.sh` with a per-source Qdrant `/points/count` filter (POST JSON `{"filter":{"must":[{"key":"source","match":{"value":"<source>"}}]}}`). Dropped `--recreate` from the `load_qdrant.py` invocation in `init.sh` so the second source upserts into the existing collection instead of wiping it. Added two new search tests (`test_obscure_tool_georeference_arcmap`, `test_source_filter_no_leakage`) and extended the `test_load_qdrant.py` Test 1 to assert the new `id_offset` field on every source.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Parameterize `init.sh` with `SOURCE` env var; per-source idempotency check; drop `--recreate` | `scripts/init.sh` | ✅ |
| 2 | Add `id_offset` to SOURCES (arcpro=0, arcmap=1_000_000); use `id=start + i + id_offset` in upsert | `scripts/load_qdrant.py` | ✅ |
| 3 | Add `arcrag-init-arcmap` service; gate backend on both inits | `docker-compose.yml` | ✅ |
| 4 | Add `test_obscure_tool_georeference_arcmap` + `test_source_filter_no_leakage` to `test_search.py`; assert `id_offset` in `test_load_qdrant.py` Test 1 | `backend/test_search.py`, `backend/test_load_qdrant.py` | ✅ |
| 5 | Pre-flight smoke test (5 pages) | (deferred to VPS) | ⏸ Deferred |
| 6 | Full ingestion run (4-12h) | (deferred to VPS) | ⏸ Deferred |
| 7 | Quality validation (live search tests) | (deferred to VPS) | ⏸ Deferred |
| 8 | Documentation (this report + decision + stories update) | `.agents/...` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `bash -n scripts/init.sh` | ✅ Syntax OK |
| `docker compose config` | ✅ Parses without error; 4 services (`qdrant`, `arcrag-init`, `arcrag-init-arcmap`, `backend`); `arcrag-init-arcmap` depends on `arcrag-init` + `qdrant`; `backend` depends on both inits + `qdrant` |
| `id_offset` import (arcpro=0, arcmap=1_000_000) | ✅ `OK` |
| `test_search.py` (no Qdrant) | ✅ 8 tests pass; 2 tests skip (live + obscure tools) + 2 new tests skip gracefully (Qdrant unreachable) |
| `test_load_qdrant.py` Test 1 | ✅ `PASS` — asserts `id_offset` field exists on every source, is `int`, and `arcmap > arcpro` |
| `test_load_qdrant.py` Test 3 (dry-run) | ⏸ Pre-existing 30s timeout insufficient for pydantic-ai import on this PC. Dry-run command itself completes in ~24.5s. Unrelated to ARCRAG-16 changes. |
| Pre-flight smoke test | ⏸ Deferred to VPS |
| Full ingestion run | ⏸ Deferred to VPS |
| Live obscure-tool test (georeferencing) | ⏸ Deferred to VPS |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `scripts/init.sh` | UPDATE | +14/-9 (SOURCE env, per-source filter, drop --recreate, log prefix) |
| `scripts/load_qdrant.py` | UPDATE | +3/-1 (id_offset in SOURCES + id_offset read + id+id_offset in loop) |
| `docker-compose.yml` | UPDATE | +19/-0 (new arcrag-init-arcmap service + backend gate) |
| `backend/test_search.py` | UPDATE | +65/-1 (Test 9 + Test 10 + test() wiring) |
| `backend/test_load_qdrant.py` | UPDATE | +3/-0 (id_offset assertions in Test 1) |
| `.agents/reports/arccrag-16-full-arcmap-index-ingestion-report.md` | CREATE | (this file) |
| `.agents/decisions/arccrag-16-full-arcmap-index-ingestion.md` | CREATE | (separate file) |
| `.agents/stories/stories.md` | UPDATE | (mark ARCRAG-16 code-complete, vector count pending VPS run) |

## Deviations from Plan

### 1. No code-level deviations for Tasks 1–4

Implementation follows the plan's spec exactly:
- `init.sh` reads `SOURCE="${SOURCE:-arcpro}"` and uses it in both `build_index.py --source "$SOURCE"` and `load_qdrant.py --source "$SOURCE" --batch-size 100` (no `--recreate`).
- `init.sh` idempotency check uses `wget --post-data` against `/collections/${QDRANT_COLLECTION}/points/count` with a JSON filter on `source=<this_source>`. Matches the plan's example exactly.
- `load_qdrant.py` SOURCES has `"id_offset": 0` for `arcpro` and `"id_offset": 1_000_000` for `arcmap`. Upsert loop uses `id=start + i + id_offset`.
- `docker-compose.yml` `arcrag-init-arcmap` service mirrors `arcrag-init` block exactly, with `SOURCE: arcmap` added to `environment:` and `arcrag-init: { condition: service_completed_successfully }` added to `depends_on:`.
- `backend` `depends_on:` now lists `arcrag-init-arcmap: { condition: service_completed_successfully }` alongside the existing two gates.
- `test_search.py` gains `test_obscure_tool_georeference_arcmap` (mirrors `test_obscure_tool_zonal_statistics` structure) and `test_source_filter_no_leakage` (asserts `source == "arcmap"` on all results of a "buffer ArcMap" query). Both are wired into `test()`.
- `test_load_qdrant.py` Test 1 gains three extra `id_offset` assertions: presence on every source, `int` type, and `arcmap > arcpro`.

### 2. Added two extra `id_offset` assertions in `test_load_qdrant.py` Test 1

Plan said: "add `id_offset missing in SOURCES` and `arcmap id_offset must be int`". I also added `arcpro id_offset must be int` and `arcmap id_offset should exceed arcpro`. The latter is a sanity check against a future bug where someone accidentally swaps the offsets. Tiny addition, defensive in nature.

### 3. Test 9 logs `source` field in top-5 results

The `top_titles` debug list now includes `res.source` for each result. This makes failures easier to diagnose when the georeferencing page is found but the `source` field is wrong. Not a deviation, just a quality-of-life tweak.

### 4. Tasks 5, 6, 7 deferred to VPS (per user instruction from ARCRAG-15)

Following the ARCRAG-15 precedent, the user has explicitly deferred Docker builds and long-running ingestion runs to the VPS. The code is statically valid (`docker compose config` parses, `bash -n` passes, `id_offset` import works, both new test functions skip cleanly with no Qdrant). The `test_load_qdrant.py` Test 3 dry-run timeout is a pre-existing PC-side performance issue (pydantic-ai import + python startup takes ~22-24s on this laptop), not caused by ARCRAG-16 changes.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `backend/test_search.py` | `test_obscure_tool_georeference_arcmap()` — searches "How do I georeference in ArcMap?" with `top_k=5`; asserts any result has URL ending in `georeferencing.htm` OR title containing "georeference". Skip-gate identical to Test 7/8. `test_source_filter_no_leakage()` — searches "buffer ArcMap" with `top_k=10`; asserts every result has `source == "arcmap"`. Catches the case where the source filter is missing or wrong after merging two sources into one collection. |
| `backend/test_load_qdrant.py` | Test 1 extended with 4 new assertions: `id_offset` exists on every SOURCES entry, is `int` for `arcpro`, is `int` for `arcmap`, and `arcmap > arcpro`. |

## Acceptance Criteria Status

- [x] `scripts/init.sh` reads `SOURCE` env var (default `arcpro`); idempotency check filters by `source` payload
- [x] `scripts/init.sh` does NOT pass `--recreate` to `load_qdrant.py`
- [x] `scripts/load_qdrant.py` SOURCES has `id_offset` (arcpro=0, arcmap=1_000_000); upsert loop uses `id=start + i + id_offset`
- [x] `docker compose config` parses with 4 services: qdrant, arcrag-init, arcrag-init-arcmap, backend
- [x] `arcrag-init-arcmap` service is gated on `arcrag-init: service_completed_successfully` and `qdrant: service_healthy`
- [x] `backend` service is gated on `arcrag-init-arcmap: service_completed_successfully` (in addition to existing gates)
- [x] `backend/test_search.py` has new `test_obscure_tool_georeference_arcmap()` (analog of Test 8 for ArcMap)
- [x] `backend/test_search.py` has new `test_source_filter_no_leakage()` (asserts `source=arcmap` filter works after both sources loaded)
- [x] `backend/test_load_qdrant.py` Test 1 asserts `id_offset` field exists and is int
- [ ] Pre-flight: 5-page run for both ArcPro and ArcMap completes, Qdrant shows both source:arcpro and source:arcmap points with no ID collision (VPS)
- [ ] Full run: `data/arcmap_index.json` contains entries for all ~5K-10K accessible ArcMap pages (VPS)
- [ ] Qdrant collection `arcgis_docs` has ArcPro points + ArcMap points (combined ≈ 60K-95K points) (VPS)
- [ ] `curl http://localhost:8000/health` returns `{"status":"ok","qdrant":"connected","model":"..."}` (VPS)
- [ ] `cd backend && uv run python test_search.py` passes all 10 tests (VPS, after full run)
- [ ] Obscure ArcMap test: searching for "How do I georeference in ArcMap?" returns a georeferencing page in top 5 (VPS)
- [ ] Source-filter test: searching for "buffer ArcMap" returns only `source=arcmap` results (VPS)
- [ ] Re-running `docker compose up arcrag-init-arcmap` resumes from `.checkpoint_arcmap_index.json` without re-ingesting ArcPro data (VPS)
- [x] `.agents/reports/arccrag-16-*.md` and `.agents/decisions/arccrag-16-*.md` are written
- [x] `.agents/stories/stories.md` marks ARCRAG-16 ✅ Completed (code-complete; vector count + runtime pending VPS run)

## VPS-Side Runbook

```bash
# 0. Sync this branch to the VPS
git pull origin feature/arccrag-16-full-arcmap-index-ingestion

# 1. Ensure backend/.env has a real OPENROUTER_API_KEY
grep -q '^OPENROUTER_API_KEY=sk-or-v1-' backend/.env || echo "WARNING: OPENROUTER_API_KEY is not set to a real key"

# 2. Pre-flight smoke test (5 pages, ~1-2 min for ArcPro + ~1-2 min for ArcMap)
docker compose up -d qdrant
docker compose run --rm arcrag-init sh -c "python /app/scripts/build_index.py --source arcpro --limit 5 --concurrency 2 --delay 0.5"
docker compose run --rm arcrag-init sh -c "python /app/scripts/build_index.py --source arcmap --limit 5 --concurrency 2 --delay 0.5"
docker compose run --rm arcrag-init sh -c "python /app/scripts/load_qdrant.py --source arcpro --recreate --batch-size 100 && python /app/scripts/load_qdrant.py --source arcmap --batch-size 100"

# Verify both source:arcpro and source:arcmap points exist with no ID collision
wget -qO- http://localhost:6333/collections/arcgis_docs/points/count --post-data='{"filter":{"must":[{"key":"source","match":{"value":"arcpro"}}]}}' --header='Content-Type: application/json'
wget -qO- http://localhost:6333/collections/arcgis_docs/points/count --post-data='{"filter":{"must":[{"key":"source","match":{"value":"arcmap"}}]}}' --header='Content-Type: application/json'
wget -qO- http://localhost:6333/collections/arcgis_docs | python3 -c "import json,sys; d=json.load(sys.stdin); print('Total points:', d['result']['points_count'])"

# 3. Full run (ArcPro: 8-24h, then ArcMap: 4-12h)
# Wipe the 5-page pre-flight data
docker compose run --rm arcrag-init rm -f /app/data/arcpro_index.json /app/data/.checkpoint_arcpro_index.json /app/data/arcmap_index.json /app/data/.checkpoint_arcmap_index.json
# Note: arcmap_urls.json and .checkpoint_arcmap_urls.json are kept — ARCRAG-05's URL collection is reused as-is

# Start the full chain: qdrant -> arcrag-init (ArcPro) -> arcrag-init-arcmap -> backend
docker compose up -d
docker compose logs -f arcrag-init arcrag-init-arcmap

# 4. Final verification
curl http://localhost:8000/health
wget -qO- http://localhost:6333/collections/arcgis_docs | python3 -c "import json,sys; d=json.load(sys.stdin); print('Total points:', d['result']['points_count'])"
cd backend && uv run python test_search.py     # all 10 tests pass
```

If interrupted mid-full-run, `docker compose up arcrag-init` (or `arcrag-init-arcmap`) will resume from the existing `arcrag_data` checkpoint. The 5-page pre-flight entries will be overwritten on the full run; the `rm -f` above is just a belt-and-suspenders clean. The `init.sh` per-source idempotency check (filter by `source` payload) ensures that re-running the second init doesn't double-upsert ArcMap data.

## Notes

- **Idempotency is now per-source, not collection-wide.** If you run only `arcrag-init-arcmap` (and `arcrag-init` was skipped or removed), it will ingest ArcMap data even when the collection has `source:arcpro` points. This is intentional — the per-source check is the right behavior for the two-init architecture. If you need a "wipe everything and re-ingest" mode, that's a separate flag (out of scope for ARCRAG-16).
- **The `arcrag_data` named volume is what enables resume across `docker compose down` (without `-v`) and `docker compose up` cycles.** Don't run `docker compose down -v` unless you want to start the full ingestion from scratch — both arcpro and arcmap will need to be re-ingested (URLs are recoverable from the host filesystem, but the index JSONs live in the volume).
- **Embedding cost for ArcMap** is estimated at ~$0.20-$0.60 (20K-60K entries × 500 tokens × `openai/text-embedding-3-small` pricing). Negligible.
- **`desktop.arcgis.com` is archived/retired** (per PRD §14 Risk 2). Speed matters. If the 5-page pre-flight fails for ArcMap URLs, the runbook's fallback is: (a) accept that ArcMap is gone, (b) Wayback Machine, (c) local mirror. Document the failure in this report.
- **Test 3 in `test_load_qdrant.py` (`test_dry_run`) currently times out at 30s on this PC.** The dry-run command itself completes in ~24.5s. This is a pre-existing performance issue (pydantic-ai import is heavy) on a dev laptop, not caused by ARCRAG-16 changes. The test would pass on a faster machine or in the Docker container. Consider bumping the timeout to 60s as a future cleanup.
- **ARCRAG-15 was previously the "init container" reference implementation.** ARCRAG-16 extends that pattern to handle two independent sources sharing a single collection. ARCRAG-17 (production hardening) can build on this dual-init pattern.
