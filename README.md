# ArcGIS Documentation RAG Agent

A multi-modal RAG (Retrieval-Augmented Generation) agent that serves as an interactive documentation guide for students learning ArcGIS Pro and ArcMap. Students ask natural language questions and receive detailed answers with inline screenshots, diagrams, and source citations pulled directly from Esri's official documentation.

## How It Works

The system uses a **"thin index + live fetch"** architecture:

1. A lightweight semantic index (~15K–20K entries) is built by scraping page titles, summaries, and section headings from Esri's documentation sitemaps
2. These entries are embedded and stored in a Qdrant vector database
3. At query time, the agent searches the index to find the most relevant documentation pages
4. The agent then fetches the full page content live from Esri's servers
5. The LLM generates an answer grounded in the fetched content, including inline images and source citations

This avoids the cost and complexity of pre-chunking 300K+ documentation pages while still delivering accurate, image-rich answers.

```
┌──────────────────────────────────────────────────────────┐
│                      FRONTEND                            │
│  Next.js 15 + CopilotKit (CopilotSidebar)               │
│  /api/copilotkit → Copilot Runtime → AG-UI to backend   │
└────────────────────────┬─────────────────────────────────┘
                         │ AG-UI (SSE)
┌────────────────────────▼─────────────────────────────────┐
│                      BACKEND                             │
│  FastAPI + PydanticAI Agent                              │
│                                                          │
│  Tools:                                                  │
│    search_index(query) → Qdrant semantic search          │
│    fetch_page(url) → Live scrape + parse HTML            │
│                                                          │
│  LLM: OpenRouter (configurable model)                    │
└──────────┬────────────────────────────┬──────────────────┘
           │                            │
┌──────────▼──────────┐   ┌────────────▼─────────────────┐
│      Qdrant         │   │  Live Documentation Sites     │
│  (Docker, port 6333)│   │  pro.arcgis.com               │
│                     │   │  desktop.arcgis.com            │
│  Collection:        │   └──────────────────────────────┘
│  arcgis_docs        │
└─────────────────────┘
```

## Features

- **Semantic search** across both ArcGIS Pro and ArcMap documentation indexes
- **Live page fetching** — answers are grounded in real, up-to-date documentation content
- **Inline image rendering** — screenshots and diagrams from documentation display directly in chat
- **Source citations** — every answer includes a clickable link back to the original Esri documentation page
- **Suggestion pills** — clickable starter questions for common GIS topics
- **Model flexibility** — swap LLM models via OpenRouter without code changes
- **Source-aware filtering** — queries mentioning "ArcMap" automatically filter to ArcMap documentation results
- **TTL caching** — recently fetched pages are cached for 5 minutes to avoid redundant requests

## Tech Stack

### Backend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Agent framework | PydanticAI | Agent + tools definition, type-safe |
| Web framework | FastAPI | AG-UI endpoint, health checks |
| HTTP client | httpx | Async page fetching |
| HTML parser | BeautifulSoup4 | Documentation page parsing |
| Vector DB | Qdrant | Semantic search index |
| Vector DB client | qdrant-client | Search and upsert operations |
| LLM provider | OpenRouter | Model-agnostic LLM access |
| Embeddings | OpenRouter (`text-embedding-3-small`) | Query and document embedding |
| Caching | cachetools (TTLCache) | In-memory page cache (100 entries, 5min TTL) |
| ASGI server | uvicorn | Production server |

### Frontend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | Next.js 15 (App Router) | React framework |
| AI UI | @copilotkit/react-core, @copilotkit/react-ui | Chat interface + AG-UI client |
| Runtime | @copilotkit/runtime | CopilotKit server-side runtime |
| Styling | Tailwind CSS 4 | UI styling |
| Language | TypeScript | Type safety |

### Infrastructure

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Vector database | Qdrant (Docker) | Semantic search index |
| Containerization | Docker Compose | Service orchestration |
| Reverse proxy | Caddy | HTTPS termination, rate limiting |

### Ingestion Scripts

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Sitemap parsing | xml.etree.ElementTree | Parse sitemap XML files |
| Page scraping | httpx + BeautifulSoup4 | Extract page metadata |
| Embedding | OpenRouter API | Generate vectors |

## Project Structure

