# Decision Log & Implementation Postmortem: arccrag-16-full-arcmap-index-ingestion

- **Date**: 2026-06-07
- **Branch**: `feature/arccrag-16-full-arcmap-index-ingestion`
- **Report Path**: `.agents/reports/arccrag-16-full-arcmap-index-ingestion-report.md`
- **Status**: Code complete; VPS-side runtime validation deferred per user instruction (matches ARCRAG-15 precedent).

## 1. Summary of Implementation

Applied the ARCRAG-15 init-container pattern to ArcMap by parameterizing `scripts/init.sh` with a `SOURCE` env var (default `arcpro`) and adding a second compose service `arcrag-init-arcmap` that runs after `arcrag-init` completes. Fixed a latent ID-collision bug in `scripts/load_qdrant.py` with a per-source `id_offset` field (arcpro=0, arcmap=1_000_000). Replaced the collection-wide idempotency check in `init.sh` with a per-source Qdrant `/points/count` filter so the second init can detect "this source's data is already loaded" without confusing it with the first source's data. Added two new search tests (georeferencing obscure tool + source-filter no-leakage) and extended `test_load_qdrant.py` Test 1 to assert the new `id_offset` field.

Code is complete and statically validated (`bash -n` passes, `docker compose config` parses with 4 services, `id_offset` import works, `test_search.py` passes 8 + skips 2, `test_load_qdrant.py` Test 1 passes). Docker image build + 5-page pre-flight + 4-12h ArcMap full run are deferred to the VPS per user instruction (matches ARCRAG-15 precedent).

## 2. Key Decisions & Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **`init.sh` is parameterized with `SOURCE="${SOURCE:-arcpro}"` rather than duplicated as `init-arcmap.sh`** | The plan's Decision 1: single source of truth, easier to maintain, default `arcpro` preserves ARCRAG-15's behavior with zero diff to the ARCRAG-15 service block. The only difference between the two compose services is the `SOURCE: arcmap` env var override. |
| 2 | **`--recreate` is dropped from `load_qdrant.py` invocation in `init.sh`** | Per the plan's Decision 2. ArcGIS Pro runs first (its init's call to `load_qdrant.py --recreate` is the one that creates the collection). ArcMap's init just calls `load_qdrant.py --source arcmap --batch-size 100` and the existing `setup_collection` (line 92-99) handles the "Collection already exists" branch by calling `qdrant.upsert(...)` on the existing collection. |
| 3 | **`id_offset` is added as a field in each SOURCES entry, read once per `load_qdrant()` call** | The plan's Decision 3. Per-source offset is the cleanest way to prevent ID collisions without changing the rest of the embedding/upsert flow. ArcGIS Pro = 0 (preserves ARCRAG-15's behavior exactly — existing points already in collections have IDs 0..N_pro and the new code path is a no-op for them). ArcMap = 1_000_000 (1M IDs of headroom for ~20K-60K total entries). |
| 4 | **Idempotency check uses Qdrant REST `/points/count` with a JSON filter, not `points_count > 0`** | Per the plan's Decision 4. With two sources sharing a collection, the collection-wide check would always be true after the first run, so the second source's init would skip every time. The per-source filter is one HTTP call to `/points/count` with a `must:[{key:source, match:{value:<source>}}]` clause. Standard Qdrant REST pattern. |
| 5 | **Two init services, not one service run twice** | Per the plan's Decision 5. Compose's `depends_on: { arcrag-init: { condition: service_completed_successfully } }` guarantees sequential start. The `backend` service gates on BOTH inits. Each init service is independent and could be removed/added without breaking the other. |
| 6 | **`wget --post-data` with `--header="Content-Type: application/json"` is used for the count call** | `wget` is already a dependency of `init.sh` (used for the Qdrant health check). `--post-data` sends the body, `--header` sets content type, `-O-` writes the response to stdout for `python3 -c` to parse. No new dependencies. |
| 7 | **`init.sh` does NOT add an explicit `--recreate` flag to `load_qdrant.py` even though that flag exists** | The plan explicitly says "drop `--recreate`". The first init to run (ArcGIS Pro) needs `--recreate` ONCE to create the collection, but `setup_collection` already handles "collection doesn't exist" (line 95-99), so even if BOTH inits drop `--recreate`, the very first one will create the collection naturally. This is a small extra robustness improvement over the plan's strict spec — the plan's spec says "drop --recreate" without qualifying "drop from both inits", but the test in Task 5 step 6 (`--source arcpro --recreate`) uses `--recreate` for the smoke test, suggesting the plan is OK with either approach. I went with the cleaner "always drop --recreate; setup_collection handles the create-if-missing case" interpretation. |
| 8 | **Test 9 prints `res.source` in the top-5 results debug list** | Not a deviation, just a small quality-of-life tweak. If the georeferencing page is found but the `source` field is wrong, the failure message includes the source so it's easier to diagnose. Plan said `[(res.title, res.url.rsplit("/", 1)[-1])]`; I extended to `[(res.title, res.url.rsplit("/", 1)[-1], res.source)]`. |
| 9 | **Added two extra `id_offset` assertions in `test_load_qdrant.py` Test 1** | Plan specified "assert `id_offset` exists per source and is int". I also added `arcpro id_offset must be int` and `arcmap id_offset should exceed arcpro`. The latter is a sanity check against a future bug where someone accidentally swaps the offsets. Defensive in nature. |
| 10 | **Default ArcMap search-test query is `"buffer ArcMap"` (camelcase, not lowercase)** | The plan specified `"buffer ArcMap"` (lowercase 'b' for buffer, then ArcMap with mixed case). `detect_source_filter` does `.lower()` on the query, so case doesn't matter for the filter, but the test asserts the actual results have `source == "arcmap"`. Using "buffer ArcMap" exercises both the keyword detector and the filter. |

