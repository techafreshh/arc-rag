# Decision Log & Implementation Postmortem: arccrag-15-full-arcpro-index-ingestion

- **Date**: 2026-06-06
- **Branch**: `feature/arccrag-15-full-arcpro-index-ingestion`
- **Report Path**: `.agents/reports/arccrag-15-full-arcpro-index-ingestion-report.md`
- **Status**: Code complete; VPS-side runtime validation deferred per user instruction.

## 1. Summary of Implementation

Implemented the Docker Compose init container pattern for ARCRAG-15 — a one-shot `arcrag-init` service that runs `build_index.py` then `load_qdrant.py --recreate` against the existing `data/arcpro_urls.json` (16,419 URLs from ARCRAG-05), plus a `backend` service (FastAPI) gated on the init container's success. A new named volume `arcrag_data` mounts `/app/data` in both services so the checkpoint survives restarts. Added the 429 retry to `build_index.py` that ARCRAG-06's postmortem flagged as a gap. Added the obscure-tool test (Zonal Statistics as Table) that ARCRAG-15's acceptance criteria call out.

Code is complete and statically validated (`docker compose config` parses, modules import, `test_search.py` passes unit-style tests, Qdrant-dependent tests skip gracefully). Docker image build + 5-page pre-flight + 8-24h full run are deferred to the VPS per user instruction.

## 2. Key Decisions & Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **`fetch_html` retry uses an explicit `for attempt in range(2)` loop, not a separate `retries` parameter** | The plan said "mirror the simple retry style of `parse_sitemaps.py:38-50`" but that function uses `httpx.get` synchronously. The async version is cleaner with a simple `for/continue` because we need to `await asyncio.sleep(5)`. 2 iterations = 1 initial + 1 retry, matching the plan's "1 retry" spec. |
| 2 | **`init.sh` polls Qdrant for up to 5 minutes (60 × 5s)** | The plan doesn't specify a timeout. 5 min is enough for any normal Qdrant boot; the failure path is loud (`exit 1` with an error message) rather than silent. Trivial to bump later. |
| 3 | **`init.sh` idempotency check uses the Qdrant REST API directly** | The plan's spec: "If `arcgis_docs` collection has points, skip ingestion and exit 0". The check is `GET /collections/arcgis_docs` and parses `result.points_count`. This is the authoritative source of truth (not the local JSON files, which could be stale or partial). |
| 4 | **`arcrag-init` uses `restart: "no"`** | Per the plan's spec. Init containers are one-shot; if they fail, you want to see the failure and re-investigate, not silently retry forever. Re-runs are explicit `docker compose up arcrag-init` invocations. |
| 5 | **`backend` service mounts `arcrag_data` at `/app/data`** | The backend itself doesn't read `/app/data` directly (it talks to Qdrant), but mounting the volume keeps the data path consistent and lets the backend be debugged (e.g., `docker compose exec backend ls /app/data`) in the same layout as the init container. No cost; small ergonomic win. |
| 6 | **`docker-compose.yml` injects `QDRANT_URL=http://qdrant:6333` explicitly in environment** | `env_file: backend/.env` brings in `QDRANT_URL` (which currently points at `http://localhost:6333`). Inside the Docker network, the hostname is `qdrant`, not `localhost`. Setting the override in the compose `environment:` block is the standard way to redirect inter-service DNS without touching the `.env` file. |
| 7 | **`init.sh` runs build_index before load_qdrant sequentially** | Per the plan's spec. The order matters: `load_qdrant.py` reads `data/arcpro_index.json` (the build's output). Running them in parallel would be a data race. |
| 8 | **Test 8 uses a substring match on URL suffix AND a `lower()` substring match on title** | The plan: "asserts the top-5 results contain a URL ending in `zonal-statistics-as-table.htm` (or has 'Zonal Statistics' in title)". The OR is implemented as `target_suffix in result.url.lower() or "zonal statistics" in result.title.lower()`. Lowercasing the URL handles `ZONAL-STATISTICS-AS-TABLE.HTM` (the URL is case-insensitive in HTTP, even if Esri serves it lowercase). |
| 9 | **Dockerfile installs `cachetools`** | Not in the repo's root `pyproject.toml` (only `pydantic-ai, fastapi, uvicorn, httpx, beautifulsoup4, qdrant-client, python-dotenv`), but `backend/src/tools/fetch.py:5` does `from cachetools import TTLCache`. It's installed transitively in the dev `.venv` via `pydantic-ai`'s dep tree, but the Docker image is built from scratch and would fail at import time without it. The plan's Dockerfile spec explicitly includes `cachetools` — followed exactly. |

## 3. Errors & Roadblocks Encountered

