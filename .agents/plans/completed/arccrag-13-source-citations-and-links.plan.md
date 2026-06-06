# Plan: ARCRAG-13 — Source Citations & Links

## Summary

Override the markdown `a` (anchor) renderer used by `<CopilotSidebar>` so that every link in agent responses — including the required `**Source:** [Page Title](url)` citation at the end of every answer — opens in a new browser tab via `target="_blank" rel="noopener noreferrer"`. This is a frontend-only change that mirrors the ARCRAG-12 image-renderer pattern (`ChatImage` component + entry in `markdownComponents`). The agent's system prompt in `backend/src/agent.py:28` already instructs the model to include `**Source:** [Page Title](url)`, so no backend changes are required.

## User Story

As a student
I want every link in the agent's answer — especially the source citation — to open the original Esri documentation page in a new tab
So that I can read more context without losing my chat scroll position

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (frontend renderer override) |
| Complexity | LOW |
| Systems Affected | Frontend only (`frontend/src/components/`, `frontend/src/app/page.tsx` is untouched) |
| Jira Issue | ARCRAG-13 |

---

## Patterns to Follow

### Naming — Chat-prefixed component files mirroring `ChatImage`

```
// SOURCE: frontend/src/components/ChatImage.tsx:1-3
import React from "react";

export const ChatImage: React.FC<React.ImgHTMLAttributes<HTMLImageElement>> = ({
  src,
  alt,
  ...props
}) => {
```

Mirror this for `ChatLink` using `React.AnchorHTMLAttributes<HTMLAnchorElement>` and a `<a>` element.

### Component registration — barrel map of markdown tag renderers

```
// SOURCE: frontend/src/components/markdownComponents.tsx:1-5
import { ChatImage } from "./ChatImage";

export const markdownComponents = {
  img: ChatImage,
};
```

Add an `a: ChatLink` entry alongside the existing `img: ChatImage` entry.

### Security pattern — `target="_blank"` always paired with `rel="noopener noreferrer"`

```
// SOURCE: frontend/src/components/ChatImage.tsx:23
<a href={src} target="_blank" rel="noopener noreferrer">
```

Reuse the same `rel` attributes for `ChatLink` (prevents tab-nabbing and leaks of `window.opener`).

### Props spreading — preserve upstream handler attributes

```
// SOURCE: frontend/src/components/ChatImage.tsx:17
{...props}
```

Spread `...props` on the underlying `<a>` so any handlers CopilotKit injects (e.g. `onClick`) are not stripped.

### Test orchestration — no test framework configured; rely on tsc + next build

```
// SOURCE: .agents/decisions/arccrag-12-inline-image-rendering.md:38-39
// Build timeout: next build takes 46-86s; use 600s timeout
// Smoke test: curl localhost:3000 returns 200
```

Validation is via TypeScript (`./node_modules/.bin/tsc --noEmit`) and production build (`./node_modules/.bin/next build`), plus a curl smoke test.

### Agent prompt — already mandates source citation; no backend change needed