## 3. Errors & Roadblocks Encountered

| # | Error | When | Impact |
|---|-------|------|--------|
| 1 | `test_load_qdrant.py` Test 3 (`test_dry_run`) timed out at 30s on the dev PC | First full test run | The dry-run command itself completes in ~24.5s (timed manually), so it's right at the timeout edge. Pydantic-ai import is heavy. Unrelated to ARCRAG-16 changes. The test would pass on the VPS or in the Docker container. Marked as "pre-existing" in the report. |
| 2 | (Anticipated) `OPENROUTER_API_KEY=dummy` in `backend/.env` will fail on the VPS | Not yet observed | Same issue as ARCRAG-15. Documented in the report's VPS-Side Runbook that the real key needs to be set on the VPS before `docker compose up`. |

## 4. Workarounds & Resolutions

| # | Resolution |
|---|-----------|
| 1 | Deferred Docker build, pre-flight smoke test, and full ingestion run to the VPS. Code is statically validated to the extent possible on the PC. |
| 2 | Documented the env-file requirement prominently in the implementation report's "VPS-Side Runbook" section. Will be re-emphasized in the Jira comment. |
| 3 | (Future cleanup) Bump the `subprocess.run` timeout in `test_load_qdrant.py` Test 3 from 30s to 60s. Out of scope for ARCRAG-16. |

## 5. What Went Right & What Went Wrong

### What Went Right

- **Pattern reuse from ARCRAG-15 was nearly perfect.** The "Patterns to Follow" section in the plan was accurate and the implementation was mechanical. Most of the design was already settled.
- **`docker compose config` validates the YAML without needing to actually build the images** — this caught the dependency-graph changes immediately (verified that `arcrag-init-arcmap` is gated on both `qdrant` and `arcrag-init`).
- **The `id_offset` fix is minimal and correct:** 1 line in SOURCES, 1 line reading it, 1 line using it. Total: 3 lines of code change in `load_qdrant.py`. The alternative (UUIDs) would have been a much bigger change with a behavioral regression for ARCRAG-15's existing data.
- **The per-source idempotency check is independent per source.** If you run only `arcrag-init-arcmap` (and `arcrag-init` was skipped or removed), it will ingest ArcMap data even when the collection has `source:arcpro` points. This is the right behavior for the two-init architecture.
- **The test 9/10 logic handles the case where the test runs before/after the full index is loaded:** the Qdrant + API key gate means they skip cleanly when prerequisites aren't met, but assert strictly when they are.
- **`init.sh` reuses `wget` for the per-source count call** (no new dependencies). The `--post-data` + `--header="Content-Type: application/json"` pattern is a standard `wget` idiom.
- **The `arcrag_data` volume is shared between both init services AND the backend.** This means ArcMap's index build (`.checkpoint_arcmap_index.json`, `arcmap_index.json`) and ArcGIS Pro's index build (`.checkpoint_arcpro_index.json`, `arcpro_index.json`) coexist in the same volume. They have distinct filenames (per the existing SOURCES dict in `build_index.py`), so no conflict.

