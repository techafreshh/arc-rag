# Plan: fetch_page Tool — Live Documentation Scraper

## Summary

Create an async `fetch_page` tool that fetches ArcGIS documentation pages via httpx, parses HTML with BeautifulSoup4 to extract main content (stripping nav/footer), and returns a structured Pydantic model with text sections, images, and code blocks. Includes a TTLCache (~100 entries, 5 min TTL) for repeat fetches and graceful error handling for 404/timeout. The tool is registered on the existing PydanticAI agent.

## User Story

As a student
I want the agent to fetch full documentation page content live
So that I get detailed, up-to-date answers with images

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | Backend |
| Jira Issue | ARCRAG-03 |

---

## Patterns to Follow

### Agent & Tool Registration
```python
# SOURCE: backend/src/agent.py:1-19
import os
from dotenv import load_dotenv
from pydantic_ai import Agent

load_dotenv()

model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")

agent = Agent(
    f"openrouter:{model}",
    instructions=("..."),
)

# PydanticAI tool decorator pattern (from pydantic_ai v1.104.0 API):
# @agent.tool
# async def my_tool(ctx: RunContext[DepsType], param: str) -> str:
#     """Docstring becomes tool description."""
#     ...
```

### HTML Structure (from live exploration of doc.esri.com)
```
# Pages redirect: pro.arcgis.com → doc.esri.com (must follow redirects)
# Content container: <article id="main">
# Strip: <nav> (5 instances), <footer> (1 instance)
# Images: relative URLs like "images/buffer_new_horizontal-F5467.png"
# Code: <pre> blocks containing ArcPy examples
# H2 sections: Summary, Illustration, Usage, Parameters, Environments, Licensing, Related topics
```

### Config Pattern
```python
# SOURCE: backend/src/agent.py:7
# Uses os.getenv() with defaults, loaded via load_dotenv()
model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/src/tools/__init__.py` | CREATE | Make tools a package |
| `backend/src/tools/fetch.py` | CREATE | fetch_page implementation: models, parsing, caching |
| `backend/src/agent.py` | UPDATE | Import and register fetch_page tool on agent |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Create tools package

- **File**: `backend/src/tools/__init__.py`
- **Action**: CREATE
- **Implement**: Empty file (package marker)
- **Validate**: `cd backend && .venv\Scripts\python.exe -c "import src.tools"`

### Task 2: Create fetch_page module with Pydantic models and parsing logic

- **File**: `backend/src/tools/fetch.py`
- **Action**: CREATE
- **Implement**:
  - Define Pydantic models:
    - `ImageInfo(url: str, alt: str)`
    - `Section(heading: str, content: str)`
    - `PageContent(url: str, title: str, sections: list[Section], images: list[ImageInfo], code_blocks: list[str], error: str | None = None)`
  - Create module-level `TTLCache(maxsize=100, ttl=300)` from `cachetools`
  - Create `async def fetch_page(url: str) -> PageContent`:
    - Check cache first (key = url)
    - Use `httpx.AsyncClient(follow_redirects=True, timeout=10.0)` to GET the URL
    - On `httpx.TimeoutException`: return `PageContent(url=url, title="", sections=[], images=[], code_blocks=[], error="Timeout fetching page")`
    - On HTTP 404 or other non-200: return `PageContent(..., error=f"HTTP {status_code}")`
    - Parse HTML with `BeautifulSoup(html, "html.parser")`
    - Find `<article id="main">` (fallback to `<main>` or `<article>`)
    - Remove all `<nav>` and `<footer>` elements from the article
    - Extract title from `<h1>` text
    - Extract images: find all `<img>` in article, resolve relative `src` to absolute using the final response URL as base
    - Extract code blocks: find all `<pre>` in article, get text content
    - Extract sections: find all `<h2>` in article, for each h2 collect all sibling content until next h2 as the section content (get_text with separator)
    - Build and return `PageContent`, store in cache
  - Handle general exceptions with a catch-all returning an error PageContent
- **Mirror**: Agent pattern from `backend/src/agent.py` (module-level, simple imports)
- **Validate**: `cd backend && .venv\Scripts\python.exe -c "from src.tools.fetch import fetch_page, PageContent; print('OK')"`

### Task 3: Register fetch_page as a tool on the agent

