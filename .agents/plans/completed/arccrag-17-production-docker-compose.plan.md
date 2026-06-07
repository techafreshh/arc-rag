# Plan: ARCRAG-17 — Production Docker Compose

## Summary

Add a production-hardened `docker-compose.prod.yml` (plus a new `frontend/Dockerfile`) so that `docker compose -f docker-compose.prod.yml up` brings up the runtime stack — two ingest init containers + FastAPI backend + Next.js frontend — with memory limits, restart policies, health checks, and persistent named volumes. **Qdrant is assumed to already be running externally on the VPS** (separate from this compose) and is NOT brought up by `docker-compose.prod.yml`. The current `docker-compose.yml` covers ingestion (Qdrant + 2 inits + backend) but has no frontend service, no memory limits, and no restart policies, so it is suitable for dev/single-host use but not for the production VPS. The dev `docker-compose.yml` stays untouched per the user's decision; the prod file is a separate overlay that reuses the existing `backend/Dockerfile` and adds a multi-stage `frontend/Dockerfile`. Reuses the ARCRAG-15/16 dual-init pattern, which is already idempotent per source, so the inits can safely be included in prod: they no-op (skip in ~5s) when the source's points are already in the external Qdrant, and they can resume from the existing `arcrag_data` named volume's checkpoints if a re-ingestion is ever needed. Backend, frontend, and inits all connect to the external Qdrant via the `QDRANT_URL` env var.

## User Story

As a developer
I want a production-ready Docker Compose configuration that runs the full stack (Qdrant + ArcGIS Pro/ArcMap ingestion + FastAPI backend + Next.js frontend) with memory limits, restart policies, persistent volumes, and only the frontend port exposed externally
So that the VPS deployment is a single `docker compose -f docker-compose.prod.yml up -d --build` command and the resulting system survives container restarts without losing the Qdrant index or ingestion checkpoints

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (production infrastructure; mirrors ARCRAG-15/16 dev→prod pattern) |
| Complexity | MEDIUM (lower than ARCRAG-15/16 because backend Dockerfile + ingestion scripts already exist; main work is compose wiring + new frontend Dockerfile + memory/restart policies + tests) |
| Systems Affected | `docker-compose.prod.yml` (new — runtime stack only, no Qdrant), `frontend/Dockerfile` (new), `frontend/.dockerignore` (new), `frontend/next.config.js` (1-line change for `output: 'standalone'`), `backend/test_prod_compose.py` (new) |
| Jira Issue | ARCRAG-17 |
| Blocked By | ARCRAG-10 ✅, ARCRAG-11 ✅ |
| Blocks | ARCRAG-18 (HTTPS reverse proxy), ARCRAG-19 (E2E validation) |

---

## Current State (verified during planning)

| Artifact | State | Implication |
|----------|-------|-------------|
| `docker-compose.yml` | 4 services: `qdrant`, `arcrag-init` (ArcPro), `arcrag-init-arcmap` (ArcMap), `backend`. No `frontend`. No `mem_limit` on any service. No `restart` on backend/qdrant. Ports 6333, 6334, 8000 all mapped to host. | Dev/single-host. Sufficient for ARCRAG-15/16 testing on the dev PC, not hardened for the VPS. ARCRAG-17 does NOT touch this file. |
| **External Qdrant on VPS** | **Already running** (per user statement). Has the `arcgis_docs` collection populated by ARCRAG-15/16 with both `source: arcpro` and `source: arcmap` points. | Prod compose does NOT bring up Qdrant. `QDRANT_URL` env var must point to the external Qdrant (e.g., `http://<qdrant-host>:6333` — set in `backend/.env` on the VPS). |
| `backend/Dockerfile` | `python:3.11-slim`, installs all deps (`pydantic-ai[openrouter]`, `fastapi`, `uvicorn`, `httpx`, `bs4`, `qdrant-client`, `python-dotenv`, `cachetools`), copies `src/` and `scripts/`, `CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]`. | Production-ready as-is. Reused for `backend` and both `arcrag-init*` services. |
| `frontend/Dockerfile` | **Does not exist** | Must be created. Multi-stage build with `node:20-alpine`. |
| `frontend/.dockerignore` | **Does not exist** | Must be created. Excludes `node_modules`, `.next`, etc. |
| `frontend/next.config.js` | `reactStrictMode: true`, `images.remotePatterns` for `pro.arcgis.com` / `desktop.arcgis.com` / `doc.esri.com`. **No `output: 'standalone'`.** | Need to add `output: 'standalone'` to keep runtime image small (~150 MB instead of ~1 GB). |
| `frontend/package.json` | `next ^15.1.0`, `react ^19.0.0`, `@copilotkit/react-core ^1.8.0`, `@copilotkit/react-ui ^1.8.0`, `@copilotkit/runtime ^1.8.0`, `@ag-ui/client` (transitive). Scripts: `dev`, `build`, `start`, `lint`. | `npm run build && npm start` is the production path. `start` runs `next start` (port 3000). With `output: 'standalone'`, Docker will run `node server.js` instead. |
| `frontend/src/app/api/copilotkit/route.ts` | Server-side route mounts `CopilotRuntime` + `HttpAgent` to `${NEXT_PUBLIC_BACKEND_URL}/ag-ui`. | The API route runs server-side inside the container, so `NEXT_PUBLIC_BACKEND_URL` is read at build time and points to the Docker-internal `http://backend:8000`. Browser never talks to backend directly. |
| `scripts/init.sh` | Per-source idempotency (per ARCRAG-16). Runs `build_index.py` then `load_qdrant.py`. Wait-for-Qdrant poll loop (60 × 5s). | Safe to include in prod compose — re-running an init is a no-op when its source's points already exist. |
| `backend/src/main.py` | FastAPI app, `/health` endpoint, `/ag-ui` endpoint, CORS restricted to `FRONTEND_ORIGIN` env var (default `http://localhost:3000`). | `CORS` is a non-issue because the browser hits `/api/copilotkit` (same origin in prod via reverse proxy or same host in dev), which then proxies server-to-server to the backend. |
| `.env.example` | `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_API_KEY`, `QDRANT_URL`, `QDRANT_COLLECTION`, `BACKEND_HOST`, `BACKEND_PORT`, `NEXT_PUBLIC_BACKEND_URL`. | Production reuses `backend/.env` (same filename). Runbook will verify a real `OPENROUTER_API_KEY` is present. |
| Qdrant image tag | `qdrant/qdrant:v1.12.1` (per `docker-compose.yml:3`) | Used in dev only. Prod assumes Qdrant is already running externally (managed by the user). The image tag/version must match the dev tag for vector compatibility, but ARCRAG-17 does not need to bring up a Qdrant container. |
| `arcrag_data` named volume | Created by ARCRAG-15 (on the VPS) and used by ARCRAG-16. Contains `arcpro_urls.json`, `arcmap_urls.json`, `arcpro_index.json`, `arcmap_index.json`, `.checkpoint_*_index.json`. | Prod compose reuses this same named volume. The inits can resume from existing checkpoints if they ever need to re-run. |
| VPS target | Self-hosted server (per PRD §3 and §4). Specs not yet pinned; user confirmed `qdrant=4g, backend=1g, frontend=512m` limits. | Memory limits match the user's choice. The user can override on the VPS if the host has more or less RAM. |

