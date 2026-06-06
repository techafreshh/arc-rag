# Implementation Report

**Plan**: `.agents/plans/arccrag-13-source-citations-and-links.plan.md`
**Branch**: `feature/arccrag-13-source-citations-and-links`
**Status**: COMPLETE

## Summary

Overrode the markdown `a` (anchor) renderer used by `<CopilotSidebar>` so every link in agent responses — including the required `**Source:** [Page Title](url)` citation — opens in a new browser tab with `target="_blank" rel="noopener noreferrer"`. Mirrors the ARCRAG-12 image-renderer pattern (`ChatImage` + `markdownComponents` barrel). No backend changes needed; `backend/src/agent.py` already instructs the model to emit the citation.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create `ChatLink` component (typed `React.FC<React.AnchorHTMLAttributes<HTMLAnchorElement>>`, renders `<a target="_blank" rel="noopener noreferrer">` with `{...props}` spread) | `frontend/src/components/ChatLink.tsx` | ✅ |
| 2 | Register `ChatLink` as the `a` renderer in the `markdownComponents` barrel | `frontend/src/components/markdownComponents.tsx` | ✅ |
| 3 | Build the frontend to verify compilation (`tsc --noEmit` + `next build`) | N/A | ✅ |
| 4 | Smoke test the running app (`next start` + `curl -sI localhost:3001` returns 200) | N/A | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Type check (`tsc --noEmit`) | ✅ (0 errors) |
| Build (`next build`, 600s timeout) | ✅ (compiled in 65s, 5/5 static pages) |
| Smoke test (`curl -sI http://localhost:3001`) | ✅ HTTP/1.1 200 OK |
| Lint (`next lint`) | ⚠️ `next lint` deprecated in Next.js 15.5; not run. `next build` includes linting step (`Linting and checking validity of types ...`) which passed. |
| Tests | N/A — no test framework configured (per ARCRAG-12 lesson: relies on `tsc` + `next build`) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `frontend/src/components/ChatLink.tsx` | CREATE | +19 |
| `frontend/src/components/markdownComponents.tsx` | UPDATE | +2/-0 |

Net diff:

```
frontend/src/components/markdownComponents.tsx | 2 ++
 1 file changed, 2 insertions(+)
```

`ChatLink.tsx` is new (19 lines, matches the plan's `ChatImage` import-free, default-export pattern with `React.FC<T>` typing and `{...props}` spread).

## Deviations from Plan

**None.** The plan was followed exactly:

- ✅ `ChatLink` uses `React.AnchorHTMLAttributes<HTMLAnchorElement>` (no `import type { Components } from "react-markdown"` — per ARCRAG-12 lesson, that triggers `Cannot find namespace 'JSX'` errors).
- ✅ Tailwind class is conservative (`text-sky-700 underline hover:text-sky-900`); Tailwind v4 is loaded via `globals.css`.
- ✅ `markdownComponents.tsx` barrel registers `a: ChatLink` alongside existing `img: ChatImage`; no explicit type annotation (inference is structurally compatible with `ComponentsMap`).
- ✅ `page.tsx` already has `"use client"` (set in ARCRAG-12), so no directive was needed.
- ✅ `{...props}` spread is on the `<a>` (after `target`/`rel`/`className`) so upstream handlers (e.g. CopilotKit's `onClick`) are preserved.
- ✅ No backend, script, `package.json`, or `tsconfig.json` changes.
- ✅ No new dependencies.
- ✅ No comments added to code (per "DO NOT ADD ANY COMMENTS" rule and plan acceptance criteria).

## Acceptance Criteria

- [x] `frontend/src/components/ChatLink.tsx` exists, exports a `ChatLink` functional component
- [x] `ChatLink` renders `<a>` with `target="_blank"` and `rel="noopener noreferrer"`
- [x] `ChatLink` spreads `{...props}` to preserve upstream `onClick`/handlers
- [x] `frontend/src/components/markdownComponents.tsx` registers both `img: ChatImage` and `a: ChatLink`
- [x] `tsc --noEmit` reports zero errors
- [x] `next build` exits 0
- [x] `GET /` returns HTTP 200
- [x] No backend, script, or `package.json` changes
- [x] No comments added to code
- [x] No new dependencies installed

## Tests Written

None. No test framework is configured in the project (per the ARCRAG-12 decision: validation is `tsc --noEmit` + `next build` + curl smoke test). The plan's `Risks & Mitigations` table explicitly cites the ARCRAG-12 lesson that this project relies on `tsc` + `next build` rather than a unit test framework.

## E2E Verification

Per the plan, the only automated E2E step is the smoke test:

- [x] `next start` starts cleanly on port 3001
- [x] `curl -sI http://localhost:3001` → `HTTP/1.1 200 OK`, `Content-Length: 13238`
- [x] HTML serves successfully (`x-nextjs-prerender: 1` confirms static prerender)
- [x] Manual UI verification of `target="_blank"` is noted as a follow-up not in this story's automated scope

## Notes for Reviewers

- The ChatLink renderer activates only when an agent message contains a markdown link (e.g. the `**Source:** [Page Title](url)` citation at end of every answer). The static landing page (`/`) shows only the welcome text, so `target="_blank"` will not appear in the initial HTML payload. To verify end-to-end: ask the agent a question in the running app and inspect any link it returns.
- `ChatLink` uses Tailwind utility classes for visual affordance (sky-blue underline, darkens on hover). Adjust to taste; the security attributes (`target`, `rel`) are non-negotiable.
- ARCRAG-12's lessons were applied: no `react-markdown` type imports, no explicit type annotation on `markdownComponents` (inference handles bridging to CopilotKit's `ComponentsMap`), no `"use client"` change needed (already in `page.tsx`).
