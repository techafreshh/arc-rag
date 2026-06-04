# Plan: ARCRAG-06 — Index Builder Script

## Summary

Create `scripts/build_index.py` that consumes the URL lists produced by ARCRAG-05 (`data/arcpro_urls.json`, `data/arcmap_urls.json`), fetches each documentation page via bounded async concurrency, parses lightweight metadata (title, first-paragraph summary, H2/H3 sections, breadcrumb, image alt+URL), and writes a structured JSON index with checkpoint-based resume. The script is the second step of the ingestion pipeline (sitemap → URLs → metadata → embeddings → Qdrant) and must follow the same checkpoint/SOURCES/argparse patterns established in `scripts/parse_sitemaps.py`.

## User Story

As a developer
I want a script that scrapes page titles, summaries, section headings, and image metadata from each documentation URL
So that I can build the thin index for semantic search

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | LARGE |
| Systems Affected | Scripts, Data |
| Jira Issue | ARCRAG-06 |
| Blocked By | ARCRAG-05 (completed) |

---

## Patterns to Follow

### SOURCES dict config (mirrors parse_sitemaps.py)
```python
# SOURCE: scripts/parse_sitemaps.py:17-36
SOURCES = {
    "arcpro": {
        "sitemap_entry": "https://doc.esri.com/sitemap.xml",
        "guide_filters": ["/arcgis-pro/", "/en/arcgis-pro/"],
        "output": str(PROJECT_DIR / "data/arcpro_urls.json"),
        "checkpoint": str(PROJECT_DIR / "data/.checkpoint_arcpro_urls.json"),
        "path_filter": "/en/arcgis-pro/",
        "exclude_filters": ["/sdk/"],
        "delay": 0.5,
    },
    "arcmap": { ... },
}
```

### Checkpoint load/save with backward-compat
```python
# SOURCE: scripts/parse_sitemaps.py:62-76
def load_checkpoint(path: str) -> tuple[set[str], set[str]]:
    checkpoint_file = Path(path)
    if checkpoint_file.exists():
        data = json.loads(checkpoint_file.read_text())
        if isinstance(data, dict):
            return set(data.get("urls", [])), set(data.get("done_sitemaps", []))
        return set(data), set()
    return set(), set()

def save_checkpoint(path: str, urls: set[str], done_sitemaps: set[str]):
    Path(path).write_text(json.dumps({
        "urls": sorted(urls),
        "done_sitemaps": sorted(done_sitemaps),
    }, indent=2))
```

### Async HTTP fetch with redirects (proven in fetch.py)
```python
# SOURCE: backend/src/tools/fetch.py:36-37
async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
    resp = await client.get(url)
```

### HTML container selection
```python
# SOURCE: backend/src/tools/fetch.py:49-54
article = soup.find("article", id="main") or soup.find("main") or soup.find("article")
if not article:
    return PageContent(..., error="No main content found")
for tag in article.find_all(["nav", "footer"]):
    tag.decompose()
```

### Title extraction
```python
# SOURCE: backend/src/tools/fetch.py:56-57
title_tag = article.find("h1")
title = title_tag.get_text(strip=True) if title_tag else ""
```

### H2 section extraction (sibling traversal)
```python
# SOURCE: backend/src/tools/fetch.py:67-75
for h2 in article.find_all("h2"):
    parts = []
    for sib in h2.next_siblings:
        if sib.name == "h2":
            break
        text = sib.get_text(separator="\n", strip=True) if hasattr(sib, "get_text") else str(sib).strip()
        if text:
            parts.append(text)
    sections.append(Section(heading=h2.get_text(strip=True), content="\n".join(parts)))
```

### Image extraction with absolute URL resolution
```python
# SOURCE: backend/src/tools/fetch.py:59-62
images = [
    ImageInfo(url=urljoin(base_url, img.get("src", "")), alt=img.get("alt", ""))
    for img in article.find_all("img") if img.get("src")
]
```