---

## Patterns to Follow

### ARCRAG-15/16 init container pattern (parameterize, don't rewrite)
```bash
# SOURCE: scripts/init.sh:1-40
#!/bin/bash
set -e
QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-arcgis_docs}"
SOURCE="${SOURCE:-arcpro}"
# ... waits for Qdrant, per-source idempotency check, runs build_index then load_qdrant
```
**Apply as-is in prod compose.** Both `arcrag-init` and `arcrag-init-arcmap` services reuse this script with their own `SOURCE` env override.

### ARCRAG-15/16 compose init service (mirror)
```yaml
# SOURCE: docker-compose.yml:16-50
arcrag-init:
  build: { context: ., dockerfile: backend/Dockerfile }
  command: ["/app/scripts/init.sh"]
  restart: "no"
  env_file: backend/.env
  environment:
    - QDRANT_URL=http://qdrant:6333
    - QDRANT_COLLECTION=arcgis_docs
  volumes:
    - arcrag_data:/app/data
  depends_on:
    qdrant:
      condition: service_healthy
```
**Apply as-is in prod compose.** Add `mem_limit: 1g` (defensive; inits are short-lived so it almost never matters, but prevents runaway on bad data).

### ARCRAG-15/16 backend service (gated on both inits)
```yaml
# SOURCE: docker-compose.yml:51-70
backend:
  build: { context: ., dockerfile: backend/Dockerfile }
  command: ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
  ports: ["8000:8000"]
  env_file: backend/.env
  environment: [QDRANT_URL=http://qdrant:6333, QDRANT_COLLECTION=arcgis_docs]
  volumes: [arcrag_data:/app/data]
  depends_on:
    qdrant: { condition: service_healthy }
    arcrag-init: { condition: service_completed_successfully }
    arcrag-init-arcmap: { condition: service_completed_successfully }
```
**Apply in prod compose with these changes:**
- Drop `ports: ["8000:8000"]` (per user decision: only frontend is externally exposed)
- Add `mem_limit: 1g`
- Add `restart: unless-stopped`
- Add `healthcheck: test: ["CMD", "wget", "-q", "--spider", "http://localhost:8000/health"]`

### CopilotKit runtime URL pattern (server-to-server)
```typescript
# SOURCE: frontend/src/app/api/copilotkit/route.ts:9-17
const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
const runtime = new CopilotRuntime({
  agents: { default: new HttpAgent({ url: `${backendUrl}/ag-ui` }) },
});
```
**Apply in prod:** `NEXT_PUBLIC_BACKEND_URL=http://backend:8000` is baked at frontend build time via `--build-arg`. The API route runs server-side inside the `frontend` container and reaches the `backend` service via Docker's internal DNS.

### Next.js standalone output (smaller images)
Next.js supports `output: 'standalone'` in `next.config.js`, which produces a self-contained `server.js` that bundles only the runtime dependencies. Reduces image size from ~1 GB to ~150 MB and eliminates the need for `node_modules` in the runtime stage.
```js
// SOURCE: Next.js docs — https://nextjs.org/docs/app/api-reference/config/next-config-js/output
module.exports = { output: 'standalone' };
```

---

## Key Design Decisions

### 1. Separate `docker-compose.prod.yml`, leave dev `docker-compose.yml` untouched

**Decision:** Create a new `docker-compose.prod.yml` that is a self-contained production stack. Do not modify `docker-compose.yml`.

**Rationale (per user answer):** The user explicitly chose "Leave dev `docker-compose.yml` untouched, prod in separate file (Recommended)". Two-file separation has clear benefits:
- Dev compose keeps its current shape (qdrant + 2 inits + backend) and is the "iterate on the dev PC" path
- Prod compose is the "deploy to VPS" path with memory limits, restart policies, frontend service, and only the frontend port exposed
- Each file has one purpose; merging them with `extends:` / YAML anchors adds complexity that isn't justified at this scale

The downside (some duplication of `qdrant`, `arcrag-init`, `arcrag-init-arcmap`, `backend` service blocks) is acceptable for clarity.

### 2. Include both init containers in prod compose (not just runtime)

**Decision:** `docker-compose.prod.yml` includes `arcrag-init` (ArcPro), `arcrag-init-arcmap` (ArcMap), `backend`, and `frontend`. A single `up -d --build` produces a fully-ingested, fully-served system. **Qdrant is NOT in this compose** — it's assumed to be running externally on the VPS (per user statement).

