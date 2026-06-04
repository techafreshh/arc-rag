# Decision Log & Implementation Postmortem: arccrag-06-index-builder

- **Date**: 2026-06-04
- **Branch**: `main` (merged from `feature/arccrag-06-index-builder`)
- **Report Path**: `.agents/reports/arccrag-06-index-builder-report.md`

## 1. Summary of Implementation

Implemented `scripts/build_index.py` — the second step of the ARCRAG ingestion pipeline. The script consumes the URL lists produced by ARCRAG-05 (`data/arcpro_urls.json`, `data/arcmap_urls.json`), fetches each documentation page via bounded async concurrency (semaphore=5, default 0.2s delay), parses lightweight metadata (title from `<h1>`, summary from first `<p>` > 40 chars, H2/H3 sections with sibling text, breadcrumb, image alt+absolute URL), and writes a structured JSON index with checkpoint-based resume. Follows the same `SOURCES`/checkpoint/argparse patterns as `scripts/parse_sitemaps.py` and the same async fetch + BeautifulSoup patterns as `backend/src/tools/fetch.py`.

Validation: 5-URL subset test, schema assertion, and resume (no re-fetch) all pass against real Esri doc pages.

## 2. Key Decisions & Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Apply `--limit` as a scope cap (`all_urls[:limit]`), not a batch size on remaining work** | The plan's Task 5 validation requires that `--limit 5` on resume produces *no HTTP calls* and *identical output*. A literal "truncate `remaining[:limit]`" implementation would fetch URLs 6–10 on the second run, contradicting the validation. The scope interpretation also matches the natural meaning of `--limit` (cap the test set). |
| 2 | **Also decompose `<script>` and `<style>` in `parse_page`** | The plan's Risks & Mitigations table explicitly says to do this ("Strip `<script>` and `<style>` from article in `parse_page` (mirror `fetch.py`'s nav/footer decompose)"). Defensive against script/style text leaking into section extraction. |
| 3 | **No retry logic in `fetch_html`** | Followed the plan's exact code block for `fetch_html`. The 429-retry mitigation is documented in the risks table but not in the code spec — kept the implementation minimal to match the spec exactly. If 429s become an issue during the full 16K/10K runs, retry can be added then. |
| 4 | **Repo-root anchoring via `SCRIPT_DIR.parent`** | Mirrors `parse_sitemaps.py:12-14`. Ensures data paths resolve to `<repo>/data/...` regardless of cwd. This lets the user run the script from any directory. |
| 5 | **Filter breadcrumb URL-path fallback by dropping `en` and numeric/version segments** | The plan's spec is somewhat ambiguous ("non-`en`, non-numeric (e.g., `latest` filtered out only if it appears as a version segment)"). Interpreted as: drop language segment `en` and segments matching a version pattern (`3.7` → dropped, `latest` → kept). Falls back gracefully when the Esri template's `.breadcrumb` element is absent. |
| 6 | **Checkpoint format: `{done_urls, pages, failed_urls}`** | Extends ARCRAG-05's `{urls, done_sitemaps}` pattern with a `pages` list (needed for resume — we must persist the actual scraped data, not just the set of done URLs) and a `failed_urls` set (for visibility into partial failures). `isinstance(data, dict)` check keeps the loader backward-compat with the old list-only format. |
| 7 | **Inline validation (no separate `test_build_index.py`)** | The plan's "Files to Change" table mentions `backend/test_build_index.py`, but the actual Tasks 3–5 already cover all of that file's purpose via inline shell commands (live subset run, schema assertion, resume check). Skipping the test file avoids duplication; the inline checks are the authoritative validation. |
| 8 | **Run via `uv run --directory backend`** | The `httpx`/`beautifulsoup4` dependencies live in `backend/pyproject.toml`, not the repo root. Using `--directory backend` points uv at the right project without requiring a root-level `pyproject.toml` (which doesn't exist). The script's `SCRIPT_DIR.parent` anchoring makes it cwd-independent. |

## 3. Errors & Roadblocks Encountered

| # | Error | When | Impact |
|---|-------|------|--------|
| 1 | `ModuleNotFoundError: No module named 'httpx'` on first import | Task 1 validation | Couldn't run `uv run python -c "import build_index"` from repo root. The repo has no root-level `pyproject.toml`; dependencies are in `backend/pyproject.toml`. |
| 2 | `FileNotFoundError: .../backend/scripts/build_index.py` | Task 1 validation, second attempt | `uv run --directory backend` changes cwd to `backend/`, so relative paths in `-c` resolve under `backend/`, not the repo root. |
| 3 | **Resume re-fetched different URLs (6–10 instead of skipping)** | Task 5 validation | The literal plan spec `remaining = all_urls - done_urls; remaining[:limit]` causes `--limit 5` on resume to fetch the *next* 5 un-done URLs, not skip. This violates the plan's own validation criteria ("No HTTP calls made", "data/arcpro_index.json is unchanged in content"). |
| 4 | **No branch created before starting work** | User feedback mid-implementation | Was on `main` when starting to write `scripts/build_index.py`. User asked why we weren't on a new branch. Fixed by `git checkout -b feature/arccrag-06-index-builder` mid-session — untracked files carry over to the new branch, so no work was lost. |

## 4. Workarounds & Resolutions

| # | Resolution |
|---|-----------|
| 1 | Use `uv run --directory backend python …` for any invocation that needs `httpx`/`bs4`. The script's data paths are anchored to the repo root, so cwd doesn't matter for correctness. |
| 2 | Use absolute paths in `-c "importlib.util.spec_from_file_location('build_index', '/home/.../scripts/build_index.py')"` so the loader finds the file regardless of `uv`'s `--directory` cwd change. |
| 3 | Reorder the limit application: `scope = all_urls[:limit]; remaining = [u for u in scope if u not in done_urls]`. This makes `--limit` a cap on the *scope* (first N URLs) rather than a cap on the *batch* (next N un-done). Documented as a deviation in the report. |
| 4 | Created the branch after Task 1 but before commit. Since `scripts/build_index.py` was untracked, `git checkout -b` carried it over to the new branch with no manual intervention. Commit + merge then proceeded normally on the feature branch. |

## 5. What Went Right & What Went Wrong

### What Went Right

- **Pattern reuse was high-leverage**: The plan's "Patterns to Follow" section made the implementation mechanical. Mirroring `parse_sitemaps.py` (SOURCES dict, checkpoint, argparse, repo-root anchoring) and `fetch.py` (async client, article selection, title/sections/images extraction) meant most of the design was already settled.
- **Validation caught the `--limit` bug immediately**: Running Task 5 (resume check) after the first subset run revealed that the second run fetched 5 *different* URLs. The md5 diff made the bug obvious. If validation had been deferred, the bug would have shipped.
- **User catch on the branch**: The user's "also why are we not on a new branch?" caught a procedural miss before the commit. Easy to fix mid-session because untracked files survive branch switches.
- **First-pass imports were clean**: The module imported on the first try (after fixing the `uv --directory` issue). No syntax errors, no missing imports.
- **The diff between first run and resume was byte-identical** (same md5) once the `--limit` fix was in place — confirming the checkpoint round-trips correctly.

### What Went Wrong

- **Internal contradiction in the plan**: The plan's "Implement" section says "truncate `remaining[:limit]`" but its "Validation" section requires that `--limit 5` on resume produces no fetches. These are mutually exclusive — one of them had to yield. I chose to follow the validation intent (the more user-visible spec) and documented the deviation.
- **The "Files to Change" table vs "Tasks" table mismatch**: The table lists `backend/test_build_index.py` as a CREATE, but no Task in the numbered task list creates it. I went with the Tasks section (the authoritative execution order) and skipped the test file. Worth flagging for the planner to keep these two sections in sync.
- **Two environment gotchas (httpx missing, `--directory` cwd shift)** cost 2-3 iterations before the right invocation pattern was settled. Could have been preempted by reading the repo's `pyproject.toml` layout first.

## 6. Lessons Learned & Recommendations

1. **When the plan has both an "Implement" spec and a "Validation" spec, prefer the validation spec** when they conflict — the validation is what proves correctness, and the implement spec is just one possible way to get there.
2. **The "Files to Change" table and the "Tasks" list should be kept in sync.** If a file is listed as CREATE in the table, there should be a corresponding Task. If there's a Task, the file should appear in the table.
3. **Create the feature branch *before* writing any code**, not after. Even though untracked files carry over to a new branch, committing on `main` (even accidentally via a fast-forward) is a process smell. Add a preflight check to the implement workflow.
4. **For scripts that need project-specific deps, the right invocation pattern in this repo is `uv run --directory backend python <script>`** — note this in any future plan that involves running a script outside `backend/`. A root-level `pyproject.toml` would simplify this, but adding one is out of scope for ARCRAG-06.
5. **The `--limit` semantics chosen (scope cap, not batch size) is the more intuitive one** and should be the documented behavior. If the user later wants "process the next N un-done URLs", that's a separate flag (e.g., `--batch-size` or `--skip`).
6. **The script is ready for the full run**, but full runs should be launched in `tmux`/`screen` and monitored for 429s. If 429s appear, add a single retry with 5s backoff to `fetch_html` (the plan's risks table already specifies this).
7. **Generated data files are correctly gitignored** (`data/*.json` in `.gitignore`). The checkpoint and output JSON files are local artifacts and should not be committed.