```
// SOURCE: backend/src/agent.py:27-29
"Always include relevant images from the fetched page using markdown ![alt](url) syntax. "
"Always end responses with a source citation: **Source:** [Page Title](url). "
"If you are unsure about something, say so rather than guessing."
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `frontend/src/components/ChatLink.tsx` | CREATE | Markdown `a` override: wraps `<a>` with `target="_blank" rel="noopener noreferrer"` |
| `frontend/src/components/markdownComponents.tsx` | UPDATE | Register `ChatLink` as the `a` renderer alongside the existing `img` override |

No other files (backend, scripts, config) need to change.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Create `ChatLink` component

- **File**: `frontend/src/components/ChatLink.tsx`
- **Action**: CREATE
- **Implement**: Export a `ChatLink` functional component typed as `React.FC<React.AnchorHTMLAttributes<HTMLAnchorElement>>`. Destructure `href`, `children`, and `...props` (preserve any upstream handlers like `onClick`). Render `<a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>`. Add a small Tailwind class for affordance (e.g. `className="text-sky-700 underline hover:text-sky-900"`) — keep conservative; Tailwind v4 is already loaded via `globals.css` and works inside Client Components.
- **Mirror**: `frontend/src/components/ChatImage.tsx:3-35` — same import-free default-export pattern, same `React.FC<T>` typing, same `{...props}` spread at the end of the element.
- **Avoid**: Do not import `import type { Components } from "react-markdown"` (ARCRAG-12 lesson — `react-markdown` ships `.ts` source files that fail type resolution under `jsx: "preserve"`). Rely on type inference.
- **Validate**: `./node_modules/.bin/tsc --noEmit` returns zero errors (run from `frontend/`).

### Task 2: Register `ChatLink` in `markdownComponents`

- **File**: `frontend/src/components/markdownComponents.tsx`
- **Action**: UPDATE
- **Implement**: Add `import { ChatLink } from "./ChatLink";` and a `a: ChatLink,` entry in the `markdownComponents` object. Keep the existing `img: ChatImage,` entry unchanged.
- **Mirror**: `frontend/src/components/markdownComponents.tsx:1-5` — same barrel-map structure, same relative import path.
- **Validate**: `./node_modules/.bin/tsc --noEmit` returns zero errors (run from `frontend/`).

### Task 3: Build the frontend to verify compilation

- **File**: N/A (build step)
- **Action**: VALIDATE
- **Implement**: Run `./node_modules/.bin/next build` from `frontend/` with a 600s timeout (per ARCRAG-12 lesson: `next build` takes 46-86s, default 180s is too short).
- **Validate**: Build exits with code 0 and emits "Compiled successfully" or similar success line. No type errors, no SSR errors about Server-to-Client Component prop passing (the override is already inside a `"use client"` file via `page.tsx`, so no extra directive is needed).

### Task 4: Smoke test the running app

- **File**: N/A (smoke test)
- **Action**: VALIDATE
- **Implement**: Start `next start` (or `next dev`) in the background, then `curl -sI http://localhost:3000` and confirm HTTP 200. Optionally, run a scripted chat through the AG-UI endpoint and grep the SSE stream for a markdown link to confirm the renderer will receive an `<a>` element.
- **Validate**: HTTP 200 on `GET /`. (Manual UI verification of `target="_blank"` is a follow-up, not in this story's automated scope.)

---

## Validation

```bash
# Type check (from frontend/, with --ignore-scripts npm if WSL)
cd frontend
./node_modules/.bin/tsc --noEmit

# Build
timeout 600 ./node_modules/.bin/next build

# Smoke test
./node_modules/.bin/next start &
sleep 2
curl -sI http://localhost:3000   # expect HTTP/1.1 200
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `react-markdown` `.ts` source files break type resolution under `jsx: "preserve"` (ARCRAG-12 lesson) | Do not import `import type { Components } from "react-markdown"`. Use `React.FC<React.AnchorHTMLAttributes<HTMLAnchorElement>>` (a React-provided type) and let inference handle the bridge to CopilotKit's `ComponentsMap`. |
| `target="_blank"` without `rel` is a tab-nabbing vector | Always pair with `rel="noopener noreferrer"` (same as `ChatImage`). |
| Internal anchor links (`#section`) opening in a new tab is awkward but harmless | Acceptable — CopilotKit does not emit internal anchors today, and even if it did, the new tab will just scroll to the anchor. |
| `CopilotSidebar` not allowed to receive function refs from Server Components (ARCRAG-12 lesson) | `page.tsx` already has `"use client"`; no change needed. `markdownComponents` is consumed inside the same Client boundary. |
| `next build` default 180s timeout insufficient | Use 600s timeout (per ARCRAG-12 measured 46-86s build time). |
| WSL/Windows npm `cmd.exe` postinstall failure (ARCRAG-11 lesson) | Pre-existing; no new install required (no new deps). If reinstall is ever needed, use `npm install --ignore-scripts` + force-install `@next/swc-linux-x64-gnu`. |

---

## Acceptance Criteria

- [ ] `frontend/src/components/ChatLink.tsx` exists, exports a `ChatLink` functional component
- [ ] `ChatLink` renders `<a>` with `target="_blank"` and `rel="noopener noreferrer"`
- [ ] `ChatLink` spreads `{...props}` to preserve upstream `onClick`/handlers
- [ ] `frontend/src/components/markdownComponents.tsx` registers both `img: ChatImage` and `a: ChatLink`
- [ ] `tsc --noEmit` reports zero errors
- [ ] `next build` exits 0
- [ ] `GET /` returns HTTP 200
- [ ] No backend, script, or `package.json` changes
- [ ] No comments added to code
- [ ] No new dependencies installed
