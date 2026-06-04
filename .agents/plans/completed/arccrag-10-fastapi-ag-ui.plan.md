# Plan: FastAPI Server with AG-UI Endpoint

## Summary

Create `backend/src/main.py` exposing the existing PydanticAI agent via a FastAPI server using the AG-UI protocol. The file will define a `POST /ag-ui` endpoint for CopilotKit integration, a `GET /health` endpoint for status checks, and CORS middleware allowing the frontend origin. All dependencies are already installed — this is a single-file implementation that wires existing components together.

## User Story

As a developer
I want the PydanticAI agent exposed via a FastAPI server using the AG-UI protocol
So that CopilotKit can connect to it from the frontend

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | Backend API |
| Jira Issue | ARCRAG-10 |

---

## Patterns to Follow

### Config Loading
```python
# SOURCE: backend/src/agent.py:1-12
import os
from dotenv import load_dotenv
load_dotenv()
model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
```

### Import Style
```python
# SOURCE: backend/src/agent.py:1-8
import os                                    # stdlib

from dotenv import load_dotenv               # third-party
from pydantic_ai import Agent, RunContext

from src.tools.fetch import ...              # local (full paths, no relative)
```

### Error Handling — Return Error Data, Don't Raise
```python
# SOURCE: backend/src/tools/search.py:63-64
if not query or not query.strip():
    return SearchResults(results=[], error="Empty query")
```

### Qdrant Connectivity Check
```python
# SOURCE: backend/src/tools/search.py:74-78
try:
    qdrant = QdrantClient(url=QDRANT_URL)
    qdrant.get_collections()
except Exception as e:
    return SearchResults(results=[], error=f"Qdrant unreachable at {QDRANT_URL}: {e}")
```

### Type Annotations
```python
# SOURCE: backend/src/tools/fetch.py:27
error: str | None = None
# SOURCE: backend/src/embed.py:14
async def embed_batch(...) -> list[list[float]]:
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/src/main.py` | CREATE | FastAPI app with AG-UI endpoint, health check, CORS |
| `backend/test_server.py` | CREATE | Tests for health check, AG-UI endpoint, CORS |

---

## Tasks

### Task 1: Create `backend/src/main.py`

- **File**: `backend/src/main.py`
- **Action**: CREATE
- **Implement**: FastAPI application with three concerns:

#### 1a. Imports and Configuration

```python
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic_ai.ui.ag_ui import AGUIAdapter
from qdrant_client import QdrantClient
from starlette.requests import Request
from starlette.responses import Response

from src.agent import agent

load_dotenv()
```

- Follow existing import ordering: stdlib → third-party → local
- Use full `src.` import paths (no relative imports)
- Call `load_dotenv()` at module level

#### 1b. Configuration Constants

```python
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
FRONTEND_ORIGIN = os.getenv("NEXT_PUBLIC_BACKEND_URL", "http://localhost:3000")
```

- Follow `backend/src/tools/search.py:13-16` pattern (UPPER_CASE module constants)
- Source `.env.example` for variable names and defaults

#### 1c. FastAPI App + CORS

```python
app = FastAPI(title="ArcGIS Documentation RAG Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- PRD specifies CORS restricted to frontend origin (`.agents/PRDs/PRD.md:319`)
- `FRONTEND_ORIGIN` defaults to `http://localhost:3000` (Next.js dev server default)

#### 1d. Health Check Endpoint

```python
@app.get("/health")
async def health():
    qdrant_status = "disconnected"
    try:
        client = QdrantClient(url=QDRANT_URL)
        client.get_collections()
        qdrant_status = "connected"
    except Exception:
        pass
    return {"status": "ok", "qdrant": qdrant_status, "model": OPENROUTER_MODEL}
```

- Matches PRD spec: `.agents/PRDs/PRD.md:355-361`
- Uses same Qdrant check pattern as `backend/src/tools/search.py:74-78`
- Returns model name from env var

#### 1e. AG-UI Endpoint

```python
@app.post("/ag-ui")
async def ag_ui_endpoint(request: Request) -> Response:
    return await AGUIAdapter.dispatch_request(request, agent=agent)
```

- Uses `AGUIAdapter.dispatch_request()` — the current (non-deprecated) API
- Import from `pydantic_ai.ui.ag_ui` (not deprecated `pydantic_ai.ag_ui`)
- Endpoint path `/ag-ui` matches PRD spec: `.agents/PRDs/PRD.md:341`
- The agent is imported from `src.agent` (existing module at `backend/src/agent.py:14`)

#### 1f. Uvicorn Entry Point

```python
if __name__ == "__main__":
    import uvicorn
    host = os.getenv("BACKEND_HOST", "0.0.0.0")
    port = int(os.getenv("BACKEND_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
```

- Enables `python -m src.main` for local development
- Reads host/port from env (matches `.env.example:14-16`)

- **Mirror**: PydanticAI docs "Handle a Starlette request" pattern
- **Validate**: `cd backend && ./.venv/bin/python -c "from src.main import app; print('OK')"`

---

### Task 2: Create `backend/test_server.py`

