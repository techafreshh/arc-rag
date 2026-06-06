# Jira Stories — ArcGIS Documentation RAG Agent

**Source PRD**: `.agents/PRDs/PRD.md`
**Generated**: 2026-05-28

---

## Phase 1: Foundation

---

### ARCRAG-01: Project Scaffolding & Docker Infrastructure

**Type**: Technical
**Jira Type**: Task
**Priority**: High
**Complexity**: Small
**Phase**: 1 — Foundation
**Labels**: `infrastructure`, `devops`
**Blocked By**: —

#### Description
As a developer, I want to set up the monorepo structure and Docker infrastructure, so that all services can be developed and run locally.

#### Acceptance Criteria
- [ ] Given the repo is cloned, when I run `docker compose up`, then Qdrant starts and is accessible at `localhost:6333/dashboard`
- [ ] Given the project structure exists, when I look at the repo, then I see `frontend/`, `backend/`, `scripts/`, `data/` directories
- [ ] Given `.env.example` exists, when I copy it to `.env` and fill in keys, then all services can read their configuration
- [ ] Given `pyproject.toml` exists, when I run `pip install -e .` in `backend/`, then all Python dependencies install successfully
- [ ] Given `package.json` exists in `frontend/`, when I run `npm install`, then all Node dependencies install successfully

#### Technical Notes
- `docker-compose.yml`: Qdrant service with persistent volume, port 6333
- `.env.example`: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `QDRANT_URL`, `QDRANT_COLLECTION`, `BACKEND_PORT`, `NEXT_PUBLIC_BACKEND_URL`
- Python deps: `pydantic-ai[openrouter]`, `fastapi`, `uvicorn`, `httpx`, `beautifulsoup4`, `qdrant-client`, `python-dotenv`
- Node deps: `next`, `@copilotkit/react-core`, `@copilotkit/react-ui`, `tailwindcss`

---

### ARCRAG-02: PydanticAI Agent with OpenRouter Connection

**Type**: Feature
**Jira Type**: Story
**Priority**: High
**Complexity**: Medium
**Phase**: 1 — Foundation
**Labels**: `backend`, `agent`
**Blocked By**: ARCRAG-01

#### Description
As a developer, I want to create a PydanticAI agent connected to OpenRouter, so that I have a working LLM agent I can extend with tools.

#### Acceptance Criteria
- [ ] Given `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` are set in `.env`, when the agent is instantiated, then it connects to OpenRouter successfully
- [ ] Given the agent is running, when I send it a plain text message, then it responds with a streamed answer
- [ ] Given the model env var is changed (e.g., from Claude to Gemini), when the agent restarts, then it uses the new model without code changes
- [ ] Given an invalid API key, when the agent tries to respond, then it raises a clear error (not a crash)

#### Technical Notes
- File: `backend/src/agent.py`
- Use `from pydantic_ai.models.openrouter import OpenRouterModel`
- System prompt: GIS documentation guide persona
- Config loaded from `backend/src/config.py` using pydantic-settings

---

### ARCRAG-03: fetch_page Tool — Live Documentation Scraper

**Type**: Feature
**Jira Type**: Story
**Priority**: High
**Complexity**: Medium
**Phase**: 1 — Foundation
**Labels**: `backend`, `tools`
**Blocked By**: ARCRAG-02

#### Description
As a student, I want the agent to fetch full documentation page content live, so that I get detailed, up-to-date answers with images.

#### Acceptance Criteria
- [ ] Given a valid ArcGIS Pro doc URL, when `fetch_page` is called, then it returns the page's main text content (nav/footer stripped)
- [ ] Given a valid URL, when `fetch_page` is called, then it returns a list of image URLs with their alt text
- [ ] Given a valid URL, when `fetch_page` is called, then it preserves code blocks as separate structured elements
- [ ] Given a URL that returns 404, when `fetch_page` is called, then it returns a graceful error message (not an exception)
- [ ] Given a URL that times out (>10s), when `fetch_page` is called, then it returns a timeout error message
- [ ] Given a page was fetched in the last 5 minutes, when `fetch_page` is called again for the same URL, then it returns the cached result

