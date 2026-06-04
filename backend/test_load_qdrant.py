import asyncio
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SPEC_PATH = Path(__file__).resolve().parent.parent / "scripts" / "load_qdrant.py"

def _load_module():
    spec = importlib.util.spec_from_file_location("load_qdrant", str(SPEC_PATH))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


async def test_import():
    print("--- Test 1: Import check ---")
    m = _load_module()
    assert hasattr(m, "SOURCES"), "SOURCES missing"
    assert list(m.SOURCES.keys()) == ["arcpro", "arcmap"], f"Unexpected sources: {list(m.SOURCES.keys())}"
    assert hasattr(m, "flatten_entries"), "flatten_entries missing"
    assert hasattr(m, "embed_batch"), "embed_batch missing"
    assert hasattr(m, "detect_vector_size"), "detect_vector_size missing"
    assert hasattr(m, "setup_collection"), "setup_collection missing"
    assert hasattr(m, "load_qdrant"), "load_qdrant missing"
    print("PASS - module imports cleanly, SOURCES has arcpro/arcmap")


async def test_flatten():
    print("\n--- Test 2: Flatten check ---")
    m = _load_module()
    sample_page = {
        "url": "https://example.com/test",
        "title": "Test Page",
        "summary": "A test summary.",
        "breadcrumb": ["test", "page"],
        "source": "arcpro",
        "sections": [
            {"heading": "Section One", "brief_text": "First section content"},
            {"heading": "Section Two", "brief_text": "Second section content"},
        ],
        "images": [{"url": "https://example.com/img.png", "alt": "test"}],
    }
    entries = m.flatten_entries([sample_page])
    pages = [e for e in entries if e["payload"]["type"] == "page"]
    sections = [e for e in entries if e["payload"]["type"] == "section"]

    assert len(pages) == 1, f"Expected 1 page entry, got {len(pages)}"
    assert len(sections) == 2, f"Expected 2 section entries, got {len(sections)}"

    page = pages[0]
    assert page["embed_text"] == "Test Page - A test summary.", f"Unexpected page embed_text: {page['embed_text']}"
    assert page["payload"]["url"] == "https://example.com/test"
    assert page["payload"]["section"] == ""
    assert page["payload"]["type"] == "page"
    assert page["payload"]["source"] == "arcpro"

    sec = sections[0]
    assert sec["embed_text"] == "Test Page > Section One - First section content", f"Unexpected section embed_text: {sec['embed_text']}"
    assert sec["payload"]["section"] == "Section One"
    assert sec["payload"]["type"] == "section"

    print(f"PASS - {len(pages)} page + {len(sections)} section entries, payload schema correct")


async def test_dry_run():
    print("\n--- Test 3: Dry-run check ---")
    index_path = SPEC_PATH.parent.parent / "data" / "arcpro_index.json"
    if not index_path.exists():
        print("SKIP - arcpro_index.json not found")
        return

    result = subprocess.run(
        [sys.executable, str(SPEC_PATH), "--source", "arcpro", "--dry-run"],
        capture_output=True, text=True, timeout=30,
    )
    stdout = result.stdout
    stderr = result.stderr
    print(stdout)
    if result.returncode != 0:
        print(f"STDERR: {stderr}")
        assert False, f"Dry-run exited with code {result.returncode}"

    assert "Flattened into" in stdout, "Expected 'Flattened into' in output"
    assert "Dry-run complete" in stdout, "Expected 'Dry-run complete' in output"
    assert "entries would be embedded and upserted" in stdout, "Expected count summary"
    print("PASS - dry-run outputs flattened entry stats and summary")


async def test_live_embed():
    print("\n--- Test 4: Live embed + upsert (conditional) ---")
    api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")

    if not api_key:
        print("SKIP - no EMBEDDING_API_KEY or OPENROUTER_API_KEY set in .env")
        return

    from qdrant_client import QdrantClient
    try:
        qdrant = QdrantClient(url=qdrant_url)
        qdrant.get_collections()
    except Exception:
        print("SKIP - Qdrant not reachable at", qdrant_url)
        return

    print(f"  API key found, Qdrant reachable at {qdrant_url}")

    m = _load_module()
    sample_pages = [
        {
            "url": "https://example.com/test1",
            "title": "Test One",
            "summary": "First test page.",
            "breadcrumb": ["test"],
            "source": "arcpro",
            "sections": [
                {"heading": "Intro", "brief_text": "Introduction content"},
            ],
            "images": [],
        },
        {
            "url": "https://example.com/test2",
            "title": "Test Two",
            "summary": "Second test page.",
            "breadcrumb": ["test"],
            "source": "arcpro",
            "sections": [],
            "images": [],
        },
    ]
    entries = m.flatten_entries(sample_pages)
    assert len(entries) == 3, f"Expected 3 entries, got {len(entries)}"

    import httpx
    async with httpx.AsyncClient() as client:
        vector_size = await m.detect_vector_size(client)
    assert vector_size > 0, f"Invalid vector size: {vector_size}"
    print(f"  Vector dimension: {vector_size}")

    collection_name = "test_arcrag_tmp"
    if qdrant.collection_exists(collection_name):
        qdrant.delete_collection(collection_name)
    qdrant.create_collection(
        collection_name=collection_name,
        vectors_config=m.VectorParams(size=vector_size, distance=m.Distance.COSINE),
    )
    print(f"  Created temp collection: {collection_name}")

    try:
        async with httpx.AsyncClient() as client:
            texts = [e["embed_text"] for e in entries]
            vectors = await m.embed_batch(client, texts)
        assert len(vectors) == 3, f"Expected 3 vectors, got {len(vectors)}"
        assert len(vectors[0]) == vector_size, f"Vector dimension mismatch: {len(vectors[0])} vs {vector_size}"

        from qdrant_client.models import PointStruct
        points = [
            PointStruct(id=i, vector=vectors[i], payload=entries[i]["payload"])
            for i in range(len(entries))
        ]
        qdrant.upsert(collection_name=collection_name, points=points)

        count_result = qdrant.count(collection_name=collection_name)
        count = count_result.count if hasattr(count_result, "count") else count_result
        assert count >= 3, f"Expected >= 3 points, got {count}"
        print(f"  Upserted {count} points successfully")
    finally:
        qdrant.delete_collection(collection_name)
        print(f"  Cleaned up temp collection: {collection_name}")

    print("PASS - live embed + upsert with 2 pages (3 entries) completed")


async def test():
    await test_import()
    await test_flatten()
    await test_dry_run()
    await test_live_embed()
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(test())
