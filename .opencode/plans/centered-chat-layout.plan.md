# Plan: Sidebar → Centered Chat Layout

## Summary

Replace the `CopilotSidebar` component with `CopilotChat` in embedded mode to create a centered, full-width chat interface. Add an Esri logo placeholder and app description above the chat. The `.copilotKitChat` CSS class has no fixed positioning (unlike sidebar/popup variants), making it ideal for a centered layout with minimal overrides.

## User Story

As a GIS student
I want to see the chat interface centered and full-width when I visit the app
So that the Q&A experience is the primary focus, not a sidebar panel next to a useless landing page

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR |
| Complexity | LOW |
| Systems Affected | Frontend UI |
| Jira Issue | N/A |

---

## Patterns to Follow

### Component Export Style
```tsx
// SOURCE: src/components/ChatLink.tsx:3
export const ChatLink: React.FC<React.AnchorHTMLAttributes<HTMLAnchorElement>> = ({
```
Named exports for components, React.FC typed, arrow functions with destructured props.

### "use client" Placement
```tsx
// SOURCE: src/app/page.tsx:1
"use client";

```
Always line 1 of the file, blank line after.

### Tailwind Styling
```tsx
// SOURCE: src/app/page.tsx:19-30
<main className="mx-auto max-w-3xl px-6 py-16">
  <h1 className="text-3xl font-semibold tracking-tight">
```
Utility-first Tailwind v4. No custom CSS modules. Slate color palette for text/bg, sky for links.

### CopilotKit Import Pattern
```tsx
// SOURCE: src/app/page.tsx:3-4
import { CopilotSidebar } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";
```
Import component from `@copilotkit/react-ui`, side-effect import for styles.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `frontend/src/app/page.tsx` | UPDATE | Replace CopilotSidebar with CopilotChat, add header with logo + description, center layout |
| `frontend/src/app/globals.css` | UPDATE | Add minimal overrides for full-height centered chat |

---

## Tasks

### Task 1: Update `globals.css` with centered chat overrides

- **File**: `frontend/src/app/globals.css`
- **Action**: UPDATE
- **Implement**: Add CSS overrides to ensure `.copilotKitChat` fills the viewport height and centers properly. The default `.copilotKitChat` class has no height constraint (just `display: flex; flex-direction: column`), so we need to set `height: 100%` on it and ensure the flex column fills the screen.
- **Mirror**: Tailwind v4 `@import "tailwindcss"` pattern — keep existing import, add custom styles below it
- **Validate**: Visual check that chat fills viewport

```css
/* Add below existing @import "tailwindcss" */
.copilotKitChat {
  height: 100%;
  flex: 1;
  min-height: 0;
}
```

### Task 2: Replace CopilotSidebar with centered CopilotChat layout in `page.tsx`

- **File**: `frontend/src/app/page.tsx`
- **Action**: UPDATE
- **Implement**:
  1. Change import from `CopilotSidebar` to `CopilotChat`
  2. Keep the `@copilotkit/react-ui/styles.css` side-effect import
  3. Replace the `<CopilotSidebar>` wrapper with a centered flex container:
     - Outer div: `flex flex-col h-screen` (full viewport height, column layout)
     - Header div: centered, contains Esri logo `<img>`, title, subtitle
     - `CopilotChat` component: `flex-1 min-h-0` to fill remaining space
  4. Pass same props to `CopilotChat`: `labels`, `markdownTagRenderers`
  5. Remove `defaultOpen` prop (not applicable to embedded chat)
  6. Remove the static `<main>` landing page content (replaced by header above chat)
  7. Keep `ChatSuggestions` inside the chat (via `useCopilotChatSuggestions` hook — no change needed)
- **Mirror**: Follow existing Tailwind class patterns from `page.tsx:19-30`
- **Validate**: `npm run build`

### Task 3: Add Esri logo placeholder and description to header

- **File**: `frontend/src/app/page.tsx` (same file, part of Task 2)
- **Action**: UPDATE
- **Implement**: Inside the header div from Task 2:
  - Esri logo: `<img src="https://www.esri.com/content/dam/esrisites/en-us/common/icons/esri-logo.svg" alt="Esri" className="h-10 mx-auto mb-4" />`
  - Title: `<h1 className="text-2xl font-semibold tracking-tight text-center">ArcGIS Documentation Guide</h1>`
  - Description: `<p className="text-sm text-slate-500 text-center mt-1">AI-powered Q&A for ArcGIS Pro and ArcMap documentation</p>`
  - Add `onError` handler to logo img to hide if it fails to load (same pattern as `ChatImage.tsx:14-16`)
- **Mirror**: Error handling pattern from `src/components/ChatImage.tsx:14-16`
- **Validate**: Visual check, verify logo loads or gracefully hides

---

## Validation

```bash
# Type check and build
cd frontend && npm run build

# Lint
npm run lint

# Visual verification
npm run dev
# - Visit http://localhost:3000
# - Confirm centered layout with logo + description header
# - Confirm chat fills remaining space
# - Confirm suggestion pills appear
# - Confirm inline images and source links render correctly
```

---

## Acceptance Criteria

- [ ] CopilotSidebar replaced with CopilotChat (embedded mode)
- [ ] Esri logo placeholder visible above chat (or hidden if URL fails)
- [ ] App description visible below logo
- [ ] Chat interface centered, max-width constrained, fills viewport height
- [ ] Suggestion pills still appear before first message
- [ ] Inline images and source citation links still render correctly
- [ ] No sidebar panel or floating toggle button visible
- [ ] `npm run build` passes with no errors
- [ ] Mobile responsive (chat fills width on small screens)

---

## Risks

| Risk | Mitigation |
|------|------------|
| Esri logo URL may not resolve or may be blocked | `onError` handler hides the image gracefully (same pattern as ChatImage.tsx) |
| CopilotChat may not include a close button (sidebar did) | Not needed — embedded chat is the main UI, no close/dismiss concept |
| CopilotKit styles may leak sidebar positioning classes | `.copilotKitChat` class has no fixed positioning by design; sidebar classes only apply when using `CopilotSidebar` component |
