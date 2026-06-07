# Implementation Report

**Plan**: `.agents/plans/arccrag-17-production-docker-compose.plan.md`
**Branch**: `feature/arccrag-17-production-docker-compose`
**Status**: COMPLETE (dev-PC scope; VPS runbook inlined below)

## Summary

Added a production-hardened `docker-compose.prod.yml` plus a multi-stage
`frontend/Dockerfile` so `docker compose -f docker-compose.prod.yml up`
brings up the full runtime stack — two idempotent init containers + FastAPI
backend + Next.js frontend — with memory limits, restart policies, health
checks, and the existing `arcrag_data` named volume. Qdrant remains external
(per user decision) and is connected to via `QDRANT_URL` from
`backend/.env`. The dev `docker-compose.yml` is untouched.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create `.dockerignore` excluding `node_modules` and `.next` | `frontend/.dockerignore` | ✅ |
| 2 | Add `output: 'standalone'` for smaller runtime image | `frontend/next.config.js` | ✅ |
| 3 | Multi-stage `node:20-alpine` Dockerfile with non-root `nextjs` user | `frontend/Dockerfile` | ✅ |
| 4 | Production compose (4 services, no `qdrant`, `3000:3000` only) | `docker-compose.prod.yml` | ✅ |
| 5 | Static validation test suite (29 assertions) | `backend/test_prod_compose.py` | ✅ |
| 6 | Pre-flight on VPS | (deferred — see VPS runbook) | ⏭ |
| 7 | Full production run on VPS | (deferred — see VPS runbook) | ⏭ |
| 8 | Documentation (decision log + stories.md update) | (deferred to VPS run per plan) | ⏭ |

## Validation Results

| Check | Command | Result |
|-------|---------|--------|
| `.dockerignore` excludes `node_modules` | `grep -q '^node_modules$' frontend/.dockerignore` | ✅ |
| `next.config.js` has `output: 'standalone'` | `node -e "const c=require('./frontend/next.config.js'); if(c.output!=='standalone') process.exit(1)"` | ✅ |
| Dockerfile has all 3 stages + ARG + server.js + HEALTHCHECK | `grep` on `frontend/Dockerfile` | ✅ |
| Prod compose structure (4 services, no qdrant, mem_limits, restart, healthcheck, ports) | `python3 -c "import yaml; ..."` | ✅ |
| Static test suite | `python3 backend/test_prod_compose.py` | ✅ **29 passed, 0 failed** |
| Existing test suites | `python3 test_load_qdrant.py`, `test_search.py` | ✅ ALL TESTS PASSED (Qdrant-down tests skip cleanly) |
| Dev `docker-compose.yml` untouched | `git diff docker-compose.yml` | ✅ (no diff) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `frontend/.dockerignore` | CREATE | +9 |
| `frontend/next.config.js` | UPDATE (1 line) | +1 |
| `frontend/Dockerfile` | CREATE | +34 |
| `docker-compose.prod.yml` | CREATE | +73 |
| `backend/test_prod_compose.py` | CREATE | +177 |
| `docker-compose.yml` | NO CHANGE | 0 |

## Deviations from Plan

| # | Deviation | Rationale |
|---|-----------|-----------|
| 1 | `frontend/Dockerfile` `CMD` uses exec form `["node", "server.js"]` instead of shell form `node server.js` | Exec form is the standard for `CMD` in Dockerfiles; passes the lint `node server.js` substring check in spirit (both `node` and `server.js` are present). The test suite explicitly handles this with `'CMD ["node", "server.js"]' in text`. |
| 2 | `test_prod_compose.py` parses `next.config.js` via regex (not Node `require()`) | The plan suggested `node -e "require(...)"` for ad-hoc validation; the test suite is Python-only (no Node dependency) and uses a regex to extract the `output:` value. Functionally equivalent. |
| 3 | Test suite has **29** assertions, exceeding the plan's "15+ assertions" target | Each plan-listed check is implemented as one or more granular assertions to give better failure diagnostics. Plan said "15+ static assertions" — 29 ≥ 15. |

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `backend/test_prod_compose.py` | 4 test groups, 29 individual assertions: (1) `frontend/Dockerfile` structure, (2) `frontend/.dockerignore` excludes `node_modules`/`.next`, (3) `frontend/next.config.js` has `output: 'standalone'`, (4) `docker-compose.prod.yml` has 4 services, no `qdrant`, correct `mem_limit`/`restart`/`healthcheck`/`ports`/`build.args`/`depends_on` |

## Acceptance Criteria — Dev-PC Scope (1-21)

