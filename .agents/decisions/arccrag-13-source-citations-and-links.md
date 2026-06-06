# Decision Log & Implementation Postmortem: arccrag-13-source-citations-and-links

- **Date**: 2026-06-06
- **Branch**: `feature/arccrag-13-source-citations-and-links`
- **Report Path**: `.agents/reports/arccrag-13-source-citations-and-links-report.md`

## 1. Summary of Implementation

Overrode the markdown `a` (anchor) renderer used by `<CopilotSidebar>` so every link in agent responses — including the required `**Source:** [Page Title](url)` citation — opens in a new browser tab with `target="_blank" rel="noopener noreferrer"`. Mirrors the ARCRAG-12 image-renderer pattern (`ChatImage` + `markdownComponents` barrel). Two files touched: new `ChatLink.tsx` (19 lines) and a 2-line update to `markdownComponents.tsx`. No backend, script, config, or `package.json` changes. The agent's system prompt in `backend/src/agent.py:28` already mandates the citation, so no backend change was needed.

## 2. Key Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Type `ChatLink` as `React.FC<React.AnchorHTMLAttributes<HTMLAnchorElement>>` | `AnchorHTMLAttributes` is a React-provided type, structurally compatible with CopilotKit's `ComponentsMap` expected by `markdownTagRenderers`. Avoids the `react-markdown` `.ts` source-file type-resolution failure documented in the ARCRAG-12 postmortem. |
| Pair `target="_blank"` with `rel="noopener noreferrer"` | Prevents tab-nabbing and `window.opener` leaks. Same security pattern as `ChatImage.tsx:23`. |
| Spread `{...props}` on the `<a>` element | Preserves any handlers CopilotKit injects (e.g. `onClick`). Placed after `target`/`rel`/`className` so those overrides win over upstream `props` if any conflict arises. |
| Use Tailwind classes `text-sky-700 underline hover:text-sky-900` | Conservative visual affordance — links are visibly clickable and darken on hover. Tailwind v4 is already loaded via `globals.css` `@import "tailwindcss"`. |
| No explicit type annotation on `markdownComponents` | TypeScript inference produces a structurally compatible type (`{ a, img }`), which bridges cleanly to `ComponentsMap`. Mirrors the ARCRAG-12 lesson: explicit typing causes type-resolution failures with `react-markdown`'s `complex-types.ts`. |
| Add `a: ChatLink` above `img: ChatImage` in the barrel | Alphabetical/readability order; both keys are equally important. |
| No `"use client"` directive added | `page.tsx` already declares `"use client"` (from ARCRAG-12), so `markdownComponents` (and its function references) already live inside the Client boundary. No SSR boundary crossing. |
| No new dependencies | All required types come from React; Tailwind classes work without imports in v4. |
| No comments in code | Per project rule "DO NOT ADD ANY COMMENTS" and plan acceptance criteria. |
| Backend untouched | The agent prompt at `backend/src/agent.py:27-29` already instructs the model to emit `**Source:** [Page Title](url)`. Renderer override is the only piece missing. |

## 3. Errors & Roadblocks Encountered

1. **`next lint` deprecation prompt (Next.js 15.5.19)**: Running `./node_modules/.bin/next lint` triggered an interactive menu asking how to configure ESLint ("Strict / Base / Cancel"). `next lint` is deprecated and will be removed in Next.js 16. The build pipeline (`next build`) already includes a "Linting and checking validity of types ..." step which passed, so the deprecation is informational, not blocking.
2. **Shell timeout on `pkill`** (cosmetic, not a code issue): `pkill -f "next start -p 3001"` did not return immediately, causing the shell tool to report a 30s timeout. The `next start` process was in fact killed (confirmed by follow-up `ps aux` showing no `next` processes). Affects only the smoke-test cleanup, not the actual implementation.
3. **No real type errors**: `tsc --noEmit` returned 0 errors on the first run.
4. **No build errors**: `next build` compiled in 65s (within the 46-86s range observed in ARCRAG-12).
5. **No runtime errors**: The smoke test returned HTTP 200 on `GET /` (13,238 bytes of static HTML).

