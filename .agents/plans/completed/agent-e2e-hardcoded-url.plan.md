# Plan: Agent Answers Questions Using Hardcoded URL

## Summary

Add a `lookup_url` tool with a hardcoded dictionary mapping common GIS topics to ArcGIS Pro documentation URLs, then update the agent's system prompt to instruct it to use the lookup → fetch → answer flow. Create an E2E script that asks "What is the Buffer tool?" and verifies the response includes markdown images and a source citation. This validates the full tool chain: tool registration → tool call → content extraction → LLM generation with context — all before adding semantic search.

## User Story

As a developer
I want to verify the agent can use the fetch_page tool to answer a question from a known URL
So that the end-to-end tool flow works before adding search

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | SMALL |
| Systems Affected | Backend |
| Jira Issue | ARCRAG-04 |
| Blocked By | ARCRAG-03 (completed) |

---

## Patterns to Follow

### Tool Registration
```python
# SOURCE: backend/src/agent.py:23-45
@agent.tool
async def fetch_page(ctx: RunContext, url: str) -> str:
    """Fetch and parse an ArcGIS documentation page. Returns the page content including text sections, images, and code blocks."""
    result = await _fetch_page(url)
    if result.error:
        return f"Error fetching {url}: {result.error}"
    # ... format as markdown, include images and source
```

### PydanticAI Tool Signature
```python
# SOURCE: backend/src/agent.py:23-24
# Tools take (ctx: RunContext, ...) with type hints. Docstring becomes tool description for the LLM.
@agent.tool
async def tool_name(ctx: RunContext, param: type) -> str:
    """Tool description — the LLM reads this to decide when to use the tool."""
```

### Error Handling Pattern
```python
# SOURCE: backend/src/tools/fetch.py:38-44
# Return a model with .error field rather than raising exceptions
except httpx.TimeoutException:
    return PageContent(url=url, title="", sections=[], images=[], code_blocks=[], error="Timeout fetching page")
except Exception as e:
    return PageContent(url=url, title="", sections=[], images=[], code_blocks=[], error=str(e))
```

### Test Pattern
```python
# SOURCE: backend/test_fetch.py:1-20
import asyncio
from src.tools.fetch import fetch_page

async def test():
    url = 'https://pro.arcgis.com/...'
    r = await fetch_page(url)
    print(f'Title: {r.title}')
    assert r.title, "No title extracted"
    assert r.sections, "No sections extracted"
    assert not r.error, f"Unexpected error: {r.error}"
    print('PASS - live fetch')

if __name__ == "__main__":
    asyncio.run(test())
```

### Config (env vars)
```python
# SOURCE: backend/src/agent.py:10
# Uses os.getenv() with defaults, loaded via load_dotenv()
model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/src/tools/lookup.py` | CREATE | URL lookup dict + tool for mapping topic names to doc URLs |
| `backend/src/agent.py` | UPDATE | Register lookup_url tool, update system prompt for lookup→fetch→answer flow |
| `backend/test_e2e.py` | CREATE | End-to-end test: ask about Buffer tool, verify images + source in response |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Create URL lookup tool

- **File**: `backend/src/tools/lookup.py`
- **Action**: CREATE
- **Implement**:
  - Define a `Pydantic` model: `LookupResult(url: str, title: str, tools: str | None)` to represent a mapped URL entry
  - Create module-level `URL_MAP: dict[str, dict[str, str]]` with at least 6 entries mapping common GIS topics to ArcGIS Pro documentation URLs. Each entry has `url` and `title` keys. Topics should cover analysis tools (Buffer, Clip, Intersect), data management (Merge), concepts (Geodatabase), and scripting (ArcPy). Use lowercase keys for case-insensitive matching.
  - Create `async def lookup_url(query: str) -> dict[str, str] | None`:
    - Clean input: lowercase, strip whitespace
    - If exact match in URL_MAP, return the entry dict `{url, title}`
    - If no exact match, iterate keys and return first where query substring appears in key OR key substring appears in query
    - If still no match, return `None` (agent will handle gracefully)
  - This function is NOT decorated with `@agent.tool` — it's a plain utility. The tool wrapper is registered in `agent.py` (following the fetch_page pattern where `_fetch_page` is imported and wrapped).
- **Mirror**: `backend/src/tools/fetch.py:1-6` — module-level dict + plain async function
- **Validate**: `cd backend && .venv/Scripts/python.exe -c "from src.tools.lookup import lookup_url, URL_MAP; import asyncio; r = asyncio.run(lookup_url('buffer')); assert r['url'] == 'https://pro.arcgis.com/en/pro-app/latest/tool-reference/analysis/buffer.htm'; print('OK')"`

### Task 2: Register lookup_url tool on agent and update system prompt

