# Plan: ARCRAG-14 — Suggestion Pills for Common Queries

## Summary

Add 4-6 static suggestion pills shown only when the chat is empty, mixing ArcGIS Pro and ArcMap topics. Clicking a pill sends its `message` to the agent as if typed. Pure frontend change (two files: one CREATE, one UPDATE) using CopilotKit's first-class `useCopilotChatSuggestions` hook with the static-config variant. The built-in `<Suggestions>` renderer inside `<CopilotSidebar>` consumes the registered pills; we only feed data, no custom markup needed. No new dependencies, no backend/script changes.

## User Story

As a GIS student
I want to see suggested questions I can click on when I open the chat
So that I know what kinds of things I can ask the agent

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (UX enhancement) |
| Complexity | LOW |
| Systems Affected | frontend only (`frontend/src/components/`, `frontend/src/app/page.tsx`) |
| Jira Issue | ARCRAG-14 |
| Blocked By | ARCRAG-11 ✅ (deps satisfied) |

---

## Patterns to Follow

### Naming — `ChatXxx` component naming

```tsx
// SOURCE: frontend/src/components/ChatImage.tsx:1-3
import React from "react";

export const ChatImage: React.FC<React.ImgHTMLAttributes<HTMLImageElement>> = ({
  src, alt, ...props
}) => {
```

```tsx
// SOURCE: frontend/src/components/ChatLink.tsx:1-3
import React from "react";

export const ChatLink: React.FC<React.AnchorHTMLAttributes<HTMLAnchorElement>> = ({
  href, children, ...props
}) => {
```

Mirror with `ChatSuggestions` — a `"use client"` component that calls a hook and returns `null`.

### Module style — barrel registration for markdown renderers

```tsx
// SOURCE: frontend/src/components/markdownComponents.tsx:1-7
import { ChatImage } from "./ChatImage";
import { ChatLink } from "./ChatLink";

export const markdownComponents = {
  a: ChatLink,
  img: ChatImage,
};
```

**Note**: This barrel pattern is for *rendered* components. `ChatSuggestions` is a *hook-consuming* component (no render output), so it does **not** go in `markdownComponents` — it's mounted directly in `page.tsx`.

### Page composition — `"use client"` at the top

```tsx
// SOURCE: frontend/src/app/page.tsx:1-5
"use client";

import { CopilotSidebar } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";
import { markdownComponents } from "@/components/markdownComponents";
```

Add the new component alongside `markdownComponents` import.

### Type hygiene — do not import from `react-markdown`

```text
// SOURCE: .agents/decisions/arccrag-12-inline-image-rendering.md:57-58
// "Avoid importing types from `react-markdown` directly in this project.
//  The package ships `.ts` sources (not just `.d.ts`) that are incompatible
//  with the project's `jsx: "preserve"` + `strict: true` config."
```

If the `Suggestion` type can't be cleanly imported (its declaration file resolves), rely on inference or define a local type.

### Validation orchestration — `tsc` + `next build` + curl

```text
// SOURCE: .agents/decisions/arccrag-13-source-citations-and-links.md:30-32
// tsc --noEmit returns 0 errors
// next build takes 46-86s; use 600s timeout
// curl localhost:3000 returns HTTP 200 on smoke test
```

### No comments in code

```text
// SOURCE: .agents/decisions/arccrag-13-source-citations-and-links.md:23
// "Per project rule 'DO NOT ADD ANY COMMENTS' and plan acceptance criteria."
```

### Documentation workflow — plan → report → decision log

```text
// SOURCE: .agents/plans/completed/arccrag-13-source-citations-and-links.plan.md (whole file)
.agents/plans/{kebab-name}.plan.md      // this file
.agents/reports/{kebab-name}-report.md  // after implementation
.agents/decisions/{kebab-name}.md       // after implementation
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `frontend/src/components/ChatSuggestions.tsx` | CREATE | `"use client"` component that calls `useCopilotChatSuggestions({ suggestions: [...], available: "before-first-message" })` and returns `null` |
| `frontend/src/app/page.tsx` | UPDATE | Import + mount `<ChatSuggestions />` inside the existing `<CopilotSidebar>` |

No other files change. No `package.json`, `next.config.js`, backend, or script edits.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Create `ChatSuggestions` component

- **File**: `frontend/src/components/ChatSuggestions.tsx`
- **Action**: CREATE
- **Implement**:
  - `"use client"` directive at line 1
  - Import `useCopilotChatSuggestions` from `@copilotkit/react-core`
  - Module-level `const SUGGESTIONS = [{ title, message }, ...] x 6` (per `stories.md:409`):
    1. "How do I create a buffer in ArcGIS Pro?"
    2. "What is a geodatabase?"
    3. "How to export a map to PDF?"
    4. "How do I georeference in ArcMap?"
    5. "What's the difference between Clip and Intersect?"
    6. "How to use ArcPy for batch processing?"
  - `export const ChatSuggestions: React.FC = () => { useCopilotChatSuggestions({ suggestions: SUGGESTIONS, available: "before-first-message" }); return null; };`
- **Mirror**: `frontend/src/components/ChatImage.tsx:1-3` for component shape; `page.tsx:1-5` for `"use client"` directive
- **Avoid**: Do **not** `import type { Components } from "react-markdown"`; do **not** import `Suggestion` from `@copilotkit/core` if its declaration files fail to resolve — rely on TypeScript inference (the `SUGGESTIONS` const will be inferred as `Omit<Suggestion, "isLoading">[]` from the hook's parameter type)
- **Validate**: `cd frontend && ./node_modules/.bin/tsc --noEmit` returns 0

### Task 2: Mount `<ChatSuggestions />` in `page.tsx`

- **File**: `frontend/src/app/page.tsx`
- **Action**: UPDATE
- **Implement**:
  - Add `import { ChatSuggestions } from "@/components/ChatSuggestions";` next to the `markdownComponents` import (line 5)
  - Add `<ChatSuggestions />` as a child of `<CopilotSidebar>` (placement is cosmetic since it returns `null`; placing it before `<main>` is conventional)
- **Mirror**: `frontend/src/app/page.tsx:5` for import pattern; `frontend/src/app/page.tsx:9-31` for `<CopilotSidebar>` child structure
- **Validate**: `cd frontend && ./node_modules/.bin/tsc --noEmit` returns 0

### Task 3: Build the frontend

- **Action**: VALIDATE
- **Implement**: `cd frontend && timeout 600 ./node_modules/.bin/next build`
- **Validate**: Build exits with code 0; emits "Compiled successfully" or equivalent. No SSR errors (component is already inside the `"use client"` boundary in `page.tsx`). No type errors.

### Task 4: Smoke test the running app

- **Action**: VALIDATE
- **Implement**:
  - `cd frontend && ./node_modules/.bin/next start -p 3000 &`
  - `sleep 2 && curl -sI http://localhost:3000` → expect `HTTP/1.1 200`
  - Kill background process