#### Technical Notes
- File: `backend/src/tools/fetch.py`
- Use `httpx.AsyncClient` with 10s timeout
- Parse with BeautifulSoup4: find `<main>` or `<article>` or `#main-content`
- LRU cache (~100 entries) using `functools.lru_cache` or `cachetools.TTLCache`
- Return Pydantic model: `PageContent(url, title, sections: list[Section], images: list[Image], code_blocks: list[str])`
- Test with: `https://pro.arcgis.com/en/pro-app/latest/tool-reference/analysis/buffer.htm`

---

### ARCRAG-04: Agent Answers Questions Using Hardcoded URL

**Type**: Feature
**Jira Type**: Story
**Priority**: Medium
**Complexity**: Small
**Phase**: 1 — Foundation
**Labels**: `backend`, `agent`, `integration`
**Blocked By**: ARCRAG-03

#### Description
As a developer, I want to verify the agent can use the fetch_page tool to answer a question from a known URL, so that the end-to-end tool flow works before adding search.

#### Acceptance Criteria
- [ ] Given the agent has the `fetch_page` tool registered, when I ask "What is the Buffer tool?", then the agent calls `fetch_page` with the Buffer tool URL and generates an answer
- [ ] Given the agent generates an answer, when I read the response, then it includes markdown image references from the fetched page
- [ ] Given the agent generates an answer, when I read the response, then it includes a source citation link to the original page

#### Technical Notes
- For this story, the agent can have the Buffer tool URL hardcoded or use a simple URL lookup dict
- This validates: tool registration → tool call → content extraction → LLM generation with context
- Run from terminal: `python -m backend.src.agent` with a test query


---

## Phase 2: Index & Search

---

### ARCRAG-05: Sitemap Parser Script

**Type**: Technical
**Jira Type**: Task
**Priority**: High
**Complexity**: Medium
**Phase**: 2 — Index & Search
**Labels**: `scripts`, `ingestion`
**Blocked By**: ARCRAG-01

#### Description
As a developer, I want a script that parses ArcGIS Pro and ArcMap sitemap XML files, so that I have a complete list of documentation page URLs to index.

#### Acceptance Criteria
- [ ] Given the script is run with `--source arcpro`, when it completes, then it outputs a JSON file with all English `/latest/` page URLs from `pro.arcgis.com/sitemap_index.xml`
- [ ] Given the script is run with `--source arcmap`, when it completes, then it outputs a JSON file with all English `/latest/` page URLs from `desktop.arcgis.com/sitemap_index.xml`
- [ ] Given the sitemap index has 80+ sub-sitemaps, when the script runs, then it fetches and parses all sub-sitemaps with 1s delay between requests
- [ ] Given a sub-sitemap fails to download, when the script encounters the error, then it logs the failure and continues with remaining sitemaps
- [ ] Given the script has run before, when it runs again, then it can resume from where it left off (saves progress)

#### Technical Notes
- File: `scripts/parse_sitemaps.py`
- Output: `data/arcpro_urls.json` and `data/arcmap_urls.json`
- Use `xml.etree.ElementTree` for XML parsing
- Filter: only URLs matching `/en/` and `/latest/` (skip other languages and versions)
- Expected output: ~30K-50K URLs for ArcGIS Pro, ~5K-10K for ArcMap

---

### ARCRAG-06: Index Builder Script — Page Metadata Scraper

**Type**: Technical
**Jira Type**: Task
**Priority**: High
**Complexity**: Large
**Phase**: 2 — Index & Search
**Labels**: `scripts`, `ingestion`
**Blocked By**: ARCRAG-05

#### Description
As a developer, I want a script that scrapes page titles, summaries, section headings, and image metadata from each documentation URL, so that I can build the thin index.

