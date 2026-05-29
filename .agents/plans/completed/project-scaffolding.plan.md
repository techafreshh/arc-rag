# Plan: Project Scaffolding & Docker Infrastructure

## Summary

Set up the monorepo structure for the ArcGIS Documentation RAG Agent with Docker infrastructure (Qdrant), Python backend project configuration, and Node.js frontend project configuration. This is a greenfield project — all files are new. The goal is a working local development environment where `docker compose up` starts Qdrant, Python deps install via `pip install -e .`, and Node deps install via `npm install`.

## User Story

As a developer
I want to set up the monorepo structure and Docker infrastructure
So that all services can be developed and run locally

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | LOW |
| Systems Affected | Infrastructure, Backend, Frontend |
| Jira Issue | ARCRAG-01 |

---

## Patterns to Follow

### Greenfield — No Existing Patterns

This is the first code in the repository. Patterns established here will be followed by all subsequent stories. Key conventions to set:

- Python: src layout (`backend/src/`) with pyproject.toml
- Node: standard Next.js app directory (`frontend/src/app/`)
- Config: environment variables via `.env` file, documented in `.env.example`
- Infrastructure: Docker Compose for services

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `.gitignore` | CREATE | Prevent committing secrets, deps, and generated files |
| `.env.example` | CREATE | Document required environment variables |
| `docker-compose.yml` | CREATE | Qdrant service with persistent volume |
| `backend/pyproject.toml` | CREATE | Python project config and dependencies |
| `backend/src/__init__.py` | CREATE | Python package marker for src layout |
| `frontend/package.json` | CREATE | Node.js project config and dependencies |
| `scripts/.gitkeep` | CREATE | Preserve empty scripts directory in git |
| `data/.gitkeep` | CREATE | Preserve empty data directory in git |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Create .gitignore

- **File**: `.gitignore`
- **Action**: CREATE
- **Implement**: Standard Python + Node.js gitignore covering:
  - Python: `__pycache__/`, `*.egg-info/`, `.venv/`, `dist/`
  - Node: `node_modules/`, `.next/`, `out/`
  - Environment: `.env` (but NOT `.env.example`)
  - Data: `data/*.json` (generated index files, not .gitkeep)
  - IDE: `.vscode/`, `.idea/`
  - OS: `.DS_Store`, `Thumbs.db`
- **Validate**: File exists and `.env` is listed

### Task 2: Create .env.example

- **File**: `.env.example`
- **Action**: CREATE
- **Implement**: Template with all required env vars from the PRD technical notes:
  ```
  # LLM
  OPENROUTER_API_KEY=sk-or-...
  OPENROUTER_MODEL=anthropic/claude-3.5-sonnet

  # Embedding
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
- **Validate**: File exists with all keys listed above

### Task 3: Create docker-compose.yml

- **File**: `docker-compose.yml`
- **Action**: CREATE
- **Implement**: Single service for now (Qdrant only — backend/frontend containers come in later stories):
  ```yaml
  services:
    qdrant:
      image: qdrant/qdrant:v1.12.1
      ports:
        - "6333:6333"
        - "6334:6334"
      volumes:
        - qdrant_data:/qdrant/storage
      environment:
        - QDRANT__SERVICE__GRPC_PORT=6334

  volumes:
    qdrant_data:
  ```
  - Use a pinned version tag (not `latest`) for reproducibility
  - Port 6333 = REST API + dashboard, 6334 = gRPC
  - Named volume for data persistence across restarts
- **Validate**: `docker compose config` passes (validates YAML syntax). Then `docker compose up -d` starts Qdrant and `http://localhost:6333/dashboard` is accessible.

### Task 4: Create backend/pyproject.toml

- **File**: `backend/pyproject.toml`
- **Action**: CREATE
- **Implement**: Standard Python project config with:
  ```toml
  [build-system]
  requires = ["setuptools>=68.0", "wheel"]
  build-backend = "setuptools.build_meta"

  [project]
  name = "arcrag-backend"
  version = "0.1.0"
  requires-python = ">=3.11"
  dependencies = [
      "pydantic-ai[openrouter]",
      "fastapi",
      "uvicorn",
      "httpx",
      "beautifulsoup4",
      "qdrant-client",
      "python-dotenv",
  ]

  [tool.setuptools.packages.find]
  where = ["."]
  include = ["src*"]
  ```
- **Validate**: From `backend/`, run `pip install -e .` — should install all dependencies without errors.

### Task 5: Create backend/src/__init__.py

- **File**: `backend/src/__init__.py`
- **Action**: CREATE
- **Implement**: Empty file (package marker only)
- **Validate**: File exists (enables `from src import ...` within the backend)

### Task 6: Create frontend/package.json

- **File**: `frontend/package.json`
- **Action**: CREATE
- **Implement**: Minimal Next.js project config:
  ```json
  {
    "name": "arcrag-frontend",
    "version": "0.1.0",
    "private": true,
    "scripts": {
      "dev": "next dev",
      "build": "next build",
      "start": "next start",
      "lint": "next lint"
    },
    "dependencies": {
      "next": "^15.1.0",
      "@copilotkit/react-core": "^1.8.0",
      "@copilotkit/react-ui": "^1.8.0",
      "react": "^19.0.0",
      "react-dom": "^19.0.0"
    },
    "devDependencies": {
      "tailwindcss": "^4.0.0",
      "@tailwindcss/postcss": "^4.0.0",
      "typescript": "^5.7.0",
      "@types/node": "^22.0.0",
      "@types/react": "^19.0.0",
      "@types/react-dom": "^19.0.0"
    }
  }
  ```
  Note: Use caret ranges for flexibility during development. Exact pinning can be enforced via lockfile.
- **Validate**: From `frontend/`, run `npm install` — should install all dependencies without errors.

### Task 7: Create scripts/.gitkeep and data/.gitkeep

- **File**: `scripts/.gitkeep`, `data/.gitkeep`
- **Action**: CREATE
- **Implement**: Empty files to preserve directory structure in git
- **Validate**: Both directories exist and are tracked by git

---

## Validation

```bash
# Verify directory structure
ls frontend/ backend/ scripts/ data/

# Verify Docker
docker compose config
docker compose up -d
# Wait 5s, then check:
curl http://localhost:6333/dashboard
docker compose down

# Verify Python
cd backend
pip install -e .
cd ..

# Verify Node
cd frontend
npm install
cd ..
```

---

## Acceptance Criteria

- [ ] `docker compose up` starts Qdrant accessible at `localhost:6333/dashboard`
- [ ] Repo contains `frontend/`, `backend/`, `scripts/`, `data/` directories
- [ ] `.env.example` exists with all required configuration keys
- [ ] `pip install -e .` in `backend/` installs all Python dependencies
- [ ] `npm install` in `frontend/` installs all Node dependencies
