# Plan: Add Langfuse Observability to PydanticAI Agent

## Summary

Integrate Langfuse LLM observability into the existing PydanticAI agent using OpenTelemetry instrumentation. The Langfuse SDK acts as an OTel backend — PydanticAI already ships with OTel support, so the integration is minimal: install `langfuse`, call `Agent.instrument_all()`, and add `instrument=True` to the agent constructor. All agent runs, tool calls (`search_index`, `fetch_page`, `lookup_url`), and LLM interactions will be traced and sent to the user's self-hosted Langfuse instance.

## User Story

As a developer, I want to trace agent runs and tool calls in Langfuse, so that I can debug student queries, monitor latency, and track LLM costs.

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | Backend (agent, deps, Dockerfile, env) |
| Jira Issue | N/A |

---

## Patterns to Follow

### Env var loading
```python
# SOURCE: backend/src/agent.py:1-12
import os
from dotenv import load_dotenv

load_dotenv()

model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
```
Every module calls `load_dotenv()` independently, then reads vars with `os.getenv("KEY", "default")`. No centralized config module.

### Agent instantiation
```python
# SOURCE: backend/src/agent.py:14-31
agent = Agent(
    f"openrouter:{model}",
    instructions=("..."),
)
```
Agent is created at module level. Tools added via `@agent.tool` decorator below.

### Import style
```python
# SOURCE: backend/src/agent.py:1-8
import os
from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from src.tools.fetch import PageContent, fetch_page as _fetch_page
```
Absolute `src.` prefixed imports. No relative imports. Stdlib first, then third-party, then local.

### Dockerfile deps
```dockerfile
# SOURCE: backend/Dockerfile:7-15
RUN pip install --no-cache-dir \
    "pydantic-ai[openrouter]" \
    fastapi \
    ...
    cachetools
```
Dependencies installed directly via pip in Dockerfile (not from pyproject.toml). Both must be updated.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/pyproject.toml` | UPDATE | Add `langfuse` to dependencies |
| `backend/Dockerfile` | UPDATE | Add `langfuse` to pip install |
| `.env.example` | UPDATE | Add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` |
| `backend/src/agent.py` | UPDATE | Initialize Langfuse + enable instrumentation |

---

## Tasks

### Task 1: Add `langfuse` dependency to `pyproject.toml`

- **File**: `backend/pyproject.toml`
- **Action**: UPDATE
- **Implement**: Add `"langfuse"` to the `dependencies` list after `"python-dotenv"`
- **Validate**: `cd backend && python -c "import langfuse"`

### Task 2: Add `langfuse` to Dockerfile

- **File**: `backend/Dockerfile`
- **Action**: UPDATE
- **Implement**: Add `langfuse` to the `pip install` block after `cachetools`
- **Mirror**: `backend/Dockerfile:7-15` — same pattern as other deps
- **Validate**: `docker build -f backend/Dockerfile .`

### Task 3: Add Langfuse env vars to `.env.example`

- **File**: `.env.example`
- **Action**: UPDATE
- **Implement**: Append a new `# Langfuse` section with three vars:
  - `LANGFUSE_PUBLIC_KEY=pk-lf-...`
  - `LANGFUSE_SECRET_KEY=sk-lf-...`
  - `LANGFUSE_BASE_URL=https://your-langfuse-instance.com`
- **Mirror**: `.env.example:1-25` — same comment-section + key=value pattern

### Task 4: Initialize Langfuse instrumentation in `agent.py`

- **File**: `backend/src/agent.py`
- **Action**: UPDATE
- **Implement**:
  1. Add import: `from langfuse import get_client`
  2. After `load_dotenv()`, initialize Langfuse and verify auth:
     ```python
     langfuse = get_client()
     if not langfuse.auth_check():
         print("Warning: Langfuse authentication failed — traces will not be exported")
     ```
  3. Call `Agent.instrument_all()` before the agent instantiation (this sets up OTel tracing for all PydanticAI agents)
  4. Add `instrument=True` to the `Agent(...)` constructor call
- **Mirror**: Follows the exact pattern from [Langfuse PydanticAI docs](https://langfuse.com/docs/integrations/pydantic-ai)
- **Validate**: `cd backend && python -c "from src.agent import agent"`

---

## Validation

```bash
# Install deps and verify import
cd backend && pip install -e . && python -c "import langfuse; print('OK')"

# Verify agent module loads with instrumentation
cd backend && python -c "from src.agent import agent; print('Agent loaded')"

# Docker build
docker build -f backend/Dockerfile -t arcrag-backend .

# Full stack test (after setting Langfuse env vars in backend/.env)
docker compose up backend
# Then query the agent and check Langfuse UI for traces
```

---

## Acceptance Criteria

- [ ] `langfuse` appears in `backend/pyproject.toml` and `backend/Dockerfile`
- [ ] `.env.example` documents `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`
- [ ] `backend/src/agent.py` calls `Agent.instrument_all()` and creates agent with `instrument=True`
- [ ] Agent starts without errors when Langfuse env vars are set
- [ ] Agent starts without errors when Langfuse env vars are missing (graceful degradation)
- [ ] Traces appear in Langfuse UI after querying the agent

---

## Risks

| Risk | Mitigation |
|------|------------|
| Langfuse env vars missing in dev — agent startup fails | `get_client()` handles missing creds gracefully; `auth_check()` prints warning, doesn't crash |
| OTel spans from httpx/qdrant-client pollute Langfuse | These are already present via pydantic-ai deps; can filter in Langfuse UI if needed |
| `Agent.instrument_all()` not available in pydantic-ai v1.104.0 | Verified in lockfile — OTel instrumentation packages are already resolved; `instrument_all()` is the documented API |
