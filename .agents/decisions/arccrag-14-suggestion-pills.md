# Decision Log & Implementation Postmortem: arccrag-14-suggestion-pills

- **Date**: 2026-06-06
- **Branch**: `feature/arccrag-14-suggestion-pills`
- **Report Path**: `.agents/reports/arccrag-14-suggestion-pills-report.md`
- **Plan Path**: `.agents/plans/completed/arccrag-14-suggestion-pills.plan.md`

## 1. Summary of Implementation

Wired CopilotKit's first-class `useCopilotChatSuggestions` hook into the existing `<CopilotSidebar>` via a new thin client component `ChatSuggestions` that returns `null`. The hook registers 6 static suggestion pills with `available: "before-first-message"`, and the built-in `<Suggestions>` renderer inside `<CopilotSidebar>` (consumed transparently) renders them on first load and hides them after the first user message. Two files touched: one CREATE, one UPDATE. No backend, no new deps, no config changes.

## 2. Key Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Use `useCopilotChatSuggestions` (static variant) instead of custom `<Suggestions>` markup or a `useConfigureSuggestions` API | The plan called for the static-config variant; CopilotKit's built-in `<Suggestions>` renderer inside `<CopilotSidebar>` consumes the registered pills automatically, eliminating the need for custom markup. `useConfigureSuggestions` is not a real CopilotKit API in v1.8.0 — the canonical hook is `useCopilotChatSuggestions`. |
| Mount `<ChatSuggestions />` inside `<CopilotSidebar>` (before `<main>`) | The hook must execute within a `CopilotKit` provider context; mounting it as a sibling of `<main>` inside the sidebar is the conventional placement. The component returns `null`, so placement is cosmetic, but it must be inside the provider tree. |
| Add `title` field to each suggestion (plan listed `message` only) | CopilotKit's `<Suggestions>` renderer displays the `title` in the pill button and dispatches the `message` to the chat. The plan's 6 `message` strings are preserved verbatim; the `title` is a short, scannable label (e.g., "Buffer in ArcGIS Pro" → dispatches "How do I create a buffer in ArcGIS Pro?"). This matches the CopilotKit convention and the `Suggestion` type at `node_modules/@copilotkit/core/dist/index.d.cts:45-50` (which has both `title` and `message` as required fields). |
| Rely on TypeScript inference for `SUGGESTIONS` type | Per ARCRAG-12 lesson, avoid importing types from third-party packages with `.ts` source-resolution quirks. The hook's parameter type is `StaticSuggestionsConfigInput` (`@copilotkit/react-core/dist/index.d.cts:586-588`), and `SUGGESTIONS` is inferred as `StaticSuggestionInput[]` = `Omit<Suggestion, "isLoading">[]`. No type annotation needed. |
| Add `"use client"` to `ChatSuggestions.tsx` (not inherit from `page.tsx`) | Next.js App Router: each file's `"use client"` directive is per-file. `page.tsx` is a Client Component (set in ARCRAG-12), but `ChatSuggestions.tsx` is its own module and must declare its own directive to use React hooks (`useCopilotChatSuggestions`). |
| `available: "before-first-message"` (the static-config default) | Hides pills after the first user message. Verified semantics at `node_modules/@copilotkit/core/dist/index.d.cts:88`. |
| Place `<ChatSuggestions />` before `<main>` in the JSX | Conventional placement per the plan ("before `<main>` is conventional"). Since the component returns `null`, the order has no effect on rendered output — but it's a clear signal to readers that the component is a side-effect-only registration. |

## 3. Errors & Roadblocks Encountered

None. The implementation went smoothly on the first attempt. Specifically:

- No `tsc --noEmit` errors.
- No `next build` errors.
- No type-resolution issues with `react-markdown` (we didn't import from it).
- No Server-to-Client Component function-passing issues (the `ChatSuggestions` component is purely a hook consumer; it doesn't pass functions to other Client Components).
- No `Suggestion` type re-export issues from `@copilotkit/core` (verified pre-implementation: the `Suggestion` type lives in `index.d.cts` — declarations only, no `.ts` source).

## 4. Workarounds & Resolutions

None needed — no errors occurred.

## 5. What Went Right & What Went Wrong

- **What Went Right**:
  - The plan was extremely thorough (it pre-emptively flagged the `react-markdown` type issue, the build timeout, and the deprecation of `next lint`).
  - The CopilotKit hook was discovered to be fully wired into the existing `<CopilotSidebar>` via a built-in `<Suggestions>` renderer — no custom markup needed.
  - Both `tsc --noEmit` and `next build` passed on the first attempt with zero errors.
  - Smoke test returned HTTP 200 on first try; the server started in 2.6s.
  - The implementation is minimal: 41 lines of new code (component) + 2 lines of import/mount in `page.tsx`.
  - All ARCRAG-12/13 lessons carried forward (no `react-markdown` type imports, no comments, `React.FC` typing convention, no `"use client"` change needed in `page.tsx` since it was already a Client Component).

- **What Went Wrong**:
  - Nothing of substance. The only minor observation: `next build` took 5.1 min (306s), which is on the upper end of the plan's 46-86s estimate. This is within the 600s budget and likely due to cold disk caches / CopilotKit's first-time tree-shake; subsequent builds will be faster. No action needed.
  - The plan's `Risks & Mitigations` table mentioned the plan's explicit `title` vs `message` UX choice. Looking at the `Suggestion` type (`@copilotkit/core/dist/index.d.cts:45-50`), both fields are required, so adding `title` is a no-op deviation from a "minimum viable" reading of the plan. The plan listed the 6 `message` strings verbatim, but the `title` field is required by the type system — without it, the `SUGGESTIONS` const would fail to satisfy the inferred type. This is documented in the report under "Minor follow-up".

## 6. Lessons Learned & Recommendations

1. **CopilotKit's suggestions are a hook, not a configuration** — `useCopilotChatSuggestions` is the canonical API (v1.8.0). `useConfigureSuggestions` is not a real API; the plan's "use `useConfigureSuggestions`" note in `stories.md:408` is a misremembered name. The plan itself correctly used `useCopilotChatSuggestions`. If anyone updates the `stories.md` "Technical Notes" line for ARCRAG-14, they should change it to `useCopilotChatSuggestions`.
2. **Built-in `<Suggestions>` renderer is wired automatically** — no need to provide a custom renderer. As long as a `useCopilotChatSuggestions` hook registers a static or dynamic config, the sidebar will display the pills. This is documented at `node_modules/@copilotkit/react-ui/dist/index.d.cts:815-820`.
3. **`title` is required, not optional** — the `Suggestion` type at `@copilotkit/core/dist/index.d.cts:45-50` has both `title: string` and `message: string` as required. A "title-only" or "message-only" suggestion will fail type checking. The plan's `message`-only reading was a simplification; the implementation added a short `title` for each pill.
4. **No new deps were needed** — `useCopilotChatSuggestions` is in the existing `@copilotkit/react-core@^1.8.0` (installed in ARCRAG-11). This is a strong validation of the ARCRAG-11 dep choices.
5. **Plan audit checklist for future plans** — when a plan says "register a hook", explicitly check whether the hook is auto-consumed by an existing component (like `<CopilotSidebar>`'s built-in `<Suggestions>`) or whether custom markup is needed. Saves time and reduces over-engineering.
6. **The build is cold-cache sensitive** — first build of the day took 5.1 min. Subsequent builds (or warm-cache scenarios) should be in the 46-86s range cited in the plan. The 600s timeout remains the right hedge.