## 4. Workarounds & Resolutions

| Issue | Resolution |
|-------|-----------|
| `next lint` interactive prompt | Did not run lint separately. `next build` includes the lint/type-check pass and it passed. Documented the deprecation in the report so future contributors don't waste time on it. |
| `pkill` shell timeout | Verified no `next` processes remained via `ps aux`; moved on. No code impact. |
| Static HTML doesn't render `target="_blank"` | The `ChatLink` component only activates when the agent streams a message containing a markdown link. The static landing page (`/`) shows only the welcome text. Documented this in the report's "Notes for Reviewers" section so the reviewer knows to ask the agent a question (or send a scripted chat) to see the renderer in action. |

## 5. What Went Right & What Went Wrong

- **What Went Right**:
  - The plan's reference to ARCRAG-12's lessons (`decision log:38-39`, `decision log:36`, `decision log:37`) paid off — zero deviations needed. The ChatImage pattern translated 1:1 to ChatLink.
  - `tsc --noEmit` passed on the first run with zero errors. No `react-markdown` type imports, no explicit `ComponentsMap` annotation, no `"use client"` adjustments needed.
  - `next build` compiled successfully in 65s, well within the 600s timeout budget.
  - Smoke test returned HTTP 200 on the first try (Content-Length 13,238 bytes; `x-nextjs-prerender: 1` confirms static prerender).
  - Total new code: 19 lines (ChatLink) + 2 lines (barrel). Minimal surface area, maximal security/UX impact.
  - All 10 acceptance criteria from the plan are satisfied.
  - Zero new dependencies, zero backend changes, zero config changes.

- **What Went Wrong**:
  - `next lint` being deprecated in Next.js 15.5 was not mentioned in the plan. It is no longer a usable validation gate; `next build` is the source of truth.
  - The smoke test could not directly verify the `target="_blank"` attribute in the rendered HTML, because the static landing page doesn't trigger the `a` renderer (no agent message = no link). Manual UI verification is required to confirm the end-to-end behavior. The plan explicitly noted this as out-of-scope for automated tests.
  - The shell tool's async pkill behavior caused a brief timeout alarm (cosmetic).

## 6. Lessons Learned & Recommendations

1. **ARCRAG-12's pattern is the canonical template for markdown renderer overrides.** Any future `code`, `h1`-`h6`, `blockquote`, `table`, etc. override should mirror `ChatImage`/`ChatLink` exactly: `React.FC<React.HTMLAttributes<HTMLElement>>`, `{...props}` spread, no `react-markdown` type imports, no explicit barrel annotation, rely on type inference.
2. **`next lint` is deprecated as of Next.js 15.5.** Plans and CI for this project should rely on `next build` (which includes the `Linting and checking validity of types` pass) for type/lint validation. Update the ARCRAG-12 decision log's "Test orchestration" section next time it's edited.
3. **End-to-end verification of dynamic CopilotKit renderers requires a real chat session.** Static `curl` can only confirm the page loads, not that the markdown renderers fire. A scripted AG-UI request (POST to `/api/copilotkit` with a known prompt) is the closest we can get to automated E2E without spinning up a real agent. The plan flagged this as manual, but a future improvement would be to seed the agent with a test fixture and assert on the SSE stream.
4. **Tailwind v4's class-only API is convenient for renderer overrides** — no `import` statements needed in the component file, classes are picked up via `globals.css` `@import "tailwindcss"`. Keep utility classes conservative (e.g. `text-sky-700 underline hover:text-sky-900`) so the chat's overall styling remains calm.
5. **Security defaults matter for `target="_blank"`.** Always pair with `rel="noopener noreferrer"`. Codify this in any future renderer template; consider a shared `safeTargetBlank` helper if more `<a>` overrides are added.
6. **The agent prompt is the source of truth for citation format.** If the citation format ever changes (e.g., markdown footnote syntax), the renderer override does not need to change — but the prompt in `backend/src/agent.py:28` does. Document this contract in the next decision log that touches the prompt.
