import os

import httpx
from dotenv import load_dotenv

load_dotenv()

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"
DEFAULT_TIMEOUT = 60.0


async def embed_batch(client: httpx.AsyncClient, texts: list[str], model: str | None = None) -> list[list[float]]:
    used_model = model or EMBEDDING_MODEL
    resp = await client.post(
        OPENROUTER_EMBEDDINGS_URL,
        json={"input": texts, "model": used_model},
        headers={"Authorization": f"Bearer {EMBEDDING_API_KEY}"},
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return [item["embedding"] for item in data["data"]]


async def embed_query(client: httpx.AsyncClient, text: str, model: str | None = None) -> list[float]:
    vectors = await embed_batch(client, [text], model=model)
    return vectors[0]