- **File**: `backend/src/agent.py`
- **Action**: UPDATE
- **Implement**:
  - Add import: `from src.tools.lookup import lookup_url as _lookup_url`
  - Register tool using `@agent.tool` decorator:
    ```python
    @agent.tool
    async def lookup_url(ctx: RunContext, topic: str) -> str:
        """Look up the ArcGIS documentation URL for a given GIS topic or tool name (e.g. 'buffer', 'clip', 'geodatabase'). Use this BEFORE calling fetch_page to find the correct URL."""
        result = _lookup_url(topic)
        if result is None:
            return f"No URL found for topic: {topic}"
        return f"URL: {result['url']}\nTitle: {result['title']}"
    ```
  - Update `instructions` string on the `Agent(...)` constructor to include explicit workflow guidance:
    - When asked about a specific ArcGIS tool or concept: call `lookup_url` first to find the documentation URL, then call `fetch_page` with that URL to get the full content
    - Always include relevant images from the fetched page using markdown `![alt](url)` syntax
    - Always end responses with a source citation: `**Source:** [Page Title](url)`
    - If lookup_url returns no URL, tell the student you don't have that specific tool in your reference set yet
- **Mirror**: `backend/src/agent.py:23-45` — same `@agent.tool` decorator pattern, same `RunContext` first arg, same string return
- **Validate**: `cd backend && .venv/Scripts/python.exe -c "from src.agent import agent; n = len(agent._function_tools); print(f'Tools: {n}'); assert n >= 2, f'Expected >= 2 tools, got {n}'; print('OK')"`

### Task 3: Create end-to-end test

- **File**: `backend/test_e2e.py`
- **Action**: CREATE
- **Implement**:
  - Import `agent` from `src.agent`
  - Define `async def test():` that:
    - Calls `result = await agent.run("What is the Buffer tool in ArcGIS Pro?")`
    - Prints the response output for manual inspection
    - Asserts that response contains `![` (markdown image syntax), indicating images were included
    - Asserts that response contains `Source:` followed by a URL, indicating a citation was included
    - Prints "PASS - E2E tool flow" on success
  - `if __name__ == "__main__": asyncio.run(test())`
  - NOTE: this test requires a valid `.env` with `OPENROUTER_API_KEY` — print a clear message if the key is missing
  - Add a timeout guard around `agent.run()` (e.g., 30s) since it calls live APIs
- **Mirror**: `backend/test_fetch.py:1-20` — same structure (import, async test function, asyncio.run, assert + print PASS)
- **Validate**: `cd backend && .venv/Scripts/python.exe test_e2e.py` — prints the response, images found, source citation found, PASS

---

## Validation

```bash
# 1. Verify lookup_url import + exact match
cd backend && .venv/Scripts/python.exe -c "
import asyncio
from src.tools.lookup import lookup_url, URL_MAP
# Test exact match
r = asyncio.run(lookup_url('buffer'))
assert r is not None and 'pro.arcgis.com' in r['url'], f'Buffer URL not found: {r}'
print(f'Buffer URL: {r[\"url\"]}')

# Test fuzzy match
r2 = asyncio.run(lookup_url('buffer tool'))
assert r2 is not None, 'Fuzzy match failed for \"buffer tool\"'
print(f'Fuzzy match OK: {r2[\"title\"]}')

# Test miss
r3 = asyncio.run(lookup_url('quantum physics'))
assert r3 is None, 'Non-GIS query should return None'
print('Miss handling OK')

# Print all mappings
print(f'Total mappings: {len(URL_MAP)}')
print('PASS - lookup_url')
"

# 2. Verify agent has both tools
cd backend && .venv/Scripts/python.exe -c "
from src.agent import agent
n = len(agent._function_tools)
assert n >= 2, f'Expected >= 2 tools, got {n}'
print(f'Tools registered: {n}')
print('PASS - tool registration')
"

# 3. Verify agent import works (requires .env with OPENROUTER_API_KEY)
cd backend && .venv/Scripts/python.exe -c "
from src.agent import agent
print('Agent imported successfully')
print(f'Model: {agent._model}')
"

# 4. Run E2E test (requires .env with OPENROUTER_API_KEY)
cd backend && .venv/Scripts/python.exe test_e2e.py

# 5. Manual CLI verification
cd backend && .venv/Scripts/python.exe -m src.agent
# Type: "What is the Buffer tool?"
# Expected: agent calls lookup_url, then fetch_page, responds with images + source link
```

---

## Acceptance Criteria

- [ ] `backend/src/tools/lookup.py` exists with `URL_MAP` dict (6+ entries) and `lookup_url()` function
- [ ] `lookup_url("buffer")` returns the Buffer tool doc URL
- [ ] `lookup_url("nonexistent tool")` returns `None`
- [ ] Fuzzy/partial matching works (e.g., "buffer tool" matches "buffer")
- [ ] `lookup_url` tool is registered on the agent in `agent.py`
- [ ] Agent's system prompt instructs the lookup → fetch → answer flow
- [ ] Given the agent is asked "What is the Buffer tool?", it calls lookup_url then fetch_page and generates an answer
- [ ] The generated answer includes markdown image references (`![alt](url)`)
- [ ] The generated answer includes a source citation (`Source: [title](url)`)
- [ ] `backend/test_e2e.py` exists and passes (requires valid `.env` with OPENROUTER_API_KEY)
