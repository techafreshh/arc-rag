# Decision Log & Implementation Postmortem: arccrag-08-search-tool

- **Date**: 2026-06-04
- **Branch**: `feature/arccrag-08-search-tool`
- **Report Path**: `.agents/reports/arccrag-08-search-tool-report.md`

## 1. Summary of Implementation

Built the `search_index` agent tool for semantic search against the Qdrant documentation index. Extracted the shared OpenRouter embeddings client (`embed_batch`, `embed_query`) from `scripts/load_qdrant.py` into a new `backend/src/embed.py` module. Registered `search_index` as an `@agent.tool` in `backend/src/agent.py` with an updated system prompt that prefers it over `lookup_url`. Added `summary` field to page-level payloads in `load_qdrant.py`. Created `scripts/__init__.py`. Wrote `backend/test_search.py` with 6 always-passing tests and 1 conditional live test.

## 2. Key Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Extract `embed_batch`/`embed_query` into shared `embed.py` | Avoid duplication between ingestion (`load_qdrant.py`) and search (`search.py`); single source of truth for OpenRouter embedding config |
| Use `sys.path.insert` shim in `load_qdrant.py` | Script runs directly (`python scripts/load_qdrant.py`), not as a package module; shim enables `from src.embed import ...` without restructuring the project |
| URL deduplication by keeping best score per URL | Section-level and page-level entries share the same URL; agent only needs one link per page, so collapse duplicates preserving the highest-relevance match |
| Keyword-based source filter for "arcmap" | Simple, fast, no external dependency; only triggers on explicit ArcMap mentions to avoid false positives in mixed queries |
| Fallback chain for empty `summary` field | Old ingested data (pre-refactor) lacks `summary` in payload; fall back to `section` then `title` so search still returns useful context |
| Fresh `httpx.AsyncClient` per search call | Acceptable overhead at low QPS; avoids client lifecycle management complexity; can be optimized later with shared client pool |
| Keep `lookup_url` as fallback | Maintains backward compatibility for well-known tool shortcuts; agents can still use it when search_index fails or returns no results |

## 3. Errors & Roadblocks Encountered

1. **`load_qdrant.py` import validation failed** — The plan's validation command used `importlib.util.spec_from_file_location('load_qdrant', 'scripts/load_qdrant.py')` from the `backend/` working directory. The relative path resolved to `backend/scripts/load_qdrant.py` which doesn't exist.

2. **`Agent` object has no public `.tools` attribute** — The installed version of `pydantic-ai` does not expose `agent.tools`. The `@agent.tool` decorator registers tools internally via `_function_toolset`, but there is no public iteration API. Internal `get_tools(ctx)` requires a valid `RunContext` object which is only available during an active run.

3. **E2E test fails with 401 Authentication Error** — `test_e2e.py` checks `if not OPENROUTER_API_KEY: print("SKIP")`, but the `.env` file contains `OPENROUTER_API_KEY=dummy` (a non-empty invalid value), so the skip is bypassed and the agent attempts a real API call that fails.

4. **No lint/build commands configured** — The project has `pyproject.toml` with no lint (ruff, flake8, pylint) or type-check (mypy, pyright) configuration. No `pnpm run lint` or `pnpm run build` commands exist.

5. **Qdrant not available in environment** — Tests 6 and 7 (Qdrant unreachable / live search) cannot be fully exercised without a running Qdrant instance.

## 4. Workarounds & Resolutions

| Roadblock | Resolution |
|-----------|------------|
| `load_qdrant.py` relative path issue | Used absolute path `/home/techafresh/projects/arcpro-docs/scripts/load_qdrant.py` in the validation command |
| No `agent.tools` attribute | Verified tool registration by: (a) confirming `@agent.tool` decorator succeeds on import, (b) checking function callability via `inspect.iscoroutinefunction`, (c) running agent CLI initialization |
| Invalid dummy API key in `.env` | Accepted as pre-existing condition; E2E test requires valid credentials and is marked as conditional in the plan |
| No lint infrastructure | Validated via Python import checks and test execution as a substitute; noted as a project-level gap |
| Qdrant unavailable | Tests 1-5 (import, models, source detection, dedupe, empty query) are stateless and pass; Tests 6 (unreachable) passes because connection is refused; Test 7 (live) gracefully skips |

## 5. What Went Right & What Went Wrong

- **What Went Right**:
  - All stateless unit tests pass on first run (import check, model validation, source detection, deduplication, empty query handling)
  - `load_qdrant.py` refactor clean — existing tests (`test_load_qdrant.py`) pass with no regressions
  - Agent initialization succeeds with all 3 tools registered (search_index, fetch_page, lookup_url)
  - `summary` field added to page-level payload without breaking existing payload structure
  - Task implementation order was well-defined — each file built on the previous one cleanly

- **What Went Wrong**:
  - Plan's validation command for `agent.tools` did not match the actual pydantic-ai API version in the project
  - Plan's `load_qdrant.py` validation assumed `uv run --directory backend` could resolve a relative `scripts/` path, which doesn't work because the scripts directory is at the project root, not inside `backend/`
  - E2E test cannot run due to invalid API key in pre-existing `.env` — this would have been caught earlier if the E2E test was run during the initial project setup
  - No automated lint or type-checking in CI/development workflow

## 6. Lessons Learned & Recommendations

1. **Validate validation commands against the actual codebase before writing plans** — The `agent.tools` and `load_qdrant.py` path assumptions in the plan did not match reality. Plans should reference the exact pydantic-ai API version and understand the directory layout.

2. **Pin version-specific API patterns** — `pydantic-ai` is actively developed. Document which version is used and verify tool registration pattern matches that version's API.

3. **Add lint and type-checking infrastructure** — Install `ruff` for linting and `mypy` or `pyright` for type checking. Add them to `pyproject.toml` and a CI workflow. This catches issues early and provides consistent code quality.

4. **Test E2E with real credentials before cutting a release** — The E2E test is the highest-value integration test. Ensure a valid API key and running Qdrant are available in the CI environment.

5. **Consider shared `httpx.AsyncClient` instance** — For production use, a shared client pool (or at least connection reuse) would reduce latency on every search call. Defer to a future optimization story.

6. **Scripts that import from `backend.src` should use a consistent path strategy** — The `sys.path.insert` shim works but is fragile. Consider making `scripts/` a proper package or using `PYTHONPATH` in a wrapper script.
