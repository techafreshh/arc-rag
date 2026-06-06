# Decision Log & Implementation Postmortem: arccrag-12-inline-image-rendering

- **Date**: 2026-06-06
- **Branch**: `feature/arccrag-12-inline-image-rendering`
- **Report Path**: `.agents/reports/arccrag-12-inline-image-rendering-report.md`

## 1. Summary of Implementation

Overrode the markdown `img` renderer used by `<CopilotSidebar>` so that screenshots and diagrams emitted by the agent display inline with max-width, rounded corners, and click-to-open-in-new-tab behavior, with graceful alt-text fallback on broken URLs. Two new components (`ChatImage`, `markdownComponents`) were created and wired into the existing `page.tsx`. `next.config.js` was updated with `images.remotePatterns` for forward-compatibility with `next/image`.

## 2. Key Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Wrap `<img>` in `<a href={src} target="_blank">` | Provides click-to-open-in-new-tab behavior without needing JavaScript or a modal library |
| Apply Tailwind classes `max-w-full h-auto rounded-lg my-2 block` | Ensures images scale responsively, have rounded corners, and block-level layout without affecting surrounding text |
| `onError` hides the img element (`display: none`) | Prevents broken-image-icon display; alt text is preserved for screen readers via the `alt` attribute |
| Guard `typeof src !== "string"` before `<a>` wrapping | TypeScript strict mode: `ImgHTMLAttributes` allows `Blob` for `src`, but `<a href>` only accepts `string` |
| Omit `Components` type from `react-markdown` | `react-markdown` ships a `.ts` source file (`complex-types.ts`) that references `JSX.IntrinsicElements` in a way incompatible with this project's `jsx: "preserve"` config, causing pre-existing type errors |
| Added `"use client"` to `page.tsx` | `CopilotSidebar` is a Client Component; Next.js App Router forbids passing function references (e.g., `ChatImage` as `markdownTagRenderers`) from Server Components to Client Components |
| Added `images.remotePatterns` for 3 Esri hosts | Forward-compat — when the project switches from `<img>` to `next/image`, the config is already in place |
| No explicit type annotation on `markdownComponents` | The inferred type `{ img: React.FC<ImgHTMLAttributes<HTMLImageElement>> }` is structurally compatible with `ComponentsMap` expected by `markdownTagRenderers` |

## 3. Errors & Roadblocks Encountered

1. **`<a href>` type error (TS2322)**: `Type 'string | Blob | undefined' is not assignable to type 'string | undefined'` when passing `src` directly to `<a href={src}>`.
2. **`react-markdown` type resolution failure (TS2503)**: Importing `import type { Components } from "react-markdown"` caused `Cannot find namespace 'JSX'` errors in `node_modules/react-markdown/lib/complex-types.ts` (lines 25-27). This is a pre-existing issue in react-markdown's own `.ts` source files, not in our code.
3. **Next.js SSR build error**: `Functions cannot be passed directly to Client Components unless you explicitly expose it by marking it with "use server"` — `markdownTagRenderers={markdownComponents}` passes a function reference (`ChatImage`) from a Server Component to a Client Component.
4. **`next build` timeout**: Initial build command timed out at the default 180s; compilation alone took 46-86s.

## 4. Workarounds & Resolutions

| Error | Resolution |
|-------|------------|
| `<a href>` type mismatch | Added `if (!src \|\| typeof src !== "string")` guard to render plain `<img>` for non-string src, and `<a><img>` for string src |
| `react-markdown` type errors | Removed the `import type { Components }` and dropped the explicit type annotation on `markdownComponents` — TypeScript inference produces a structurally compatible type |
| Server-to-Client Component function passing | Added `"use client"` directive at the top of `page.tsx` |
| Build timeout | Ran `next build` with a 600s timeout (10 minutes) |

## 5. What Went Right & What Went Wrong

- **What Went Right**:
  - The implementation closely followed the plan's structure and intent
  - After fixing the `"use client"` issue, `next build` compiled successfully on the first attempt (46s)
  - All 4 files were created/updated as specified
  - The smoke test (curl localhost:3000) returned HTTP 200 with 13KB HTML
  - Minimal code — only ~48 lines of new code

- **What Went Wrong**:
  - `react-markdown`'s bundled `.ts` source files caused type resolution errors, forcing a deviation from the plan's explicit typing approach
  - The plan did not account for Next.js App Router's restriction on passing function references from Server Components to Client Components — `"use client"` was needed but not mentioned
  - Blob-typed `src` from `ImgHTMLAttributes` caused a strict mode type error that was not anticipated by the plan

## 6. Lessons Learned & Recommendations

1. **Plan audits needed**: Plans for Next.js App Router features should explicitly check whether new/updated files need `"use client"` when passing render-props or component references.
2. **Type hygiene for `react-markdown`**: Avoid importing types from `react-markdown` directly in this project. The package ships `.ts` sources (not just `.d.ts`) that are incompatible with the project's `jsx: "preserve"` + `strict: true` config. Instead, rely on type inference or define local type aliases.
3. **Build timeout**: `next build` in this project takes 46-86s. Any automation should use a generous timeout (≥300s).
4. **Testing gap**: No test framework is configured. As the project grows, adding Vitest or Jest with React Testing Library would enable proper unit tests for UI components.
5. **The `ComponentsMap` type**: CopilotKit's `ComponentsMap` type expects `React.FC<{ children?: ReactNode } & T[K]>`, which is stricter than `react-markdown`'s `Components`. These types are structurally incompatible, so type assertions or inference is preferred over explicit typing when bridging the two libraries.
