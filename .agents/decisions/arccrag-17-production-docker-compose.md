# Decision Log & Implementation Postmortem: arccrag-17-production-docker-compose

- **Date**: 2026-06-07
- **Branch**: `feature/arccrag-17-production-docker-compose`
- **Report Path**: `.agents/reports/arccrag-17-production-docker-compose-report.md`

## 1. Summary of Implementation

Added a production-hardened `docker-compose.prod.yml` (4 services: 2 idempotent
init containers + FastAPI backend + Next.js frontend) plus a multi-stage
`frontend/Dockerfile` with `output: 'standalone'`. The dev
`docker-compose.yml` is untouched per user decision. Qdrant is treated as
external and connected to via `QDRANT_URL` from `backend/.env`. Includes
`mem_limit` (backend=1g, frontend=512m), `restart: unless-stopped` on
long-lived services, `restart: "no"` on inits, healthchecks on backend and
frontend, and the existing `arcrag_data` named volume for ingestion
checkpoints.

A self-contained static test suite (`backend/test_prod_compose.py`) with 29
assertions validates the dev-PC-side of the plan; the actual `docker
compose up` runs on the VPS per the plan's explicit deferral.

## 2. Key Decisions & Rationale

### 2.1 Separate `docker-compose.prod.yml`, leave dev file untouched

**Decision**: Created a new file rather than modifying `docker-compose.yml`
or using `extends:` / anchors.

**Rationale**: The user explicitly chose this in the plan's "Key Design
Decisions" section. Two-file separation is cleaner at this scale: dev
compose keeps its current 4-service shape (Qdrant + 2 inits + backend) for
PC iteration, prod compose is the hardened VPS path with the frontend
service, memory limits, restart policies, and only port 3000 exposed.

### 2.2 Both init containers included in prod compose (not just runtime)

**Decision**: `arcrag-init` + `arcrag-init-arcmap` are in
`docker-compose.prod.yml` alongside backend + frontend.

**Rationale**: `scripts/init.sh` is idempotent per source (per ARCRAG-16):
when Qdrant already has points for a source, the init sees the per-source
count, logs "skipping ingestion", and exits 0 in ~5-10s. With the user's
external Qdrant already populated from ARCRAG-15/16, the inits are no-ops.
The `depends_on: { condition: service_completed_successfully }` gate
ensures the backend/frontend don't start until both inits have run (or
no-op'd). `restart: "no"` on inits means failures are loud and explicit
(rather than silent retry loops).

### 2.3 Qdrant is external — not a service in the prod compose

**Decision**: No `qdrant` service block. Backend and inits read
`QDRANT_URL` from `backend/.env` (already supported by `env_file:`).

**Rationale**: The user confirmed Qdrant is already running externally on
the VPS. Connecting via env var is more portable than `external: true`
network references (which tie the compose to specific Docker network
names). The dev compose's pattern of overriding `QDRANT_URL` in
`environment:` is replaced in prod by letting `env_file: backend/.env`
provide it, so the operator controls the external Qdrant's URL from one
place.

**Consequence**: No `depends_on: qdrant` in the prod compose. The init
container's success is the proxy for "Qdrant is reachable" — if the
external Qdrant is down, the inits fail loudly and the backend never
starts. The backend's `/health` endpoint also reports `qdrant:
"connected"` / `"disconnected"` for soft-failure observability.

### 2.4 Only frontend port 3000 is host-exposed

**Decision**: `frontend.ports: ["3000:3000"]`. `backend` has no
`ports:` key (internal only). No host port for Qdrant (external).

**Rationale**: Host firewall is the first line of defense. An attacker
cannot directly reach the backend's `/ag-ui` endpoint. ARCRAG-18 (Caddy
reverse proxy) will terminate TLS in front of port 3000 and proxy to the
frontend container — this compose is the foundation ARCRAG-18 builds on.
Internal debugging is via `docker compose exec backend curl
http://localhost:8000/health`.

### 2.5 `NEXT_PUBLIC_BACKEND_URL` baked at build time via `--build-arg`

**Decision**: Frontend Dockerfile declares
`ARG NEXT_PUBLIC_BACKEND_URL=http://backend:8000`, set as `ENV`, and prod
compose passes it via `build.args`. Frozen at image build time.

**Rationale**: Next.js's `NEXT_PUBLIC_*` convention inlines values at
build time. The `frontend/src/app/api/copilotkit/route.ts` API route runs
server-side inside the container, so it uses the build-time value. Inside
the Docker network, `http://backend:8000` resolves to the backend service
via Compose's internal DNS.

**Trade-off**: Changing the backend URL requires a frontend rebuild.
Acceptable for prod (URL is stable across deployments); documented in
the runbook.

