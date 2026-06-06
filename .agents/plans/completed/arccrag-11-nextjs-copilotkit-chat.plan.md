# Plan: Next.js App with CopilotKit Chat UI

## Summary

Create the Next.js 15 frontend (greenfield — only `frontend/package.json` exists today) with a CopilotKit chat UI that proxies to the existing FastAPI AG-UI endpoint. The frontend has three layers: a Tailwind-styled `app/layout.tsx` wrapping `<CopilotKit runtimeUrl="/api/copilotkit">`, an `app/page.tsx` with `<CopilotSidebar>` plus a brief welcome panel, and an `app/api/copilotkit/route.ts` Next.js route handler that mounts a `CopilotRuntime` whose only agent is an `HttpAgent` pointing at the FastAPI `/ag-ui` endpoint. The story explicitly mandates the API-route proxy pattern (matches PRD §6 and §10), which the existing backend `backend/src/main.py:42-44` is already wired to accept.

## User Story

As a GIS student
I want a clean chat interface where I can type GIS questions and see streamed answers
So that I can get help without navigating complex documentation

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | Frontend (Next.js), Backend integration (existing AG-UI endpoint) |
| Jira Issue | ARCRAG-11 |

---

## Patterns to Follow

### Backend contract this story must respect

```python
# SOURCE: backend/src/main.py:17,42-44
FRONTEND_ORIGIN = os.getenv("NEXT_PUBLIC_BACKEND_URL", "http://localhost:3000")
...
@app.post("/ag-ui")
async def ag_ui_endpoint(request: Request) -> Response:
    return await AGUIAdapter.dispatch_request(request, agent=agent)
```

- The AG-UI server already lives at `<NEXT_PUBLIC_BACKEND_URL>/ag-ui` and accepts CORS from the frontend origin — the frontend must hit this URL through the runtime proxy.
- CORS is restricted (not `*`) — the runtime route runs server-side and is the only thing talking to FastAPI, so this works without relaxing CORS.

### Test-script shape (used for any smoke checks)

```python
# SOURCE: backend/test_agent_flow.py:7-19
from dotenv import load_dotenv
load_dotenv()
def _skip_no_key():
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key or key == "dummy":
        print("SKIP - OPENROUTER_API_KEY missing or 'dummy'")
        return True
    return False
```

Use the same conditional-skip idiom for any frontend smoke test that needs backend up.

### Project conventions

- `pyproject.toml` style: dependency lists with caret ranges (`^1.8.0`) — keep this in `package.json` (already done).
- PRD §6 mandates `<CopilotSidebar>` for a persistent chat panel — use that, not `CopilotPopup`.
- Title/branding from story: "ArcGIS Documentation Guide".
- No code comments (per global convention).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `frontend/package.json` | UPDATE | Add `@copilotkit/runtime` dep (not currently installed — see Risks) |
| `frontend/tsconfig.json` | CREATE | TypeScript config for Next.js 15 / React 19 |
| `frontend/next.config.js` | CREATE | Next.js config (no special options needed; optionally allow remote images later for ARCRAG-12) |
| `frontend/postcss.config.mjs` | CREATE | PostCSS config required by Tailwind v4 |
| `frontend/next-env.d.ts` | CREATE | Next.js auto-generated types reference (created by `next build` but commit it) |
| `frontend/src/app/globals.css` | CREATE | Tailwind v4 entry: `@import "tailwindcss";` |
| `frontend/src/app/layout.tsx` | CREATE | Root layout: `<html><body><CopilotKit runtimeUrl="/api/copilotkit">{children}</CopilotKit></body></html>` |
| `frontend/src/app/page.tsx` | CREATE | Home page with welcome panel + `<CopilotSidebar>` |
| `frontend/src/app/api/copilotkit/route.ts` | CREATE | API route: `CopilotRuntime` + `HttpAgent` → `NEXT_PUBLIC_BACKEND_URL/ag-ui` |
| `frontend/.env.local` | CREATE (not committed) | `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000` for local dev |
| `.env.example` | UPDATE | Add `NEXT_PUBLIC_BACKEND_URL` (already present — verify) and any new `COPILOTKIT_*` keys |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Add the missing runtime dependency