**Rationale (per user answer):** The user chose "Include both inits (Recommended)". This is safe because:
- `scripts/init.sh` is idempotent per source (per ARCRAG-16's per-source Qdrant count check). Re-runs are no-ops when the source's points are already loaded. With Qdrant already containing both `source: arcpro` and `source: arcmap` points, the inits will each wait for Qdrant, do the per-source count check, see points exist, log "skipping ingestion", and exit 0 in ~5-10 seconds.
- `restart: "no"` on inits means they don't loop on failure — failures are loud and explicit.
- The `backend` and `frontend` services gate on `arcrag-init-arcmap: { condition: service_completed_successfully }`, so they don't start until both inits have completed (whether the ingestion actually ran or was skipped).
- Single-command deployment is much simpler for the user than a two-step "ingest, then serve" workflow.
- The init containers are NOT gated on a Qdrant service (because Qdrant is external). They poll the external Qdrant via `QDRANT_URL` from `init.sh`'s wait-for-Qdrant loop. If the external Qdrant is down, the inits fail loudly.

### 3. Memory limits: backend=1g, frontend=512m (no Qdrant limit — Qdrant is external)

**Decision (per user answer):** Apply these limits in the prod compose. No `mem_limit` on the inits (they're short-lived one-shots; their memory is bounded by the script's working set, which is small).

**Rationale:**
- **Backend 1 GB:** Python interpreter + FastAPI + PydanticAI + httpx client is comfortably under 1 GB at idle. The agent's LLM calls go to OpenRouter, so memory is for process state only.
- **Frontend 512 MB:** Next.js standalone + Node 20 alpine is well under 512 MB. The CopilotKit client is small.
- **Inits (`arcrag-init`, `arcrag-init-arcmap`):** No `mem_limit`. They run for hours but their memory footprint is small (a few `httpx` connections + BeautifulSoup DOM trees). If they ever need a cap, ~1 GB each is plenty. The user can add `mem_limit: 1g` defensively if they prefer — recommended for production hygiene.
- **Qdrant (external):** Not in this compose, so no `mem_limit` is set here. The user manages Qdrant's memory externally (e.g., a separate systemd unit or a sidecar compose with its own limits).

### 4. External exposure: only frontend port 3000

**Decision (per user answer):** `frontend.ports: ["3000:3000"]`. `backend` is NOT port-mapped to the host. Qdrant is external and not part of this compose (its exposure is the user's concern, not ARCRAG-17's).

**Rationale:** The host firewall is the first line of defense. By exposing only the frontend, an attacker cannot directly reach `/ag-ui` (backend). The external Qdrant is the user's existing setup — if it's exposed to the public, that's a pre-existing risk ARCRAG-17 cannot fix; if it's on a private network, the user can leave it that way. ARCRAG-18 (Caddy reverse proxy with HTTPS) will terminate TLS in front of port 3000 and proxy to the frontend container; this prod compose is the foundation ARCRAG-18 builds on.

**Internal debugging:** When something goes wrong, an operator can use `docker compose exec backend curl http://localhost:8000/health` to debug the backend without exposing the port. To debug the external Qdrant, the operator can `wget -qO- http://<qdrant-host>:6333/collections/arcgis_docs` from the host (assuming the Qdrant host allows the VPS's IP).

### 5. External Qdrant is reached via `QDRANT_URL` env var (no Compose service)

**Decision:** Qdrant is NOT a service in `docker-compose.prod.yml`. All services that need Qdrant (init containers, backend) read `QDRANT_URL` from `backend/.env` (already supported via `env_file: backend/.env`). On the VPS, `backend/.env` must set `QDRANT_URL=http://<qdrant-host>:6333` (or whatever the external Qdrant's URL is).

**Rationale:** Per user statement, Qdrant is already running on the VPS. The cleanest way to connect to an externally-managed service from inside a Docker container is to set the URL via env var. The existing `scripts/init.sh` and `backend/src/main.py` already read `QDRANT_URL` from env (see `init.sh:4` and `main.py:15`), so no code change is needed. The only requirement is that `backend/.env` on the VPS is updated to point to the external Qdrant.

**Why not reference Qdrant via Compose's `external: true` network?** That requires Qdrant to be on a user-defined Docker network with a known name, which is fragile and ties the prod compose to the Qdrant deployment's specifics. The env-var approach is more portable and matches the dev compose's pattern (where `QDRANT_URL=http://qdrant:6333` is set in the `environment:` block, overriding the `.env`'s `http://localhost:6333`).

**Production env example (VPS `backend/.env`):**
```env
# ... other vars ...
QDRANT_URL=http://localhost:6333   # if Qdrant runs on the VPS host
# OR
QDRANT_URL=http://qdrant.internal:6333   # if Qdrant is on a different container/host
```

**Healthcheck on the backend** still uses `wget --spider http://localhost:8000/health` (loopback inside the container, not the Qdrant URL). The `/health` endpoint itself probes Qdrant via `QDRANT_URL` and returns `qdrant: "connected"` or `qdrant: "disconnected"`.

### 6. `NEXT_PUBLIC_BACKEND_URL` baked at build time

**Decision (per user answer):** The frontend Dockerfile declares `ARG NEXT_PUBLIC_BACKEND_URL=http://backend:8000` and the prod compose passes `--build-arg NEXT_PUBLIC_BACKEND_URL=http://backend:8000`. The value is frozen at image build time.

**Rationale:** Next.js's `NEXT_PUBLIC_*` env vars are inlined at build time (this is a Next.js convention, not a project choice). The API route at `frontend/src/app/api/copilotkit/route.ts:9` reads `process.env.NEXT_PUBLIC_BACKEND_URL` server-side, so it uses the build-time value. Inside the Docker network, `http://backend:8000` resolves to the `backend` service via Compose's internal DNS.

**Trade-off:** Changing the backend URL requires rebuilding the frontend image. This is acceptable for prod (the URL is stable across deployments). Documented in the runbook.

**Alternative considered:** Pass `BACKEND_URL` (no `NEXT_PUBLIC_` prefix) as a runtime env var and refactor the API route to read it. Rejected because: (a) the build-time approach is the standard Next.js pattern, (b) it requires no code change, (c) runtime env vars in Next.js are tricky in production builds.

### 7. Multi-stage frontend Dockerfile with `output: 'standalone'`

**Decision:** Three-stage build (`deps` → `build` → `runtime`) using `node:20-alpine` throughout. Runtime image contains only the standalone server + static assets, not `node_modules` or the build toolchain.

**Rationale:**
- Smaller image (~150 MB vs ~1 GB) means faster pulls on the VPS
- No build tools in the runtime image = smaller attack surface
- `output: 'standalone'` is the official Next.js feature for this exact use case (per Next.js docs)
- Non-root `nextjs` user for defense in depth

**Healthcheck:** `wget -q --spider http://localhost:3000/`. Alpine ships with BusyBox `wget`, so no extra dependencies. Returns 0 if the frontend serves a 200, non-zero otherwise.

### 8. Healthcheck on backend using existing `/health` endpoint

**Decision:** Backend uses `test: ["CMD", "wget", "-q", "--spider", "http://localhost:8000/health"]` as its Docker healthcheck. The frontend's `depends_on.backend: { condition: service_healthy }` won't start until the backend's `/health` returns 200.

**Rationale:** The `/health` endpoint at `backend/src/main.py:30-39` already returns 200 with `{"status":"ok", "qdrant":"connected", "model":"..."}`. If Qdrant is unreachable, the endpoint still returns 200 with `qdrant: "disconnected"`, but that's a soft signal — for the purpose of "is the backend process up", it's fine. A stricter check would parse the JSON and fail on `qdrant != "connected"`, but the current approach is sufficient and matches the ARCRAG-15/16 precedent.

**Trade-off:** A backend that starts but can't reach the external Qdrant would pass the healthcheck. The `depends_on: arcrag-init-arcmap: service_completed_successfully` gate is the real protection — by the time the backend starts, the init container has already polled the external Qdrant and confirmed it is reachable. If the inits fail (Qdrant down), the backend never starts.

### 9. Restart policy: `unless-stopped` on long-lived services, `no` on inits

**Decision:**
- `backend`, `frontend`: `restart: unless-stopped`
- `arcrag-init`, `arcrag-init-arcmap`: `restart: "no"` (matches ARCRAG-15/16)
- **Qdrant: N/A** (external, managed outside this compose)

**Rationale:** Long-lived services should auto-recover from crashes (OOM, transient network blip, host reboot). Inits should NOT auto-restart — if ingestion failed, an operator should investigate rather than have the init silently loop and overwrite partial data.

`unless-stopped` (vs `always`): if the operator explicitly stops a service with `docker compose stop`, it stays stopped. This is the right default — explicit stops are intentional.

### 10. Static-only test suite in `backend/test_prod_compose.py`

**Decision:** All ARCRAG-17 validation runs on the dev PC without Docker. No integration tests, no live container runs.

**Rationale (per user answer "Same as ARCRAG-15/16: code complete on PC, full run on VPS"):** The user chose to follow the ARCRAG-15/16 precedent of doing static validation on PC and deferring the full `docker compose up` to the VPS. This avoids the multi-GB image build + multi-hour init runs on the dev laptop.

**What's testable statically:**
- `docker-compose.prod.yml` parses (YAML syntax)
- 4 services present with correct names (and no `qdrant` service)
- Memory limits on the right services
- Restart policies on the right services
- Healthcheck on backend
- Frontend Dockerfile exists with the right structure
- `next.config.js` has `output: 'standalone'`
- `.dockerignore` excludes `node_modules`

**What's deferred to VPS:**
- `docker compose -f docker-compose.prod.yml config` actually resolves
- The Docker images build successfully
- The full chain (qdrant → inits → backend → frontend) starts up
- The frontend HTML loads in a browser
- The chat works end-to-end

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `docker-compose.prod.yml` | CREATE | Production-hardened compose with 4 services (`arcrag-init`, `arcrag-init-arcmap`, `backend`, `frontend`), memory limits, restart policies, frontend service. **No `qdrant` service** — Qdrant is external and connected via `QDRANT_URL` env var. |
| `frontend/Dockerfile` | CREATE | Multi-stage `node:20-alpine` build with `output: 'standalone'` |
| `frontend/.dockerignore` | CREATE | Excludes `node_modules`, `.next`, `.git`, etc. |
| `frontend/next.config.js` | UPDATE (1 line) | Add `output: 'standalone'` |
| `backend/test_prod_compose.py` | CREATE | Static validation of prod compose + frontend Dockerfile (no Docker required) |
| `.agents/plans/arccrag-17-production-docker-compose.plan.md` | CREATE (this file) | Plan document |
| `.agents/reports/arccrag-17-production-docker-compose-report.md` | CREATE (post-run) | Implementation report (deferred to VPS run) |
| `.agents/decisions/arccrag-17-production-docker-compose.md` | CREATE (post-run) | Decision log / postmortem (deferred to VPS run) |
| `.agents/stories/stories.md` | UPDATE (post-run) | Mark ARCRAG-17 in-progress (now) → ✅ Completed (after VPS run) |
| `docker-compose.yml` | NO CHANGE | Dev/single-host compose, left untouched per user decision |

---

## Tasks

Execute in order. Each task is atomic and verifiable on the dev PC. Tasks 1-4 are code-only; Task 5 is the long-running run on the VPS.

### Task 1: Create `frontend/.dockerignore`

- **File**: `frontend/.dockerignore`
- **Action**: CREATE
- **Content**:
  ```
  node_modules
  .next
  .git
  .gitignore
  *.tsbuildinfo
  npm-debug.log*
  .DS_Store
  README.md
  ```
- **Rationale**: Excludes `node_modules` and `.next` (the build cache and the standalone output) so Docker doesn't pull them into the build context. `*.tsbuildinfo` is excluded per the ARCRAG-14 commit that added it to `.gitignore`.
- **Validate**: `cat frontend/.dockerignore` shows the 9 lines above.

### Task 2: Modify `frontend/next.config.js` to add `output: 'standalone'`

- **File**: `frontend/next.config.js`
- **Action**: UPDATE (1 line addition)
- **Implement**: Add `output: 'standalone',` to the `nextConfig` object (between `reactStrictMode` and `images`).
- **Mirror**: Standard Next.js pattern. See https://nextjs.org/docs/app/api-reference/config/next-config-js/output.
- **Avoid**: Don't remove the existing `images.remotePatterns` — the chat renders images from `pro.arcgis.com`, `desktop.arcgis.com`, and `doc.esri.com` and this config is required for that.
- **Validate**: `node -e "const c = require('./frontend/next.config.js'); console.log(c.output)"` should print `standalone`. (Or `cat frontend/next.config.js` and visually confirm.)

### Task 3: Create `frontend/Dockerfile`

- **File**: `frontend/Dockerfile`
- **Action**: CREATE
- **Implement**: Three-stage build:
  - **Stage 1 (`deps`):** `node:20-alpine`, copy `package.json` + `package-lock.json`, run `npm ci --no-audit --no-fund`. Produces a clean `node_modules`.
  - **Stage 2 (`build`):** `node:20-alpine`, declare `ARG NEXT_PUBLIC_BACKEND_URL=http://backend:8000`, set as `ENV`, copy `node_modules` from `deps`, copy source, run `npm run build`. Produces `.next/standalone/` + `.next/static/` + `public/`.
  - **Stage 3 (`runtime`):** `node:20-alpine`, create `nextjs` user (uid 1001), copy standalone output from `build` with `--chown=nextjs:nodejs`, switch to non-root user, expose 3000, declare `HEALTHCHECK` using `wget --spider`, `CMD ["node", "server.js"]`.
- **Mirror**: Standard Next.js standalone Dockerfile pattern. See Next.js docs example.
- **Avoid**: Don't use `npm run dev` anywhere; don't install build tools in the runtime stage; don't use `latest` tags (pin `20-alpine` for reproducibility).
- **Validate**: `cat frontend/Dockerfile` shows the three stages; `node -e "const fs=require('fs'); const d=fs.readFileSync('frontend/Dockerfile','utf8'); ['FROM node:20-alpine AS deps','FROM node:20-alpine AS build','FROM node:20-alpine AS runtime','ARG NEXT_PUBLIC_BACKEND_URL','node server.js','HEALTHCHECK'].forEach(s => console.assert(d.includes(s), 'missing: '+s));"` exits 0.

### Task 4: Create `docker-compose.prod.yml`

- **File**: `docker-compose.prod.yml`
- **Action**: CREATE
- **Implement** (4 services in dependency order — **no `qdrant` service** because Qdrant runs externally):
  1. `arcrag-init` — `build: { context: ., dockerfile: backend/Dockerfile }`, `command: ["/app/scripts/init.sh"]`, `restart: "no"`, `env_file: backend/.env`, `environment: [QDRANT_COLLECTION=arcgis_docs]` (no `QDRANT_URL` override here — it comes from `backend/.env` which the operator sets to the external Qdrant's URL on the VPS), `volumes: [arcrag_data:/app/data]`. **No `depends_on: qdrant`** (Qdrant is external). The init's `init.sh` polls `QDRANT_URL` (from env) and exits 0 if the data is already loaded.
  2. `arcrag-init-arcmap` — mirror of `arcrag-init` with `SOURCE=arcmap` added to `environment:` and `arcrag-init: { condition: service_completed_successfully }` added to `depends_on:`
  3. `backend` — `build: { context: ., dockerfile: backend/Dockerfile }`, `command: ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]`, `restart: unless-stopped`, `mem_limit: 1g`, NO `ports:` (internal only), `env_file: backend/.env`, `environment: [QDRANT_COLLECTION=arcgis_docs]`, `volumes: [arcrag_data:/app/data]`, `healthcheck: { test: ["CMD", "wget", "-q", "--spider", "http://localhost:8000/health"], interval: 30s, timeout: 5s, retries: 3, start_period: 30s }`, `depends_on: { arcrag-init: { condition: service_completed_successfully }, arcrag-init-arcmap: { condition: service_completed_successfully } }`. **No `depends_on: qdrant`** (Qdrant is external; the init's success is the proxy for "Qdrant is reachable and has data").
  4. `frontend` — `build: { context: ./frontend, args: [NEXT_PUBLIC_BACKEND_URL=http://backend:8000] }`, `restart: unless-stopped`, `mem_limit: 512m`, `ports: ["3000:3000"]`, `depends_on: { backend: { condition: service_healthy } }`
- **Top-level `volumes:`:** `arcrag_data:` (reuses the named volume from ARCRAG-15/16 — contains the ingestion checkpoints and index JSONs). **No `qdrant_data:`** (Qdrant has its own external volume).
- **Mirror**: ARCRAG-15/16 compose patterns for the init and backend services; the frontend is new but follows the same shape.
- **Avoid**: Don't reference a `qdrant` service. Don't map backend's port 8000 to the host. Don't add `init: true` on the frontend (not needed in modern Docker). Don't use a `version: '3.x'` top-level key (obsolete in Compose v2). Don't override `QDRANT_URL` in the `environment:` block — let `env_file: backend/.env` provide it so the operator controls it from one place.
- **Validate**: `python -c "import yaml; d=yaml.safe_load(open('docker-compose.prod.yml')); assert set(d['services'].keys()) == {'arcrag-init','arcrag-init-arcmap','backend','frontend'}, d['services'].keys(); assert 'qdrant' not in d['services']; assert 'qdrant_data' not in d.get('volumes', {})"` exits 0 (if PyYAML is available; otherwise parse manually).

### Task 5: Create `backend/test_prod_compose.py`

- **File**: `backend/test_prod_compose.py`
- **Action**: CREATE
- **Implement**: A self-contained Python test (no pytest needed, matches the project's `if __name__ == "__main__":` + `test()` orchestrator pattern) that validates the prod compose statically:
  1. `frontend/Dockerfile` exists and contains `ARG NEXT_PUBLIC_BACKEND_URL`, `FROM node:20-alpine AS runtime`, `node server.js`, `HEALTHCHECK`
  2. `frontend/.dockerignore` exists and excludes `node_modules`
  3. `frontend/next.config.js` exports a config with `output == 'standalone'`
  4. `docker-compose.prod.yml` is parseable YAML (try-except on yaml.YAMLError)
  5. The compose has exactly 4 services: `arcrag-init`, `arcrag-init-arcmap`, `backend`, `frontend`. **No `qdrant` service** (Qdrant is external).
  6. `backend` and `frontend` each have a `mem_limit` key
  7. `backend` and `frontend` each have `restart: unless-stopped`
  8. `arcrag-init` and `arcrag-init-arcmap` each have `restart: "no"`
  9. `backend` has a `healthcheck` block
  10. `frontend.ports` is `["3000:3000"]` (the only host-mapped port)
  11. `backend` does NOT have a `ports:` key (internal-only)
  12. `frontend.build.args` contains `NEXT_PUBLIC_BACKEND_URL`
  13. `arcrag-init-arcmap.depends_on` includes `arcrag-init` with `condition: service_completed_successfully`
  14. `backend.depends_on` includes both `arcrag-init` and `arcrag-init-arcmap` with `condition: service_completed_successfully`. **No `qdrant` key** in any `depends_on` (Qdrant is external; the init's success is the proxy for Qdrant reachability).
  15. `frontend.depends_on.backend` has `condition: service_healthy`
  16. **No `qdrant` service** and **no `qdrant_data` volume** in the compose (Qdrant is external)
  17. The top-level `volumes:` declares `arcrag_data:` (reused from ARCRAG-15/16)
- **Mirror**: `backend/test_load_qdrant.py` for the test() orchestrator pattern (manual `print` headers, `asyncio.run` if needed, exit 0/1 on pass/fail).
- **Avoid**: Don't shell out to `docker compose config` — that requires the Docker daemon. Use PyYAML only. If PyYAML isn't available, fall back to a tiny manual parser (the file is small and we control its shape).
- **Validate**: `cd backend && python test_prod_compose.py` prints "ALL TESTS PASS" and exits 0.

### Task 6: Pre-flight smoke test on VPS (~10 min, deferred)

- **Action**: VALIDATE (deferred to VPS per user decision)
- **Implement**:
  - On VPS: `cd /opt/arcpro-docs && git pull origin feature/arccrag-17-production-docker-compose`
  - **Verify the external Qdrant is reachable from the VPS host** (assumed pre-existing): `wget -qO- http://<qdrant-host>:6333/health` returns `{"status":"green"}`. If not, ARCRAG-17 cannot proceed — Qdrant must be running.
  - **Verify `backend/.env` is updated** for production:
    - `OPENROUTER_API_KEY=sk-or-v1-...` (real key, not `dummy`)
    - `QDRANT_URL=http://<qdrant-host>:6333` (the external Qdrant — replaces the dev `http://localhost:6333` or `http://qdrant:6333`)
  - `docker compose -f docker-compose.prod.yml build backend frontend` (builds the two service images)
  - `docker compose -f docker-compose.prod.yml config` (validate the rendered config — should show 4 services, no `qdrant`, no `qdrant_data`)
  - `docker compose -f docker-compose.prod.yml up -d arcrag-init arcrag-init-arcmap backend` (skip the frontend for the smoke test)
  - `docker compose -f docker-compose.prod.yml ps` (verify init containers exit 0, backend is `Up (healthy)`)
  - `docker compose -f docker-compose.prod.yml exec backend wget -qO- http://localhost:8000/health` (should return `{"status":"ok","qdrant":"connected","model":"..."}` — the `qdrant: "connected"` confirms `QDRANT_URL` is correct)
  - `docker compose -f docker-compose.prod.yml logs arcrag-init arcrag-init-arcmap` (verify both inits no-op'd quickly: "Collection 'arcgis_docs' already has N points with source='arcpro', skipping ingestion" and same for `arcmap`)
  - `docker compose -f docker-compose.prod.yml down` (tear down — Qdrant untouched)
- **Validate**: All 3 services come up; backend's `/health` returns 200 with `qdrant: "connected"`; both inits exit 0 in <30s (skip path, not the 10-36h ingest path).

### Task 7: Full production run on VPS (~5-15 min when data is already loaded, deferred)

- **Action**: VALIDATE (deferred to VPS per user decision)
- **Implement**:
  - `docker compose -f docker-compose.prod.yml up -d --build` (single command: builds images, runs both inits, starts backend, starts frontend; inits no-op in ~10s since Qdrant already has the data)
  - `docker compose -f docker-compose.prod.yml logs -f arcrag-init arcrag-init-arcmap` (should show both inits skipping in seconds, not the multi-hour build+load path)
  - `docker compose -f docker-compose.prod.yml ps` (verify all 4 services are `Up` / `Exited (0)` for the inits)
  - `curl http://localhost:3000/` (frontend HTML, served by Next.js)
  - `docker compose -f docker-compose.prod.yml exec backend wget -qO- http://localhost:8000/health` (backend healthy)
  - `docker compose -f docker-compose.prod.yml exec backend wget -qO- <QDRANT_URL>/collections/arcgis_docs` (Qdrant shows expected point count from the external service)
- **Validate**:
  - All 4 services start successfully
  - Frontend HTML loads on port 3000
  - Backend `/health` returns 200 with `qdrant: "connected"` (proving `QDRANT_URL` is correctly pointing to the external Qdrant)
  - Qdrant shows both `source: arcpro` and `source: arcmap` points
  - `docker compose -f docker-compose.prod.yml restart backend` works (the restart policy in action)
  - Spot-test: open `http://<vps>:3000` in a browser, ask the chat "What is the Buffer tool?" — should get a grounded answer with image + source link

**Note on first-time data:** If the operator has just populated Qdrant for the first time (e.g., they ran the inits manually before deploying this compose), the inits will see the data and skip. If the operator's Qdrant is empty (unusual but possible), the inits will run the full build+load (8-24h for ArcPro + 4-12h for ArcMap). The plan assumes the former.

### Task 8: Documentation

- **Action**: DOCUMENT
- **Implement**:
  - Create `.agents/reports/arccrag-17-production-docker-compose-report.md` following the ARCRAG-15/16 template (summary, files changed, validation results, deviations, acceptance criteria checklist, VPS runbook)
  - Create `.agents/decisions/arccrag-17-production-docker-compose.md` (summary, key decisions, errors, lessons learned) — focus on the new design decisions (separate prod file, inits in prod, memory limits, standalone build, build-time NEXT_PUBLIC_)
  - Update `.agents/stories/stories.md`: mark ARCRAG-17 in-progress (now) → ✅ Completed with timestamp after VPS run
- **Mirror**: `.agents/reports/arccrag-16-...md` and `.agents/decisions/arccrag-16-...md` for format
- **Validate**: Files exist; all 5 acceptance criteria from the story are checked off

---

## Validation Block

```bash
# After Tasks 1-5 (code complete, before Task 6)
cd /home/techafresh/projects/arcpro-docs

# Task 1: .dockerignore
test -f frontend/.dockerignore && grep -q '^node_modules$' frontend/.dockerignore

# Task 2: next.config.js output: standalone
node -e "const c = require('./frontend/next.config.js'); if (c.output !== 'standalone') process.exit(1)"

# Task 3: Dockerfile structure
grep -q 'FROM node:20-alpine AS deps'    frontend/Dockerfile
grep -q 'FROM node:20-alpine AS build'   frontend/Dockerfile
grep -q 'FROM node:20-alpine AS runtime' frontend/Dockerfile
grep -q 'ARG NEXT_PUBLIC_BACKEND_URL'    frontend/Dockerfile
grep -q 'node server.js'                 frontend/Dockerfile
grep -q 'HEALTHCHECK'                    frontend/Dockerfile

# Task 4: prod compose structure
python3 -c "
import yaml
d = yaml.safe_load(open('docker-compose.prod.yml'))
svcs = d['services']
assert set(svcs.keys()) == {'arcrag-init','arcrag-init-arcmap','backend','frontend'}, svcs.keys()
assert 'qdrant' not in svcs, 'qdrant should NOT be a service (external)'
vols = d.get('volumes', {})
assert 'qdrant_data' not in vols, 'qdrant_data should NOT be a volume (external Qdrant has its own)'
assert 'arcrag_data' in vols, 'arcrag_data must be declared (reused from ARCRAG-15/16)'
assert svcs['backend'].get('mem_limit') == '1g'
assert svcs['frontend'].get('mem_limit') == '512m'
assert svcs['backend'].get('restart')  == 'unless-stopped'
assert svcs['frontend'].get('restart') == 'unless-stopped'
assert svcs['arcrag-init'].get('restart')       == 'no'
assert svcs['arcrag-init-arcmap'].get('restart')== 'no'
assert 'healthcheck' in svcs['backend']
assert svcs['frontend']['ports']  == ['3000:3000']
assert 'ports' not in svcs['backend']
assert 'NEXT_PUBLIC_BACKEND_URL' in str(svcs['frontend']['build']['args'])
assert svcs['arcrag-init-arcmap']['depends_on']['arcrag-init']['condition'] == 'service_completed_successfully'
assert svcs['backend']['depends_on']['arcrag-init-arcmap']['condition']     == 'service_completed_successfully'
assert 'qdrant' not in svcs['backend']['depends_on'], 'backend should not depend on qdrant (external)'
assert svcs['frontend']['depends_on']['backend']['condition']               == 'service_healthy'
print('OK: docker-compose.prod.yml validated')
"

# Task 5: run the static test suite
cd backend && python test_prod_compose.py    # all 15 assertions pass
cd ..

# Pre-flight on VPS (Task 6) — deferred
# 0. Verify external Qdrant is reachable
ssh vps 'wget -qO- http://<qdrant-host>:6333/health'
# 1. Sync and verify .env
ssh vps 'cd /opt/arcpro-docs && git pull && grep -q "^OPENROUTER_API_KEY=sk-or-v1-" backend/.env && grep -q "^QDRANT_URL=http" backend/.env'
# 2. Build images
ssh vps 'cd /opt/arcpro-docs && docker compose -f docker-compose.prod.yml build backend frontend'
# 3. Validate the rendered config
ssh vps 'cd /opt/arcpro-docs && docker compose -f docker-compose.prod.yml config | head -30'
# 4. Bring up inits + backend (no frontend, no qdrant)
ssh vps 'cd /opt/arcpro-docs && docker compose -f docker-compose.prod.yml up -d arcrag-init arcrag-init-arcmap backend'
ssh vps 'cd /opt/arcpro-docs && docker compose -f docker-compose.prod.yml ps'
ssh vps 'cd /opt/arcpro-docs && docker compose -f docker-compose.prod.yml exec backend wget -qO- http://localhost:8000/health'
ssh vps 'cd /opt/arcpro-docs && docker compose -f docker-compose.prod.yml logs arcrag-init arcrag-init-arcmap'
# 5. Tear down
ssh vps 'cd /opt/arcpro-docs && docker compose -f docker-compose.prod.yml down'

# Full prod run on VPS (Task 7) — deferred
ssh vps 'cd /opt/arcpro-docs && docker compose -f docker-compose.prod.yml up -d --build'
ssh vps 'cd /opt/arcpro-docs && docker compose -f docker-compose.prod.yml logs -f arcrag-init arcrag-init-arcmap'
ssh vps 'cd /opt/arcpro-docs && docker compose -f docker-compose.prod.yml ps'
ssh vps 'cd /opt/arcpro-docs && curl http://localhost:3000/'
ssh vps 'cd /opt/arcpro-docs && docker compose -f docker-compose.prod.yml exec backend wget -qO- http://localhost:8000/health'
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `node:20-alpine` doesn't ship with `wget` (HEALTHCHECK in Dockerfile) | Alpine includes BusyBox `wget` by default — confirmed. Fallback: use `wget -q --spider` (BusyBox) or `node -e "fetch(...).then(r => process.exit(r.ok ? 0 : 1))"` if wget is removed in a future Alpine release. |
| `output: 'standalone'` doesn't pick up all dependencies (e.g., CopilotKit uses dynamic requires) | The Next.js docs note: some packages may need to be added to `outputFileTracingIncludes` in `next.config.js`. If Task 6's pre-flight fails with "module not found" at startup, add the offending path to `outputFileTracingIncludes` and rebuild. |
| Frontend image build is slow on the VPS (~5-10 min for first build) | Document the expected build time in the runbook. Use `--build-arg` to bake the backend URL — no post-build configuration needed. |
| `NEXT_PUBLIC_BACKEND_URL` baked at build time means changing the backend URL requires a rebuild | Acceptable for prod (URL is stable). Documented in the runbook. Future hardening could move to a runtime env var (see Decision 5). |
| Qdrant `mem_limit: 4g` may be too low for HNSW growth | Bump to 8g if Qdrant logs OOM. Current estimate is ~600 MB raw vectors + HNSW overhead at 95K entries. The 4g limit leaves ~3.4g of headroom. |
| Inits in prod compose means a fresh deployment always takes 10-36h | This is unavoidable (it's the cost of full ingestion). The user has accepted this. Mitigation: ship a small "smoke" compose (`docker-compose.prod.yml` + a `SMOKE=1` env var that adds `--limit 100` to the build_index calls) in a future story. Out of scope for ARCRAG-17. |
| `init.sh` per-source idempotency check is broken / wrong field name | The check was verified in ARCRAG-16 (Qdrant `/points/count` with `{"filter":{"must":[{"key":"source","match":{"value":"<source>"}}]}}`). No code change in ARCRAG-17. The pre-flight (Task 6) catches any regression. |
| Frontend port 3000 conflicts with another service on the VPS | Standard port. If the VPS already has a Next.js dev server on 3000, change the mapping to `3001:3000` (or any other host port). |
| `docker-compose.yml` (dev) and `docker-compose.prod.yml` drift over time | Out of scope for ARCRAG-17. Future hardening: add a CI step that diffs the two files and flags differences. The current differences (memory limits, restart policies, frontend service, port exposure) are intentional. |
| `arcrag_data` volume wiped by `docker compose down -v` | Same as ARCRAG-15/16 lesson. Documented in the runbook. Re-running the inits after a `down -v` re-ingests both ArcPro and ArcMap from scratch (URLs are recoverable from the host filesystem, but index JSONs live in the volume). |
| `wget` is not in `python:3.11-slim` (used by `backend/Dockerfile` for the inits) | The existing `backend/Dockerfile:5-13` doesn't include `wget` explicitly, but `wget` IS in `python:3.11-slim` by default (verified). The init script's `wget` for the Qdrant health check works. No change needed. |
| `QDRANT_URL` in `backend/.env` points to the wrong host on the VPS | The pre-flight (Task 6) explicitly tests `wget -qO- http://<qdrant-host>:6333/health` and the backend's `/health` endpoint's `qdrant: "connected"` field. If `QDRANT_URL` is wrong, the backend's `/health` returns `qdrant: "disconnected"` and the inits fail with Qdrant-unreachable errors. Loud failure, easy to diagnose. |
| External Qdrant goes down mid-run | The inits poll `QDRANT_URL` via `init.sh`'s 60×5s wait loop. If Qdrant is down, the inits fail. The backend's `/health` returns `qdrant: "disconnected"` but the backend process stays up (its healthcheck still passes — only `/health` reports the soft failure). Mitigation: use Docker restart policies + monitoring (out of scope for ARCRAG-17). |
| External Qdrant is on a host the prod backend cannot reach (firewall / DNS) | Pre-flight catches this immediately. Mitigation: document the network requirement (VPS → Qdrant host:6333 must be open) in the runbook. |
| The `arcrag_data` volume doesn't exist on the VPS (e.g., fresh VPS that didn't run ARCRAG-15/16) | The init containers will create the volume on first use. The `*_urls.json` files in the volume are missing, so the inits will fail at `build_index.py` with "URLs file not found". Mitigation: if the user is starting from a fresh VPS, they need to either (a) run `parse_sitemaps.py` first to populate the URLs JSONs, or (b) mount a different `arcrag_data` volume that has the data. Out of scope for ARCRAG-17 to automate. |
| `python:3.11-slim` is deprecated / EOL'd | Not currently. Python 3.11 is supported until October 2024 for security fixes; 3.12 would be the next bump. Out of scope for ARCRAG-17. |
| CORS misconfiguration blocks the chat | The frontend hits `/api/copilotkit` (same origin via the reverse proxy in ARCRAG-18 or same host in dev). The API route proxies server-to-server to the backend. Browser CORS is never triggered. The backend's CORS middleware is still set to `NEXT_PUBLIC_BACKEND_URL` for direct-debugging scenarios. |

---

## Acceptance Criteria

- [ ] `docker-compose.prod.yml` exists and parses as valid YAML
- [ ] `docker-compose.prod.yml` defines exactly 4 services: `arcrag-init`, `arcrag-init-arcmap`, `backend`, `frontend` (no `qdrant` — external)
- [ ] `backend` has `mem_limit: 1g` and `restart: unless-stopped`
- [ ] `frontend` has `mem_limit: 512m` and `restart: unless-stopped`
- [ ] `arcrag-init` has `restart: "no"`
- [ ] `arcrag-init-arcmap` has `restart: "no"`
- [ ] `backend` has a `healthcheck` block (using `wget --spider` against `/health`)
- [ ] `frontend.ports` is `["3000:3000"]`
- [ ] `backend` does NOT have a `ports:` key (internal-only)
- [ ] `frontend.build.args` contains `NEXT_PUBLIC_BACKEND_URL=http://backend:8000`
- [ ] `arcrag-init-arcmap.depends_on` includes `arcrag-init` with `condition: service_completed_successfully`
- [ ] `backend.depends_on` includes both `arcrag-init` and `arcrag-init-arcmap` with `condition: service_completed_successfully`
- [ ] **No service has `qdrant` in its `depends_on`** (Qdrant is external)
- [ ] `frontend.depends_on.backend` has `condition: service_healthy`
- [ ] Top-level `volumes:` declares `arcrag_data:` (reused from ARCRAG-15/16); **no `qdrant_data:`** (Qdrant has its own external volume)
- [ ] `frontend/Dockerfile` exists with three stages (`deps`, `build`, `runtime`) and uses `node:20-alpine`
- [ ] `frontend/Dockerfile` declares `ARG NEXT_PUBLIC_BACKEND_URL` and `CMD ["node", "server.js"]`
- [ ] `frontend/Dockerfile` has a `HEALTHCHECK` instruction
- [ ] `frontend/.dockerignore` exists and excludes `node_modules` and `.next`
- [ ] `frontend/next.config.js` has `output: 'standalone'`
- [ ] `backend/test_prod_compose.py` exists and runs 15+ static assertions, all passing
- [ ] Pre-flight on VPS: external Qdrant is reachable (`wget -qO- http://<qdrant-host>:6333/health` returns green)
- [ ] Pre-flight on VPS: `backend/.env` on VPS has `QDRANT_URL=http://<qdrant-host>:6333` and a real `OPENROUTER_API_KEY`
- [ ] Pre-flight on VPS: `docker compose -f docker-compose.prod.yml build backend frontend` succeeds
- [ ] Pre-flight on VPS: `docker compose -f docker-compose.prod.yml up -d arcrag-init arcrag-init-arcmap backend` brings 3 services to `Up` / `Exited (0)` (inits)
- [ ] Pre-flight on VPS: `docker compose -f docker-compose.prod.yml exec backend wget -qO- http://localhost:8000/health` returns 200 with `{"status":"ok", "qdrant": "connected", ...}`
- [ ] Pre-flight on VPS: both inits log "Collection 'arcgis_docs' already has N points with source='<src>', skipping ingestion" and exit 0 in <30s
- [ ] Full run on VPS: `docker compose -f docker-compose.prod.yml up -d --build` starts all 4 services
- [ ] Full run on VPS: frontend HTML loads on `http://<vps>:3000`
- [ ] Full run on VPS: chat works end-to-end (ask "What is the Buffer tool?" → grounded answer with image + source link)
- [ ] Restart test on VPS: `docker compose -f docker-compose.prod.yml restart backend` brings the backend back up automatically
- [ ] `.agents/reports/arcrag-17-...md` and `.agents/decisions/arccrag-17-...md` are written
- [ ] `.agents/stories/stories.md` marks ARCRAG-17 ✅ Completed (with timestamp) after VPS run

---

## Open Questions / Assumptions

1. **`output: 'standalone'` works for this Next.js 15 + CopilotKit 1.8 app.** Standard Next.js feature since 12.x. CopilotKit uses standard `import` statements, not exotic dynamic requires, so it should be picked up by Next.js's tracing. If Task 6's pre-flight fails with a module-not-found at frontend startup, the fix is to add the path to `outputFileTracingIncludes` in `next.config.js`. This is a known escape hatch.

2. **`wget` is in `node:20-alpine` for the frontend HEALTHCHECK.** Verified: Alpine ships with BusyBox `wget` by default. If a future Alpine release removes it, fallback to `node -e "fetch('http://localhost:3000/').then(r => process.exit(r.ok ? 0 : 1))"`.

3. **`wget` is in `python:3.11-slim` for the backend HEALTHCHECK and the inits.** Verified: `python:3.11-slim` is Debian-based and ships with `wget`. The existing `backend/Dockerfile` and `scripts/init.sh` already use it.

4. **`backend/.env` will have a real `OPENROUTER_API_KEY` on the VPS.** Per ARCRAG-15/16 runbook precedent. The Task 6 pre-flight explicitly checks this and aborts with a clear error if it's still `dummy`.

5. **The external Qdrant on the VPS is reachable at the URL set in `QDRANT_URL`.** Per user statement, Qdrant is "already running on the VPS." The exact URL (`http://localhost:6333` if on the same host, `http://<hostname>:6333` if on a different container/host) is the operator's responsibility. The plan assumes the operator sets `QDRANT_URL` correctly in `backend/.env` on the VPS. The pre-flight (Task 6) verifies connectivity.

6. **Qdrant v1.12.1 is stable for production.** Used in dev and pre-ARCRAG-15 work. No reason to bump for ARCRAG-17. (N/A in this compose since Qdrant is external, but the user should ensure their external Qdrant is on a compatible version.)

7. **No `docker-compose.override.yml` or `extends:` is needed.** The two-file approach (dev + prod) is sufficient. If a third environment appears (e.g., staging), it can be a third file or an override.

8. **The Caddy reverse proxy (ARCRAG-18) will be added as a fifth top-level service in a future story.** The current `docker-compose.prod.yml` exposes only port 3000 on the host; ARCRAG-18 will add a Caddy service that listens on 80/443 and proxies to the frontend container, terminating HTTPS in front of it. This composes cleanly with the current design (no changes needed to ARCRAG-17's services when ARCRAG-18 lands).

9. **The frontend is reachable on port 3000 without HTTPS in this iteration.** ARCRAG-18 adds HTTPS via Caddy. The current `docker-compose.prod.yml` is sufficient for an internal-network deployment or a reverse-proxied deployment. For a public deployment, ARCRAG-18 must be in place first.

10. **The backend's `volumes: [arcrag_data:/app/data]` mount is a no-op for the running backend** (the backend talks to Qdrant, not to local files). Kept for debug ergonomics (`docker compose exec backend ls /app/data` works the same as the init container). This matches the ARCRAG-15 pattern (see `docker-compose.yml:63`).

11. **No log aggregation, metrics, or tracing.** Out of scope for MVP per PRD §9. Each container logs to stdout (Docker default), which is sufficient for an MVP. A future hardening story could add a Loki or similar sidecar.

12. **No image vulnerability scanning or multi-arch builds.** Out of scope for MVP. Future hardening.

13. **The user wants code-complete-on-PC, full-run-on-VPS (per their answer).** This plan's Tasks 1-5 run on PC; Tasks 6-7 are explicitly deferred to VPS; Task 8 is documentation that happens after the VPS run.

14. **The `arcrag_data` volume from ARCRAG-15/16 is reused.** The plan assumes the same named volume exists on the VPS (from the prior ARCRAG-15/16 runs). If the VPS is fresh and the volume doesn't exist, Docker will create an empty one on first use, and the inits will fail at `build_index.py` for missing `*_urls.json` files. The plan does not automate the recovery from a missing volume. If the user is on a fresh VPS, they need to either restore the volume from a backup, or run `parse_sitemaps.py` to populate the URLs JSONs first.

15. **Qdrant data is already in the `arcgis_docs` collection.** The plan assumes both `source: arcpro` and `source: arcmap` points are present (from ARCRAG-15/16). If only one source's data is present, the corresponding init will run a full ingest on first `up` (8-24h or 4-12h). The plan does not automate the "first-time ingest" case beyond relying on the init scripts' existing behavior.

---

## VPS-Side Runbook (preview; full version goes in the report after VPS run)

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

**Note:** The `arcrag_data` named volume persists across `docker compose down` (without `-v`) and `docker compose up` cycles. Don't run `docker compose down -v` unless you want to start the full ingestion from scratch. **Qdrant is not part of this compose and is not affected by `docker compose down` / `up` — it runs externally.**
