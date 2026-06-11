import os

import httpx
from dotenv import load_dotenv

load_dotenv()

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"
DEFAULT_TIMEOUT = 60.0


async def embed_batch(client: httpx.AsyncClient, texts: list[str], model: str | None = None, max_retries: int = 5) -> list[list[float]]:
    import asyncio
    used_model = model or EMBEDDING_MODEL
    for attempt in range(max_retries):
        resp = await client.post(
            OPENROUTER_EMBEDDINGS_URL,
            json={"input": texts, "model": used_model},
            headers={"Authorization": f"Bearer {EMBEDDING_API_KEY}"},
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code == 429:
            wait = 2 ** attempt
            print(f"Rate limited, waiting {wait}s (attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        if "data" not in data:
            raise ValueError(f"Unexpected embeddings response: {data}")
        return [item["embedding"] for item in data["data"]]
    raise RuntimeError(f"Embedding failed after {max_retries} retries")


async def embed_query(client: httpx.AsyncClient, text: str, model: str | None = None) -> list[float]:
    vectors = await embed_batch(client, [text], model=model)
    return vectors[0]
