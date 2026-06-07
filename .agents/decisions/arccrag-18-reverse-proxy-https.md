# Decision Log & Implementation Postmortem: arccrag-18-reverse-proxy-https

- **Date**: 2026-06-07
- **Branch**: `feature/arccrag-18-reverse-proxy-https`
- **Report Path**: `.agents/reports/arccrag-18-reverse-proxy-https-report.md`

## 1. Summary of Implementation

Wired the operator's existing external Caddy into the prod stack via:

1. A named Docker network `arcrag-net` declared in
   `docker-compose.prod.yml` and attached to all 4 services
   (`arcrag-init`, `arcrag-init-arcmap`, `backend`, `frontend`). The
   `frontend.ports: ["3000:3000"]` mapping is preserved for host-side
   debugging.
2. A copy-paste reference `deploy/Caddyfile` with HTTPS site block,
   `reverse_proxy frontend:3000` (resolves via Docker's embedded DNS),
   `/api/*`-scoped rate limit (default 20 req/min, env-var configurable),
   explicit HTTP→HTTPS redirect, and `{$VAR:default}` placeholders for
   `CADDY_DOMAIN`, `CADDY_EMAIL`, `CADDY_RATE_LIMIT_PER_MINUTE`.
3. Documentation of the 3 Caddy env vars in `.env.example` (these are
   for the operator's external Caddy environment — the compose itself
   does NOT consume them).

No Caddy service was added to `docker-compose.prod.yml`. The existing
ARCRAG-17 test suite (`backend/test_prod_compose.py`) still passes all
29 assertions — the network addition is non-breaking by design. VPS-side
validation (Caddy `validate`, network attach, HTTPS smoke, rate-limit
smoke) is deferred to the operator per the plan's explicit handoff.

## 2. Key Decisions & Rationale

### 2.1 No Caddy service in `docker-compose.prod.yml`

**Decision**: The compose stays at 4 services. The operator runs Caddy
externally on the VPS.

**Rationale**: User explicitly stated Caddy is already running on the
VPS. Adding a second Caddy container would:
- Clash on host ports 80/443 (or force non-standard ports)
- Split TLS cert management across two places
- Create confusing "which Caddy served this?" debugging
- Violate the boundary: this repo owns the app stack; the operator owns
  the reverse proxy.

**Consequence**: The Caddyfile is a reference artifact (`deploy/Caddyfile`)
the operator copies into their existing Caddy config. The compose only
ships the named network that the external Caddy attaches to.

### 2.2 Named Docker network `arcrag-net` (not the compose project default)

**Decision**: Top-level `networks: { arcrag-net: { name: arcrag-net } }`
with `name:` explicitly set so the network identifier is stable
regardless of project directory name.

**Rationale**: The default Compose network is `<project-dir>_default`
(fragile to directory renames, recreated on some `down`/`up` cycles, and
hard to document for external attachments). A named network is:
- Predictable (`arcrag-net` always, regardless of where the compose lives)
- Persistent across `docker compose down` + `up`
- Easy to instruct the operator: "your Caddy needs `docker network
  connect arcrag-net <caddy>`"
- Resolves `frontend` via Docker's embedded DNS for
  `reverse_proxy frontend:3000`.

### 2.3 `deploy/Caddyfile` location (not root, not `examples/`)

**Decision**: `/deploy/Caddyfile` — a new top-level directory.

**Rationale**:
- Root-level `Caddyfile` would be ambiguous (active config? reference?
  override?).
- `examples/` is in `.gitignore` (line 27), so unavailable for committed
  files.
- `deploy/` is the conventional home for deployment artifacts
  (`k8s/`, `terraform/`, `helm/` are analogues elsewhere).
- This Caddyfile is a copy-paste reference, not active config in this
  repo's compose. The directory name signals that.

### 2.4 Rate limit scoped to `/api/*` (not global), env-var configurable

**Decision**:
```caddyfile
@api path /api/*
rate_limit @api {$CADDY_RATE_LIMIT_PER_MINUTE:20}r/m
```

**Rationale**: A page refresh hits ~5-10 static asset requests. A global
20/min limit would block a legitimate user after 2-3 refreshes. Scoping
to `/api/*` (which is just `/api/copilotkit` today) matches PRD §9
literally and avoids false positives on static assets/page navigations.
The default zone key is the client IP (Caddy's built-in default for
`rate_limit`); no explicit `zone` clause needed for per-IP behavior.

### 2.5 Caddy `{$VAR:default}` env-var syntax (not hardcoded values)

**Decision**: Domain, email, and rate-limit value all use
`{$VAR:default}` placeholders.

**Rationale**: The operator copies `deploy/Caddyfile` as-is and overrides
via Caddy's own environment (systemd `Environment=`, `docker -e`,
`--env` flag). Hardcoding the operator's domain in the repo would force
a code change for every deployment. The defaults make the file
self-documenting and runnable in a default-domain test scenario.

### 2.6 Auto-HTTPS via Let's Encrypt (no manual cert management)

**Decision**: `email {$CADDY_EMAIL:admin@example.com}` in the global
options block. Caddy auto-issues LE certs on first HTTPS request to the
configured domain.

**Rationale**: Caddy's killer feature. Zero cert management. The user's
existing Caddy setup already supports this. **Implementation tweak**:
the plan showed `email` implicitly under the site block, but Caddy v2
requires global directives like `email` to live in the unnamed top-level
options block (not inside a site block). The Caddyfile uses the correct
syntax — see Deviation §1 in the report.

### 2.7 Preserve `frontend.ports: ["3000:3000"]` (don't tighten)

**Decision**: Keep the host port mapping.

**Rationale**: Security concern is moot — Caddy terminates TLS in front,
and the VPS firewall (operator-controlled) blocks port 3000 from public
internet. The mapping is for the VPS host's own debugging:
`curl http://localhost:3000/` from the VPS shell bypasses Caddy/TLS and
isolates frontend vs proxy issues. Decision §1 of the plan documents
this trade-off; the team chose debugging convenience over a marginal
"surface area" reduction (which the firewall already provides).

### 2.8 No static test suite — Caddyfile validated on VPS

**Decision**: No `backend/test_caddyfile.py` or similar in-repo Python
checker. Validation = `caddy validate --config deploy/Caddyfile` on the
VPS + a real HTTPS smoke test.

**Rationale**: Per the user's plan-time direction ("Skip static tests,
document only"). Caddy itself does strict config validation at startup;
an in-repo Python parser would re-implement that. The 5-line `grep`
check in the plan's Validation Block catches the structural elements
(domain placeholder, `reverse_proxy frontend:3000`, `@api` matcher,
`rate_limit` directive, HTTP→HTTPS redirect) — that's sufficient as a
dev-PC gate.

## 3. Errors & Roadblocks Encountered

### 3.1 Global `email` directive needs the unnamed options block

**Error**: The plan's `deploy/Caddyfile` structure section showed the
email implicitly under the site block — but Caddy v2 requires
`email` (and other global settings) to live in the unnamed top-level
options block, not inside a site block. Attempting to put it under the
site block would have failed `caddy validate` on the VPS.

**Resolution**: Added a separate `{ email {$CADDY_EMAIL:admin@example.com} }`
global options block at the top of the file. This is the standard Caddy
v2 way; the placement is the only correction (the semantic intent —
"this is the Let's Encrypt account email" — is unchanged).

### 3.2 No Caddy binary on dev PC for direct `caddy validate`

**Issue**: `command -v caddy` returns nothing on the dev PC. Cannot do
the official "Caddy parses this file" check on PC.

**Resolution**: Per plan Decision §6, syntactic validation is deferred to
the VPS where Caddy is installed. The dev-PC scope is text-grep
validation (5 structural elements) plus the existing
`test_prod_compose.py` regression check (29 assertions).

### 3.3 Atlassian MCP / `gh` / `jira` not available

**Issue**: Same as ARCRAG-17 — no MCP, no `gh`, no `jira` CLI in
session. Cannot automate Jira transition + comment.

**Resolution**: Documented manual Jira steps in the report.

## 4. Workarounds & Resolutions

| # | Issue | Workaround |
|---|-------|-----------|
| 1 | Plan put `email` under the site block; Caddy v2 requires it in global options | Created a separate `{}` global options block at the top of `deploy/Caddyfile` |
| 2 | No `caddy` binary on dev PC | Deferred syntactic validation to VPS per plan Decision §6; dev-PC scope is grep-based structural validation |
| 3 | No Atlassian MCP / Jira CLI | Documented manual Jira-update steps in the report's "Jira Update" section |

## 5. What Went Right & What Went Wrong

### 5.1 What Went Right

- **Existing 29-assertion test suite passed unchanged.** The
  network addition is non-structural per the plan's design (it only
  adds a `networks:` field to each service and a top-level `networks:`
  block); none of the ARCRAG-17 assertions touch that surface. Clean
  validation that the change is backward-compatible.
- **All 3 files match the plan structure 1:1.** `docker-compose.prod.yml`,
  `deploy/Caddyfile`, and `.env.example` were straightforward to
  implement from the plan's specification. Only the global `email`
  directive placement needed correction.
- **Plan adherence was high.** Every "Patterns to Follow" item
  (ARCRAG-17 named-volume mirroring, init container pattern preserved,
  `{$VAR:default}` syntax, Docker DNS for `reverse_proxy`) was followed
  as specified.
- **`frontend.ports: ["3000:3000"]` was correctly preserved**, matching
  the plan's Decision §1 and the existing test suite's
  `frontend.ports == ['3000:3000']` assertion.
- **Dev `docker-compose.yml` and all app code untouched.** Zero risk
  of regression on dev workflows or runtime behavior.

### 5.2 What Went Wrong

- **The plan's Caddyfile snippet showed `email` under the site block.**
  Required a small placement fix to match Caddy v2 syntax. Documented as
  Deviation §1 in the report — minor and non-behavioral.
- **Jira update could not be automated** (same as ARCRAG-17 — known
  environment limitation). Operator must transition + comment manually.
- **VPS validation is fully deferred.** Per plan, this is intentional,
  but it means the report's "Complete" status applies only to the
  dev-PC scope; the VPS scope remains an open task for the operator
  before merging to main.

## 6. Lessons Learned & Recommendations

### 6.1 Lessons Learned

1. **Caddy v2 global directives go in the unnamed top-level options
   block.** Site-block scope is for per-site directives only.
   `email`, `acme_ca`, `debug`, `default_sni`, etc. belong at the top.
   When the plan's snippet implies otherwise, lift them out.
2. **Named Docker networks are the right boundary for "let an external
   container talk to a compose stack".** The pattern (top-level
   `networks: { name: name }` + per-service `networks: [name]` + `docker
   network connect` for the external container) is clean, documented,
   and survives `docker compose down`/`up`. Use it whenever an external
   service needs to reach a compose service by name.
3. **`{$VAR:default}` placeholders make Caddyfiles deployment-friendly.**
   The operator can paste the file unchanged and override via their env.
   No code change per environment.
4. **`/api/*` scoped rate limiting > global rate limiting** for any app
   that serves both APIs and static assets. The PRD's "20 req/min" only
   makes sense for the chat endpoint; global would block legitimate
   browsing.
5. **Existing test suites are cheap regression insurance.** Running
   `test_prod_compose.py` after the network addition took <1s and
   confirmed nothing structural shifted. Re-run existing tests on any
   compose change.

### 6.2 Recommendations

1. **Operator must run the VPS runbook** (Steps 0-8 in the report) before
   merging. `caddy validate`, `docker network connect`, HTTPS smoke, and
   rate-limit smoke are the gates that take this from "code complete"
   to "Done".
2. **If the operator's Caddy doesn't have the `rate_limit` module**, they
   need to install `github.com/mholt/caddy-ratelimit` or use `xcaddy` to
   build a custom binary. Most distro packages ship with it, but check.
3. **If port 80 isn't reachable from the public internet** (e.g., strict
   VPS firewall), Let's Encrypt's HTTP-01 challenge will fail. The
   alternatives are: (a) open port 80, (b) use the DNS-01 challenge
   (requires a Caddy DNS provider plugin — out of scope for ARCRAG-18).
4. **The default `arcgis-docs.example.com` in `deploy/Caddyfile` and
   `.env.example` is a placeholder.** Operator must override
   `CADDY_DOMAIN` with the real domain — Caddy will happily try to
   issue an LE cert for `arcgis-docs.example.com` and fail (which is the
   safer failure mode than silently serving traffic on the wrong domain).
5. **For ARCRAG-19 (E2E validation)**, include the rate-limit smoke test
   (25 POSTs to `/api/copilotkit` → first ~20 succeed, rest 429) as a
   permanent check. This is the canary for "did the operator wire the
   Caddyfile correctly".
6. **If a future story adds a non-rate-limited API path** (e.g., a
   `/api/health` endpoint that monitoring hits frequently), refactor
   the `@api` matcher to explicitly list the limited paths
   (`@chat path /api/copilotkit*`) instead of matching all `/api/*`.
7. **Document `deploy/` as the deployment-artifacts directory** in a
   future top-level README, so future stories know where to put
   Kubernetes manifests, Terraform, or additional reverse-proxy configs.
