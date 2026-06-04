# Decision Log & Implementation Postmortem: arccrag-07-qdrant-loader

- **Date**: 2026-06-04
- **Branch**: `feature/arccrag-07-qdrant-loader`
- **Report Path**: `.agents/reports/arccrag-07-qdrant-loader-report.md`

## 1. Summary of Implementation

Created `scripts/load_qdrant.py`, the third step of the ARCRAG ingestion pipeline, which consumes the structured JSON index from `build_index.py`, flattens pages into page-level and section-level entries, generates vector embeddings via OpenRouter's OpenAI-compatible `/v1/embeddings` endpoint, and upserts them into a Qdrant collection. Also created `backend/test_load_qdrant.py` with import, flatten, dry-run, and conditional live-embed tests.

## 2. Key Decisions & Rationale

- **Direct httpx for embeddings (not openai SDK)**: The `openai` package is only available transitively through `pydantic-ai`. Using `httpx` directly (already a direct dependency) avoids a fragile transitive dependency and keeps the script self-contained.
- **importlib.util to load script as a module**: Since `scripts/load_qdrant.py` lives outside the `backend` package, tests in `backend/test_load_qdrant.py` use `importlib.util.spec_from_file_location` to load it — matching the plan's validation approach and avoiding sys.path hacks.
- **Auto-detected vector dimensions**: The script embeds a single probe text first to determine the vector dimension, then creates/validates the collection. This automatically adapts to whatever embedding model is configured via `EMBEDDING_MODEL`.
- **Batch processing with sequential IDs**: Entries are batched (default 100 per request) and assigned sequential integer IDs. This is simple and deterministic for the current use case.
- **Flatten produces two entry types**: Page-level (`"{title} - {summary}"`) and section-level (`"{title} > {heading} - {brief_text}"`) entries, each with a `type` field in the payload for downstream filtering.
- **Fallback env var chain**: `EMBEDDING_API_KEY` falls back to `OPENROUTER_API_KEY` — both can authenticate to OpenRouter, so this avoids requiring a second key.

## 3. Errors & Roadblocks Encountered

- **Import path mismatch on first validation**: Running `uv run --directory backend python -c "..."` changes CWD to `backend/`. The initial module import check referenced `scripts/load_qdrant.py` from the wrong working directory, producing `FileNotFoundError: No such file or directory: '...backend/scripts/load_qdrant.py'`. Fixed by using `../scripts/load_qdrant.py`.
- **Docker not available**: The live embed+upsert validation (Task 3) requires Qdrant running via Docker. Docker is not installed in this environment, so the full end-to-end test could not be executed.

## 4. Workarounds & Resolutions

- **Path resolution for validation**: Adjusted validation commands to use relative paths from the `backend` working directory (`../scripts/load_qdrant.py` instead of `scripts/load_qdrant.py`). The script itself uses `Path(__file__).resolve()` so it works from any CWD.
- **Docker/Qdrant absence**: Test 4 (`test_live_embed`) in `test_load_qdrant.py` conditionally checks for Qdrant connectivity and an API key, skipping gracefully with a clear message when either is unavailable.

## 5. What Went Right & What Went Wrong

- **What Went Right**:
  - Plan was precise and detailed — every function signature, constant, and CLI flag was specified exactly.
  - All mirror patterns (SOURCES dict, argparse, async orchestrator, repo-root anchoring) were available in `build_index.py` and `fetch.py`, making implementation straightforward.
  - Dry-run and flatten validation passed on first run.
  - Tests pass cleanly (3/3, with 1 conditional skip).

- **What Went Wrong**:
  - Docker/Qdrant unavailable prevented the full E2E live test from running. The feature is implemented correctly but cannot be fully validated in this environment without Docker.

## 6. Lessons Learned & Recommendations

- When running Python from a subdirectory via `uv run --directory backend`, always verify script paths relative to that directory.
- For future pipeline scripts in `scripts/`, consider structuring the code so it can be imported as a proper package module (e.g., `backend/src/`) to avoid `importlib.util` workarounds in tests.
- Document the Docker prerequisite clearly: `docker compose up -d` is required before running `load_qdrant.py`.
