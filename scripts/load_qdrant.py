import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import CollectionParams, Distance, PointStruct, VectorParams

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
(PROJECT_DIR / "data").mkdir(exist_ok=True)

load_dotenv()

backend_dir = PROJECT_DIR / "backend"
sys.path.insert(0, str(backend_dir if backend_dir.exists() else PROJECT_DIR))
from src.embed import EMBEDDING_MODEL, EMBEDDING_API_KEY, OPENROUTER_EMBEDDINGS_URL, embed_batch

SOURCES = {
    "arcpro": {
        "index_json": str(PROJECT_DIR / "data/arcpro_index.json"),
        "source": "arcpro",
        "id_offset": 0,
    },
    "arcmap": {
        "index_json": str(PROJECT_DIR / "data/arcmap_index.json"),
        "source": "arcmap",
        "id_offset": 1_000_000,
    },
}

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "arcgis_docs")


def flatten_entries(pages: list[dict]) -> list[dict]:
    entries = []
    for page in pages:
        title = page["title"]
        summary = page.get("summary", "")
        if title:
            embed_text = f"{title} - {summary}".strip(" -")
            entries.append({
                "embed_text": embed_text,
                "payload": {
                    "url": page["url"],
                    "title": title,
                    "summary": summary,
                    "section": "",
                    "breadcrumb": page.get("breadcrumb", []),
                    "source": page["source"],
                    "type": "page",
                    "images": page.get("images", []),
                },
            })
        for sec in page.get("sections", []):
            heading = sec["heading"]
            brief = sec.get("brief_text", "")
            embed_text = f"{title} > {heading} - {brief}".strip(" -")
            entries.append({
                "embed_text": embed_text,
                "payload": {
                    "url": page["url"],
                    "title": title,
                    "section": heading,
                    "breadcrumb": page.get("breadcrumb", []),
                    "source": page["source"],
                    "type": "section",
                    "images": page.get("images", []),
                },
            })
    return entries


async def detect_vector_size(client: httpx.AsyncClient) -> int:
    vectors = await embed_batch(client, ["dimension probe"])
    return len(vectors[0])


def setup_collection(client: QdrantClient, collection_name: str, vector_size: int, recreate: bool):
    if recreate:
        if client.collection_exists(collection_name):
            client.delete_collection(collection_name)
            print(f"Deleted existing collection: {collection_name}")
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        print(f"Created collection: {collection_name} (dim={vector_size})")
    else:
        if client.collection_exists(collection_name):
            print(f"Collection {collection_name} already exists")
            return
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        print(f"Created collection: {collection_name} (dim={vector_size})")


async def load_qdrant(source: str, recreate: bool, dry_run: bool, batch_size: int = 100):
    if source not in SOURCES:
        print(f"Unknown source: {source}. Choices: {list(SOURCES.keys())}")
        sys.exit(1)

    index_path = Path(SOURCES[source]["index_json"])
    if not index_path.exists():
        print(f"Index file not found: {index_path}")
        sys.exit(1)

    id_offset = SOURCES[source]["id_offset"]

    pages = json.loads(index_path.read_text())
    print(f"Loaded {len(pages)} pages from {index_path.name}")

    entries = flatten_entries(pages)
    page_entries = [e for e in entries if e["payload"]["type"] == "page"]
    section_entries = [e for e in entries if e["payload"]["type"] == "section"]
    print(f"Flattened into {len(entries)} entries ({len(page_entries)} pages, {len(section_entries)} sections)")

    if dry_run:
        print(f"\nDry-run: first {min(5, len(entries))} entries:")
        for entry in entries[:5]:
            print(f"  embed_text: {entry['embed_text'][:80]}...")
            print(f"  payload: type={entry['payload']['type']}, url={entry['payload']['url']}, section={entry['payload']['section']}")
            print(f"  payload keys: {list(entry['payload'].keys())}")
        print(f"\nDry-run complete. {len(entries)} entries would be embedded and upserted.")
        return

    if not EMBEDDING_API_KEY:
        print("ERROR: EMBEDDING_API_KEY or OPENROUTER_API_KEY not set in .env")
        sys.exit(1)

    print(f"Connecting to Qdrant at {QDRANT_URL}")
    qdrant = QdrantClient(url=QDRANT_URL)
    print(f"  Collections: {qdrant.get_collections()}")

    print(f"Detecting vector size using model {EMBEDDING_MODEL}...")
    async with httpx.AsyncClient() as client:
        vector_size = await detect_vector_size(client)
    print(f"  Vector size: {vector_size}")

    setup_collection(qdrant, QDRANT_COLLECTION, vector_size, recreate)

    total = len(entries)
    upserted = 0
    async with httpx.AsyncClient() as client:
        for start in range(0, total, batch_size):
            batch = entries[start:start + batch_size]
            texts = [e["embed_text"] for e in batch]
            vectors = await embed_batch(client, texts)
            points = [
                PointStruct(
                    id=start + i + id_offset,
                    vector=vectors[i],
                    payload=batch[i]["payload"],
                )
                for i in range(len(batch))
            ]
            qdrant.upsert(collection_name=QDRANT_COLLECTION, points=points)
            upserted += len(points)
            print(f"  Upserted {upserted}/{total} ({len(points)} in batch)")

    count_result = qdrant.count(collection_name=QDRANT_COLLECTION)
    count = count_result.count if hasattr(count_result, "count") else count_result
    print(f"\nDone. {upserted} points upserted. Collection count: {count}")


def main():
    parser = argparse.ArgumentParser(description="Load documentation index into Qdrant with embeddings")
    parser.add_argument("--source", required=True, choices=["arcpro", "arcmap"])
    parser.add_argument("--recreate", action="store_true", help="Drop and recreate the collection")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be upserted without calling APIs")
    parser.add_argument("--batch-size", type=int, default=100, help="Embedding/upsert batch size")
    args = parser.parse_args()
    asyncio.run(load_qdrant(args.source, args.recreate, args.dry_run, args.batch_size))


if __name__ == "__main__":
    main()