- [x] `docker-compose.prod.yml` exists and parses as valid YAML
- [x] `docker-compose.prod.yml` defines exactly 4 services: `arcrag-init`, `arcrag-init-arcmap`, `backend`, `frontend` (no `qdrant` — external)
- [x] `backend` has `mem_limit: 1g` and `restart: unless-stopped`
- [x] `frontend` has `mem_limit: 512m` and `restart: unless-stopped`
- [x] `arcrag-init` has `restart: "no"`
- [x] `arcrag-init-arcmap` has `restart: "no"`
- [x] `backend` has a `healthcheck` block (using `wget --spider` against `/health`)
- [x] `frontend.ports` is `["3000:3000"]`
- [x] `backend` does NOT have a `ports:` key (internal-only)
- [x] `frontend.build.args` contains `NEXT_PUBLIC_BACKEND_URL=http://backend:8000`
- [x] `arcrag-init-arcmap.depends_on` includes `arcrag-init` with `condition: service_completed_successfully`
- [x] `backend.depends_on` includes both `arcrag-init` and `arcrag-init-arcmap` with `condition: service_completed_successfully`
- [x] **No service has `qdrant` in its `depends_on`** (Qdrant is external)
- [x] `frontend.depends_on.backend` has `condition: service_healthy`
- [x] Top-level `volumes:` declares `arcrag_data:`; **no `qdrant_data:`** (Qdrant has its own external volume)
- [x] `frontend/Dockerfile` exists with three stages (`deps`, `build`, `runtime`) and uses `node:20-alpine`
- [x] `frontend/Dockerfile` declares `ARG NEXT_PUBLIC_BACKEND_URL` and `CMD ["node", "server.js"]`
- [x] `frontend/Dockerfile` has a `HEALTHCHECK` instruction
- [x] `frontend/.dockerignore` exists and excludes `node_modules` and `.next`
- [x] `frontend/next.config.js` has `output: 'standalone'`
- [x] `backend/test_prod_compose.py` exists and runs 29 static assertions, all passing

## Acceptance Criteria — VPS Scope (22-32) — DEFERRED

These are run on the VPS by the operator. The runbook is reproduced below.

## Jira Update

**Jira Issue**: `ARCRAG-17`

The Atlassian MCP tools (`mcp__atlassian__*`) are not available in this
execution environment, and neither `gh` nor `jira` CLIs are installed on
PATH. The Jira update phase (transition + comment) could not be performed
automatically. The operator should manually:

1. Transition ARCRAG-17 to **In Review** (or appropriate status)
2. Add a comment with this implementation summary and a link to
   `.agents/reports/arccrag-17-production-docker-compose-report.md`
3. Once the VPS run is complete, transition to **Done**

## VPS-Side Runbook (deferred to VPS run)

```bash
# 0. Sync to VPS
cd /opt/arcpro-docs && git pull origin feature/arccrag-17-production-docker-compose

# 1. Verify the external Qdrant is reachable
wget -qO- http://<qdrant-host>:6333/health || { echo "ERROR: external Qdrant not reachable"; exit 1; }

# 2. Verify .env is updated for production
grep -q '^OPENROUTER_API_KEY=sk-or-v1-' backend/.env || { echo "ERROR: set a real OPENROUTER_API_KEY in backend/.env"; exit 1; }
grep -q '^QDRANT_URL=http' backend/.env || { echo "ERROR: set QDRANT_URL in backend/.env to the external Qdrant"; exit 1; }

# 3. Pre-flight: build images + start runtime-only stack (no frontend yet)
docker compose -f docker-compose.prod.yml build backend frontend
docker compose -f docker-compose.prod.yml config > /dev/null
docker compose -f docker-compose.prod.yml up -d arcrag-init arcrag-init-arcmap backend
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml exec backend wget -qO- http://localhost:8000/health
docker compose -f docker-compose.prod.yml logs arcrag-init arcrag-init-arcmap
docker compose -f docker-compose.prod.yml down

# 4. Full prod run
docker compose -f docker-compose.prod.yml up -d --build

# 5. Monitor
docker compose -f docker-compose.prod.yml logs -f arcrag-init arcrag-init-arcmap
docker compose -f docker-compose.prod.yml ps

# 6. Verify
curl http://localhost:3000/                                                                                         # frontend HTML
docker compose -f docker-compose.prod.yml exec backend wget -qO- http://localhost:8000/health                        # 200 OK with qdrant:"connected"
docker compose -f docker-compose.prod.yml exec backend wget -qO- $(grep QDRANT_URL backend/.env | cut -d= -f2)/collections/arcgis_docs | python3 -c "import json,sys; print('Total points:', json.load(sys.stdin)['result']['points_count'])"

# 7. Test the chat
# Open http://<vps>:3000 in a browser, ask "What is the Buffer tool?"
# Expected: grounded answer with image + source link

# 8. Test restart policy
docker compose -f docker-compose.prod.yml restart backend
docker compose -f docker-compose.prod.yml ps  # backend should be Up (healthy) within 30s
```

**Note:** The `arcrag_data` named volume persists across `docker compose down`
(without `-v`) and `docker compose up` cycles. Don't run
`docker compose down -v` unless you want to start the full ingestion from
scratch. **Qdrant is not part of this compose and is not affected by
`docker compose down` / `up` — it runs externally.**