#### Acceptance Criteria
- [ ] Given a list of URLs from the sitemap parser, when the script runs, then it fetches each page and extracts: title (h1), first paragraph (summary), H2/H3 headings with brief text, breadcrumb path, and image alt texts + URLs
- [ ] Given rate limiting of 1-2 req/sec, when processing 50K URLs, then the script respects the delay and doesn't overwhelm the server
- [ ] Given the script is interrupted, when it restarts, then it resumes from the last processed URL (checkpoint file)
- [ ] Given a page fails to load, when the error occurs, then it logs the URL and continues
- [ ] Given the script completes, when I inspect the output, then each entry has: `{url, title, summary, sections: [{heading, brief_text}], images: [{url, alt}], breadcrumb, source}`

#### Technical Notes
- File: `scripts/build_index.py`
- Output: `data/arcpro_index.json`, `data/arcmap_index.json`
- Use `httpx` + `BeautifulSoup4`
- Page-level entry: `"{title} - {summary}"` (for embedding later)
- Section-level entries: `"{title} > {heading} - {brief_text}"` (for embedding later)
- Checkpoint: save progress every 100 pages to `data/.checkpoint_arcpro.json`
- For initial testing, run on a subset (one toolbox, ~50 pages)

---

### ARCRAG-07: Qdrant Loader Script — Embed & Upsert

**Type**: Technical
**Jira Type**: Task
**Priority**: High
**Complexity**: Medium
**Phase**: 2 — Index & Search
**Labels**: `scripts`, `ingestion`, `vectordb`
**Blocked By**: ARCRAG-06

#### Description
As a developer, I want a script that generates embeddings for index entries and upserts them into Qdrant, so that the search_index tool can query them.

#### Acceptance Criteria
- [ ] Given `arcpro_index.json` exists, when the script runs, then it creates a Qdrant collection `arcgis_docs` with appropriate vector dimensions
- [ ] Given index entries, when they are embedded, then page-level entries use `"{title} - {summary}"` as embedding text
- [ ] Given index entries, when they are embedded, then section-level entries use `"{title} > {heading} - {brief_text}"` as embedding text
- [ ] Given each entry, when it is upserted, then its payload includes: `url`, `title`, `section`, `breadcrumb`, `source` (arcpro|arcmap), `type` (page|section), `images`
- [ ] Given 20K entries, when the script runs, then it batches upserts (100 at a time) and completes without OOM
- [ ] Given the collection already exists, when the script runs with `--recreate`, then it drops and recreates the collection

#### Technical Notes
- File: `scripts/load_qdrant.py`
- Embedding model: configurable via env var `EMBEDDING_MODEL` (default: `openai/text-embedding-3-small` via OpenRouter)
- Batch embedding: 100 texts per API call
- Qdrant collection config: cosine distance, vector size matching embedding model output
- Add a `--dry-run` flag that shows what would be upserted without calling APIs

---

### ARCRAG-08: search_index Tool — Qdrant Semantic Search

**Type**: Feature
**Jira Type**: Story
**Priority**: High
**Complexity**: Medium
**Phase**: 2 — Index & Search
**Labels**: `backend`, `tools`, `vectordb`
**Blocked By**: ARCRAG-07

#### Description
As a student, I want the agent to find the most relevant documentation pages for my question, so that it fetches the right content to answer me.

#### Acceptance Criteria
- [ ] Given a student query, when `search_index` is called, then it embeds the query and searches Qdrant returning top 5-10 results
- [ ] Given results are returned, when I inspect them, then each result includes: URL, title, summary, breadcrumb, source, and relevance score
- [ ] Given a query mentioning "ArcMap", when `search_index` is called, then results from `source: arcmap` are prioritized
- [ ] Given a query with an exact tool name like "Buffer", when `search_index` is called, then the exact tool page appears in top 3 results
- [ ] Given Qdrant is unreachable, when `search_index` is called, then it returns a clear error message

#### Technical Notes
- File: `backend/src/tools/search.py`
- Use same embedding model as ingestion (consistency critical)
- Return Pydantic model: `SearchResults(results: list[SearchResult])` where `SearchResult` has `url, title, summary, breadcrumb, source, score`
- Consider adding metadata filter: `source` field for ArcPro vs ArcMap filtering
- Future: add BM25/keyword hybrid search for exact tool name matching

