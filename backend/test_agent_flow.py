import asyncio
import os
import re

from dotenv import load_dotenv

load_dotenv()

from src.agent import agent
from src.tools.search import search_index as _search_index


def _skip_no_key():
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key or key == "dummy":
        print("SKIP - OPENROUTER_API_KEY missing or 'dummy'")
        return True
    return False


async def _qdrant_reachable() -> bool:
    try:
        r = await _search_index("test", top_k=1)
        return r.error is None
    except Exception:
        return False


def _tool_call_order(messages) -> list[str]:
    order: list[str] = []
    for m in messages:
        for part in getattr(m, "parts", []):
            name = getattr(part, "tool_name", None) or getattr(part, "function", None)
            if name is None and hasattr(part, "part_kind") and part.part_kind == "tool-call":
                name = getattr(part, "tool_name", None)
            if name:
                if not order or order[-1] != name:
                    order.append(name)
    return order


async def test_tool_call_order():
    print("--- Test 1: Tool call order (search_index before fetch_page) ---")
    if _skip_no_key():
        return

    result = await asyncio.wait_for(
        agent.run("How do I create a buffer in ArcGIS Pro?"),
        timeout=60.0,
    )
    messages = []
    if hasattr(result, "all_messages"):
        try:
            messages = result.all_messages()
        except Exception:
            messages = []
    if not messages:
        text = str(result)
        messages = []
        for m in re.finditer(r"tool[_ ]?name['\"\"]?\s*[:=]\s*['\"]([a-zA-Z_]+)['\"]", text):
            messages.append(m.group(1))

    order = _tool_call_order(messages)
    if not order:
        text = str(result)
        order = re.findall(r"\b(search_index|fetch_page|lookup_url)\b", text)

    print(f"  Tool call sequence: {order}")

    if "search_index" not in order:
        print("WARN - no search_index call observed in messages; cannot verify order")
        return

    if "fetch_page" in order:
        assert order.index("search_index") < order.index("fetch_page"), (
            f"search_index must precede fetch_page; got order={order}"
        )
        print("PASS - search_index called before fetch_page")
    else:
        print("PASS - search_index called (fetch_page not invoked; model answered from search results)")


async def test_response_format():
    print("\n--- Test 2: Response format (image, source citation, link) ---")
    if _skip_no_key():
        return

    result = await asyncio.wait_for(
        agent.run("How do I create a buffer in ArcGIS Pro?"),
        timeout=60.0,
    )
    output = result.output if hasattr(result, "output") else str(result)
    print(f"  Output length: {len(output)} chars")

    assert "![" in output, "Response does not contain markdown image syntax"
    print("  Markdown image found")

    assert "**Source:**" in output, "Response missing **Source:** citation"
    print("  **Source:** citation found")

    link_re = re.compile(r"\[.+\]\(https?://[^\)]+\)")
    assert link_re.search(output), "Response missing markdown link"
    print("  Markdown link found")

    print("PASS - response format correct")


async def test_groundedness():
    print("\n--- Test 3: Groundedness (Buffer doc terms in response) ---")
    if _skip_no_key():
        return
    if not await _qdrant_reachable():
        print("SKIP - Qdrant unreachable; agent cannot ground")
        return

    result = await asyncio.wait_for(
        agent.run("How do I create a buffer in ArcGIS Pro?"),
        timeout=60.0,
    )
    output = (result.output if hasattr(result, "output") else str(result)).lower()

    keywords = {
        "buffer", "distance", "feature class", "input features", "output feature class",
        "dissolve", "side type", "planar", "geodesic",
    }
    hits = {kw for kw in keywords if kw in output}
    print(f"  Found {len(hits)}/{len(keywords)} Buffer terms: {sorted(hits)}")
    assert len(hits) >= 2, f"Expected >= 2 Buffer-doc terms, got {len(hits)}: {sorted(hits)}"
    print("PASS - response grounded in Buffer documentation")


async def test_no_results_branch():
    print("\n--- Test 4: No-results branch (gibberish query) ---")
    if _skip_no_key():
        return

    result = await asyncio.wait_for(
        agent.run("asdfghjkl quantum GIS dance routine"),
        timeout=60.0,
    )
    output = result.output if hasattr(result, "output") else str(result)
    print(f"  Output: {output[:200]!r}")

    assert "**Source:**" not in output, "Agent fabricated a Source: citation for nonsense query"
    assert not re.search(r"\]\(https?://(pro|desktop)\.arcgis\.com/", output), (
        "Agent fabricated an arcgis.com link for nonsense query"
    )
    print("PASS - no fabricated citation or arcgis.com link for gibberish query")


async def test():
    await test_tool_call_order()
    await test_response_format()
    await test_groundedness()
    await test_no_results_branch()
    print("\n=== ALL TESTS DONE ===")


if __name__ == "__main__":
    asyncio.run(test())
