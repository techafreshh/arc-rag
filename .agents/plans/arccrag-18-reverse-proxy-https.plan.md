# Plan: ARCRAG-18 — Reverse Proxy with HTTPS (External Caddy)

## Summary

The user already runs Caddy on the VPS, so ARCRAG-18 does **not** add a Caddy service to `docker-compose.prod.yml`. Instead, it (1) provides a self-contained `deploy/Caddyfile` the operator copies into their existing Caddy config, (2) adds a named Docker network (`arcrag-net`) to the prod compose so the external Caddy can attach and resolve `frontend:3000` over Docker's internal DNS, (3) documents the 3 env vars in `.env.example` for the operator's external Caddy, and (4) writes a runbook showing how to wire it all up. The existing `frontend.ports: ["3000:3000"]` mapping is **preserved** for host-side debugging. Rate limiting (default 20 req/min per IP) is configurable via Caddy's `{$VAR:default}` env-var syntax. No static test suite — per user direction, the Caddyfile is a copy-paste reference, validated by the operator on the VPS with `caddy validate`.

## User Story

As an operator
I want a copy-paste Caddyfile and a runbook for wiring my existing external Caddy into the `docker-compose.prod.yml` stack over a shared Docker network
So that the app is reachable on a real domain with HTTPS, HTTP→HTTPS redirect, and rate-limited chat in a single file copy + a `docker network connect`.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (deployment infra — adds Docker network + deploy artifact; no app code changes) |
| Complexity | SMALL (no compose service change, no app code change; Caddyfile + named network + docs only) |
| Systems Affected | `docker-compose.prod.yml` (add named network), `deploy/Caddyfile` (CREATE), `.env.example` (3 new env vars documented), `.agents/plans/`, `.agents/reports/`, `.agents/decisions/`, `.agents/stories/` |
| Jira Issue | ARCRAG-18 |
| Blocked By | ARCRAG-17 ✅ |
| Blocks | ARCRAG-19 (E2E validation) |

---

## Current State (verified during planning)

| Artifact | State | Implication |
|----------|-------|-------------|
| `docker-compose.prod.yml` | 4 services on the default network (no `networks:` block); `frontend.ports: ["3000:3000"]` is the only host-exposed port | Need to add a top-level named network (`arcrag-net`) and attach all 4 services to it. Keep the `3000:3000` mapping for host-side debugging. |
| `frontend/Dockerfile` | `node:20-alpine`, standalone, healthcheck via `wget --spider` | No change. |
| `frontend/src/app/api/copilotkit/route.ts` | Server-side route proxies to `${NEXT_PUBLIC_BACKEND_URL}/ag-ui` (baked at build time as `http://backend:8000`) | The `/api/copilotkit` path is what Caddy's rate_limit targets. Browser → Caddy (HTTPS) → frontend:3000 → backend:8000 — single-origin from the browser's perspective. |
| `backend/src/main.py:17,23` | CORS restricted to `NEXT_PUBLIC_BACKEND_URL` (default `http://localhost:3000`) | In prod, `NEXT_PUBLIC_BACKEND_URL=http://backend:8000` (baked at build). Browser never talks to backend directly. CORS is effectively a no-op for the chat flow. **No change needed** for ARCRAG-18. |
| Caddy on VPS | User-stated as already running | ARCRAG-18 doesn't deploy a Caddy container. Operator copies `deploy/Caddyfile` into their existing Caddy config. |
| `.env.example` | Has `OPENROUTER_*`, `EMBEDDING_*`, `QDRANT_*`, `BACKEND_*`, `NEXT_PUBLIC_BACKEND_URL` | Add 3 Caddy env vars: `CADDY_DOMAIN`, `CADDY_EMAIL`, `CADDY_RATE_LIMIT_PER_MINUTE` — **documented but not consumed by the compose** (they're for the operator's external Caddy). |
| `deploy/` directory | Does not exist | Will be created. `.gitignore` does not exclude it. |

