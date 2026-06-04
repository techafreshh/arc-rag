# Plan: Sitemap Parser Script

## Summary

Create a script that parses ArcGIS Pro and ArcMap sitemap XML files to collect all documentation page URLs. Handles the new `doc.esri.com` 3-level sitemap hierarchy for ArcGIS Pro and the legacy `desktop.arcgis.com` 2-level structure for ArcMap. Includes checkpoint-based resume, retry logic, rate limiting, and URL filtering to output sorted JSON arrays of documentation URLs.

## User Story

As a developer
I want a script that parses ArcGIS Pro and ArcMap sitemap XML files
So that I have a complete list of documentation page URLs to index

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | Scripts, Data |
| Jira Issue | ARCRAG-05 |
| Blocked By | ARCRAG-01 (completed) |

---

## Patterns to Follow

### Script Structure
```python
# SOURCE: scripts/parse_sitemaps.py:1-14
import argparse
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
(PROJECT_DIR / "data").mkdir(exist_ok=True)
```

### HTTP Fetch Pattern
```python
# SOURCE: scripts/parse_sitemaps.py:38-50
def fetch_xml(url: str, timeout: float = 15.0, retries: int = 2) -> str | None:
    last_error = None
    for attempt in range(retries + 1):
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            last_error = e
            if attempt < retries:
                time.sleep(2)
    print(f" FAILED: {last_error}")
    return None
```

### XML Namespace Handling
```python
# SOURCE: scripts/parse_sitemaps.py:128-136
for el in root:
    loc_el = el.find(f"{{{SITEMAP_NS}}}loc")
    if loc_el is None or not loc_el.text:
        continue
    target = loc_el.text.strip()
    if el.tag == f"{{{SITEMAP_NS}}}sitemap":
        sub_sitemaps.append(target)
    elif el.tag == f"{{{SITEMAP_NS}}}url":
        page_urls.append(target)
```

### Checkpoint Pattern
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

### CLI Pattern
```python
# SOURCE: scripts/parse_sitemaps.py:171-184
def main():
    parser = argparse.ArgumentParser(description="Parse ArcGIS documentation sitemaps")
    parser.add_argument(
        "--source",
        required=True,
        choices=["arcpro", "arcmap"],
        help="Which documentation source to parse",
    )
    args = parser.parse_args()
    parse(args.source)

if __name__ == "__main__":
    main()
```

### XML Entity Recovery
```python
# SOURCE: scripts/parse_sitemaps.py:116-123
import re
cleaned = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)\S+?;', '&amp;', xml_text)
try:
    root = ET.fromstring(cleaned)
except ET.ParseError:
    print(f" -> XML parse error (unrecoverable): {e}")
    continue
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `scripts/parse_sitemaps.py` | CREATE | Sitemap parser with multi-level hierarchy navigation, checkpoint/resume, URL filtering |
| `data/arcpro_urls.json` | GENERATED | ArcGIS Pro documentation page URLs (~16K entries) |
| `data/arcmap_urls.json` | GENERATED | ArcMap documentation page URLs (~10K entries) |
| `data/.checkpoint_arcpro_urls.json` | GENERATED | Resume checkpoint for ArcGIS Pro parsing |
| `data/.checkpoint_arcmap_urls.json` | GENERATED | Resume checkpoint for ArcMap parsing |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Create parse_sitemaps.py module

- **File**: `scripts/parse_sitemaps.py`
- **Action**: CREATE
- **Implement**:
  - Define `SITEMAP_NS` constant for XML namespace
  - Define `SOURCES` dict with two entries:
    - `arcpro`: sitemap entry at `https://doc.esri.com/sitemap.xml`, guide filters `["/arcgis-pro/", "/en/arcgis-pro/"]`, path filter `/en/arcgis-pro/`, exclude `["/sdk/"]`, delay 0.5s
    - `arcmap`: sitemap entry at `http://desktop.arcgis.com/sitemap_index.xml`, guide filters `["/en/arcmap/latest/"]`, path filter `/en/arcmap/latest/`, exclude `[]`, delay 1.0s
  - Create `fetch_xml()` with retries (2) and 2s backoff between attempts
  - Create `should_include()` for path filter + exclude filter logic
  - Create `load_checkpoint()` / `save_checkpoint()` with dict format `{"urls": [...], "done_sitemaps": [...]}` and backward-compatible list fallback
  - Create `parse()` function with BFS sitemap traversal:
    - Start from entry URL, visit sub-sitemaps matching guide filters
    - Skip already-processed sitemaps on resume (check before HTTP call)
    - Extract page URLs from leaf sitemaps, apply path/exclude filters
    - Rate limit with configurable delay between successful leaf fetches
    - Save checkpoint every 5 new leaf sitemaps
    - Handle XML parse errors with entity recovery regex
    - Write final sorted JSON array to output path
  - Create `main()` with argparse `--source arcpro|arcmap`
- **Mirror**: `backend/test_fetch.py:1-20` — standalone script pattern with `if __name__ == "__main__":`
- **Validate**: `uv run python scripts/parse_sitemaps.py --source arcpro` completes and writes output

### Task 2: Run ArcGIS Pro sitemap parsing

- **Action**: RUN
- **Implement**: `uv run python scripts/parse_sitemaps.py --source arcpro`
- **Validate**: `data/arcpro_urls.json` exists with ~16K+ URLs, all containing `/en/arcgis-pro/` and no `/sdk/` entries

### Task 3: Run ArcMap sitemap parsing

- **Action**: RUN
- **Implement**: `uv run python scripts/parse_sitemaps.py --source arcmap`
- **Validate**: `data/arcmap_urls.json` exists with ~10K+ URLs, all containing `/en/arcmap/latest/`

---

## Validation

```bash
# ArcGIS Pro
uv run python scripts/parse_sitemaps.py --source arcpro
python3 -c "import json; d=json.load(open('data/arcpro_urls.json')); print(f'{len(d)} URLs'); assert all('/en/arcgis-pro/' in u for u in d); assert not any('/sdk/' in u for u in d); print('OK')"

# ArcMap
uv run python scripts/parse_sitemaps.py --source arcmap
python3 -c "import json; d=json.load(open('data/arcmap_urls.json')); print(f'{len(d)} URLs'); assert all('/en/arcmap/latest/' in u for u in d); print('OK')"

# Resume (re-run should skip processed sitemaps)
uv run python scripts/parse_sitemaps.py --source arcmap
```

---

## Acceptance Criteria

- [ ] `scripts/parse_sitemaps.py` exists with `--source arcpro|arcmap` CLI
- [ ] Given `--source arcpro`, outputs `data/arcpro_urls.json` with all English `/en/arcgis-pro/` page URLs
- [ ] Given `--source arcmap`, outputs `data/arcmap_urls.json` with all English `/en/arcmap/latest/` page URLs
- [ ] ArcGIS Pro sitemap resolution handles the 3-level hierarchy: `doc.esri.com/sitemap.xml` → `arcgis-pro/sitemap.xml` → `en/arcgis-pro/3.7/sitemap.xml`
- [ ] SDK documentation (`/sdk/`) is excluded from ArcPro URLs
- [ ] Sub-sitemap fetch failures are logged and the script continues with remaining sitemaps
- [ ] Given the script has run before, it resumes from checkpoint (skips already-processed sitemaps)
- [ ] Invalid XML entities (e.g., `&nbsp;` in desktop.arcgis.com sitemaps) are handled with entity recovery
- [ ] Rate limiting respects 1s delay between requests to desktop.arcgis.com