- **File**: `backend/src/agent.py`
- **Action**: UPDATE
- **Implement**:
  - Add import: `from pydantic_ai import RunContext`
  - Add import: `from src.tools.fetch import fetch_page as _fetch_page, PageContent`
  - Register tool using `@agent.tool` decorator:
    ```python
    @agent.tool
    async def fetch_page(ctx: RunContext, url: str) -> str:
        """Fetch and parse an ArcGIS documentation page. Returns the page content including text sections, images, and code blocks."""
        result = await _fetch_page(url)
        if result.error:
            return f"Error fetching {url}: {result.error}"
        # Format as readable text for the LLM
        parts = [f"# {result.title}", ""]
        for section in result.sections:
            parts.append(f"## {section.heading}")
            parts.append(section.content)
            parts.append("")
        if result.code_blocks:
            parts.append("## Code Examples")
            for code in result.code_blocks:
                parts.append(f"```python\n{code}\n```")
            parts.append("")
        if result.images:
            parts.append("## Images")
            for img in result.images:
                parts.append(f"![{img.alt}]({img.url})")
            parts.append("")
        parts.append(f"Source: {result.url}")
        return "\n".join(parts)
    ```
- **Mirror**: PydanticAI tool decorator pattern (RunContext as first arg, docstring as description)
- **Validate**: `cd backend && .venv\Scripts\python.exe -c "from src.agent import agent; print(f'Tools: {len(agent._function_tools)}')"`

### Task 4: Integration test — fetch a real page

- **Action**: RUN
- **Implement**: Run a quick async test to verify the full flow works:
  ```bash
  cd backend && .venv\Scripts\python.exe -c "
  import asyncio
  from src.tools.fetch import fetch_page
  async def test():
      result = await fetch_page('https://pro.arcgis.com/en/pro-app/latest/tool-reference/analysis/buffer.htm')
      print(f'Title: {result.title}')
      print(f'Sections: {len(result.sections)}')
      print(f'Images: {len(result.images)}')
      print(f'Code blocks: {len(result.code_blocks)}')
      print(f'Error: {result.error}')
      assert result.title, 'No title extracted'
      assert result.sections, 'No sections extracted'
      assert result.images, 'No images extracted'
      assert not result.error, f'Unexpected error: {result.error}'
      print('PASS')
  asyncio.run(test())
  "
  ```
- **Validate**: Output shows title, sections > 0, images > 0, no error, prints PASS

---

## Validation

```bash
# Import check
cd backend && .venv\Scripts\python.exe -c "from src.tools.fetch import fetch_page, PageContent; print('Import OK')"

# Tool registration check
cd backend && .venv\Scripts\python.exe -c "from src.agent import agent; print(f'Tools registered: {len(agent._function_tools)}')"

# Live fetch test
cd backend && .venv\Scripts\python.exe -c "
import asyncio
from src.tools.fetch import fetch_page
async def test():
    r = await fetch_page('https://pro.arcgis.com/en/pro-app/latest/tool-reference/analysis/buffer.htm')
    assert r.title and r.sections and not r.error
    print('PASS - live fetch')
asyncio.run(test())
"

# Error handling test (404)
cd backend && .venv\Scripts\python.exe -c "
import asyncio
from src.tools.fetch import fetch_page
async def test():
    r = await fetch_page('https://pro.arcgis.com/en/pro-app/latest/nonexistent-page.htm')
    assert r.error
    print(f'PASS - error handled: {r.error}')
asyncio.run(test())
"

# Agent CLI test (manual)
cd backend && .venv\Scripts\python.exe -m src.agent
# Ask: "Fetch the buffer tool page at https://pro.arcgis.com/en/pro-app/latest/tool-reference/analysis/buffer.htm"
```

---

## Acceptance Criteria

- [ ] `backend/src/tools/__init__.py` exists
- [ ] `backend/src/tools/fetch.py` exists with `fetch_page` async function and Pydantic models
- [ ] Given a valid ArcGIS Pro doc URL, `fetch_page` returns main text content (nav/footer stripped)
- [ ] Given a valid URL, `fetch_page` returns image URLs resolved to absolute paths with alt text
- [ ] Given a valid URL, `fetch_page` preserves code blocks as separate elements
- [ ] Given a 404 URL, `fetch_page` returns a graceful error (not an exception)
- [ ] Given a timeout, `fetch_page` returns a timeout error message
- [ ] Given a recently fetched page, the cached result is returned (TTLCache, 100 entries, 5 min)
- [ ] `fetch_page` is registered as a tool on the agent in `agent.py`
- [ ] Agent can be run from CLI and use the tool to answer questions