---

## Patterns to Follow

### ARCRAG-17 "compose reuses prior patterns, no surprises" (mirror)
The ARCRAG-17 plan added `arcrag_data` named volume and `depends_on` with `condition: service_completed_successfully` / `condition: service_healthy` for the inits/backend. ARCRAG-18's network addition follows the same minimal-diff philosophy: add a top-level `networks:` block, add `networks: [arcrag-net]` to each service, don't touch the rest of the file.

### ARCRAG-15/16 init container pattern (don't break it)
The dual-init pattern depends on `depends_on: { arcrag-init-arcmap: { condition: service_completed_successfully } }`. Adding a named network doesn't affect `depends_on` semantics; both still work. The inits' health/gate logic is unchanged.

### Caddy `{$VAR:default}` env-var syntax (idiomatic)
Caddy's Caddyfile supports `{$VAR}` (required) and `{$VAR:default}` (with default). The `deploy/Caddyfile` uses the latter so the operator can copy the file as-is and override env vars in their Caddy environment (systemd `Environment=`, Docker `-e`, Caddy's `--env` flag, etc.).

### `reverse_proxy` to Docker DNS name (the standard pattern)
The external Caddy container joins `arcrag-net`. Caddyfile uses `reverse_proxy frontend:3000` — Docker's embedded DNS resolves `frontend` to the compose service's container IP on that network. No host port mapping needed for the Caddy → frontend hop (the `3000:3000` mapping is for host-side debugging, not the Caddy → frontend path).

---

## Key Design Decisions

### 1. No Caddy service in `docker-compose.prod.yml`

**Decision:** The compose stays at 4 services (`arcrag-init`, `arcrag-init-arcmap`, `backend`, `frontend`). No Caddy container is added.

**Rationale:** The user runs Caddy externally on the VPS. Adding another Caddy container creates:
- Port conflicts (both want 80/443 on the host)
- Operational complexity (two places to renew certs, two configs to keep in sync)
- Confusing failure modes (which Caddy served this request?)

The right boundary: **this repo owns the app stack; the operator owns the reverse proxy.** The Caddyfile in `/deploy/` is a reference; the operator copies it into their existing Caddy config.

