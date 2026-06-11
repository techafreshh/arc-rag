import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langfuse import get_client
from pydantic_ai.ui.ag_ui import AGUIAdapter
from qdrant_client import QdrantClient
from starlette.requests import Request
from starlette.responses import Response

from src.agent import agent

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
FRONTEND_ORIGIN = os.getenv("NEXT_PUBLIC_BACKEND_URL", "http://localhost:3000")

app = FastAPI(title="ArcGIS Documentation RAG Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
def shutdown_event():
    langfuse = get_client()
    langfuse.flush()


@app.get("/health")
async def health():
    qdrant_status = "disconnected"
    try:
        client = QdrantClient(url=QDRANT_URL)
        client.get_collections()
        qdrant_status = "connected"
    except Exception:
        pass
    return {"status": "ok", "qdrant": qdrant_status, "model": OPENROUTER_MODEL}


@app.post("/ag-ui")
async def ag_ui_endpoint(request: Request) -> Response:
    return await AGUIAdapter.dispatch_request(request, agent=agent)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("BACKEND_HOST", "0.0.0.0")
    port = int(os.getenv("BACKEND_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