- **File**: `backend/test_server.py`
- **Action**: CREATE
- **Implement**: Tests following existing test patterns from `backend/test_agent_flow.py`

#### 2a. Test Structure

Follow the existing test script pattern:
- `async def test_N()` functions with `print("--- Test N: Description ---")` headers
- `async def test()` orchestrator calling all tests
- `if __name__ == "__main__": asyncio.run(test())`
- Graceful SKIP for missing infrastructure

```python
import asyncio
import os

from dotenv import load_dotenv
load_dotenv()

from httpx import ASGITransport, AsyncClient

from src.main import app

def _skip_no_key():
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key or key == "dummy":
        print("SKIP - OPENROUTER_API_KEY missing or 'dummy'")
        return True
    return False
```

#### 2b. Test 1: Health Check

```python
async def test_health():
    print("--- Test 1: Health check ---")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "qdrant" in data
    assert "model" in data
    print(f"  Response: {data}")
    print("PASS - health check returns expected shape")
```

- Uses `httpx.AsyncClient` with `ASGITransport` to test FastAPI without running a server
- Verifies response shape matches PRD spec

#### 2c. Test 2: AG-UI Endpoint Returns SSE

```python
async def test_ag_ui_endpoint():
    print("\n--- Test 2: AG-UI endpoint returns SSE ---")
    if _skip_no_key():
        return
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/ag-ui",
            json={"threadId": "test-1", "runId": "run-1", "messages": [
                {"role": "user", "content": "Say hello in one word"}
            ]},
            headers={"Accept": "text/event-stream"},
        )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    assert len(resp.content) > 0
    print(f"  Status: {resp.status_code}, Content-Type: {resp.headers.get('content-type')}")
    print("PASS - AG-UI endpoint returns SSE response")
```

- Sends minimal AG-UI `RunAgentInput` to the endpoint
- Verifies SSE response (status 200, correct content-type, non-empty body)
- Skips if no API key (agent would fail to connect to OpenRouter)

#### 2d. Test 3: CORS Headers

```python
async def test_cors():
    print("\n--- Test 3: CORS headers ---")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.options(
            "/ag-ui",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert resp.status_code == 200
    allow_origin = resp.headers.get("access-control-allow-origin", "")
    assert allow_origin in ("http://localhost:3000", "*"), f"Unexpected CORS origin: {allow_origin}"
    print(f"  Access-Control-Allow-Origin: {allow_origin}")
    print("PASS - CORS allows frontend origin")
```

- Tests preflight OPTIONS request
- Verifies CORS headers allow the configured frontend origin

- **Mirror**: `backend/test_agent_flow.py` test structure (print headers, assert with messages, SKIP pattern)
- **Validate**: `cd backend && ./.venv/bin/python test_server.py`

---

### Task 3: Validate Integration

- **Action**: Run validation commands
- **Validate**:
  1. `cd backend && ./.venv/bin/python -c "from src.main import app; print('Import OK')"` — module loads without errors
  2. `cd backend && ./.venv/bin/python test_server.py` — all tests pass
  3. Manual: `cd backend && ./.venv/bin/python -m src.main` then `curl http://localhost:8000/health` — returns health JSON

---

## Validation

```bash
# Import check (no API keys needed)
cd backend && ./.venv/bin/python -c "from src.main import app; print('Import OK')"

# Run tests (health + CORS work without API keys; AG-UI test needs OPENROUTER_API_KEY)
cd backend && ./.venv/bin/python test_server.py

# Manual smoke test (optional - requires terminal)
cd backend && ./.venv/bin/python -m src.main
# In another terminal:
curl -s http://localhost:8000/health | python -m json.tool
```

---

## Acceptance Criteria

- [ ] `backend/src/main.py` exists with FastAPI app, `/ag-ui` POST endpoint, `/health` GET endpoint, CORS middleware
- [ ] `GET /health` returns `{"status": "ok", "qdrant": "<connected|disconnected>", "model": "<configured model>"}`
- [ ] `POST /ag-ui` accepts AG-UI requests and returns SSE events (TextMessageStart, TextMessageContent, TextMessageEnd)
- [ ] CORS allows requests from the configured frontend origin
- [ ] `backend/test_server.py` passes all tests
- [ ] Module imports cleanly without errors
- [ ] Uses non-deprecated PydanticAI AG-UI API (`AGUIAdapter.dispatch_request` from `pydantic_ai.ui.ag_ui`)
- [ ] Follows existing code conventions (import order, `load_dotenv()`, UPPER_CASE constants, full `src.` import paths)

---

## Risks

| Risk | Mitigation |
|------|-----------|
| AG-UI `RunAgentInput` schema mismatch with test payload | Use actual CopilotKit request format; test with minimal valid input |
| Qdrant health check blocks startup if Qdrant is down | Health check catches exception and returns `"disconnected"` (non-blocking) |
| Deprecated AG-UI API used | Verified: `pydantic_ai.ui.ag_ui.AGUIAdapter.dispatch_request` is the current API; `pydantic_ai.ag_ui` is the deprecated shim |
| `FRONTEND_ORIGIN` env var mismatch | Default to `http://localhost:3000` (Next.js dev default); configurable via `.env` |
