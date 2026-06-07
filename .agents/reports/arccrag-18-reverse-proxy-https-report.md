# Implementation Report

**Plan**: `.agents/plans/arccrag-18-reverse-proxy-https.plan.md`
**Branch**: `feature/arccrag-18-reverse-proxy-https`
**Status**: COMPLETE (dev-PC scope; VPS runbook inlined below)

## Summary

Wired the existing external Caddy on the VPS into the prod stack via a
named Docker network + a copy-paste Caddyfile. No new Caddy service was
added to `docker-compose.prod.yml` (the user runs Caddy externally, so a
second Caddy would clash on ports 80/443). Three changes total:

1. `docker-compose.prod.yml` — added top-level `networks: { arcrag-net:
   { name: arcrag-net } }` and `networks: [arcrag-net]` to all 4
   services. `frontend.ports: ["3000:3000"]` preserved for host-side
   debugging.
2. `deploy/Caddyfile` — new reference Caddyfile with HTTPS site block,
   `reverse_proxy frontend:3000` over Docker DNS, `/api/*`-scoped
   rate limit (default 20 req/min, configurable), explicit HTTP→HTTPS
   redirect, and `{$VAR:default}` placeholders for `CADDY_DOMAIN`,
   `CADDY_EMAIL`, `CADDY_RATE_LIMIT_PER_MINUTE`.
3. `.env.example` — documented the 3 Caddy env vars (operator sets
   these in their Caddy environment; the compose does NOT read them).

The 29-assertion `backend/test_prod_compose.py` suite still passes
(the network addition is non-breaking by design).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add named network `arcrag-net` to prod compose; attach all 4 services | `docker-compose.prod.yml` | ✅ |
| 2 | Create `deploy/Caddyfile` (HTTPS, reverse_proxy, `/api/*` rate_limit, HTTP→HTTPS redirect, env-var placeholders) | `deploy/Caddyfile` | ✅ |
| 3 | Document 3 Caddy env vars (`CADDY_DOMAIN`, `CADDY_EMAIL`, `CADDY_RATE_LIMIT_PER_MINUTE`) | `.env.example` | ✅ |
| 4 | VPS-side validation (`caddy validate`, network connect, full HTTPS smoke test) | (deferred — see VPS runbook) | ⏭ |
| 5 | Documentation (report, decision log, stories.md update) | `.agents/reports/`, `.agents/decisions/`, `.agents/stories/stories.md` | ✅ |

## Validation Results

| Check | Command | Result |
|-------|---------|--------|
| Top-level `networks: { arcrag-net: { name: arcrag-net } }` exists; all 4 services attach | `python3 -c "import yaml; d=yaml.safe_load(open('docker-compose.prod.yml')); ..."` | ✅ |
| `frontend.ports == ['3000:3000']` preserved | same check | ✅ |
| `deploy/Caddyfile` has `{$CADDY_DOMAIN`, `reverse_proxy frontend:3000`, `@api path /api/*`, `rate_limit @api`, `redir https://` | `grep -q ...` (5 checks) | ✅ |
| `.env.example` has `CADDY_DOMAIN=`, `CADDY_EMAIL=`, `CADDY_RATE_LIMIT_PER_MINUTE=` | `grep -q '^CADDY_...='` (3 checks) | ✅ |
| Existing ARCRAG-17 test suite still passes (network addition is non-breaking) | `python3 backend/test_prod_compose.py` | ✅ **29 passed, 0 failed** |
| Dev `docker-compose.yml` untouched | `git diff docker-compose.yml` | ✅ (no diff) |
| App code untouched | `git diff backend/ frontend/src/` | ✅ (no diff) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `docker-compose.prod.yml` | UPDATE | +12 (top-level `networks:` block + 4 per-service entries) |
| `deploy/Caddyfile` | CREATE | +39 |
| `.env.example` | UPDATE | +7 |
| `.agents/reports/arccrag-18-reverse-proxy-https-report.md` | CREATE | (this file) |
| `.agents/decisions/arccrag-18-reverse-proxy-https.md` | CREATE | (decision log) |
| `.agents/stories/stories.md` | UPDATE | +1 (status field on ARCRAG-18 + summary row) |
| `docker-compose.yml` (dev) | NO CHANGE | 0 |
| `frontend/`, `backend/src/` (app code) | NO CHANGE | 0 |

## Deviations from Plan

| # | Deviation | Rationale |
|---|-----------|-----------|
| 1 | Added a global `{ email {$CADDY_EMAIL:admin@example.com} }` options block at the top of `deploy/Caddyfile` (the plan only showed it implicitly under the site block) | The Caddyfile's global `email` directive must live in the unnamed top-level options block, not inside a site block. This is the idiomatic Caddy v2 way to wire Let's Encrypt account email, and matches the plan's intent (Decision §5) that `CADDY_EMAIL` is the Let's Encrypt account email. No behavioral change vs the plan; only the syntactic placement is corrected. |
| 2 | Test suite assertion count unchanged (29) | The plan said "29 existing assertions still pass" — confirmed verbatim. No new assertions added to `test_prod_compose.py` because the network addition is non-structural and the plan explicitly chose "no static test suite" (Decision §6). The grep-based one-shot validation in the plan's Validation Block is the test for this story. |

## Acceptance Criteria — Dev-PC Scope