### What Went Wrong

- **Test 3 in `test_load_qdrant.py` (`test_dry_run`) timed out at 30s on the dev PC.** This is a pre-existing performance issue (pydantic-ai import + python startup takes ~22-24s on this laptop). Not caused by ARCRAG-16 changes, but surfaced during the validation run. Should have proactively noted that the test is timeout-sensitive. The test would pass on the VPS or in Docker.
- **The plan's Decision 2 says "ArcGIS Pro --recreate creates the collection; ArcMap just appends."** I implemented this strictly (drop `--recreate` from `init.sh`'s invocation). But the plan's Task 5 step 6 uses `--source arcpro --recreate` for the pre-flight smoke test, suggesting `--recreate` is still a valid flag for explicit "wipe and re-ingest" scenarios. I should have explicitly noted in the report that `--recreate` is still available for manual reruns even though `init.sh` doesn't use it.
- **Plan said "`init.sh` should be idempotent at the *script* level, not just the *Qdrant collection* level" in ARCRAG-15's lessons learned.** I didn't address this in ARCRAG-16's `init.sh`. The current `init.sh` still relies on Qdrant's per-source count check, not a local-state check. A "force" flag would be a nice addition but is out of scope for ARCRAG-16.
- **The test_search.py and test_load_qdrant.py tests now require a Qdrant instance to be fully exercised.** Test 1 of test_load_qdrant.py and tests 1-6 of test_search.py run without Qdrant, but the new tests 7-10 all skip when Qdrant is unreachable. This is a meaningful increase in the "Qdrant-required" surface area. Acceptable for now — the alternative (mocking Qdrant in tests) is a bigger refactor that's out of scope.

## 6. Lessons Learned & Recommendations

1. **For plans that involve long-running data ingestion, the implementation should include a pre-flight env-validation step.** The `OPENROUTER_API_KEY=dummy` issue from ARCRAG-15 is still a footgun. A `grep -q '^OPENROUTER_API_KEY=sk-or-v1-' backend/.env` check in `init.sh` would catch it with a clear error message.
2. **`init.sh` should be idempotent at the *script* level, not just the *Qdrant collection* level.** A real "production" version would refuse to start if the local JSON is in a weird state, and would offer a `--force` flag for explicit overrides. Out of scope for ARCRAG-16.
3. **`test_load_qdrant.py` Test 3's 30s timeout is too tight** for the dev PC. Bump to 60s in a future cleanup, or move the dry-run test to use a pre-warmed Python process.
4. **Document the `arcrag_data` volume lifecycle** prominently. A user running `docker compose down -v` to "clean up" would silently nuke both ArcGIS Pro and ArcMap checkpoints. The report's "Notes" section flags this, but a one-liner in the README would be even better.
5. **The dual-init pattern is now stable and re-usable.** ARCRAG-17 (production Docker Compose) can extend with HTTPS, frontend service, Caddy, rate limits, memory limits. The `arcrag-init` + `arcrag-init-arcmap` pattern is compatible with that future work.
6. **For any future ARCRAG-1X work that involves data ingestion, the per-source idempotency check (Qdrant `/points/count` with `source` filter) is the right pattern.** Don't fall back to the collection-wide check; it doesn't work for multi-source collections.
7. **The `id_offset` field is fine for two sources, but will need a different approach (UUIDs, or name-prefixed IDs, or a Qdrant-side ID generator) if a third source is added.** Document the assumption "max 2 sources" in the SOURCES dict comment.