- **Validate**: HTTP 200 on `GET /`. (Pill rendering is verified manually in browser since the static landing page does not include the chat's message history; follow-up: a scripted AG-UI chat would assert on the SSE stream for `useCopilotChatSuggestions`-driven pill registration.)

---

## Validation Block

```bash
cd frontend

./node_modules/.bin/tsc --noEmit        # type check (from frontend/)

timeout 600 ./node_modules/.bin/next build    # build + (deprecated) lint pass

./node_modules/.bin/next start -p 3000 &
sleep 2
curl -sI http://localhost:3000          # expect HTTP/1.1 200
pkill -f "next start"
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `Suggestion` type re-export from `@copilotkit/react-core` may hit ARCRAG-12's `.ts` source-resolution issue | Verified at `frontend/node_modules/@copilotkit/core/dist/index.d.cts:45-50` — `Suggestion` is declared in `.d.cts` (declarations only, no `.ts` source). If a type error still appears, drop the annotation and let inference handle it (the `SUGGESTIONS` const's type will be inferred from the hook's parameter type, which is the canonical pattern for this codebase). |
| `useCopilotChatSuggestions` requires Client Component context | Add `"use client"` directive to `ChatSuggestions.tsx` (per-file in App Router; does not inherit from `page.tsx`'s directive) |
| Pills leak through after the first message | `available: "before-first-message"` is documented at `node_modules/@copilotkit/core/dist/index.d.cts:88`; verified semantics: pills hide after first message |
| Pills collide visually with the welcome text in `<CopilotSidebar>` | Built-in `<Suggestions>` component (consumed at `node_modules/@copilotkit/react-ui/dist/index.d.cts:815-820`) renders below the initial message — no layout collision with the `<main>` hero on `page.tsx` |
| Click handler not firing | The `onSuggestionClick(message)` callback is provided internally by CopilotKit's `<Suggestions>` component (`index.d.cts:283`); we only register the data, not the handler |
| `next lint` interactive deprecation prompt (ARCRAG-13 lesson) | Do not run `next lint` separately; `next build` includes the lint/type-check pass and is the source of truth |
| Build timeout (ARCRAG-12/13 lesson) | Use 600s timeout (measured 46-86s, default 180s is too short) |

---

## Acceptance Criteria

- [ ] `frontend/src/components/ChatSuggestions.tsx` exists, is a Client Component (`"use client"` at line 1), exports `ChatSuggestions`
- [ ] `useCopilotChatSuggestions` is called with 6 static suggestions and `available: "before-first-message"`
- [ ] Suggestions cover a mix of ArcGIS Pro and ArcMap topics (5 Pro/tooling + 1 ArcMap)
- [ ] `page.tsx` mounts `<ChatSuggestions />` inside `<CopilotSidebar>` (placement before/after `<main>` is cosmetic)
- [ ] `tsc --noEmit` reports zero errors
- [ ] `next build` exits 0
- [ ] `GET /` returns HTTP 200
- [ ] Manual UI smoke: empty chat shows pills; clicking a pill sends its `message` to the agent; pills disappear after the first message
- [ ] No backend, script, `package.json`, `next.config.js`, or other config changes
- [ ] No comments in code
- [ ] No new dependencies installed

---

## Follow-up Documentation (post-implementation)

- `.agents/reports/arccrag-14-suggestion-pills-report.md` — fill in build/runtime/test results
- `.agents/decisions/arccrag-14-suggestion-pills.md` — capture any deviations from this plan + lessons learned
- Update `.agents/stories/stories.md` summary table: ARCRAG-14 moves from pending to completed