- [x] `deploy/Caddyfile` exists with HTTPS site block, `reverse_proxy frontend:3000`, `@api path /api/*` matcher, `rate_limit @api` directive, HTTP→HTTPS redirect, and `{$VAR:default}` placeholders for domain/email/rate limit
- [x] `docker-compose.prod.yml` has top-level `networks: { arcrag-net: { name: arcrag-net } }` and all 4 services declare `networks: [arcrag-net]`
- [x] `frontend.ports: ["3000:3000"]` is preserved (for host-side debugging)
- [x] `.env.example` documents `CADDY_DOMAIN`, `CADDY_EMAIL`, `CADDY_RATE_LIMIT_PER_MINUTE` with comments explaining they're for the external Caddy
- [x] Existing `backend/test_prod_compose.py` still passes (29 assertions) — the network addition is non-breaking
- [x] `.agents/reports/arccrag-18-...md` and `.agents/decisions/arccrag-18-...md` are written
- [x] `.agents/stories/stories.md` marks ARCRAG-18 status updated

## Acceptance Criteria — VPS Scope — DEFERRED

These are run on the VPS by the operator. The runbook is reproduced below.

- [ ] Pre-flight on VPS: `caddy validate --config deploy/Caddyfile` exits 0
- [ ] Pre-flight on VPS: `docker network inspect arcrag-net` shows the 4 compose services + the external Caddy container attached
- [ ] Full run on VPS: `https://$CADDY_DOMAIN/` returns 200 with valid Let's Encrypt cert
- [ ] Full run on VPS: `http://$CADDY_DOMAIN/` returns 301 → `https://$CADDY_DOMAIN/`
- [ ] Full run on VPS: chat works end-to-end via the HTTPS URL (ask "What is the Buffer tool?" → grounded answer)
- [ ] Full run on VPS: 21st request to `/api/copilotkit` from the same IP within a minute returns 429 (rate limit fires)
- [ ] `.agents/stories/stories.md` marks ARCRAG-18 ✅ Completed (with timestamp after VPS run)

## Jira Update

**Jira Issue**: `ARCRAG-18`

The Atlassian MCP tools (`mcp__atlassian__*`) are not available in this
execution environment, and neither `gh` nor `jira` CLIs are installed on
PATH. The Jira update phase (transition + comment) could not be performed
automatically. The operator should manually:

1. Transition ARCRAG-18 to **In Review** (or appropriate status)
2. Add a comment with this implementation summary and a link to
   `.agents/reports/arccrag-18-reverse-proxy-https-report.md`
3. Once the VPS run is complete, transition to **Done**

## VPS-Side Runbook (deferred to VPS run)

```bash
# 0. Sync to VPS
cd /opt/arcpro-docs && git pull origin feature/arccrag-18-reverse-proxy-https

# 1. Validate the Caddyfile syntactically (uses the operator's existing Caddy binary)
caddy validate --config deploy/Caddyfile
# (or: caddy adapt --config deploy/Caddyfile | caddy validate --config -)

# 2. Bring up the prod stack (this creates the arcrag-net network)
docker compose -f docker-compose.prod.yml up -d --build
docker network inspect arcrag-net    # confirm 4 services attached

# 3. Attach the external Caddy container to arcrag-net (idempotent; skip if already on it)
docker network connect arcrag-net <caddy-container-name>
docker network inspect arcrag-net    # now shows 5 containers (4 + caddy)

# 4. Copy Caddyfile into the operator's Caddy config (path depends on the operator's setup)
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile.d/arcrag-docs
# OR include it from the main Caddyfile:
#   echo 'import /etc/caddy/Caddyfile.d/arcrag-docs' | sudo tee -a /etc/caddy/Caddyfile

# 5. Set the env vars in Caddy's environment
# Option A (systemd):
sudo systemctl edit caddy
# Add under [Service]:
#   Environment="CADDY_DOMAIN=arcgis-docs.your-domain.com"
#   Environment="CADDY_EMAIL=admin@your-domain.com"
#   Environment="CADDY_RATE_LIMIT_PER_MINUTE=20"
sudo systemctl daemon-reload && sudo systemctl restart caddy
# Option B (docker):
#   docker restart -e CADDY_DOMAIN=... -e CADDY_EMAIL=... -e CADDY_RATE_LIMIT_PER_MINUTE=20 <caddy-container>

# 6. Verify
curl -I https://$CADDY_DOMAIN/                          # 200 with valid LE cert + HSTS header
curl -I http://$CADDY_DOMAIN/                           # 301 redirect to https://
# Manual: open https://$CADDY_DOMAIN in a browser, ask "What is the Buffer tool?"
# Expected: grounded answer with image + source link

# 7. Test the rate limit
for i in $(seq 1 25); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST https://$CADDY_DOMAIN/api/copilotkit
done
# Expected: first ~20 return 200/4xx (depending on POST body), remainder return 429

# 8. Confirm host-side debugging path still works (Caddy bypass)
curl http://localhost:3000/    # should return the frontend HTML directly from the VPS host
```

**Notes**:
- If `docker network connect` says "already exists on network", the Caddy
  container is already attached — no action needed.
- If `caddy validate` fails with "unknown directive: rate_limit", the
  operator's Caddy build doesn't include the `rate_limit` module. Install
  it via `caddy add-package github.com/mholt/caddy-ratelimit` or build a
  custom Caddy with `xcaddy`. (Most distro packages ship with it.)
- If Let's Encrypt fails (port 80 not reachable), check the VPS firewall.
  DNS-01 challenge is the alternative; out of scope for this story.
- The `arcrag-net` network persists across `docker compose down`/`up`
  cycles. `docker network rm arcrag-net` would force a re-attach of the
  Caddy container.