- **File**: `frontend/package.json`
- **Action**: UPDATE
- **Implement**: Add `"@copilotkit/runtime": "^1.8.0"` to `dependencies`. (Currently only `react-core` and `react-ui` are installed — see Risks for why the runtime package is required.)
- **Validate**: `cd frontend && npm install` succeeds; `ls node_modules/@copilotkit/runtime/package.json` exists; version is `1.59.0` (the lockfile resolves `^1.8.0` to this).

### Task 2: TypeScript + Next.js config files

- **File**: `frontend/tsconfig.json`
- **Action**: CREATE
- **Implement**: Standard Next.js 15 tsconfig (matches the `@types/*` versions already in `devDependencies`):
  ```json
  {
    "compilerOptions": {
      "target": "ES2022",
      "lib": ["dom", "dom.iterable", "esnext"],
      "allowJs": false,
      "skipLibCheck": true,
      "strict": true,
      "noEmit": true,
      "esModuleInterop": true,
      "module": "esnext",
      "moduleResolution": "bundler",
      "resolveJsonModule": true,
      "isolatedModules": true,
      "jsx": "preserve",
      "incremental": true,
      "plugins": [{ "name": "next" }],
      "paths": { "@/*": ["./src/*"] }
    },
    "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
    "exclude": ["node_modules"]
  }
  ```
- **File**: `frontend/next.config.js`
- **Action**: CREATE
- **Implement**:
  ```js
  /** @type {import('next').NextConfig} */
  const nextConfig = {
    reactStrictMode: true,
  };
  module.exports = nextConfig;
  ```
- **File**: `frontend/postcss.config.mjs`
- **Action**: CREATE
- **Implement** (Tailwind v4 uses a PostCSS plugin, not a config file):
  ```js
  export default {
    plugins: { "@tailwindcss/postcss": {} },
  };
  ```
- **Mirror**: `frontend/package.json:19-20` (already declares `tailwindcss ^4.0.0` + `@tailwindcss/postcss ^4.0.0`)
- **Validate**: `cd frontend && npx tsc --noEmit` passes (zero errors).

### Task 3: Tailwind global stylesheet

- **File**: `frontend/src/app/globals.css`
- **Action**: CREATE
- **Implement**:
  ```css
  @import "tailwindcss";
  ```
- **Mirror**: `frontend/package.json:19-20`
- **Validate**: File exists; `cd frontend && npm run build` succeeds without "could not find tailwindcss" warnings.

### Task 4: API route — Copilot Runtime proxy

- **File**: `frontend/src/app/api/copilotkit/route.ts`
- **Action**: CREATE
- **Implement**: Matches the v1.x pattern (story notes line 330 call out `copilotRuntimeNextJSAppRouterEndpoint`):
  ```ts
  import { NextRequest } from "next/server";
  import {
    CopilotRuntime,
    EmptyAdapter,
    copilotRuntimeNextJSAppRouterEndpoint,
  } from "@copilotkit/runtime";
  import { HttpAgent } from "@ag-ui/client";

  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

  const serviceAdapter = new EmptyAdapter();

  const runtime = new CopilotRuntime({
    agents: {
      default: new HttpAgent({ url: `${backendUrl}/ag-ui` }),
    },
  });

  export const POST = async (req: NextRequest) => {
    const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
      runtime,
      serviceAdapter,
      endpoint: "/api/copilotkit",
    });
    return handleRequest(req);
  };
  ```
- **Mirror**: PRD §6 directory structure (line 160) lists `frontend/src/app/api/copilotkit/route.ts`; PRD §10 line 365 names the endpoint `POST /api/copilotkit`.
- **Risk note**: `EmptyAdapter` is the v1.8.x name; v2 (1.59.0) renamed it to `ExperimentalEmptyAdapter`. Implementation should probe the actual export on install — see Risks #1.
- **Validate**: `cd frontend && npx tsc --noEmit` passes for this file; `npm run build` compiles the route.

### Task 5: Root layout

