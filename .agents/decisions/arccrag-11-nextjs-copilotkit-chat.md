# Decision Log & Implementation Postmortem: arccrag-11-nextjs-copilotkit-chat

- **Date**: 2026-06-05
- **Branch**: `feature/arccrag-11-nextjs-copilotkit-chat`
- **Report Path**: `.agents/reports/arccrag-11-nextjs-copilotkit-chat-report.md`

## 1. Summary of Implementation

Created the Next.js 15 frontend for the ArcGIS Documentation Guide, featuring a CopilotKit chat UI that proxies through a Next.js API route to an existing FastAPI AG-UI backend. Three layers were built: a Tailwind v4-styled root layout with `<CopilotKit runtimeUrl="/api/copilotkit">`, a home page with `<CopilotSidebar>` and welcome panel, and an API route mounting a `CopilotRuntime` with an `HttpAgent` pointing at the backend's `/ag-ui` endpoint.

## 2. Key Decisions & Rationale

- **CopilotSidebar over CopilotPopup**: PRD §6 mandates a persistent chat panel. `CopilotSidebar` provides a docked sidebar that stays open alongside page content, matching the user story requirements for a GIS student to "see streamed answers" without navigating away.
- **Runtime proxy pattern (API route)**: The chat frontend never calls the FastAPI backend directly from the browser. Instead, a Next.js `app/api/copilotkit/route.ts` server-side route mounts `CopilotRuntime` + `HttpAgent`. This avoids CORS issues (the backend's CORS is restricted, not wildcard) and keeps the browser-to-backend path server-side.
- **Tailwind v4 PostCSS setup**: Used `@tailwindcss/postcss` plugin with `postcss.config.mjs` and `@import "tailwindcss"` in `globals.css`. The existing `package.json` already pinned `tailwindcss@^4.0.0` and `@tailwindcss/postcss@^4.0.0`, so no `tailwind.config.js` was needed (v4 drops that file).
- **EmptyAdapter over ExperimentalEmptyAdapter**: Probed `@copilotkit/runtime` exports at install time. Both names exist in v1.59.5; used the original `EmptyAdapter` name from the plan's v1.8.x pattern since it is still exported.
- **HttpAgent from @ag-ui/client**: The plan's import path `import { HttpAgent } from "@ag-ui/client"` was verified to work. This package is a transitive dependency of `@copilotkit/runtime` and exports `HttpAgent extends AbstractAgent`.

## 3. Errors & Roadblocks Encountered

- **npm install timeout (30+ minutes)**: Every `npm install` attempt timed out repeatedly at the default shell timeout. The Windows npm installation used via WSL is extremely slow on the WSL filesystem.
- **CMD.exe UNC path failure**: The Windows npm runs postinstall scripts via `C:\Windows\system32\cmd.exe`, which cannot handle `\\wsl.localhost\...` UNC paths. This caused `@scarf/scarf` postinstall to fail with `Cannot find module 'C:\Windows\report.js'`.
- **Wrong SWC binary installed**: Because npm reports `os: win32`, the Windows npm installed `@next/swc-win32-x64-msvc` instead of the Linux variant. `next build` then failed with "Mismatching @next/swc version" and SWC compilation errors.
- **`next build` interrupted**: The first successful build was killed before "Collecting build traces" completed, leaving `.next/` without a valid `BUILD_ID`.
- **Missing `.bin` symlinks**: npm install with `--ignore-scripts` completed but did not create the `node_modules/.bin/` directory, so `npm run build` could not find `next`.
- **No sudo available**: Could not install Linux npm via `apt-get install npm` because password-less sudo was not configured.

## 4. Workarounds & Resolutions

| Problem | Resolution |
|---------|-----------|
| npm install hangs on postinstall via cmd.exe | Used `npm install --ignore-scripts` to skip all postinstall scripts |
| Wrong SWC binary (Windows vs Linux) | Force-installed `@next/swc-linux-x64-gnu@15.5.19` with `npm install @next/swc-linux-x64-gnu --ignore-scripts --force`, then uninstalled the Windows variant |
| Missing `.bin` symlinks | Ran `chmod +x node_modules/.bin/*` for each needed binary and invoked them directly as `./node_modules/.bin/next build` |
| `npm run build` invokes cmd.exe | Avoided `npm run` entirely; used `./node_modules/.bin/next build` and `./node_modules/.bin/tsc --noEmit` directly |
| Dev server dies on command timeout | Built production bundle (`next build`) and tested via `next start` |
| No Linux npm | Downloaded npm tarball to `/tmp/` (`curl -sL https://registry.npmjs.org/npm/-/npm-10.9.3.tgz`) and extracted, but Linux node had no registry access — fell back to Windows npm with `--ignore-scripts` |

## 5. What Went Right & What Went Wrong

- **What Went Right**:
  - Plan was detailed and accurate — all file contents, imports, and configurations matched the reality of the CopilotKit v1.59.5 API.
  - TypeScript config (`tsconfig.json`) compiled with zero errors on first attempt.
  - API route with `CopilotRuntime` + `HttpAgent` + `EmptyAdapter` wired correctly on first try — the endpoint responded (not a 404/500) with a meaningful runtime error ("Missing method field") confirming the runtime initialized.
  - Tailwind v4 setup was trivial — one import line, one PostCSS plugin config, no migration issues.

- **What Went Wrong**:
  - **Environment compatibility**: The entire execution was derailed by a Windows npm installation being used inside WSL. This single environmental issue consumed ~80% of session time across repeated install attempts, cache cleans, and workarounds.
  - **npm install timeout**: The default 10-minute tool timeout was insufficient. Required 30+ minute waits even after workarounds.
  - **`.bin` directory not created**: `--ignore-scripts` skipped the "link bins" step, requiring manual `chmod` and direct path invocation.
  - **No Jira MCP tools**: Could not update the ARCRAG-11 Jira issue as specified by the plan's Phase 6.

## 6. Lessons Learned & Recommendations

1. **Check the `npm` installation first**: Before any frontend work in this WSL environment, verify `which npm` points to a Linux binary (`/usr/bin/npm`), not a Windows one (`/mnt/c/...`). If it's the Windows version, install Linux npm or use an alternative package manager.
2. **Always use `--ignore-scripts` on this system**: The Windows npm cannot run postinstall scripts on WSL filesystems. Add this flag by default and run any required scripts manually via the Linux node.
3. **Cache the correct SWC binary**: After the first successful install, the `@next/swc-linux-x64-gnu` binary should be copied to a safe location or pinned in `package.json` as an optional dependency to avoid re-downloading.
4. **Set longer tool timeouts for npm operations**: The frontend dependency tree (especially `@copilotkit/runtime` with its graphql, express, langchain, and AI SDK deps) is large. Plan for 15-30 minute installs.
5. **Use `next start` over `next dev` for E2E validation**: The production server starts faster (~1 second) and avoids the first-request compilation lag of the dev server. This makes smoke tests more reliable within time constraints.