| # | Error | When | Impact |
|---|-------|------|--------|
| 1 | User interrupted the `docker build` command mid-run | After writing `backend/Dockerfile` | User said: "we're on my pc not the vps, don't build the docker container here". No code was lost (no edits to recover from). Marked Tasks 6, 7, 8 as deferred-to-VPS. |
| 2 | (Anticipated) `OPENROUTER_API_KEY=dummy` in `backend/.env` will fail on the VPS | Not yet observed | The plan's Open Questions section flagged that `backend/.env` exists and "assumes it contains `OPENROUTER_API_KEY`". Currently it contains `dummy`. Documented in the report's VPS-Side Runbook that the real key needs to be set on the VPS before `docker compose up`. |

## 4. Workarounds & Resolutions

| # | Resolution |
|---|-----------|
| 1 | Deferred Docker build, pre-flight smoke test, and full ingestion run to the VPS. Code is statically validated to the extent possible on the PC. |
| 2 | Documented the env-file requirement prominently in the implementation report's "VPS-Side Runbook" section. Will be re-emphasized in the Jira comment. |

## 5. What Went Right & What Went Wrong

### What Went Right

- **Pattern reuse from earlier ARCRAG tickets is paying off**: the "Patterns to Follow" section in the plan was accurate and the implementation was mechanical. Mirroring `parse_sitemaps.py` (retry style) and `load_qdrant.py` (Qdrant client setup, env handling) meant most of the design was already settled.
- **`docker compose config` validates the YAML without needing to actually build the images** — this is a great static check that's now part of the validation suite.
- **The Qdrant healthcheck + `condition: service_healthy` pattern is the right way to gate the init container** — it eliminates the race where init starts before Qdrant's REST API is ready. The init.sh also has its own poll loop, which is belt-and-suspenders but cheap.
- **The 429 retry is minimal and correct**: 1 attempt, 5s sleep, no exponential backoff. This matches ARCRAG-06's "minimal match the spec" pattern and doesn't introduce a new failure mode (e.g., very long pauses if the server is hard-blocking).
- **The test 8 logic handles the case where the test runs before/after the full index is loaded**: the Qdrant + API key gate means it skips cleanly when prerequisites aren't met, but asserts strictly when they are.

### What Went Wrong

- **Had to interrupt the Docker build** because it was happening on the user's PC, not the VPS. Should have asked about the deployment target before starting Task 2. The build itself was working (it was waiting on pip install of `pydantic-ai[openrouter]`), but running a multi-GB image build on a dev laptop is wasteful when the target is a VPS.
- **The `OPENROUTER_API_KEY=dummy` issue is going to bite on first VPS run**. The plan flagged it as an "open question / assumption" but didn't include a "rotate the dummy key" step. I should have proactively added a step in the runbook to verify the key is real before the first run.
- **The plan's Task 7 says to delete `data/arcpro_index.json` and `.checkpoint_arcpro_index.json` before the full run** to avoid 5-page pollution. The `init.sh` idempotency check (Qdrant points_count > 0) does NOT catch this case (the JSON files could be partial and the collection could be empty). I documented this as a "belt-and-suspenders" cleanup in the report, but a cleaner design would have init.sh itself detect a partial JSON file and refuse to skip.

## 6. Lessons Learned & Recommendations

1. **Ask about deployment target before writing Dockerfiles.** A "where will this run?" question at the top of the implement workflow would have saved the user from a wasted build.
2. **For plans that involve long-running data ingestion, the implementation should include a pre-flight env-validation step.** Even just a `grep -q '^OPENROUTER_API_KEY=sk-or-v1-' backend/.env` in `init.sh` would catch the `dummy` key issue with a clear error message.
3. **The `arcrag-init` idempotency check should probably check both the local JSON completeness AND the Qdrant points count.** The current check is sufficient for "restart after a successful run", but a partial local JSON (5 pages from a smoke test) plus an empty Qdrant collection would NOT skip — the init would re-run and overwrite the 5 pages. This is the correct behavior in most cases but worth a `force` flag if the user wants to be explicit.
4. **The Docker image build for `pydantic-ai[openrouter]` is heavy** (multiple large transitive deps: `pydantic`, `pydantic-ai`, `openai`, `httpx`, etc.). Consider a multi-stage build later to slim the production image, or a `requirements.txt` lockfile to make the build reproducible. Out of scope for ARCRAG-15.
5. **Document the `arcrag_data` volume lifecycle** prominently. A user running `docker compose down -v` to "clean up" would silently nuke their checkpoint and force a re-ingestion. The report's "Notes" section flags this, but a one-liner in the README would be even better.
6. **The `init.sh` script should be idempotent at the *script* level, not just the *Qdrant collection* level.** That means it should refuse to start if the local JSON is in a weird state. (Current behavior: just runs and overwrites — usually fine, but a real "production" version would refuse + ask for a `--force` flag.)
7. **When a plan defers runtime validation to a different environment, the report must include a runbook with exact commands and env prerequisites.** I added this to the report, but it should be a standard section in any deferred-validation implementation report.
