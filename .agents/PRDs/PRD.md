# Product Requirements Document: ArcGIS Documentation RAG Agent

## 1. Executive Summary

This product is a multi-modal RAG (Retrieval-Augmented Generation) agent that serves as an interactive documentation guide for students learning ArcGIS Pro and ArcMap. Students ask natural language questions and receive detailed answers with inline screenshots, diagrams, and supporting documentation pulled directly from Esri's official documentation.

The system uses a "thin index + live fetch" architecture: a lightweight semantic index (~15K-20K entries) routes queries to the right documentation pages, then the agent scrapes the full page content live at query time. This avoids the cost and complexity of pre-chunking 300K+ documentation pages while still delivering accurate, image-rich answers.

**MVP Goal:** A working web application where students can ask GIS questions and receive accurate answers with inline images from ArcGIS Pro and ArcMap documentation, deployed on a self-hosted server.

---

## 2. Mission

**Mission Statement:** Make ArcGIS Pro and ArcMap documentation accessible and understandable for students through an AI-powered conversational interface that provides answers with visual context.

**Core Principles:**
1. **Visual-first answers** — GIS is visual; answers must include relevant screenshots and diagrams
2. **Accuracy over speed** — Live-fetch from official docs ensures answers are grounded in real documentation
3. **Cost-efficient architecture** — Thin index + on-demand retrieval avoids massive embedding/storage costs
4. **Model flexibility** — OpenRouter integration allows switching between models without code changes
5. **Student-friendly** — Simple chat interface, no GIS expertise required to ask questions

---

## 3. Target Users

### Primary Persona: GIS Students
- University/college students taking GIS courses
- Learning ArcGIS Pro and/or ArcMap for coursework
- Varying technical comfort (beginner to intermediate)
- Need quick answers to "how do I do X?" questions
- Frustrated by navigating Esri's sprawling documentation

### Key Pain Points
- Esri documentation is vast (50K+ pages) and hard to navigate
- Students don't know the right terminology to search effectively
- Documentation lacks conversational explanations
- Hard to find the specific screenshot or step they need
- ArcMap docs are archived and may disappear

---

## 4. MVP Scope

### In Scope — Core Functionality
- [x] Semantic search across ArcGIS Pro documentation index
- [x] Semantic search across ArcMap documentation index
- [x] Live page scraping at query time for full content retrieval
- [x] Inline image rendering in chat responses (screenshots, diagrams)
- [x] Source citations with links back to official documentation
- [x] Conversational Q&A interface

### In Scope — Technical
- [x] PydanticAI agent with search_index and fetch_page tools
- [x] Qdrant vector database (Docker, self-hosted) for thin index
- [x] OpenRouter integration for model flexibility
- [x] AG-UI protocol for frontend-agent communication
- [x] FastAPI backend serving the agent
- [x] CopilotKit (Next.js) frontend with chat UI

### In Scope — Deployment
- [x] Docker Compose for all services
- [x] Self-hosted server deployment
- [x] Persistent Qdrant storage
- [x] HTTPS via reverse proxy

### Out of Scope (Future Phases)
- [ ] Image captioning via vision models (storing alt text only for MVP)
- [ ] ColPali/ColQwen visual embeddings for layout-aware retrieval
- [ ] User authentication and session history
- [ ] Feedback/rating system for answers
- [ ] Multi-language support
- [ ] Video tutorial retrieval
- [ ] ArcGIS Online / ArcGIS Enterprise documentation
- [ ] Custom fine-tuned embedding model
- [ ] Offline mode / PWA

---

## 5. User Stories

### Primary User Stories

1. **As a** GIS student, **I want to** ask "How do I create a buffer in ArcGIS Pro?" **so that** I get step-by-step instructions with screenshots of the tool dialog.
   - *Example:* Student sees the Buffer tool dialog screenshot, parameter explanations, and a code sample.

2. **As a** GIS student, **I want to** ask "What's the difference between Clip and Intersect?" **so that** I understand which tool to use for my assignment.
   - *Example:* Agent retrieves both tool pages, shows comparison with diagrams illustrating input/output differences.

3. **As a** GIS student, **I want to** ask about ArcMap-specific workflows **so that** I can complete assignments that still require ArcMap.
   - *Example:* "How do I georeference in ArcMap?" returns the ArcMap-specific procedure with UI screenshots.

