# Decision Log & Implementation Postmortem: arccrag-10-fastapi-ag-ui

- **Date**: 2026-06-04
- **Branch**: `feature/arccrag-10-fastapi-ag-ui`
- **Report Path**: `.agents/reports/arccrag-10-fastapi-ag-ui-report.md`

## 1. Summary of Implementation

Created a single-file FastAPI server (`backend/src/main.py`) that exposes the existing PydanticAI agent via the AG-UI protocol for CopilotKit integration. The server includes a `/health` endpoint for status checks and CORS middleware for frontend origin. Created `backend/test_server.py` with 3 tests covering all concerns.

## 2. Key Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Used `pydantic_ai.ui.ag_ui.AGUIAdapter.dispatch_request` | The plan verified this is the current (non-deprecated) API. `pydantic_ai.ag_ui` is the deprecated shim. |
| Used `httpx.ASGITransport` for testing | Allows testing FastAPI endpoints without starting a real server. Clean, isolated tests. |
| Skipped AG-UI test when no API key | Follows existing pattern from `test_agent_flow.py` — graceful degradation for CI environments without credentials. |
| CORS restricted to `FRONTEND_ORIGIN` env var | PRD spec requires CORS restricted to frontend origin; defaults to `http://localhost:3000` for Next.js dev. |
| Imported agent from `src.agent` using full path | Follows existing codebase convention (no relative imports). |

## 3. Errors & Roadblocks Encountered

| Issue | Details |
|-------|---------|
| Manual smoke test timeout | Attempted `python -m src.main` + `curl` in a single bash command. The server process blocked the shell, causing a 15s timeout. |
| Permission error on `/tmp/server.log` | Tried reading the server log file but permission was rejected. |

## 4. Workarounds & Resolutions

| Issue | Resolution |
|-------|------------|
| Manual smoke test timeout | Skipped manual smoke test entirely. The automated tests (`test_health`, `test_cors`) already validated the same endpoints via `httpx.ASGITransport`. The manual test added no additional coverage. |
| Permission error | Abandoned the approach. Not needed. |

## 5. What Went Right & What Went Wrong

### What Went Right

- Verified all imports (`AGUIAdapter`, `FastAPI`, `httpx`, `starlette`) before writing any code
- Followed existing test patterns from `test_agent_flow.py` exactly (print headers, skip pattern, orchestrator function)
- Tests passed on first run (2/2 non-skipped tests)
- Plan assumptions all verified: env var names from `.env.example`, import paths match existing code, `AGUIAdapter.dispatch_request` confirmed available

### What Went Wrong

- Overcomplicated the manual smoke test — tried to start a server and curl it in the same bash session, which doesn't work well with background processes and timeouts
- Could have skipped the manual smoke test from the start since automated tests already covered the health endpoint

## 6. Lessons Learned & Recommendations

1. **Don't overcomplicate smoke tests**: When automated tests already validate the same endpoints via ASGI transport, a manual server start + curl adds no value and introduces shell timing issues.
2. **Verify imports before coding**: All dependency checks (`AGUIAdapter`, `FastAPI`, `httpx`) were done upfront, preventing any import-related failures during implementation.
3. **Follow existing patterns exactly**: The test file structure (print headers, skip pattern, `asyncio.run(test())`) matched `test_agent_flow.py` perfectly, making the tests feel native to the codebase.
