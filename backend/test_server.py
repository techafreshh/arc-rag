import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

from httpx import ASGITransport, AsyncClient

from src.main import app


def _skip_no_key():
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key or key == "dummy":
        print("SKIP - OPENROUTER_API_KEY missing or 'dummy'")
        return True
    return False


async def test_health():
    print("--- Test 1: Health check ---")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "qdrant" in data
    assert "model" in data
    print(f"  Response: {data}")
    print("PASS - health check returns expected shape")


async def test_ag_ui_endpoint():
    print("\n--- Test 2: AG-UI endpoint returns SSE ---")
    if _skip_no_key():
        return
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/ag-ui",
            json={"threadId": "test-1", "runId": "run-1", "messages": [
                {"role": "user", "content": "Say hello in one word"}
            ]},
            headers={"Accept": "text/event-stream"},
        )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    assert len(resp.content) > 0
    print(f"  Status: {resp.status_code}, Content-Type: {resp.headers.get('content-type')}")
    print("PASS - AG-UI endpoint returns SSE response")


async def test_cors():
    print("\n--- Test 3: CORS headers ---")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.options(
            "/ag-ui",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert resp.status_code == 200
    allow_origin = resp.headers.get("access-control-allow-origin", "")
    assert allow_origin in ("http://localhost:3000", "*"), f"Unexpected CORS origin: {allow_origin}"
    print(f"  Access-Control-Allow-Origin: {allow_origin}")
    print("PASS - CORS allows frontend origin")


async def test():
    await test_health()
    await test_ag_ui_endpoint()
    await test_cors()
    print("\n=== ALL TESTS DONE ===")


if __name__ == "__main__":
    asyncio.run(test())