### Argparse CLI shape
```python
# SOURCE: scripts/parse_sitemaps.py:171-180
def main():
    parser = argparse.ArgumentParser(description="Parse ArcGIS documentation sitemaps")
    parser.add_argument(
        "--source", required=True, choices=["arcpro", "arcmap"],
        help="Which documentation source to parse",
    )
    args = parser.parse_args()
    parse(args.source)

if __name__ == "__main__":
    main()
```

### Repo-root anchoring (prevents backend/data/ mistake)
```python
# SOURCE: scripts/parse_sitemaps.py:12-14
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
(PROJECT_DIR / "data").mkdir(exist_ok=True)
```

### Standalone test script pattern
```python
# SOURCE: backend/test_fetch.py:1-20
import asyncio
from src.tools.fetch import fetch_page

async def test():
    url = 'https://pro.arcgis.com/en/pro-app/latest/tool-reference/analysis/buffer.htm'
    r = await fetch_page(url)
    print(f'Title: {r.title}')
    assert r.title, "No title extracted"
    assert r.sections, "No sections extracted"
    assert not r.error, f"Unexpected error: {r.error}"
    print('PASS - live fetch')

if __name__ == "__main__":
    asyncio.run(test())
```

### Error handling: graceful field, not raise
```python
# SOURCE: backend/src/tools/fetch.py:38-44
except httpx.TimeoutException:
    return PageContent(url=url, title="", sections=[], images=[], code_blocks=[], error="Timeout fetching page")
except Exception as e:
    return PageContent(url=url, title="", sections=[], images=[], code_blocks=[], error=str(e))
```

### Branch + commit convention
- Branch: `feature/arccrag-06-index-builder`
- Commit prefix: `feat: ...` (matches recent history: `feat: add ARCRAG-04 plan/report and ARCRAG-05 sitemap parser`)

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `scripts/build_index.py` | CREATE | Async index builder with semaphore, parsing, checkpoint resume, --limit flag |
| `data/arcpro_index.json` | GENERATED | ~16K ArcGIS Pro page metadata entries |
| `data/arcmap_index.json` | GENERATED | ~10K ArcMap page metadata entries |
| `data/.checkpoint_arcpro_index.json` | GENERATED | Resume checkpoint for ArcGIS Pro |
| `data/.checkpoint_arcmap_index.json` | GENERATED | Resume checkpoint for ArcMap |
| `backend/test_build_index.py` | CREATE | Validation: run with --limit 5, assert schema, confirm resume works |
| `.agents/plans/completed/arccrag-06-index-builder.plan.md` | CREATE | This plan file |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Create build_index.py with config, parsers, and orchestrator