### 2.6 Multi-stage frontend Dockerfile with `output: 'standalone'`

**Decision**: Three-stage build (`deps` → `build` → `runtime`) on
`node:20-alpine`. Runtime image contains only the standalone `server.js`,
`.next/static/`, and `public/`. Non-root `nextjs` user (uid 1001).

**Rationale**: `output: 'standalone'` is the official Next.js feature for
this use case; reduces image from ~1 GB to ~150 MB. Non-root user is
defense in depth. `HEALTHCHECK` uses `wget --spider` against `/` (Alpine
ships BusyBox `wget` by default).

### 2.7 Healthcheck on backend using existing `/health` endpoint

**Decision**: `wget --spider http://localhost:8000/health`. Frontend's
`depends_on.backend: { condition: service_healthy }` gates on this.

**Rationale**: `backend/src/main.py` already returns
`{"status":"ok", "qdrant":"connected"|"disconnected", "model":"..."}` from
`/health`. A backend that can't reach Qdrant still passes the
healthcheck (returns 200 with `qdrant: "disconnected"`); the real
protection is `depends_on: arcrag-init-arcmap: service_completed_successfully`
— by then the init has already polled the external Qdrant and confirmed
reachability.

### 2.8 Restart policy: `unless-stopped` on long-lived, `no` on inits

**Decision**: `backend` and `frontend` get `restart: unless-stopped`;
inits get `restart: "no"`.

**Rationale**: Long-lived services should auto-recover from OOM,
transient network blips, or host reboots. `unless-stopped` (vs `always`)
respects explicit `docker compose stop` calls. Inits should fail loudly
if ingestion breaks, not loop and overwrite partial data.

### 2.9 Static test suite (no Docker required)

**Decision**: `backend/test_prod_compose.py` is pure Python + PyYAML
validation. 29 assertions across 4 test groups. Mirrors the existing
test files' `if __name__ == "__main__":` + `asyncio.run(test())` pattern.

**Rationale**: The user chose "code complete on PC, full run on VPS" per
the plan. Avoids the multi-GB image build + multi-hour init runs on the
dev laptop while still catching the static structure (4 services, no
qdrant, mem_limits, restart policies, healthcheck, ports, depends_on,
build args).

## 3. Errors & Roadblocks Encountered

### 3.1 `importlib.util.spec_from_file_location` returned `None` for `next.config.js`

**Error**: When running the test suite, importing `frontend/next.config.js`
via `importlib` failed with:
```
AttributeError: 'NoneType' object has no attribute 'loader'
```
because Python couldn't recognize the CommonJS file as a Python module
(no `loader` attribute on the spec).

**Resolution**: Switched to a regex-based parse
(`re.search(r"output\s*:\s*['\"]([^'\"]+)['\"]", text)`) on the file's
text. Functionally equivalent to `node -e "require(...).output"`, but
stays in pure Python and doesn't require a Node runtime in the test
process.

### 3.2 Dockerfile `CMD` substring check mismatch

**Error**: The plan's suggested validation looked for the literal string
`node server.js` in `frontend/Dockerfile`. My Dockerfile uses the exec
form `CMD ["node", "server.js"]` (more correct for Dockerfiles; the
shell form is for shell wrappers). The substring check failed.

**Resolution**: Updated the test to check for the exec form
`'CMD ["node", "server.js"]' in text`. Plan's intent was to confirm
`server.js` is the CMD; both forms satisfy that.

### 3.3 WSL/Windows PATH confusion when attempting `npm run build`

**Error**: Tried to validate the actual `next build` on the dev PC. The
`npm` binary on PATH was a Windows executable
(`/mnt/c/Program Files/nodejs/npm`), but `node` was the Linux one. The
Windows `npm` couldn't handle the WSL Linux path
(`\\wsl.localhost\Ubuntu\...`) — "UNC paths are not supported".

**Resolution**: Recognized that the plan explicitly defers full image
builds to the VPS. Stopped trying to run `next build` on the dev PC.
The static validation (29 assertions on file structure, YAML parse,
config keys) is the dev-PC scope. The user noted the WSL/Windows PATH
mixing up — there's a WSL-native npm on the system, but pursuing
on-PC builds was out of scope. No code change needed.

## 4. Workarounds & Resolutions

| # | Issue | Workaround |
|---|-------|-----------|
| 1 | Python can't `import` CommonJS `next.config.js` | Regex parse of file text in test suite |
| 2 | Plan's literal `node server.js` substring check fails on exec form | Test now matches `'CMD ["node", "server.js"]' in text` (both forms equivalent) |
| 3 | WSL/Windows PATH mix prevents `next build` on dev PC | Defer to VPS per plan; static validation is the dev-PC scope |
| 4 | Atlassian MCP tools and `gh`/`jira` CLIs unavailable in session | Documented the manual Jira-update steps in the report's "Jira Update" section |