```
arcpro-docs/
├── docker-compose.yml          # Development compose (Qdrant + backend + frontend)
├── docker-compose.prod.yml     # Production compose (with init containers + healthchecks)
├── deploy/
│   └── Caddyfile               # Reverse proxy config (HTTPS + rate limiting)
├── .env.example                # Environment variable template
│
├── backend/
│   ├── Dockerfile              # Python 3.11 slim image
│   ├── pyproject.toml          # Python project config + dependencies
│   ├── uv.lock                 # Python lockfile
│   └── src/
│       ├── main.py             # FastAPI app — /health and /ag-ui endpoints
│       ├── agent.py            # PydanticAI agent definition with 3 tools
│       ├── embed.py            # OpenRouter embeddings API wrapper
│       └── tools/
│           ├── search.py       # search_index — Qdrant semantic search with dedup
│           ├── fetch.py        # fetch_page — async HTML scraper with TTL cache
│           └── lookup.py       # lookup_url — hardcoded URL lookup (legacy)
│
├── frontend/
│   ├── Dockerfile              # Multi-stage build (deps → build → standalone)
│   ├── package.json            # Node dependencies + scripts
│   ├── next.config.js          # Next.js config (standalone output, image domains)
│   └── src/
│       ├── app/
│       │   ├── page.tsx        # Main page with CopilotSidebar
│       │   ├── layout.tsx      # Root layout
│       │   ├── globals.css     # Global styles
│       │   └── api/copilotkit/
│       │       └── route.ts    # CopilotKit API route → AG-UI proxy
│       └── components/
│           ├── ChatImage.tsx   # Custom image renderer (clickable, rounded)
│           ├── ChatLink.tsx    # Custom link renderer (opens in new tab)
│           ├── ChatSuggestions.tsx  # Suggestion pills for common queries
│           └── markdownComponents.tsx  # Markdown component overrides
│
├── scripts/
│   ├── parse_sitemaps.py       # Fetch + parse ArcGIS sitemap URLs
│   ├── build_index.py          # Scrape page metadata → JSON index
│   ├── load_qdrant.py          # Embed + upsert index into Qdrant
│   └── init.sh                 # Docker init: wait for Qdrant, run build + load
│
├── data/
│   └── .gitkeep                # Index JSON files (generated, not committed)
│
└── tests/
    └── e2e_queries.json        # 20-query E2E validation corpus
```

## Configuration

Copy `.env.example` to `backend/.env` and fill in your API keys:

```bash
cp .env.example backend/.env
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENROUTER_API_KEY` | OpenRouter API key for LLM access | *(required)* |
| `OPENROUTER_MODEL` | LLM model identifier | `anthropic/claude-3.5-sonnet` |
| `EMBEDDING_MODEL` | Embedding model identifier | `openai/text-embedding-3-small` |
| `EMBEDDING_API_KEY` | API key for embeddings (falls back to `OPENROUTER_API_KEY`) | — |
| `QDRANT_URL` | Qdrant connection URL | `http://localhost:6333` |
| `QDRANT_COLLECTION` | Qdrant collection name | `arcgis_docs` |
| `BACKEND_HOST` | Backend bind address | `0.0.0.0` |
| `BACKEND_PORT` | Backend port | `8000` |
| `NEXT_PUBLIC_BACKEND_URL` | Backend URL for frontend API calls | `http://localhost:8000` |

### Caddy Variables (reverse proxy only)

| Variable | Description | Default |
|----------|-------------|---------|
| `CADDY_DOMAIN` | Domain name for HTTPS | `arcgis-docs.example.com` |
| `CADDY_EMAIL` | Email for Let's Encrypt certificate | `admin@example.com` |
| `CADDY_RATE_LIMIT_PER_MINUTE` | Rate limit on `/api/*` endpoints | `20` |

## Deployment

### Prerequisites