4. **As a** GIS student, **I want to** see the actual screenshots from documentation **so that** I can visually match what I see on my screen.
   - *Example:* Answer includes inline images of the ArcGIS Pro ribbon, tool panes, and map outputs.

5. **As a** GIS student, **I want to** get Python/ArcPy code examples **so that** I can automate my geoprocessing workflows.
   - *Example:* "How do I run Buffer with ArcPy?" returns the exact syntax with a working code sample.

6. **As a** GIS student, **I want to** click through to the original documentation page **so that** I can read more context if needed.
   - *Example:* Each answer includes a "Source: Buffer (Analysis) — ArcGIS Pro Documentation" link.

### Technical User Stories

7. **As an** administrator, **I want to** switch the underlying LLM model via OpenRouter **so that** I can optimize for cost or quality without redeploying.
   - *Example:* Change `OPENROUTER_MODEL` env var from `anthropic/claude-3.5-sonnet` to `google/gemini-2.5-flash` and restart.

8. **As an** administrator, **I want to** re-run the index builder **so that** new documentation pages are included when Esri updates their docs.
   - *Example:* Run `python scripts/build_index.py --source arcpro` to refresh the ArcGIS Pro index.

---

## 6. Core Architecture & Patterns

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         FRONTEND                             │
│  Next.js + CopilotKit (CopilotSidebar)                     │
│  /api/copilotkit → Copilot Runtime → AG-UI to backend      │
└─────────────────────────┬───────────────────────────────────┘
                          │ AG-UI (SSE)
┌─────────────────────────▼───────────────────────────────────┐
│                         BACKEND                              │
│  FastAPI + PydanticAI Agent                                 │
│                                                              │
│  Tools:                                                      │
│    search_index(query) → Qdrant semantic search             │
│    fetch_page(url) → Live scrape + parse HTML               │
│                                                              │
│  LLM: OpenRouter (configurable model)                       │
└──────────┬──────────────────────────────────┬───────────────┘
           │                                  │
┌──────────▼──────────┐          ┌───────────▼────────────────┐
│      Qdrant         │          │   Live Documentation Sites  │
│  (Docker, port 6333)│          │   pro.arcgis.com            │
│                     │          │   desktop.arcgis.com         │
│  Collections:       │          └────────────────────────────┘
│  - arcgis_docs      │
│    (page + section  │
│     level entries)  │
└─────────────────────┘
```

### Directory Structure

```
arcpro-docs/
├── docker-compose.yml
├── .env.example
├── frontend/
│   ├── package.json
│   ├── next.config.js
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx
│   │   │   ├── layout.tsx
│   │   │   └── api/copilotkit/route.ts
│   │   └── components/
│   │       └── DocumentationChat.tsx
│   └── tailwind.config.ts
├── backend/
│   ├── pyproject.toml
│   ├── src/
│   │   ├── main.py              # FastAPI app + AG-UI endpoint
│   │   ├── agent.py             # PydanticAI agent definition
│   │   ├── tools/
│   │   │   ├── search.py        # search_index tool
│   │   │   └── fetch.py         # fetch_page tool
│   │   └── config.py            # Settings (env vars)
│   └── Dockerfile
├── scripts/
│   ├── parse_sitemaps.py        # Fetch + parse sitemap URLs
│   ├── build_index.py           # Scrape pages + build JSON index
│   └── load_qdrant.py           # Embed + upsert into Qdrant
└── data/
    ├── arcpro_index.json        # Generated index data
    └── arcmap_index.json        # Generated index data
