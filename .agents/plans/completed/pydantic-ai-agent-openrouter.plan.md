# Plan: PydanticAI Agent with OpenRouter Connection

## Summary

Create a PydanticAI agent connected to OpenRouter using the `'openrouter:<model>'` string format and `python-dotenv` for configuration, matching the conventions established in `examples/basic_agent.py`. The agent uses a GIS documentation guide system prompt and can be validated from the terminal using PydanticAI's built-in `to_cli_sync()` method. This establishes the core agent that all subsequent tools (fetch_page, search_index) will be registered on.

## User Story

As a developer
I want to create a PydanticAI agent connected to OpenRouter
So that I have a working LLM agent I can extend with tools

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | LOW |
| Systems Affected | Backend |
| Jira Issue | ARCRAG-02 |

---

## Patterns to Follow

### PydanticAI Agent Construction (from examples/basic_agent.py)
```python
# SOURCE: examples/basic_agent.py
from dotenv import load_dotenv
from pydantic_ai import Agent

load_dotenv()

agent = Agent(
    'openrouter:<model_name>',
    instructions='System prompt here',
)
```

### CLI Entrypoint (from library API)
```python
# SOURCE: pydantic_ai v1.104.0 API
agent.to_cli_sync(prog_name="arcrag")
```

### Build System (existing pattern)
```toml
# SOURCE: backend/pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src"]
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `backend/src/agent.py` | CREATE | PydanticAI agent with OpenRouter + CLI entrypoint |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Create agent module

- **File**: `backend/src/agent.py`
- **Action**: CREATE
- **Implement**:
  - `load_dotenv()` to load env vars from `.env`
  - Read `OPENROUTER_MODEL` from env with `os.getenv()`, default to `"anthropic/claude-3.5-sonnet"`
  - Module-level `agent = Agent(...)` using `f'openrouter:{model}'` string format
  - `instructions` parameter with GIS documentation guide persona (~5-8 lines instructing the agent to help students with ArcGIS Pro/ArcMap questions, include images and citations when tools are available)
  - `if __name__ == "__main__":` block that calls `agent.to_cli_sync(prog_name="arcrag")`
- **Validate**: `cd backend && .venv\Scripts\python.exe -m src.agent` (requires valid `.env` with `OPENROUTER_API_KEY` set — should launch interactive CLI)

---

## Validation

```bash
# Full validation (requires .env with valid OPENROUTER_API_KEY)
cd backend
.venv\Scripts\python.exe -m src.agent
# Type a message, verify streamed response, Ctrl+C to exit

# Model flexibility check
# Change OPENROUTER_MODEL in .env to a different model, re-run, verify it works
```

---

## Acceptance Criteria

- [ ] `backend/src/agent.py` exists with a module-level `agent` using `'openrouter:<model>'` format
- [ ] Uses `load_dotenv()` and `os.getenv()` for configuration (no pydantic-settings)
- [ ] Running `python -m src.agent` from `backend/` launches an interactive CLI connected to OpenRouter
- [ ] Changing `OPENROUTER_MODEL` env var switches the model without code changes
- [ ] Missing `OPENROUTER_API_KEY` produces a clear error message
