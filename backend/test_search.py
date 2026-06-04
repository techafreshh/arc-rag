import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from src.tools.search import (
    SearchResult, SearchResults, search_index,
    detect_source_filter, dedupe_by_url, DEFAULT_TOP_K, MAX_TOP_K,
)


async def test_import():
    print("--- Test 1: Import check ---")
    assert callable(search_index)
    assert callable(detect_source_filter)
    assert callable(dedupe_by_url)
    assert DEFAULT_TOP_K == 5
    assert MAX_TOP_K == 20
    print("PASS - module imports cleanly, constants set")


async def test_models():
    print("\n--- Test 2: Pydantic model schema ---")
    r = SearchResult(
        url="https://example.com", title="Test", section="",
        summary="A summary", breadcrumb=["a", "b"],
        source="arcpro", score=0.85,
    )
    assert r.url == "https://example.com"
    assert r.score == 0.85
    s = SearchResults(results=[r])
    assert s.error is None
    assert len(s.results) == 1
    print("PASS - SearchResult and SearchResults schemas valid")


async def test_source_detection():
    print("\n--- Test 3: Source keyword detection ---")
    assert detect_source_filter("How do I create a buffer in ArcMap?") == "arcmap"
    assert detect_source_filter("arcmap georeferencing") == "arcmap"
    assert detect_source_filter("Arc Map tutorial") == "arcmap"
    assert detect_source_filter("How do I create a buffer in ArcGIS Pro?") is None
    assert detect_source_filter("What is a geodatabase?") is None
    assert detect_source_filter("") is None
    print("PASS - detect_source_filter works for all cases")


async def test_dedupe():
    print("\n--- Test 4: URL deduplication ---")
    r1 = SearchResult(url="https://a", title="A", section="", summary="", breadcrumb=[], source="arcpro", score=0.9)
    r2 = SearchResult(url="https://a", title="A", section="intro", summary="intro sec", breadcrumb=[], source="arcpro", score=0.7)
    r3 = SearchResult(url="https://b", title="B", section="", summary="", breadcrumb=[], source="arcpro", score=0.8)
    deduped = dedupe_by_url([r1, r2, r3])
    assert len(deduped) == 2
    assert deduped[0].url == "https://a"
    assert deduped[0].score == 0.9
    assert deduped[1].url == "https://b"
    print("PASS - dedupe_by_url keeps best score per URL")


async def test_empty_query():
    print("\n--- Test 5: Empty query handling ---")
    result = await search_index("")
    assert result.error is not None
    assert "Empty" in result.error
    assert result.results == []
    print("PASS - empty query returns graceful error")


async def test_qdrant_unreachable():
    print("\n--- Test 6: Qdrant unreachable handling ---")
    result = await search_index("test", top_k=3)
    if result.error and "Qdrant" in result.error:
        print(f"PASS - Qdrant unreachable error: {result.error}")
    else:
        print("SKIP - Qdrant is reachable, can't test unreachable path")


async def test_live_search():
    print("\n--- Test 7: Live search (conditional) ---")
    api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    if not api_key:
        print("SKIP - no API key set")
        return
    from qdrant_client import QdrantClient
    try:
        q = QdrantClient(url=qdrant_url)
        q.get_collections()
    except Exception:
        print("SKIP - Qdrant not reachable")
        return

    from src.tools.search import search_index as si
    r = await si("buffer", top_k=3)
    assert r.error is None, f"Search error: {r.error}"
    print(f"  Query 'buffer' -> {len(r.results)} results")
    for res in r.results:
        print(f"    {res.score:.3f} {res.title} ({res.source}) -> {res.url[:60]}...")
    assert len(r.results) > 0, "Expected at least 1 result for 'buffer'"

    r2 = await si("buffer in ArcMap", top_k=3)
    print(f"  Query 'buffer in ArcMap' -> {len(r2.results)} results (source filter: {detect_source_filter('buffer in ArcMap')})")
    assert r2.error is None
    print("PASS - live search returns results for 'buffer' and 'buffer in ArcMap'")


async def test():
    await test_import()
    await test_models()
    await test_source_detection()
    await test_dedupe()
    await test_empty_query()
    await test_qdrant_unreachable()
    await test_live_search()
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(test())