- **File**: `frontend/src/app/layout.tsx`
- **Action**: CREATE
- **Implement**:
  ```tsx
  import type { ReactNode } from "react";
  import { CopilotKit } from "@copilotkit/react-core";
  import "./globals.css";

  export const metadata = {
    title: "ArcGIS Documentation Guide",
    description: "AI-powered chat for ArcGIS Pro and ArcMap documentation",
  };

  export default function RootLayout({ children }: { children: ReactNode }) {
    return (
      <html lang="en">
        <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
          <CopilotKit runtimeUrl="/api/copilotkit">
            {children}
          </CopilotKit>
        </body>
      </html>
    );
  }
  ```
- **Mirror**: PRD §7 frontend feature (line 226) and story (line 330) — title "ArcGIS Documentation Guide".
- **Validate**: `npm run build` succeeds; `npm run dev` shows a clean styled page in browser.

### Task 6: Home page

- **File**: `frontend/src/app/page.tsx`
- **Action**: CREATE
- **Implement**:
  ```tsx
  import { CopilotSidebar } from "@copilotkit/react-ui";
  import "@copilotkit/react-ui/styles.css";

  export default function HomePage() {
    return (
      <CopilotSidebar
        defaultOpen
        labels={{
          title: "ArcGIS Documentation Guide",
          initial: "Hi! Ask me anything about ArcGIS Pro or ArcMap.",
        }}
      >
        <main className="mx-auto max-w-3xl px-6 py-16">
          <h1 className="text-3xl font-semibold tracking-tight">
            ArcGIS Documentation Guide
          </h1>
          <p className="mt-4 text-slate-600">
            Ask questions about ArcGIS Pro or ArcMap and get answers pulled
            directly from Esri's official documentation, with inline screenshots
            and source citations.
          </p>
          <p className="mt-2 text-sm text-slate-500">
            Use the chat panel on the right to get started.
          </p>
        </main>
      </CopilotSidebar>
    );
  }
  ```
- **Mirror**: PRD §6 (`<CopilotSidebar>`), story line 330.
- **Validate**: `npm run dev` → `http://localhost:3000` shows the welcome panel + sidebar; typing a question streams a response (requires backend + Qdrant up + `OPENROUTER_API_KEY`).

### Task 7: Local environment file

- **File**: `frontend/.env.local`
- **Action**: CREATE
- **Implement**: `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000`
- **Note**: This file is gitignored by Next.js convention (`.env*.local` matches the existing `.gitignore` Next.js defaults at line 10-12). `.env.example` already documents the variable (line 17-18).
- **Validate**: `cat frontend/.env.local` shows the URL.

### Task 8: Verify `.env.example` and `.gitignore`

- **File**: `.env.example`, `.gitignore`
- **Action**: VERIFY (no edit needed unless missing)
- **Implement**: Confirm `.env.example` contains `NEXT_PUBLIC_BACKEND_URL` (line 17-18, present) and `.gitignore` excludes `frontend/.env*.local` (lines 10-12 cover `.next/` and `out/` but not `.env*.local` — add it: append `frontend/.env*.local` if missing).
- **Validate**: `grep NEXT_PUBLIC_BACKEND_URL .env.example` returns 1+ hits; `grep -E '\.env\*\.local' .gitignore` returns 1+ hits (add the line if absent).

### Task 9: Build + smoke test