---

### ARCRAG-09: Agent Search → Fetch → Answer Flow

**Type**: Feature
**Jira Type**: Story
**Priority**: High
**Complexity**: Small
**Phase**: 2 — Index & Search
**Labels**: `backend`, `agent`, `integration`
**Blocked By**: ARCRAG-08, ARCRAG-03

#### Description
As a student, I want to ask any GIS question and have the agent automatically search the index, fetch the relevant page, and generate an answer, so that I get accurate documentation-grounded responses.

#### Acceptance Criteria
- [ ] Given a student asks "How do I create a buffer?", when the agent processes the query, then it calls `search_index` first, then `fetch_page` on the top result, then generates an answer
- [ ] Given the agent generates an answer, when I read it, then it includes content from the fetched page (not hallucinated)
- [ ] Given the agent generates an answer, when I read it, then it includes markdown image references and a source citation
- [ ] Given the search returns no relevant results (low scores), when the agent processes this, then it tells the student it couldn't find relevant documentation
- [ ] Given 10 diverse GIS questions, when tested, then >8/10 return the correct documentation page in the search results

#### Technical Notes
- Update system prompt to instruct the agent on the search → fetch → answer workflow
- Agent should use search_index first, evaluate results, then fetch_page on the best 1-2 URLs
- System prompt should instruct: include `![alt](url)` for relevant images, include `Source: [title](url)` citation


---

## Phase 3: Frontend

---

### ARCRAG-10: FastAPI Server with AG-UI Endpoint

**Type**: Technical
**Jira Type**: Task
**Priority**: High
**Complexity**: Medium
**Phase**: 3 — Frontend
**Labels**: `backend`, `api`
**Blocked By**: ARCRAG-09

#### Description
As a developer, I want the PydanticAI agent exposed via a FastAPI server using the AG-UI protocol, so that CopilotKit can connect to it.

#### Acceptance Criteria
- [ ] Given the FastAPI server is running, when I hit `GET /health`, then it returns `{"status": "ok", "qdrant": "connected", "model": "<configured model>"}`
- [ ] Given the server is running, when CopilotKit sends a POST to the AG-UI endpoint, then it receives SSE events (TextMessageStart, TextMessageContent, TextMessageEnd)
- [ ] Given the agent uses tools, when a tool is called, then ToolCallStart/ToolCallEnd events are emitted in the SSE stream
- [ ] Given CORS is configured, when a request comes from the frontend origin, then it is allowed; other origins are rejected
- [ ] Given the server starts, when I check logs, then it shows the configured model and Qdrant connection status

#### Technical Notes
- File: `backend/src/main.py`
- Use PydanticAI's AG-UI integration (see `pydantic.dev/docs/ai/integrations/ui/ag-ui/`)
- CORS: allow `NEXT_PUBLIC_BACKEND_URL` origin
- Run with: `uvicorn backend.src.main:app --host 0.0.0.0 --port 8000`
- Add to `docker-compose.yml` as a service

---

### ARCRAG-11: Next.js App with CopilotKit Chat UI

**Type**: Feature
**Jira Type**: Story
**Priority**: High
**Complexity**: Medium
**Phase**: 3 — Frontend
**Labels**: `frontend`, `ui`
**Blocked By**: ARCRAG-10

#### Description
As a student, I want a clean chat interface where I can type GIS questions and see streamed answers, so that I can get help without navigating complex documentation.

#### Acceptance Criteria
- [ ] Given I open the app in a browser, when the page loads, then I see a CopilotKit sidebar (or popup) chat interface
- [ ] Given I type a question and press enter, when the agent responds, then the answer streams in token-by-token (not all at once)
- [ ] Given the agent is processing, when I look at the UI, then I see a loading/thinking indicator
- [ ] Given the app is styled, when I view it on desktop, then it looks clean and student-friendly (not raw unstyled HTML)
- [ ] Given the CopilotKit provider is configured, when the app starts, then it connects to `/api/copilotkit` which proxies to the backend