**Consequence:** The `frontend.ports: ["3000:3000"]` mapping (added in ARCRAG-17) is preserved. It is not on the Caddy → frontend path (that goes over Docker's internal network). It exists for `curl http://localhost:3000/` from the VPS host (a useful smoke test that skips TLS).

### 2. Named Docker network `arcrag-net` (not the project default)

**Decision:** Add a top-level `networks: { arcrag-net: { name: arcrag-net } }` block to `docker-compose.prod.yml` and have all 4 services declare `networks: [arcrag-net]`.

**Rationale:** The default network in a Compose project is `<project>_default` (e.g., `arcpro-docs_default`). This name is fragile:
- Depends on the directory name (changing the project dir changes the network name)
- Can be re-created with a fresh name on `docker compose down` (depending on the Docker version)
- Other containers can't easily attach to it without knowing the project name

A named network is:
- Predictable (`arcrag-net` regardless of project dir)
- Survives `docker compose down` + `up` cycles
- Easy to document: "your Caddy needs to be on the `arcrag-net` network"
- The Caddyfile's `reverse_proxy frontend:3000` resolves via Docker DNS

**Operator action:** `docker network connect arcrag-net <caddy-container>` (one-liner documented in the runbook).

### 3. `deploy/Caddyfile` (not `Caddyfile.example` at root, not `examples/Caddyfile`)

**Decision:** Place the Caddyfile at `/deploy/Caddyfile` at the repo root.

**Rationale:**
- Root-level `Caddyfile` would be ambiguous (is it active config? a reference? an override?)
- `examples/` is in `.gitignore` (per `.gitignore:27`), so unavailable
- A new top-level `deploy/` directory is the conventional home for deployment artifacts (similar to `k8s/`, `terraform/`, `helm/` in other projects)
- The Caddyfile is a copy-paste reference, not active config in this repo's compose

**Operator action:** `cp deploy/Caddyfile /etc/caddy/Caddyfile.d/arcrag-docs` (or wherever their Caddy config lives) and reload Caddy.

### 4. Rate limit scoped to `/api/*` only, configurable via env var

**Decision:** Caddyfile has:
```caddyfile
@api path /api/*
rate_limit @api {$CADDY_RATE_LIMIT_PER_MINUTE:20}r/m
```
The `20` default matches PRD §9. The operator overrides via `CADDY_RATE_LIMIT_PER_MINUTE` env var in their Caddy environment.

**Rationale:** A page refresh hits ~5-10 static asset requests. A global rate limit of 20/min would block legitimate users after 2-3 refreshes. Scoping to `/api/*` (which is just `/api/copilotkit` in this app) matches PRD §9 literally and avoids false positives.

**Note:** Caddy's `rate_limit` directive uses an in-memory token bucket per zone. The default zone key is the client IP (Caddy does this automatically). No explicit `zone` clause needed for "per-IP" — that's the default.

### 5. Caddy auto-HTTPS via Let's Encrypt

**Decision:** Caddyfile uses `email {$CADDY_EMAIL}` and the standard `{$CADDY_DOMAIN}` site block. Caddy auto-issues Let's Encrypt certs on first request to that domain.

**Rationale:** Caddy's killer feature. Zero cert management. The user's existing Caddy setup already supports this; the example Caddyfile just needs the right domain + email.

### 6. No static test suite (per user direction)

**Decision:** No `backend/test_caddyfile.py` or similar. The Caddyfile is validated by the operator on the VPS using `caddy validate --config /path/to/Caddyfile` (a one-liner in the runbook).

**Rationale:** Per the user's explicit answer "Skip static tests, document only." The Caddyfile is a reference artifact, not a runtime-asserted invariant. Caddy itself does strict config validation at startup; an in-repo Python checker is redundant. The runbook's smoke test (`caddy validate` + a real HTTPS request) is sufficient.

---

## Caddyfile Structure (`deploy/Caddyfile`)

```caddyfile
# ArcGIS Documentation RAG — reverse proxy + HTTPS + rate limit
#
# Copy this file into your existing Caddy config (e.g.,
# /etc/caddy/Caddyfile.d/arcrag-docs, or include it from your main
# Caddyfile with `import /etc/caddy/Caddyfile.d/arcrag-docs`).
#
# This Caddyfile assumes your Caddy container is on the same Docker
# network as the arcpro-docs compose stack (the named network
# `arcrag-net` defined in docker-compose.prod.yml). Attach it with:
#
#   docker network connect arcrag-net <caddy-container-name>
#
# Set the env vars below in your Caddy environment (systemd
# Environment=, docker run -e, or Caddy's --env flag).
#
# Required env vars (with defaults):
#   CADDY_DOMAIN                    e.g., arcgis-docs.example.com
#   CADDY_EMAIL                     e.g., admin@example.com (for Let's Encrypt)
#   CADDY_RATE_LIMIT_PER_MINUTE     default 20 (matches PRD §9)

{$CADDY_DOMAIN:arcgis-docs.example.com} {
    encode gzip zstd
    reverse_proxy frontend:3000

    # Rate-limit only the chat endpoint. Static assets and page
    # navigations are not limited (per PRD §9).
    @api path /api/*
    rate_limit @api {$CADDY_RATE_LIMIT_PER_MINUTE:20}r/m
}

# HTTP → HTTPS redirect (explicit for clarity; Caddy does this
# implicitly when an HTTPS block exists for the same domain).
http://{$CADDY_DOMAIN:arcgis-docs.example.com} {
    redir https://{host}{uri} permanent
}
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `docker-compose.prod.yml` | UPDATE | Add top-level `networks: { arcrag-net: { name: arcrag-net } }`; add `networks: [arcrag-net]` to all 4 services (`arcrag-init`, `arcrag-init-arcmap`, `backend`, `frontend`). No other changes. |
| `deploy/Caddyfile` | CREATE | The Caddyfile above. |
| `.env.example` | UPDATE | Add 3 Caddy env vars (`CADDY_DOMAIN`, `CADDY_EMAIL`, `CADDY_RATE_LIMIT_PER_MINUTE`) with comments explaining they're for the operator's external Caddy, not consumed by the compose. |
| `.agents/plans/arccrag-18-reverse-proxy-https.plan.md` | CREATE | This plan. |
| `.agents/reports/arccrag-18-reverse-proxy-https-report.md` | CREATE (post-run) | Implementation report + VPS runbook. |
| `.agents/decisions/arccrag-18-reverse-proxy-https.md` | CREATE (post-run) | Decision log / postmortem. |
| `.agents/stories/stories.md` | UPDATE | Mark ARCRAG-18 in-progress (now) → ✅ Completed (after VPS run). |
| `docker-compose.yml` (dev) | NO CHANGE | Dev compose stays untouched (per ARCRAG-17 precedent). |
| `frontend/Dockerfile`, `backend/Dockerfile`, all `backend/src/**`, `frontend/src/**` | NO CHANGE | App code is unaffected. |

---

## Tasks

Execute in order. Each task is atomic and verifiable on the dev PC (no Docker daemon required for Tasks 1-3; Task 4 is the VPS-side validation).

### Task 1: Add named network to `docker-compose.prod.yml`

- **File**: `docker-compose.prod.yml`
- **Action**: UPDATE (additions only, no removals)
- **Implement**: Add a top-level `networks:` block at the bottom (after `volumes:`):
  ```yaml
  networks:
    arcrag-net:
      name: arcrag-net
  ```
  And add `networks: [arcrag-net]` to each of the 4 services (`arcrag-init`, `arcrag-init-arcmap`, `backend`, `frontend`).
- **Mirror**: ARCRAG-17's named-volume pattern (top-level `volumes:` + per-service `volumes:`).
- **Avoid**: Don't remove the existing `frontend.ports: ["3000:3000"]` (kept for host-side debugging per Decision 1).
- **Validate**: `python3 -c "import yaml; d=yaml.safe_load(open('docker-compose.prod.yml')); assert d['networks'] == {'arcrag-net': {'name': 'arcrag-net'}}, d.get('networks'); svcs=d['services']; expected={'arcrag-init','arcrag-init-arcmap','backend','frontend'}; assert set(svcs.keys())==expected; assert all('arcrag-net' in svcs[s].get('networks', []) for s in expected)"` exits 0.

### Task 2: Create `deploy/Caddyfile`

- **File**: `deploy/Caddyfile`
- **Action**: CREATE
- **Implement**: The structure from the "Caddyfile Structure" section above. Header comment block explains how to use it; required env vars; how to attach Caddy to `arcrag-net`.
- **Mirror**: Caddy's official docs example for reverse_proxy + rate_limit.
- **Avoid**: Don't use a `version:` directive in the Caddyfile (obsolete). Don't hardcode the domain (use `{$VAR:default}`). Don't use a non-standard rate-limit syntax (use `r/m` for requests-per-minute, the standard Caddy unit).
- **Validate**: `caddy validate --config deploy/Caddyfile` (run on the VPS where Caddy is installed; deferred to Task 4). On the dev PC, `grep` checks for the 5 required structural elements (`{$CADDY_DOMAIN`, `reverse_proxy frontend:3000`, `@api path /api/*`, `rate_limit @api`, `redir https://`).

### Task 3: Update `.env.example`

- **File**: `.env.example`
- **Action**: UPDATE (append a new section at the bottom)
- **Implement**: Add:
  ```env
  # Caddy (external reverse proxy, NOT consumed by this compose — set these
  # in your Caddy environment, e.g., systemd Environment= or docker run -e.
  # See deploy/Caddyfile for usage.)
  CADDY_DOMAIN=arcgis-docs.example.com
  CADDY_EMAIL=admin@example.com
  CADDY_RATE_LIMIT_PER_MINUTE=20
  ```
- **Rationale**: The compose doesn't read these (Caddy is external). The `.env.example` documents them so the operator knows the knobs the Caddyfile exposes. This is a documentation-only addition.
- **Validate**: `grep -E '^(CADDY_DOMAIN|CADDY_EMAIL|CADDY_RATE_LIMIT_PER_MINUTE)=' .env.example` returns 3 lines.

### Task 4: VPS-side validation (deferred to VPS run per ARCRAG-15/16/17 precedent)

- **Action**: VALIDATE (deferred)
- **Implement** (VPS runbook, documented in the report):
  ```bash
  # 0. Sync to VPS
  cd /opt/arcpro-docs && git pull origin feature/arccrag-18-reverse-proxy-https

  # 1. Validate the Caddyfile syntactically
  caddy validate --config deploy/Caddyfile
  # (or: caddy adapt --config deploy/Caddyfile | caddy validate --config -)

  # 2. Bring up the prod stack (creates arcrag-net)
  docker compose -f docker-compose.prod.yml up -d --build

  # 3. Attach external Caddy to the arcrag-net network (idempotent)
  docker network connect arcrag-net <caddy-container-name>

  # 4. Copy Caddyfile into operator's Caddy config (e.g.)
  sudo cp deploy/Caddyfile /etc/caddy/Caddyfile.d/arcrag-docs
  sudo systemctl reload caddy
  # (or: docker restart <caddy-container>)

  # 5. Set the env vars in Caddy's environment
  sudo systemctl edit caddy   # add: Environment="CADDY_DOMAIN=..."
  sudo systemctl daemon-reload && sudo systemctl restart caddy

  # 6. Verify
  curl -I https://$CADDY_DOMAIN/                          # 200, HSTS, etc.
  curl -I http://$CADDY_DOMAIN/                           # 301 → https://
  # Manual: open https://$CADDY_DOMAIN in a browser, ask "What is the Buffer tool?"

  # 7. Test the rate limit
  for i in $(seq 1 25); do
    curl -s -o /dev/null -w "%{http_code}\n" -X POST https://$CADDY_DOMAIN/api/copilotkit
  done
  # Expected: first ~20 return 200/4xx, remainder return 429
  ```

### Task 5: Documentation

- **Action**: DOCUMENT
- **Implement**:
  - Create `.agents/reports/arcrrag-18-reverse-proxy-https-report.md` (summary, files changed, validation results, the VPS runbook above, deviations, acceptance criteria checklist)
  - Create `.agents/decisions/arccrag-18-reverse-proxy-https.md` (key decisions: external Caddy, named network, env-var rate limit, no static tests, etc.)
  - Update `.agents/stories/stories.md`: mark ARCRAG-18 in-progress (now) → ✅ Completed (after VPS run)
- **Validate**: All 5 acceptance criteria from the story are checked off.

---

## Validation Block

```bash
# After Tasks 1-3 (code complete, before Task 4)
cd /home/techafresh/projects/arcpro-docs

# Task 1: compose has the named network
python3 -c "
import yaml
d = yaml.safe_load(open('docker-compose.prod.yml'))
assert d.get('networks') == {'arcrag-net': {'name': 'arcrag-net'}}, d.get('networks')
expected = {'arcrag-init', 'arcrag-init-arcmap', 'backend', 'frontend'}
assert set(d['services'].keys()) == expected
for s in expected:
    assert 'arcrag-net' in d['services'][s].get('networks', []), f'{s} missing arcrag-net'
print('OK: arcrag-net on all 4 services')
"

# Task 2: Caddyfile structure (pure-text check; no Caddy required)
test -f deploy/Caddyfile
grep -q '{\$CADDY_DOMAIN'             deploy/Caddyfile
grep -q 'reverse_proxy frontend:3000' deploy/Caddyfile
grep -q '@api path /api/\*'           deploy/Caddyfile
grep -q 'rate_limit @api'             deploy/Caddyfile
grep -q 'redir https://'              deploy/Caddyfile

# Task 3: .env.example documents the Caddy env vars
grep -q '^CADDY_DOMAIN='                  .env.example
grep -q '^CADDY_EMAIL='                   .env.example
grep -q '^CADDY_RATE_LIMIT_PER_MINUTE='   .env.example

# Verify ARCRAG-17's existing test suite still passes (network addition is non-breaking)
cd backend && python3 test_prod_compose.py    # 29 existing assertions still pass
```

---

## Acceptance Criteria

- [ ] `deploy/Caddyfile` exists with HTTPS site block, `reverse_proxy frontend:3000`, `@api path /api/*` matcher, `rate_limit @api` directive, HTTP→HTTPS redirect, and `{$VAR:default}` placeholders for domain/email/rate limit
- [ ] `docker-compose.prod.yml` has top-level `networks: { arcrag-net: { name: arcrag-net } }` and all 4 services declare `networks: [arcrag-net]`
- [ ] `frontend.ports: ["3000:3000"]` is preserved (for host-side debugging)
- [ ] `.env.example` documents `CADDY_DOMAIN`, `CADDY_EMAIL`, `CADDY_RATE_LIMIT_PER_MINUTE` with comments explaining they're for the external Caddy
- [ ] Existing `backend/test_prod_compose.py` still passes (29 assertions) — the network addition is non-breaking
- [ ] Pre-flight on VPS: `caddy validate --config deploy/Caddyfile` exits 0
- [ ] Pre-flight on VPS: `docker network inspect arcrag-net` shows the 4 compose services + the external Caddy container attached
- [ ] Full run on VPS: `https://$CADDY_DOMAIN/` returns 200 with valid Let's Encrypt cert
- [ ] Full run on VPS: `http://$CADDY_DOMAIN/` returns 301 → `https://$CADDY_DOMAIN/`
- [ ] Full run on VPS: chat works end-to-end via the HTTPS URL (ask "What is the Buffer tool?" → grounded answer)
- [ ] Full run on VPS: 21st request to `/api/copilotkit` from the same IP within a minute returns 429 (rate limit fires)
- [ ] `.agents/reports/arccrag-18-...md` and `.agents/decisions/arccrag-18-...md` are written
- [ ] `.agents/stories/stories.md` marks ARCRAG-18 ✅ Completed (with timestamp after VPS run)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| External Caddy is NOT on the `arcrag-net` network → `reverse_proxy frontend:3000` fails with DNS error | The runbook step 3 explicitly runs `docker network connect arcrag-net <caddy-container>` after `docker compose up`. The compose creates the network on first `up`; the operator connects Caddy after that. |
| External Caddy is on a different network (e.g., a separate `caddy_net`) | Document both patterns in the runbook: (a) connect Caddy to `arcrag-net` (recommended), or (b) change the Caddyfile's `reverse_proxy` to `host.docker.internal:3000` (if Caddy is on the host) or `<vps-ip>:3000` (if Caddy is on a different host entirely). The Caddyfile's upstream is one line to change. |
| Caddy's `{$VAR:default}` env-var syntax requires the var to be unset OR set to the default value for the default to apply | Document explicitly: if `CADDY_DOMAIN` is unset, Caddy uses `arcgis-docs.example.com` (the default). If set to a real domain, the default is ignored. Standard Caddy behavior. |
| Let's Encrypt HTTP-01 challenge fails if port 80 isn't reachable from the internet | Caddy uses HTTP-01 by default, which requires port 80 reachable. The runbook's first verify (`curl -I https://$CADDY_DOMAIN/`) implicitly tests this — if LE fails, the request returns a Caddy self-signed fallback or an error. Operator should verify port 80 is open on the VPS firewall. Alternative: use DNS-01 challenge (Caddy supports it; would require adding a `tls` directive with a DNS provider plugin). Out of scope for MVP. |
| Operator's Caddy is on an older version that doesn't support `{$VAR:default}` syntax | This syntax has been in Caddy since v2.0 (2020). Any Caddy v2 is fine. If the operator is on Caddy v1, that's a pre-existing problem ARCRAG-18 cannot fix. |
| `arcrag-net` already exists on the host from another project | The compose's `name: arcrag-net` makes the network name explicit. If a network with that name exists, the compose `up` will fail with a clear error. Operator can either (a) use the existing one (verify it's the right one), (b) rename to `arcrag-docs-net` and update the Caddyfile's `reverse_proxy frontend:3000` to still work (it doesn't reference the network name). |
| Removing the host port mapping would break host-side debugging | **Decision: keep `3000:3000`**. The security concern is moot (Caddy terminates TLS in front). The host-side debug value (`curl localhost:3000/`) is real. |
| Rate limit on `/api/*` accidentally includes other future API paths | Currently `/api/copilotkit` is the only path under `/api/*`. If a future story adds `/api/foo`, it'll also be rate-limited (which is probably desired). Documented as a design choice, not a bug. |
| `caddy validate` is not installed on the VPS | Runbook uses Caddy to validate itself. If Caddy isn't installed, ARCRAG-18 cannot work. The user's existing Caddy setup is the source of `caddy validate`. |
| `docker network connect` requires the Caddy container to be running | If the operator starts Caddy after running `docker compose up`, they need to `docker network connect` after Caddy is up. Document the order: (1) `docker compose up -d` (creates network), (2) start Caddy (or `docker network connect` if already running). |

---

## Open Questions / Assumptions

1. **The external Caddy container is named something stable** so the operator can identify it in `docker network connect`. If the operator's Caddy is on a different host entirely, the Caddyfile's `reverse_proxy` upstream needs to be the VPS IP, not `frontend:3000` (the latter only works for same-network setups).
2. **Caddy v2** (any version) is installed on the VPS. The `{$VAR:default}` and `rate_limit` syntax is v2-only. v1 is unsupported.
3. **Port 80 is reachable from the internet** on the VPS for Let's Encrypt HTTP-01. If the VPS is behind a strict firewall, DNS-01 challenge is needed (Caddy supports it via plugins; out of scope for ARCRAG-18, document as a follow-up).
4. **The operator can reload/restart Caddy** on the VPS (systemd access or Docker control). Documented in the runbook step 4.
5. **The dev `docker-compose.yml` is NOT modified.** Per ARCRAG-17 precedent, the dev compose is for dev/single-host use and doesn't get the production network. Operators running locally can still use `localhost:3000` directly.
6. **No new dependencies** are added to the Python or Node code. ARCRAG-18 is purely deployment config.
7. **The `deploy/` directory is new** — not previously existing in the repo. `.gitignore` does not exclude it.
8. **The 3 Caddy env vars are documentation-only** in `.env.example`. They are NOT consumed by the compose. The Caddyfile reads them from Caddy's own environment, not from `backend/.env`.
9. **Caddyfile is a copy-paste reference, not the active config.** The operator copies it into their existing Caddy config directory (e.g., `/etc/caddy/Caddyfile.d/`). No include/import mechanism is enforced; the operator chooses.
10. **The Caddyfile rate limit is best-effort.** A determined attacker can rotate IPs. For MVP (open access for students), this is acceptable. Future hardening: add IP-based blocking at the firewall level, or use Cloudflare in front.
