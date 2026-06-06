# Plan: Inline Image Rendering in Chat (ARCRAG-12)

## Summary

Override the markdown `img` renderer used by `<CopilotSidebar>` so that screenshots and diagrams emitted by the agent (via `![alt](url)`) display inline with a max-width, rounded corners, and click-to-open-in-new-tab behavior, with graceful alt-text fallback on broken URLs. Two small new components + one prop wire-up + one `next.config.js` tweak; no `AssistantMessage` replacement needed.

## User Story

As a GIS student
I want to see documentation screenshots and diagrams inline in chat answers
So that I can visually match what I see on my screen.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (UI feature) |
| Complexity | LOW |
| Systems Affected | frontend (Next.js, CopilotKit) |
| Jira Issue | ARCRAG-12 (N/A — no Jira MCP configured, per ARCRAG-11 report) |
| Blocked By | ARCRAG-11 ✅ |

---

## Patterns to Follow

### Component module style (CopilotKit pattern)
```ts
// SOURCE: frontend/node_modules/@copilotkit/react-ui/dist/index.d.cts:75-77, 109-112
type ComponentsMap<T extends Record<string, object> = Record<string, object>> = {
  [K in keyof T]: React.FC<{ children?: ReactNode } & T[K]>;
};
// Used as:
<CopilotSidebar markdownTagRenderers={{ img: ChatImage }} ... />
```

### Tailwind v4 styling (no config file)
```css
/* SOURCE: frontend/src/app/globals.css:1 */
@import "tailwindcss";
```
Use utility classes directly; no `tailwind.config.js` (v4 convention).

### Page composition
```tsx
// SOURCE: frontend/src/app/page.tsx:6-12
<CopilotSidebar defaultOpen labels={{ title, initial }}>{children}</CopilotSidebar>
```

### TypeScript strict + path alias
```json
// SOURCE: frontend/tsconfig.json:8,17
"strict": true,
"paths": { "@/*": ["./src/*"] }
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `frontend/src/components/ChatImage.tsx` | CREATE | Custom `<img>` renderer with styling + click-to-enlarge + error fallback |
| `frontend/src/components/markdownComponents.tsx` | CREATE | Exports `markdownComponents` map wiring `img` → `ChatImage` |
| `frontend/src/app/page.tsx` | UPDATE | Pass `markdownTagRenderers` to `<CopilotSidebar>` |
| `frontend/next.config.js` | UPDATE | Add `images.remotePatterns` for `pro.arcgis.com`, `desktop.arcgis.com`, `doc.esri.com` (forward-compat for `next/image`; not required for MVP) |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Create ChatImage component
- **File**: `frontend/src/components/ChatImage.tsx`
- **Action**: CREATE
- **Implement**: Define `ChatImage: React.FC<ImgHTMLAttributes<HTMLImageElement>>` that:
  - Accepts standard `img` props (react-markdown passes `src`, `alt`)
  - Wraps the `<img>` in an `<a href={src} target="_blank" rel="noopener noreferrer">` for click-to-enlarge
  - Applies Tailwind classes to the `<img>`: `max-w-full h-auto rounded-lg my-2 block`
  - `onError` handler: sets `e.currentTarget.style.display = 'none'` so the browser's broken-image icon is hidden; the alt attribute is preserved so screen readers and the browser's native fallback still surface the description
- **Mirror**: `frontend/node_modules/@copilotkit/react-ui/dist/index.d.cts:75-77` (ComponentsMap shape)
- **Validate**: `cd frontend && ./node_modules/.bin/tsc --noEmit`

### Task 2: Create markdownComponents module
- **File**: `frontend/src/components/markdownComponents.tsx`
- **Action**: CREATE
- **Implement**:
  ```ts
  import type { Components } from "react-markdown";
  import { ChatImage } from "./ChatImage";

  export const markdownComponents: Components = {
    img: ChatImage,
  };
  ```
- **Mirror**: `frontend/node_modules/@copilotkit/react-ui/dist/index.d.cts:75` (ComponentsMap uses the same shape as react-markdown `Components`)
- **Validate**: `cd frontend && ./node_modules/.bin/tsc --noEmit`

### Task 3: Wire markdownTagRenderers into page
- **File**: `frontend/src/app/page.tsx`
- **Action**: UPDATE
- **Implement**:
  - Add import: `import { markdownComponents } from "@/components/markdownComponents";`
  - Add prop to `<CopilotSidebar>`: `markdownTagRenderers={markdownComponents}`
- **Mirror**: existing prop pattern at `frontend/src/app/page.tsx:6-12`
- **Validate**: `cd frontend && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next build`

### Task 4: Add image remotePatterns
- **File**: `frontend/next.config.js`
- **Action**: UPDATE
- **Implement**: Add `images: { remotePatterns: [{ protocol: "https", hostname: "pro.arcgis.com" }, { protocol: "https", hostname: "desktop.arcgis.com" }, { protocol: "https", hostname: "doc.esri.com" }] }` inside the `nextConfig` object.
- **Mirror**: `frontend/next.config.js:1-5` (existing minimal config)
- **Rationale**: Forward-compat. Even though MVP uses plain `<img>`, having the patterns in place means swapping to `next/image` later is a one-line change.
- **Validate**: `cd frontend && ./node_modules/.bin/next build`

---

## Validation

```bash
cd frontend
./node_modules/.bin/tsc --noEmit        # type check
./node_modules/.bin/next build          # build + lint
./node_modules/.bin/next start -p 3000  # smoke test
# Open browser → click suggestion → ask "How do I create a buffer in ArcGIS Pro?"
# Expect: response includes an inline image (max-width, rounded, clickable)
```

---

## Acceptance Criteria

- [ ] `frontend/src/components/ChatImage.tsx` exists with click-to-enlarge + error fallback
- [ ] `frontend/src/components/markdownComponents.tsx` exports a `Components` map
- [ ] `<CopilotSidebar>` receives `markdownTagRenderers` prop
- [ ] `next.config.js` has `images.remotePatterns` for the three Esri hosts
- [ ] `tsc --noEmit` passes with zero errors
- [ ] `next build` succeeds
- [ ] Manual smoke: question that returns an image shows the image inline (not raw markdown), with rounded corners and click-to-open-in-new-tab behavior
- [ ] Manual smoke: response with no images is unaffected (default markdown still renders)
