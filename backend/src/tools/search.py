import os

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from src.embed import embed_query

load_dotenv()

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "arcgis_docs")

DEFAULT_TOP_K = 5
MAX_TOP_K = 20
DEFAULT_MIN_SCORE = 0.0


class SearchResult(BaseModel):
    url: str
    title: str
    section: str
    summary: str
    breadcrumb: list[str]
    source: str
    score: float


class SearchResults(BaseModel):
    results: list[SearchResult]
    error: str | None = None


ARCMAP_KEYWORDS = {"arcmap", "arc map", "arc-map"}


def detect_source_filter(query: str) -> str | None:
    lowered = query.lower()
    if any(kw in lowered for kw in ARCMAP_KEYWORDS):
        return "arcmap"
    return None


def dedupe_by_url(results: list[SearchResult]) -> list[SearchResult]:
    seen: dict[str, SearchResult] = {}
    for r in results:
        existing = seen.get(r.url)
        if existing is None or r.score > existing.score:
            seen[r.url] = r
    return sorted(seen.values(), key=lambda x: x.score, reverse=True)


async def search_index(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = DEFAULT_MIN_SCORE,
    source_filter: str | None = None,
) -> SearchResults:
    if not query or not query.strip():
        return SearchResults(results=[], error="Empty query")

    top_k = max(1, min(MAX_TOP_K, top_k))

    if not EMBEDDING_API_KEY:
        return SearchResults(results=[], error="EMBEDDING_API_KEY or OPENROUTER_API_KEY not set")

    if source_filter is None:
        source_filter = detect_source_filter(query)

    try:
        qdrant = QdrantClient(url=QDRANT_URL)
        qdrant.get_collections()
    except Exception as e:
        return SearchResults(results=[], error=f"Qdrant unreachable at {QDRANT_URL}: {e}")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            vector = await embed_query(client, query)
    except Exception as e:
        return SearchResults(results=[], error=f"Embedding failed: {e}")

    try:
        search_filter = None
        if source_filter:
            search_filter = Filter(must=[FieldCondition(key="source", match=MatchValue(value=source_filter))])

        hits = qdrant.search(
            collection_name=QDRANT_COLLECTION,
            query_vector=vector,
            limit=top_k * 2,
            score_threshold=min_score,
            query_filter=search_filter,
            with_payload=True,
        )
    except Exception as e:
        return SearchResults(results=[], error=f"Qdrant search failed: {e}")

    results = [
        SearchResult(
            url=h.payload.get("url", ""),
            title=h.payload.get("title", ""),
            section=h.payload.get("section", "") or "",
            summary=h.payload.get("summary", "") or h.payload.get("section", "") or h.payload.get("title", ""),
            breadcrumb=h.payload.get("breadcrumb", []),
            source=h.payload.get("source", ""),
            score=float(h.score),
        )
        for h in hits
    ]

    deduped = dedupe_by_url(results)[:top_k]
    return SearchResults(results=deduped)