- Docker and Docker Compose v2+
- An OpenRouter API key ([openrouter.ai](https://openrouter.ai))
- (Production) A domain name pointed at your server

### Development (Local)

1. **Clone the repository and configure environment:**

   ```bash
   git clone <repo-url> && cd arcpro-docs
   cp .env.example backend/.env
   # Edit backend/.env with your API keys
   ```

2. **Start all services:**

   ```bash
   docker compose up
   ```

   This will:
   - Start Qdrant on port 6333
   - Run `arcrag-init` and `arcrag-init-arcmap` containers that parse sitemaps, build the index, and load it into Qdrant (skips if data already exists)
   - Start the FastAPI backend on port 8000
   - (Frontend must be run separately in dev mode — see below)

3. **Run the frontend in development mode:**

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

   The frontend will be available at `http://localhost:3000`.

4. **Access the application:**
   - Frontend: `http://localhost:3000`
   - Backend API: `http://localhost:8000`
   - Health check: `http://localhost:8000/health`
   - Qdrant dashboard: `http://localhost:6333/dashboard`

### Production

The production setup uses `docker-compose.prod.yml` which includes init containers for index ingestion, health checks, memory limits, and a standalone Next.js build. An external Caddy container handles HTTPS.

#### Step 1: Configure

```bash
cp .env.example backend/.env
# Edit backend/.env with production values
```

#### Step 2: Start the stack

```bash
docker compose -f docker-compose.prod.yml up -d
```

This starts:
- **arcrag-init** — one-shot container that ingests the ArcGIS Pro index (skips if already loaded)
- **arcrag-init-arcmap** — one-shot container that ingests the ArcMap index (runs after arcrag-init)
- **backend** — FastAPI server on port 8000 (1 GB memory limit)
- **frontend** — Next.js standalone build on port 3000 (512 MB memory limit)

The frontend is exposed on port 3000. All services communicate over the `arcrag-net` Docker network.

#### Step 3: Set up HTTPS reverse proxy

Run a Caddy container attached to the same Docker network:

```bash
docker run -d \
  --name caddy \
  --network arcrag-net \
  -p 80:80 -p 443:443 \
  -v /path/to/Caddyfile:/etc/caddy/Caddyfile \
  -v caddy_data:/data \
  -e CADDY_DOMAIN=your-domain.com \
  -e CADDY_EMAIL=your-email@example.com \
  -e CADDY_RATE_LIMIT_PER_MINUTE=20 \
  caddy:2-alpine
```

The included `deploy/Caddyfile` provides:
- Automatic HTTPS via Let's Encrypt
- HTTP → HTTPS redirect
- Reverse proxy to the frontend container
- Rate limiting (20 req/min) on `/api/*` endpoints

#### Step 4: Verify

```bash
# Check all services are healthy
docker compose -f docker-compose.prod.yml ps

# Test the health endpoint
curl https://your-domain.com/health  # (via proxy, or directly: curl http://localhost:8000/health)

# Test the frontend
curl -I https://your-domain.com
```

### Index Ingestion (Manual)

You can run the ingestion pipeline manually outside of Docker:

```bash
# 1. Parse sitemaps to get all documentation URLs
python scripts/parse_sitemaps.py --source arcpro
python scripts/parse_sitemaps.py --source arcmap

# 2. Build the index (scrape page metadata)
python scripts/build_index.py --source arcpro --concurrency 5 --delay 0.2
python scripts/build_index.py --source arcmap --concurrency 5 --delay 0.2

# 3. Load into Qdrant (embed + upsert)
python scripts/load_qdrant.py --source arcpro --batch-size 100
python scripts/load_qdrant.py --source arcmap --batch-size 100

# Dry run (no API calls, shows what would be loaded)
python scripts/load_qdrant.py --source arcpro --dry-run

# Recreate collection (drops existing data)
python scripts/load_qdrant.py --source arcpro --recreate
```

**Note:** Full ingestion of ArcGIS Pro (~30K–50K pages) can take 8–24 hours at 1–2 requests/second. Use `screen` or `tmux` for long-running sessions. The script saves checkpoints and can resume from where it left off.

### E2E Validation

Run the 20-query end-to-end validation suite against a running instance:

```bash
cd backend
python test_e2e.py
```

This tests:
- Answer relevance (does the agent address the actual question?)
- Image inclusion (do answers include relevant screenshots?)
- Source citation accuracy (do links point to real, accessible pages?)
- Response time (end-to-end < 10 seconds)
- Edge case handling (vague queries, non-GIS questions, typos)

## API Reference

### `GET /health`

Returns service health status.

```json
{
  "status": "ok",
  "qdrant": "connected",
  "model": "anthropic/claude-3.5-sonnet"
}
```

### `POST /ag-ui`

AG-UI protocol endpoint (SSE event stream). CopilotKit connects to this automatically. Not intended for direct client use.

### `POST /api/copilotkit`

Next.js API route that proxies to the backend AG-UI endpoint. Used by the CopilotKit frontend.

## Agent Tools

The PydanticAI agent has three registered tools:

### `search_index`

Searches the Qdrant vector database for documentation pages matching a query. Returns ranked results with URLs, titles, summaries, relevance scores, and source metadata. Automatically filters to ArcMap results when the query mentions "ArcMap".

### `fetch_page`

Fetches and parses a live ArcGIS documentation page. Returns structured content including text sections, image URLs with alt text, and code blocks. Results are cached in memory for 5 minutes.

### `lookup_url`

Looks up a hardcoded URL for common GIS topics. Used as a fallback when the semantic search doesn't return good results.

## Development

### Running Tests

```bash
# Backend unit/flow tests
cd backend
python -m pytest

# E2E validation (requires running instance with loaded index)
python test_e2e.py
```

### Rebuilding the Index

If Esri updates their documentation, re-run the ingestion pipeline:

```bash
# Rebuild from scratch
python scripts/load_qdrant.py --source arcpro --recreate
python scripts/load_qdrant.py --source arcmap --recreate
```

### Swapping LLM Models

Change `OPENROUTER_MODEL` in `backend/.env` and restart the backend:

```bash
OPENROUTER_MODEL=google/gemini-2.5-flash
```

No code changes needed — the model is read from the environment at startup.

## License

See [LICENSE](LICENSE) for details.