## 5. What Went Right & What Went Wrong

### 5.1 What Went Right

- **Static validation worked end-to-end.** All 29 assertions passed on
  first run after the two text-parse fixes (3.1, 3.2). The PyYAML
  parse + regex approach is robust and easy to extend.
- **Dev `docker-compose.yml` was not touched.** User decision was
  preserved (separate prod file). `git diff docker-compose.yml` is empty.
- **Existing test suites still pass.** `test_load_qdrant.py` and
  `test_search.py` ran cleanly (Qdrant-down tests skip as expected);
  no regression.
- **The Dockerfile is the standard Next.js standalone pattern** that
  thousands of production deployments use. No exotic dynamic requires
  in CopilotKit's imports → standalone output should trace correctly
  out of the box. The `outputFileTracingIncludes` escape hatch is
  documented in the plan as the fix path if Task 6's pre-flight finds a
  missing module at startup.
- **Plan adherence was high.** The plan's design decisions (separate
  prod file, inits in prod, env-var Qdrant, build-time
  `NEXT_PUBLIC_BACKEND_URL`, 3-stage Dockerfile, `unless-stopped` /
  `"no"` restart split, frontend-only port exposure) were all
  implemented as specified. The three deviations are minor and
  documented.

### 5.2 What Went Wrong

- **Test suite's `next.config.js` parser used Python's importlib** when
  it should have used a text/regex approach from the start. The plan
  even suggested `node -e "require(...)"` — should have gone with a
  parse strategy that doesn't need a Node runtime.
- **Did not anticipate the WSL/Windows PATH mixing.** Spent a few
  cycles trying to run `next build` before realizing (a) the plan
  defers builds to the VPS and (b) the environment can't easily run
  Windows npm against Linux paths.
- **Jira update phase (Phase 6) could not be executed.** Neither
  Atlassian MCP tools nor `gh`/`jira` CLIs are available. The user
  will need to update Jira manually. Should have checked for
  Atlassian MCP availability earlier in the session.

## 6. Lessons Learned & Recommendations

### 6.1 Lessons Learned

1. **CommonJS files cannot be `importlib`-loaded in Python tests.** Use
   text parsing or shell out to Node for JS config validation. The
   existing test files (`test_load_qdrant.py`, `test_search.py`) only
   import Python modules and `subprocess.run` shell commands — the
   `importlib` trick I tried doesn't work for non-Python files.
2. **For `output: 'standalone'` validation, prefer a text/regex
   approach** over attempting to `require()` the file in a Node
   subprocess — keeps the test self-contained and fast.
3. **The exec form `CMD ["node", "server.js"]` is the Dockerfile
   standard** and the test suite should match it specifically (not
   the shell form `CMD node server.js`).
4. **The plan's "static validation on dev PC" scope is intentional and
   valuable.** Trying to do full Docker builds on the dev PC is a
   time sink; defer them to the target environment. The 29-assertion
   static suite catches every structural mistake the plan calls out,
   cheaply and reliably.
5. **WSL + Windows-PATH-mixed npm is a known footgun.** The user has
   a WSL-native npm available — flag this earlier in future sessions
   and prefer it over the Windows one.

### 6.2 Recommendations

1. **Run the VPS runbook (Steps 0-8 in the report) before merging.**
   The static suite is necessary but not sufficient — the actual
   `docker compose up` (image build, init no-op speed, healthcheck
   intervals, restart policy) needs to be validated against a live
   external Qdrant.
2. **If the frontend container fails to start on VPS with "module not
   found"**, add the offending path to `outputFileTracingIncludes` in
   `next.config.js` per Next.js docs and rebuild. This is the known
   escape hatch for `output: 'standalone'` with dynamic requires.
3. **ARCRAG-18 (Caddy reverse proxy) can be built directly on top of
   this compose** — just add a 5th service in `docker-compose.prod.yml`
   with `ports: ["80:80", "443:443"]` and a Caddyfile that proxies to
   `frontend:3000`. No changes to ARCRAG-17's services needed.
4. **Add a `restart: unless-stopped` test** in a follow-up: simulate
   backend crash (`docker compose kill backend`) and verify the
   container comes back `Up (healthy)` within 30s. Defer to VPS.
5. **Document the `arcrag_data` named volume in the runbook warning**
   about `docker compose down -v` wiping it (this is already in the
   report's VPS runbook). A future hardening could add a `mkfs` /
   restore-from-backup step.
6. **The user's external Qdrant must be reachable from the VPS host**
   (firewall/DNS check). The backend's `/health` endpoint's
   `qdrant: "connected"` / `"disconnected"` field is the canary.