- **Action**: VALIDATE
- **Steps**:
  1. `cd frontend && npm install` — deps resolve.
  2. `cd frontend && npm run build` — Next.js build passes (typecheck + bundle).
  3. `cd frontend && npm run dev` — `http://localhost:3000` returns 200.
  4. `cd backend && ./../.venv/bin/python -m src.main` (backend up) — `curl http://localhost:8000/health` returns `{"status": "ok", ...}`.
  5. In browser: type "How do I create a buffer in ArcGIS Pro?" — response streams in with a markdown image and `**Source:**` citation (full E2E requires Qdrant with data; see Risks #2).

---

## Validation

```bash
# 1. Install frontend deps
cd frontend && npm install

# 2. Type-check (no emit)
cd frontend && npx tsc --noEmit

# 3. Lint
cd frontend && npm run lint

# 4. Build (typecheck + bundle)
cd frontend && npm run build

# 5. Run dev server (in one terminal)
cd frontend && npm run dev

# 6. Verify backend is reachable from the frontend runtime route
curl -X POST http://localhost:3000/api/copilotkit \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"messages":[{"role":"user","content":"Hello"}]}' \
  --max-time 30 | head -20
```

---

## Acceptance Criteria

- [ ] `frontend/src/app/layout.tsx` wraps children in `<CopilotKit runtimeUrl="/api/copilotkit">`
- [ ] `frontend/src/app/page.tsx` renders `<CopilotSidebar>` with title "ArcGIS Documentation Guide"
- [ ] `frontend/src/app/api/copilotkit/route.ts` mounts a `CopilotRuntime` whose `default` agent is an `HttpAgent` pointing at `${NEXT_PUBLIC_BACKEND_URL}/ag-ui`
- [ ] `frontend/package.json` lists `@copilotkit/runtime` in dependencies
- [ ] `npm run build` passes with zero TypeScript errors
- [ ] `npm run dev` serves `http://localhost:3000` with a styled welcome panel and chat sidebar
- [ ] The chat sidebar streams responses token-by-token when the backend, Qdrant, and a valid `OPENROUTER_API_KEY` are available
- [ ] CORS works (no CORS errors in browser console) because the API route is server-side and calls the backend directly
- [ ] `.env.example` documents `NEXT_PUBLIC_BACKEND_URL`; `frontend/.env.local` is gitignored
- [ ] No code comments in any new file (project convention)

---

## Risks

| Risk | Mitigation |
|------|-----------|
| **`EmptyAdapter` vs `ExperimentalEmptyAdapter` API drift** — v1.8.x docs use `EmptyAdapter`; v2 (1.59.0) uses `ExperimentalEmptyAdapter`. Lockfile already resolved to 1.59.0, so the actual import on install may be `ExperimentalEmptyAdapter`. | During Task 4, after `npm install`, run `node -e "const m = require('@copilotkit/runtime'); console.log(Object.keys(m))"` to confirm the actual export name. Use the v1 name if present, v2 name otherwise. Update the file accordingly. |
| **No real backend data to test E2E** — Qdrant may be empty, `OPENROUTER_API_KEY` is `dummy` in this env, `data/arcpro_index.json` is only 72 KB (partial). | `npm run build` and the sidebar render don't require backend data. For the chat E2E, defer to a follow-up env with real keys + loaded Qdrant (covered by ARCRAG-15/16/19). |
| **Tailwind v4 PostCSS plugin mismatch** — `tailwindcss@4` uses `@tailwindcss/postcss`, not the v3 setup with `tailwind.config.js`. | The `package.json` already pins both `tailwindcss@^4.0.0` and `@tailwindcss/postcss@^4.0.0`; the `postcss.config.mjs` and `globals.css` patterns above match the v4 PostCSS workflow. Do not create a `tailwind.config.js` for this story. |
| **CORS regression** — if `NEXT_PUBLIC_BACKEND_URL` is set to the wrong port, the runtime will 502/fetch-error. | Default to `http://localhost:8000` (matches `BACKEND_PORT` in `.env.example`). Add a console warning in the route file when the env var is missing. |
| **`HttpAgent` import path** — installed via `@ag-ui/client@0.0.53` (dep of `@copilotkit/core`), but the v1.8.x pattern imports from `@copilotkit/runtime`'s re-export. | Import from `@copilotkit/runtime` first; fall back to `@ag-ui/client` if the runtime package re-export is missing. Verify with the runtime's type file during Task 4. |
| **Image rendering not in scope** — story is "chat UI", not "inline images". The agent's markdown image output will pass through, but `<img>` won't get the custom styling from ARCRAG-12. | That's correct — ARCRAG-12 is a separate story. The default CopilotKit markdown renderer will still display images; just without the styled wrapper. |

---

## Open Questions

Resolved with the user before writing the plan:

- **Adapter API name** — Confirmed: probe `@copilotkit/runtime` exports at install time and use whichever is present (`EmptyAdapter` from v1.8.x or `ExperimentalEmptyAdapter` from 1.59.0).
- **Build verification scope** — Confirmed: write files only; user runs `npm install` + `npm run build` themselves to validate.