```

### Key Design Patterns

- **Thin Index + Live Fetch:** Index only metadata (titles, summaries, headings); fetch full content on demand
- **Tool-based Agent:** PydanticAI agent decides when to search and when to fetch based on query
- **AG-UI Protocol:** Standardized SSE event stream between frontend and agent
- **Section + Page dual indexing:** Page-level entries for routing, section-level for precision

---

## 7. Tools/Features

### Tool 1: `search_index`

**Purpose:** Find relevant documentation pages/sections for a student's query.

**Operations:**
- Embed the query using the same model used at index time
- Search Qdrant with metadata filtering (optional: filter by `source: arcpro|arcmap`)
- Return top 5-10 results with URL, title, summary, breadcrumb, and image references

**Key Features:**
- Hybrid search: dense vector similarity + optional keyword boost for tool names
- Metadata filtering by source (ArcGIS Pro vs ArcMap) and content type
- Returns both page-level and section-level matches

### Tool 2: `fetch_page`

**Purpose:** Retrieve full content from a documentation page at query time.

**Operations:**
- Fetch the HTML page via httpx (async)
- Parse with BeautifulSoup: extract main content, strip nav/footer
- Return structured content: text sections, code blocks, image URLs with alt text
- Handle errors gracefully (page not found, timeout)

**Key Features:**
- Async HTTP with timeout (10s)
- Caches recently fetched pages in memory (LRU, ~100 pages) to avoid re-fetching within a session
- Extracts images with their surrounding context (caption/alt text)
- Preserves code blocks separately for clean formatting

### Frontend Feature: Inline Image Rendering

**Purpose:** Display documentation screenshots and diagrams within chat answers.

**Implementation:**
- Agent includes markdown image syntax in responses: `![Buffer tool dialog](https://pro.arcgis.com/...)`
- CopilotKit's built-in react-markdown renders images natively
- Custom `img` component override for styling (max-width, rounded corners, click-to-expand)

---

## 8. Technology Stack

### Backend
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Agent Framework | PydanticAI | Agent + tools definition, type-safe |
| Web Framework | FastAPI | AG-UI endpoint, health checks |
| HTTP Client | httpx | Async page fetching |
| HTML Parser | BeautifulSoup4 | Documentation page parsing |
| Vector DB Client | qdrant-client | Search and upsert operations |
| LLM Provider | OpenRouter | Model-agnostic LLM access |
| Server | uvicorn | ASGI server |

### Frontend
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | Next.js (App Router) | React framework |
| AI UI | @copilotkit/react-core, @copilotkit/react-ui | Chat interface + AG-UI client |
| Styling | Tailwind CSS | UI styling |
| Markdown | react-markdown (built into CopilotKit) | Render answers with images |

### Infrastructure
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Vector Database | Qdrant (Docker) | Semantic search index |
| Containerization | Docker Compose | Service orchestration |
| Reverse Proxy | Caddy or Nginx | HTTPS, routing |

### Ingestion Scripts
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Sitemap Parsing | xml.etree.ElementTree | Parse sitemap XML |
| Page Scraping | httpx + BeautifulSoup4 | Extract page metadata |
| Embedding | OpenRouter (text-embedding model) or sentence-transformers | Generate vectors |

### Key Dependencies (Python)
```
pydantic-ai[openrouter]
fastapi
uvicorn
httpx
beautifulsoup4
qdrant-client
python-dotenv
```

### Key Dependencies (Node)
```
next
@copilotkit/react-core
@copilotkit/react-ui
tailwindcss
```

---

## 9. Security & Configuration

### Configuration (Environment Variables)

```env
# LLM
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet

# Embedding (can also go through OpenRouter or use local model)
EMBEDDING_MODEL=openai/text-embedding-3-small
EMBEDDING_API_KEY=sk-or-...

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=arcgis_docs

# Backend
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000

# Frontend
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

### Security Scope

**In Scope (MVP):**
- API key stored in environment variables (not in code)
- CORS restricted to frontend origin
- Rate limiting on the chat endpoint (basic, e.g., 20 req/min per IP)
- HTTPS via reverse proxy in production

**Out of Scope (MVP):**
- User authentication (open access for students)
- Session persistence / chat history storage
- API key rotation
- WAF / DDoS protection

### Deployment Considerations
- Qdrant data persisted via Docker volume (survives container restarts)
- OpenRouter API key is the only secret — stored in `.env`, never committed
- Backend and frontend run as separate containers behind a reverse proxy
- No student data is stored (stateless Q&A)

---

## 10. API Specification

### AG-UI Endpoint (Backend → Frontend)

**Endpoint:** `POST /ag-ui`

This follows the AG-UI protocol (SSE event stream). CopilotKit handles the wire format automatically.

**Events emitted:**
- `TextMessageStart` — Begin assistant message
- `TextMessageContent` — Streaming text tokens
- `TextMessageEnd` — End assistant message
- `ToolCallStart` / `ToolCallEnd` — Tool invocations (search_index, fetch_page)

### Health Check

**Endpoint:** `GET /health`

```json
{
  "status": "ok",
  "qdrant": "connected",
  "model": "anthropic/claude-3.5-sonnet"
}
```

### Copilot Runtime (Frontend API Route)

**Endpoint:** `POST /api/copilotkit`

Next.js API route that proxies to the backend AG-UI endpoint. Configured in the CopilotKit provider.

---

## 11. Success Criteria

### MVP Success Definition
A deployed web application where a student can ask a GIS question and receive an accurate, image-rich answer sourced from official Esri documentation within 10 seconds.

### Functional Requirements
- [x] Agent answers questions about ArcGIS Pro tools and workflows
- [x] Agent answers questions about ArcMap tools and workflows
- [x] Answers include inline images (screenshots, diagrams) when relevant
- [x] Answers include source links to official documentation
- [x] Answers include code examples when the question is about ArcPy/scripting
- [x] Agent correctly distinguishes between ArcGIS Pro and ArcMap when relevant
- [x] System handles page fetch failures gracefully (timeout, 404)

### Quality Indicators
- Answer relevance: >80% of answers address the student's actual question (manual evaluation on 20 test queries)
- Image inclusion: >60% of answers include at least one relevant image
- Source accuracy: 100% of cited sources link to real, accessible documentation pages
- Response time: <10 seconds for typical queries (search + fetch + generate)

### User Experience Goals
- Zero-friction: No login, no setup — just type and ask
- Visual: Answers feel like reading documentation, not a text wall
- Trustworthy: Every answer is grounded in official Esri docs with citations

---

## 12. Implementation Phases

### Phase 1: Foundation (Week 1)
**Goal:** Project scaffolding, infrastructure, and a working agent in the terminal.

**Deliverables:**
- [x] Project structure (frontend/, backend/, scripts/)
- [x] Docker Compose with Qdrant
- [x] PydanticAI agent with OpenRouter connection
- [x] `fetch_page` tool working (scrapes a doc page, returns structured content)
- [x] Agent answers questions using a hardcoded URL (no search yet)

**Validation:** Run agent from terminal, ask "What is the Buffer tool?", get a coherent answer with image URLs from the live page.

### Phase 2: Index & Search (Week 2)
**Goal:** Build the thin index and enable semantic search.

**Deliverables:**
- [x] Sitemap parser script (fetches all page URLs)
- [x] Index builder script (scrapes titles, summaries, sections, image refs)
- [x] Qdrant loader script (embeds and upserts)
- [x] `search_index` tool connected to Qdrant
- [x] Agent uses search → fetch → answer flow

**Validation:** Ask 10 diverse GIS questions, verify the correct documentation page is found and fetched in >8/10 cases.

### Phase 3: Frontend (Week 3)
**Goal:** CopilotKit frontend with inline images, deployed locally.

**Deliverables:**
- [x] Next.js app with CopilotKit sidebar
- [x] Copilot Runtime API route connected to backend
- [x] FastAPI AG-UI endpoint serving the agent
- [x] Inline image rendering in chat
- [x] Source citation links
- [x] Suggestion pills for common queries

**Validation:** Full end-to-end flow in browser — ask question, see streamed answer with images and source links.

### Phase 4: Full Index & Deployment (Week 4)
**Goal:** Complete index for both doc sets, deployed to self-hosted server.

**Deliverables:**
- [x] Full ArcGIS Pro index ingested (~15K-20K entries)
- [x] Full ArcMap index ingested (~5K-10K entries)
- [x] Production Docker Compose (all services)
- [x] Reverse proxy with HTTPS
- [x] Basic rate limiting
- [x] Deployed and accessible

**Validation:** Students can access the deployed URL and get accurate answers across the full breadth of both documentation sets.

---

## 13. Future Considerations

### Post-MVP Enhancements
- **Image captioning:** Use a vision model to generate rich descriptions of images at ingest time, improving search relevance for visual queries
- **ColPali/ColQwen:** Add visual embeddings for layout-heavy pages (ModelBuilder diagrams, complex tool dialogs)
- **Chat history:** Persist conversations so students can return to previous answers
- **Feedback loop:** Thumbs up/down on answers to identify weak spots in the index
- **Suggested follow-ups:** Agent suggests related topics after answering

### Integration Opportunities
- **LMS integration:** Embed as a widget in Canvas/Moodle course pages
- **ArcGIS Online docs:** Expand to cover web GIS documentation
- **Esri training materials:** Ingest Learn ArcGIS tutorials
- **Course-specific context:** Allow instructors to add course materials to the index

### Advanced Features
- **Multi-turn reasoning:** Agent remembers context across a conversation (e.g., "now how do I do that in ArcMap instead?")
- **Workflow generation:** Agent generates complete multi-step workflows (not just single tool answers)
- **Code generation:** Generate complete ArcPy scripts based on student descriptions
- **Comparison mode:** Side-by-side ArcGIS Pro vs ArcMap answers

---

## 14. Risks & Mitigations

### Risk 1: Live scraping reliability
**Risk:** Esri's documentation sites may rate-limit, block, or go down, breaking the fetch_page tool.
**Mitigation:** Implement LRU cache for recently fetched pages. Add retry logic with exponential backoff. Consider maintaining a local mirror as fallback for critical pages. Monitor fetch success rate.

### Risk 2: ArcMap documentation removal
**Risk:** Esri may take down `desktop.arcgis.com` since ArcMap is retired.
**Mitigation:** Download a full mirror of ArcMap docs as a backup. If the site goes down, switch fetch_page to read from the local mirror. Priority: do this early.

### Risk 3: Embedding/search quality
**Risk:** The thin index may not surface the right pages for ambiguous or poorly-worded student queries.
**Mitigation:** Dual-level indexing (page + section) increases recall. Add keyword/BM25 hybrid search for exact tool names. Evaluate with a test suite of 20+ queries and iterate on index content.

### Risk 4: OpenRouter cost/availability
**Risk:** High usage could lead to unexpected API costs, or OpenRouter could have outages.
**Mitigation:** Set spending limits in OpenRouter dashboard. Use cheaper models (Gemini Flash) for search embedding. Implement request rate limiting on the frontend. Have a fallback model configured.

### Risk 5: Image URL breakage
**Risk:** Stored image URLs in the index may break if Esri restructures their CDN or paths.
**Mitigation:** Images are fetched live with the page (not from stored URLs in the index). The index only stores image metadata for search relevance. Actual image URLs come from the live-fetched page HTML, so they're always current.

---

## 15. Appendix

### Key Dependencies & Links
- [PydanticAI Documentation](https://pydantic.dev/docs/ai/)
- [PydanticAI OpenRouter Integration](https://pydantic.dev/docs/ai/models/openrouter/)
- [CopilotKit PydanticAI Quickstart](https://docs.copilotkit.ai/pydantic-ai/quickstart/pydantic-ai)
- [AG-UI Protocol](https://docs.copilotkit.ai/pydantic-ai/ag-ui)
- [Qdrant Docker Quickstart](https://qdrant.tech/documentation/quickstart/)
- [OpenRouter API](https://openrouter.ai/docs)
- [ArcGIS Pro Documentation](https://pro.arcgis.com/en/pro-app/latest/)
- [ArcMap Documentation](https://desktop.arcgis.com/en/arcmap/latest/)
- [ArcGIS Pro Sitemap Index](https://pro.arcgis.com/sitemap_index.xml)
- [ArcMap Sitemap Index](http://desktop.arcgis.com/sitemap_index.xml)

### Documentation Sources
| Source | URL | Status | Estimated Pages |
|--------|-----|--------|-----------------|
| ArcGIS Pro | pro.arcgis.com/en/pro-app/latest/ | Active, updated | 30,000-50,000 |
| ArcMap | desktop.arcgis.com/en/arcmap/latest/ | Archived (retired March 2026) | 5,000-10,000 |

### Index Strategy Summary
| Level | What's indexed | Embedding content | Count (est.) |
|-------|---------------|-------------------|--------------|
| Page | Every documentation page | `"{title} - {summary}"` | ~5,000-8,000 |
| Section | H2/H3 sections within pages | `"{page_title} > {heading} - {brief_text}"` | ~10,000-15,000 |