- **File**: `scripts/build_index.py`
- **Action**: CREATE
- **Implement**:
  - **Imports**: `argparse`, `asyncio`, `json`, `sys`, `time` from stdlib; `httpx`, `bs4.BeautifulSoup`; `pathlib.Path`
  - **Constants**:
    - `SCRIPT_DIR = Path(__file__).resolve().parent`
    - `PROJECT_DIR = SCRIPT_DIR.parent`
    - `(PROJECT_DIR / "data").mkdir(exist_ok=True)`
  - **SOURCES dict** with two entries:
    ```python
    SOURCES = {
        "arcpro": {
            "urls_json": str(PROJECT_DIR / "data/arcpro_urls.json"),
            "output": str(PROJECT_DIR / "data/arcpro_index.json"),
            "checkpoint": str(PROJECT_DIR / "data/.checkpoint_arcpro_index.json"),
            "source": "arcpro",
        },
        "arcmap": {
            "urls_json": str(PROJECT_DIR / "data/arcmap_urls.json"),
            "output": str(PROJECT_DIR / "data/arcmap_index.json"),
            "checkpoint": str(PROJECT_DIR / "data/.checkpoint_arcmap_index.json"),
            "source": "arcmap",
        },
    }
    ```
  - **HTTP fetch**:
    ```python
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
  - **Parser helpers** (all take a `BeautifulSoup` and return their field):
    - `extract_title(article) -> str` — `<h1>` text, or `""`
    - `extract_summary(article) -> str` — first `<p>` with `len(get_text(strip=True)) > 40` and appearing before any heading; fallback `""`
    - `extract_sections(article) -> list[dict]` — walk all `<h2>` and `<h3>` in document order; for each heading, record `{heading, level, brief_text}` where `brief_text` is the concatenation of the next siblings' text up to the next heading (any level); skip headings whose collected text is empty
    - `extract_breadcrumb(soup, url) -> list[str]` — try `<nav aria-label="breadcrumb">` then `.breadcrumb` class; collect text from `<a>`/`<li>`/`<span>` children; fall back to URL path segments filtered to non-empty, non-`en`, non-numeric (e.g., `latest` filtered out only if it appears as a version segment)
    - `extract_images(article, base_url) -> list[dict]` — all `<img>` with `src`; resolve `src` to absolute via `urljoin(base_url, src)`; capture `alt` (default `""`); drop images with no absolute URL after join
  - **Page orchestrator**:
    ```python
    def parse_page(html: str, url: str, source: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        article = soup.find("article", id="main") or soup.find("main") or soup.find("article")
        if not article:
            return None
        for tag in article.find_all(["nav", "footer"]):
            tag.decompose()
        base_url = url
        return {
            "url": base_url,
            "source": source,
            "title": extract_title(article),
            "summary": extract_summary(article),
            "breadcrumb": extract_breadcrumb(soup, base_url),
            "sections": extract_sections(article),
            "images": extract_images(article, base_url),
            "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    ```
  - **Checkpoint** (extend ARCRAG-05 pattern with per-URL tracking):
    ```python
    def load_checkpoint(path: str) -> tuple[set[str], list[dict], set[str]]:
        p = Path(path)
        if not p.exists():
            return set(), [], set()
        data = json.loads(p.read_text())
        if isinstance(data, dict):
            return set(data.get("done_urls", [])), data.get("pages", []), set(data.get("failed_urls", []))
        return set(), [], set()

    def save_checkpoint(path: str, done_urls: set[str], pages: list[dict], failed_urls: set[str]):
        Path(path).write_text(json.dumps({
            "done_urls": sorted(done_urls),
            "pages": pages,
            "failed_urls": sorted(failed_urls),
        }, indent=2))
    ```
  - **Build orchestrator** (`build_index(source, limit=None, concurrency=5, delay=0.2)`):
    - Load config from `SOURCES[source]`
    - Load checkpoint (resumable)
    - Read `urls_json` into `all_urls` list; filter out `done_urls` to get `remaining`
    - If `limit`, truncate `remaining[:limit]`
    - Create `asyncio.Semaphore(concurrency)` and `httpx.AsyncClient(follow_redirects=True, timeout=10.0)`
    - Define inner `async def process(url)`:
      - `async with semaphore:`
      - `html = await fetch_html(client, url)`
      - `await asyncio.sleep(delay)`
      - If `html` is `None`: append to `failed_urls`, mark `done_urls`, return
      - `page = parse_page(html, url, source)`
      - If `page` is `None` or `page["title"]` is empty: append to `failed_urls`, mark `done_urls`, return
      - Append `page` to `pages`, mark `done_urls`
      - If `len(done_urls) % 25 == 0` (per 25 pages), call `save_checkpoint`
      - Print progress: `[{source}] {n}/{total} {url} -> {title[:60]}` (flush=True)
    - Use `asyncio.gather(*[process(u) for u in remaining])` to run all
    - Final `save_checkpoint`, write `output` as `json.dumps(pages, indent=2, ensure_ascii=False)`
    - Print summary: `[{source}] Done. {n} pages indexed, {m} failed -> {output}`
  - **CLI**:
    ```python
    def main():
        parser = argparse.ArgumentParser(description="Build documentation index from URL list")
        parser.add_argument("--source", required=True, choices=["arcpro", "arcmap"])
        parser.add_argument("--limit", type=int, default=None, help="Process only first N URLs (for testing)")
        parser.add_argument("--concurrency", type=int, default=5)
        parser.add_argument("--delay", type=float, default=0.2, help="Seconds to sleep after each fetch")
        args = parser.parse_args()
        asyncio.run(build_index(args.source, args.limit, args.concurrency, args.delay))

    if __name__ == "__main__":
        main()
    ```
- **Mirror**: `scripts/parse_sitemaps.py:17-180` (SOURCES, checkpoint, argparse); `backend/src/tools/fetch.py:36-77` (async fetch, article selection, title, sections, images)
- **Validate**: `uv run python -c "import sys; sys.path.insert(0, 'scripts'); import importlib.util; spec = importlib.util.spec_from_file_location('build_index', 'scripts/build_index.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('OK - module imports')"`

### Task 2: Write the plan file to its committed location

- **File**: `.agents/plans/completed/arccrag-06-index-builder.plan.md`
- **Action**: CREATE
- **Implement**: This document (the plan you are reading)
- **Validate**: `ls .agents/plans/completed/arccrag-06-index-builder.plan.md`

### Task 3: Subset validation test

- **File**: (none — run directly)
- **Action**: RUN
- **Implement**:
  ```bash
  cd /home/techafresh/projects/arcpro-docs
  uv run python scripts/build_index.py --source arcpro --limit 5
  ```
- **Validate**: 
  - Script prints progress for 5 URLs and exits cleanly
  - `data/arcpro_index.json` contains 5 entries
  - Each entry has non-empty `url`, `title`, `source == "arcpro"`, `sections` (list), `images` (list)

### Task 4: Schema assertion

- **Action**: RUN
- **Implement**:
  ```bash
  cd /home/techafresh/projects/arcpro-docs
  uv run python -c "
  import json
  data = json.load(open('data/arcpro_index.json'))
  assert len(data) == 5, f'Expected 5, got {len(data)}'
  for p in data:
      assert p['url'], f'Missing url: {p}'
      assert p['title'], f'Missing title: {p}'
      assert p['source'] == 'arcpro', f'Wrong source: {p[\"source\"]}'
      assert isinstance(p['sections'], list)
      assert isinstance(p['images'], list)
      assert isinstance(p['breadcrumb'], list)
      assert p['scraped_at']
  print(f'PASS - {len(data)} entries match schema')
  "
  ```
- **Validate**: Prints "PASS - 5 entries match schema"

### Task 5: Resume validation

- **Action**: RUN
- **Implement**: Re-run the same command and confirm it does not re-fetch the 5 URLs:
  ```bash
  cd /home/techafresh/projects/arcpro-docs
  uv run python scripts/build_index.py --source arcpro --limit 5
  ```
- **Validate**: 
  - Script reports `Resuming from checkpoint: 5 URLs done, 5 pages`
  - No HTTP calls made (output has no "fetched" lines beyond the resume notice)
  - `data/arcpro_index.json` is unchanged in content

### Task 6: Commit and merge

- **Action**: GIT
- **Implement**:
  ```bash
  cd /home/techafresh/projects/arcpro-docs
  git checkout -b feature/arccrag-06-index-builder
  git add scripts/build_index.py .agents/plans/completed/arccrag-06-index-builder.plan.md
  git commit -m "feat: add ARCRAG-06 index builder script for page metadata scraping"
  git checkout main
  git merge --no-ff feature/arccrag-06-index-builder
  git branch -d feature/arccrag-06-index-builder
  ```
- **Validate**: `git log -3 --oneline` shows new commit on main

---

## Validation

```bash
# Module import check (read-only)
cd /home/techafresh/projects/arcpro-docs
uv run python -c "
import importlib.util
spec = importlib.util.spec_from_file_location('build_index', 'scripts/build_index.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print('OK - build_index module imports cleanly')
print(f'SOURCES: {list(m.SOURCES.keys())}')
"

# Subset test (5 pages)
uv run python scripts/build_index.py --source arcpro --limit 5

# Schema check
uv run python -c "
import json
data = json.load(open('data/arcpro_index.json'))
assert len(data) == 5
for p in data:
    assert p['url'] and p['title'] and p['source'] == 'arcpro'
    assert isinstance(p['sections'], list)
    assert isinstance(p['images'], list)
    assert isinstance(p['breadcrumb'], list)
    assert p['scraped_at']
print('PASS - schema OK')
"

# Resume check (no re-fetch)
time uv run python scripts/build_index.py --source arcpro --limit 5
# Should print "Resuming from checkpoint" and exit in <2s

# Full runs (deferred to user — these take hours)
# uv run python scripts/build_index.py --source arcpro    # ~16K URLs
# uv run python scripts/build_index.py --source arcmap    # ~10K URLs
```

---

## Acceptance Criteria

- [ ] `scripts/build_index.py` exists with `--source arcpro|arcmap` CLI
- [ ] Extracts: title (h1), summary (first <p> > 40 chars), H2/H3 sections with `{heading, level, brief_text}`, breadcrumb (list of strings), image alt+absolute URL (list of dicts)
- [ ] Concurrency bounded by `asyncio.Semaphore(5)`, configurable via `--concurrency`
- [ ] Per-fetch delay configurable via `--delay` (default 0.2s)
- [ ] Checkpoint saved every 25 pages to `data/.checkpoint_{source}_index.json`; resumes on restart
- [ ] Failed pages (timeout, non-200, no title, no main content) logged to `failed_urls` list; remaining continue
- [ ] Output: `data/{arcpro,arcmap}_index.json` matches the schema below
- [ ] `--limit N` flag works for subset testing
- [ ] No comments in code (per global rule)
- [ ] Uses `httpx.AsyncClient(follow_redirects=True, timeout=10.0)` so `pro.arcgis.com` URLs redirect to `doc.esri.com` transparently
- [ ] Plan file written to `.agents/plans/completed/arccrag-06-index-builder.plan.md`
- [ ] Subset test (5 URLs) passes schema assertions
- [ ] Resume re-runs without re-fetching

### Output Schema
```json
{
  "url": "https://doc.esri.com/en/arcgis-pro/3.7/tool-reference/analysis/buffer.htm",
  "source": "arcpro",
  "title": "Buffer (Analysis)",
  "summary": "Creates buffer polygons around input features at a specified distance.",
  "breadcrumb": ["Tool Reference", "Analysis", "Buffer"],
  "sections": [
    {"heading": "Summary", "level": 2, "brief_text": "..."},
    {"heading": "Illustration", "level": 2, "brief_text": "..."}
  ],
  "images": [
    {"url": "https://doc.esri.com/.../buffer.png", "alt": "Buffer tool dialog"}
  ],
  "scraped_at": "2026-06-04T15:00:00Z"
}
```

### Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `doc.esri.com` returns 429 under load | Single retry after 5s; if still failing, log to `failed_urls` and continue |
| 16K+ URLs at 0.2s × 5 concurrent = ~10+ min minimum; full run likely hours | Document this in the plan; defer full runs to user via `tmux`/`screen` |
| Some pages have no `<h1>` or no summary paragraph | `extract_title`/`extract_summary` return `""`; pages with empty title are flagged as failed and skipped |
| `script` tags inside `<article>` could pollute text extraction | Strip `<script>` and `<style>` from article in `parse_page` (mirror `fetch.py`'s nav/footer decompose) |
| Breadcrumb selector varies across Esri doc templates | Multiple selector fallbacks (`<nav aria-label="breadcrumb">`, `.breadcrumb`); URL path fallback always works |
| Old-format checkpoint (from ARCRAG-05) is a list, not dict | `load_checkpoint` already handles both via `isinstance(data, dict)` check — same pattern carries to ARCRAG-06's loader |