#### Technical Notes
- Files: `frontend/src/app/page.tsx`, `frontend/src/app/layout.tsx`, `frontend/src/app/api/copilotkit/route.ts`
- Use `<CopilotSidebar>` component for persistent chat panel
- Copilot Runtime API route proxies to `NEXT_PUBLIC_BACKEND_URL` AG-UI endpoint
- Tailwind CSS for styling
- Title/branding: "ArcGIS Documentation Guide" or similar

---

### ARCRAG-12: Inline Image Rendering in Chat

**Type**: Feature
**Jira Type**: Story
**Priority**: High
**Complexity**: Small
**Phase**: 3 — Frontend
**Labels**: `frontend`, `ui`
**Blocked By**: ARCRAG-11

#### Description
As a student, I want to see documentation screenshots and diagrams inline in the chat answers, so that I can visually understand the tools and workflows.

#### Acceptance Criteria
- [ ] Given the agent includes `![alt text](image_url)` in its response, when rendered in the chat, then the image displays inline with the text
- [ ] Given an image is rendered, when I look at it, then it has max-width constraint (doesn't overflow the chat), rounded corners, and alt text as caption
- [ ] Given an image fails to load (broken URL), when rendered, then it shows the alt text as fallback (not a broken image icon)
- [ ] Given an image is displayed, when I click on it, then it opens in a larger view (lightbox or new tab)

#### Technical Notes
- Override the `img` component in CopilotKit's markdown renderer
- File: `frontend/src/components/DocumentationChat.tsx`
- Use Tailwind classes: `max-w-full rounded-lg cursor-pointer`
- Consider `next/image` for optimization, but external URLs may need `remotePatterns` config in `next.config.js`

---

### ARCRAG-13: Source Citations & Links

**Type**: Feature
**Jira Type**: Story
**Priority**: Medium
**Complexity**: Small
**Phase**: 3 — Frontend
**Labels**: `frontend`, `ui`
**Blocked By**: ARCRAG-11

#### Description
As a student, I want each answer to include a clickable link to the original documentation page, so that I can read more context if needed.

#### Acceptance Criteria
- [ ] Given the agent includes a source link in its response, when rendered, then it appears as a clickable hyperlink
- [ ] Given I click a source link, when the browser navigates, then it opens the Esri documentation page in a new tab
- [ ] Given every answer from the agent, when I read it, then it includes at least one source citation at the end

#### Technical Notes
- Agent system prompt instructs: always end with `**Source:** [Page Title](url)`
- Links rendered via standard markdown `[text](url)` — CopilotKit handles this natively
- Add `target="_blank"` via markdown link component override

---

### ARCRAG-14: Suggestion Pills for Common Queries

**Type**: Enhancement
**Jira Type**: Story
**Priority**: Low
**Complexity**: Small
**Phase**: 3 — Frontend
**Labels**: `frontend`, `ux`
**Blocked By**: ARCRAG-11

#### Description
As a student, I want to see suggested questions I can click on, so that I know what kinds of things I can ask the agent.

#### Acceptance Criteria
- [x] Given the chat is empty (no messages yet), when the page loads, then I see 4-6 suggestion pills/buttons with example questions
- [x] Given I click a suggestion pill, when it activates, then the question is sent to the agent as if I typed it
- [x] Given the suggestions shown, when I read them, then they cover a mix of ArcGIS Pro and ArcMap topics

#### Technical Notes
- Use CopilotKit's `useConfigureSuggestions` hook or custom initial message component
- Example suggestions: "How do I create a buffer in ArcGIS Pro?", "What is a geodatabase?", "How to export a map to PDF?", "How do I georeference in ArcMap?", "What's the difference between Clip and Intersect?", "How to use ArcPy for batch processing?"


---

## Phase 4: Full Index & Deployment

---

### ARCRAG-15: Full ArcGIS Pro Index Ingestion

**Type**: Technical
**Jira Type**: Task
**Priority**: High
**Complexity**: Large
**Phase**: 4 — Full Index & Deployment
**Labels**: `scripts`, `ingestion`, `vectordb`
**Blocked By**: ARCRAG-07, ARCRAG-09

#### Description
As a developer, I want to run the full ingestion pipeline against all ArcGIS Pro documentation pages, so that students can ask about any ArcGIS Pro topic.

#### Acceptance Criteria
- [ ] Given the sitemap parser has collected all ArcGIS Pro URLs, when the index builder runs to completion, then `arcpro_index.json` contains entries for all accessible pages
- [ ] Given the index JSON is complete, when the Qdrant loader runs, then all page-level and section-level entries are upserted (~15K-20K vectors)
- [ ] Given the full index is loaded, when I search for obscure tools (e.g., "Zonal Statistics as Table"), then the correct page appears in top 5 results
- [ ] Given the ingestion takes hours, when it is interrupted, then it can resume from the checkpoint without re-processing completed pages
- [ ] Given the full run completes, when I check Qdrant dashboard, then the collection shows the expected vector count

#### Technical Notes
- Expected runtime: 8-24 hours at 1-2 req/sec for ~30K-50K pages
- Run on a machine with stable internet; use `screen` or `tmux` for long-running process
- Monitor: log progress every 100 pages, track success/failure counts
- Embedding cost estimate: ~$5-15 for 20K entries via OpenRouter

---

### ARCRAG-16: Full ArcMap Index Ingestion

**Type**: Technical
**Jira Type**: Task
**Priority**: High
**Complexity**: Medium
**Phase**: 4 — Full Index & Deployment
**Labels**: `scripts`, `ingestion`, `vectordb`
**Blocked By**: ARCRAG-07, ARCRAG-09

#### Description
As a developer, I want to run the full ingestion pipeline against all ArcMap documentation pages, so that students can ask about ArcMap workflows.

#### Acceptance Criteria
- [ ] Given the sitemap parser has collected all ArcMap URLs, when the index builder runs, then `arcmap_index.json` contains entries for all accessible pages
- [ ] Given the index JSON is complete, when the Qdrant loader runs, then all entries are upserted into the same `arcgis_docs` collection with `source: arcmap`
- [ ] Given the full index is loaded, when I search for "georeferencing ArcMap", then ArcMap-specific pages appear (not ArcGIS Pro pages)
- [ ] Given ArcMap docs are static/archived, when pages fail to load, then failures are logged for review (may indicate docs being taken down)

#### Technical Notes
- Expected: ~5K-10K pages, faster than ArcGIS Pro run
- Same scripts as ARCRAG-15, just different `--source arcmap` flag
- Priority: run this early since desktop.arcgis.com may be taken down (ArcMap retired March 2026)
- Consider saving raw HTML as a local backup during scraping

---

### ARCRAG-17: Production Docker Compose

**Type**: Technical
**Jira Type**: Task
**Priority**: High
**Complexity**: Medium
**Phase**: 4 — Full Index & Deployment
**Labels**: `infrastructure`, `devops`, `deployment`
**Blocked By**: ARCRAG-10, ARCRAG-11

#### Description
As a developer, I want a production Docker Compose configuration that runs all services, so that I can deploy the full stack to my server.

#### Acceptance Criteria
- [ ] Given `docker compose -f docker-compose.prod.yml up`, when all services start, then Qdrant, FastAPI backend, and Next.js frontend are all running
- [ ] Given the production config, when Qdrant restarts, then data is persisted via a named Docker volume
- [ ] Given the production config, when the backend starts, then it reads `.env` for API keys and configuration
- [ ] Given the production config, when I check resource usage, then each service has memory limits set to prevent OOM on the server
- [ ] Given the frontend is built, when it runs in production mode, then it serves optimized static assets (not dev mode)

#### Technical Notes
- File: `docker-compose.prod.yml`
- Services: `qdrant`, `backend`, `frontend`
- Backend Dockerfile: Python 3.11 slim, install deps, run uvicorn
- Frontend Dockerfile: Node 20, `npm run build`, `npm start`
- Qdrant: `qdrant/qdrant:latest` with volume mount
- Network: all services on same Docker network, only frontend/proxy exposed externally

---

### ARCRAG-18: Reverse Proxy with HTTPS

**Type**: Technical
**Jira Type**: Task
**Priority**: High
**Complexity**: Small
**Phase**: 4 — Full Index & Deployment
**Labels**: `infrastructure`, `devops`, `deployment`
**Blocked By**: ARCRAG-17

#### Description
As a developer, I want HTTPS termination and routing via a reverse proxy, so that the application is secure and accessible via a domain name.

#### Acceptance Criteria
- [ ] Given a domain name is configured, when a student visits `https://domain.com`, then they see the frontend with a valid SSL certificate
- [ ] Given the proxy is running, when the frontend makes API calls, then they are routed to the backend service internally
- [ ] Given HTTP traffic, when a request comes in on port 80, then it is redirected to HTTPS (port 443)
- [ ] Given the proxy config, when I inspect it, then it includes basic rate limiting (20 req/min per IP on the chat endpoint)

#### Technical Notes
- Use Caddy (simplest — automatic HTTPS via Let's Encrypt) or Nginx + certbot
- Caddy config: `domain.com { reverse_proxy frontend:3000 }` + `/api/*` routes to backend
- Add to `docker-compose.prod.yml` as a service
- Rate limiting: Caddy has `rate_limit` directive; Nginx uses `limit_req_zone`

---

### ARCRAG-19: End-to-End Validation & Quality Check

**Type**: Technical
**Jira Type**: Task
**Priority**: Medium
**Complexity**: Medium
**Phase**: 4 — Full Index & Deployment
**Labels**: `testing`, `quality`
**Blocked By**: ARCRAG-15, ARCRAG-16, ARCRAG-18

#### Description
As a developer, I want to validate the deployed system against a test suite of representative queries, so that I'm confident it works for students.

#### Acceptance Criteria
- [ ] Given a test suite of 20 diverse GIS questions, when run against the deployed system, then >80% return answers that address the actual question
- [ ] Given the test suite, when answers are inspected, then >60% include at least one relevant inline image
- [ ] Given the test suite, when source links are checked, then 100% point to real, accessible documentation pages
- [ ] Given a typical query, when timed end-to-end, then response completes in <10 seconds
- [ ] Given edge cases (typos, vague questions, non-GIS questions), when tested, then the agent handles them gracefully (asks for clarification or states it can't help)

#### Technical Notes
- Create `tests/e2e_queries.json` with 20 test queries + expected page URLs
- Script: `scripts/validate.py` that runs queries and checks results
- Manual review needed for answer quality (automated checks for: has images, has source link, response time)
- Edge cases to test: "asdfgh", "what's the weather?", "buffer" (single word), "How do I do spatial analysis?" (very broad)


---

## Summary

### Story Overview

| ID | Title | Type | Priority | Complexity | Phase | Blocked By | Status |
|----|-------|------|----------|------------|-------|------------|--------|
| ARCRAG-01 | Project Scaffolding & Docker Infrastructure | Task | High | Small | 1 | — | ✅ Completed |
| ARCRAG-02 | PydanticAI Agent with OpenRouter Connection | Story | High | Medium | 1 | ARCRAG-01 | ✅ Completed |
| ARCRAG-03 | fetch_page Tool — Live Documentation Scraper | Story | High | Medium | 1 | ARCRAG-02 | ✅ Completed |
| ARCRAG-04 | Agent Answers Questions Using Hardcoded URL | Story | Medium | Small | 1 | ARCRAG-03 | ✅ Completed |
| ARCRAG-05 | Sitemap Parser Script | Task | High | Medium | 2 | ARCRAG-01 | ✅ Completed |
| ARCRAG-06 | Index Builder Script — Page Metadata Scraper | Task | High | Large | 2 | ARCRAG-05 | ✅ Completed |
| ARCRAG-07 | Qdrant Loader Script — Embed & Upsert | Task | High | Medium | 2 | ARCRAG-06 | ✅ Completed |
| ARCRAG-08 | search_index Tool — Qdrant Semantic Search | Story | High | Medium | 2 | ARCRAG-07 | ✅ Completed |
| ARCRAG-09 | Agent Search → Fetch → Answer Flow | Story | High | Small | 2 | ARCRAG-08, ARCRAG-03 | ✅ Completed |
| ARCRAG-10 | FastAPI Server with AG-UI Endpoint | Task | High | Medium | 3 | ARCRAG-09 | ✅ Completed |
| ARCRAG-11 | Next.js App with CopilotKit Chat UI | Story | High | Medium | 3 | ARCRAG-10 | ✅ Completed |
| ARCRAG-12 | Inline Image Rendering in Chat | Story | High | Small | 3 | ARCRAG-11 | ✅ Completed |
| ARCRAG-13 | Source Citations & Links | Story | Medium | Small | 3 | ARCRAG-11 | ✅ Completed |
| ARCRAG-14 | Suggestion Pills for Common Queries | Story | Low | Small | 3 | ARCRAG-11 | ✅ Completed |
| ARCRAG-15 | Full ArcGIS Pro Index Ingestion | Task | High | Large | 4 | ARCRAG-07, ARCRAG-09 | ⏳ In Progress (VPS run pending) |
| ARCRAG-16 | Full ArcMap Index Ingestion | Task | High | Medium | 4 | ARCRAG-07, ARCRAG-09 | Pending |
| ARCRAG-17 | Production Docker Compose | Task | High | Medium | 4 | ARCRAG-10, ARCRAG-11 | Pending |
| ARCRAG-18 | Reverse Proxy with HTTPS | Task | High | Small | 4 | ARCRAG-17 | Pending |
| ARCRAG-19 | End-to-End Validation & Quality Check | Task | Medium | Medium | 4 | ARCRAG-15, ARCRAG-16, ARCRAG-18 | Pending |

### Dependency Graph

```
ARCRAG-01 (Scaffolding)
├── ARCRAG-02 (Agent + OpenRouter)
│   └── ARCRAG-03 (fetch_page tool)
│       ├── ARCRAG-04 (Hardcoded URL test)
│       └── ARCRAG-09 (Search → Fetch → Answer) ←── also depends on ARCRAG-08
│           ├── ARCRAG-10 (FastAPI AG-UI)
│           │   └── ARCRAG-11 (CopilotKit UI)
│           │       ├── ARCRAG-12 (Inline images)
│           │       ├── ARCRAG-13 (Source citations)
│           │       └── ARCRAG-14 (Suggestion pills)
│           ├── ARCRAG-15 (Full Pro ingestion)
│           └── ARCRAG-16 (Full ArcMap ingestion)
├── ARCRAG-05 (Sitemap parser)
│   └── ARCRAG-06 (Index builder)
│       └── ARCRAG-07 (Qdrant loader)
│           └── ARCRAG-08 (search_index tool)
│
ARCRAG-17 (Prod Docker) ←── ARCRAG-10, ARCRAG-11
└── ARCRAG-18 (HTTPS proxy)
    └── ARCRAG-19 (E2E validation) ←── also depends on ARCRAG-15, ARCRAG-16
```

### Totals
- **19 stories** across 4 phases
- **4 phases**: Foundation → Index & Search → Frontend → Full Index & Deployment
- **Estimated effort**: ~4 weeks (1 developer)
- **Critical path**: ARCRAG-01 → 02 → 03 → 09 → 10 → 11 (longest dependency chain)

---

Atlassian MCP is not configured. To push stories to Jira automatically:
1. Get an API token from https://id.atlassian.com/manage/api-tokens
2. Configure `.mcp.json` with Atlassian MCP server credentials
3. Re-run this command with `--project` and `--epic` flags
