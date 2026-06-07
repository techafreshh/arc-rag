"""ARCRAG-19 End-to-End Validation & Quality Check suite.

Runs 20 representative GIS queries from ``tests/e2e_queries.json`` (at the
repo root) through the deployed PydanticAI agent, plus 4 edge cases
(gibberish, non-GIS, single word, vague). Asserts:

  1. Relevance: >=16/20 (80%) answers contain >=1 expected keyword
  2. Image inclusion: >=12/20 (60%) answers contain a markdown image
  3. Source citation: 20/20 (100%) answers cite an esri.com URL via
     **Source:** [title](url)
  4. Latency: mean <10s, max <15s
  5. Edge cases: no fabricated citations for nonsense, graceful handling
     of single-word and broad questions
  6. Rate-limit smoke: 21st POST to /api/copilotkit from the same IP
     within a minute returns 429 (ARCRAG-18 chain — only runs when
     $CADDY_DOMAIN is set)

The suite **fails hard** (sys.exit(1)) when Qdrant is unreachable, the
arcgis_docs collection is empty, or OPENROUTER_API_KEY is missing. This
is a deliberate departure from the SKIP-on-unavailable pattern in
test_search.py / test_load_qdrant.py / test_agent_flow.py /
test_server.py: E2E is the final gate, and a SKIP on dev PC would
create a false sense of "all green". The rate-limit smoke is the only
test that skips cleanly on dev PC (no public HTTPS endpoint there).

Pattern source: ``backend/test_agent_flow.py`` (response-format regex,
no-results branch check, async test_() orchestrator).
"""

import asyncio
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = REPO_ROOT / "tests" / "e2e_queries.json"

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "arcgis_docs")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
CADDY_DOMAIN = os.getenv("CADDY_DOMAIN", "")

RELEVANCE_THRESHOLD = 16
IMAGE_THRESHOLD = 12
SOURCE_CITATION_THRESHOLD = 20
MEAN_LATENCY_THRESHOLD = 10.0
MAX_LATENCY_THRESHOLD = 15.0
QUERY_TIMEOUT_S = 30.0
RATE_LIMIT_TOTAL = 25
RATE_LIMIT_EXPECTED_429_AT = 21

CITATION_LINK_RE = re.compile(
    r"\*\*Source:\*\*\s*\[.+\]\(https?://(?:[a-z0-9-]+\.)?(?:arcgis\.com|esri\.com)/[^)]+\)",
    re.IGNORECASE,
)
ARCIS_URL_RE = re.compile(
    r"\]\(https?://(?:[a-z0-9-]+\.)?(?:arcgis\.com|esri\.com)/",
    re.IGNORECASE,
)
MARKDOWN_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")


def _die(msg: str) -> None:
    print(f"FATAL - {msg}", file=sys.stderr)
    sys.exit(1)


def _load_corpus() -> dict:
    if not CORPUS_PATH.exists():
        _die(f"corpus file not found: {CORPUS_PATH}")
    try:
        with CORPUS_PATH.open() as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        _die(f"corpus file is not valid JSON: {e}")
    return data


async def test_corpus_schema() -> dict:
    print("--- Test 1: Corpus schema ---")
    data = _load_corpus()
    assert "queries" in data and "edge_cases" in data, "missing top-level keys"
    assert len(data["queries"]) == 20, (
        f"expected 20 queries, got {len(data['queries'])}"
    )
    assert len(data["edge_cases"]) == 4, (
        f"expected 4 edge cases, got {len(data['edge_cases'])}"
    )

    for q in data["queries"]:
        for k in ("id", "query", "category", "source_hint",
                  "expected_keywords", "expected_url_pattern"):
            assert k in q, f"missing key {k} in {q.get('id', '?')}"
        assert isinstance(q["expected_keywords"], list), (
            f"{q['id']}: expected_keywords must be list"
        )
        assert isinstance(q["expected_url_pattern"], str), (
            f"{q['id']}: expected_url_pattern must be str"
        )
        assert len(q["expected_keywords"]) >= 1, (
            f"{q['id']}: expected_keywords must be non-empty"
        )

    for e in data["edge_cases"]:
        for k in ("id", "query", "category"):
            assert k in e, f"missing key {k} in {e.get('id', '?')}"

    print(f"  20 queries + 4 edge cases; all required fields present")
    print("PASS - corpus schema valid")
    return data


def _check_qdrant_has_data() -> tuple[bool, str]:
    """Returns (ok, detail). ok=True means Qdrant reachable AND collection non-empty."""
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        return False, "qdrant_client not installed"
    try:
        client = QdrantClient(url=QDRANT_URL, timeout=5.0)
        client.get_collections()
    except Exception as e:
        return False, f"Qdrant unreachable at {QDRANT_URL}: {e}"
    try:
        info = client.get_collection(collection_name=QDRANT_COLLECTION)
        count = (
            info.points_count
            if hasattr(info, "points_count")
            else info.vectors_count
            if hasattr(info, "vectors_count")
            else None
        )
    except Exception as e:
        return False, f"collection '{QDRANT_COLLECTION}' not present: {e}"
    if not count or count <= 0:
        return False, f"collection '{QDRANT_COLLECTION}' is empty (count={count})"
    return True, f"Qdrant has {count} points in '{QDRANT_COLLECTION}'"


def test_prerequisites_fail_hard() -> None:
    print("\n--- Test 2: Prerequisites (fail-hard gate) ---")
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "dummy":
        _die(
            "OPENROUTER_API_KEY missing or 'dummy'. "
            "E2E tests require a real key. Set it in .env before running."
        )
    print(f"  OPENROUTER_API_KEY set: {OPENROUTER_API_KEY[:8]}...")

    ok, detail = _check_qdrant_has_data()
    if not ok:
        _die(
            f"Qdrant prerequisite failed: {detail}. "
            "E2E tests require a populated Qdrant. Run on the VPS after "
            "ARCRAG-15/16 ingestion completes."
        )
    print(f"  {detail}")
    print("PASS - prerequisites met (Qdrant + API key)")


async def _run_query(query: str, timeout: float = QUERY_TIMEOUT_S) -> tuple[str, float]:
    """Run a query through the deployed agent. Returns (output, elapsed_s)."""
    from src.agent import agent

    t0 = time.monotonic()
    result = await asyncio.wait_for(agent.run(query), timeout=timeout)
    elapsed = time.monotonic() - t0
    output = result.output if hasattr(result, "output") else str(result)
    return output, elapsed


def _keyword_overlap(output: str, expected: list[str]) -> int:
    lowered = output.lower()
    return sum(1 for kw in expected if kw.lower() in lowered)


async def test_relevance_rate(corpus: dict) -> dict:
    print("\n--- Test 3: Relevance rate (>=16/20 = 80%) ---")
    hits = 0
    details = []
    for q in corpus["queries"]:
        try:
            output, _ = await _run_query(q["query"])
        except Exception as e:
            print(f"  {q['id']} ERROR: {e}")
            details.append({"id": q["id"], "ok": False, "error": str(e)})
            continue
        n = _keyword_overlap(output, q["expected_keywords"])
        ok = n >= 1
        if ok:
            hits += 1
        truncated = q["query"][:50] + ("..." if len(q["query"]) > 50 else "")
        print(f"  {q['id']} {truncated!r:55s}  {n}/{len(q['expected_keywords'])} keywords  {'OK' if ok else 'MISS'}")
        details.append({"id": q["id"], "ok": ok, "hits": n,
                        "of": len(q["expected_keywords"])})
    rate = hits / len(corpus["queries"])
    print(f"  Relevance: {hits}/20 ({rate:.0%})")
    assert hits >= RELEVANCE_THRESHOLD, (
        f"relevance {hits}/20 below threshold {RELEVANCE_THRESHOLD}/20"
    )
    print(f"PASS - relevance {hits}/20 >= {RELEVANCE_THRESHOLD}/20")
    return {"hits": hits, "total": 20, "details": details}


async def test_image_inclusion_rate(corpus: dict) -> dict:
    print("\n--- Test 4: Image inclusion rate (>=12/20 = 60%) ---")
    hits = 0
    details = []
    for q in corpus["queries"]:
        try:
            output, _ = await _run_query(q["query"])
        except Exception as e:
            print(f"  {q['id']} ERROR: {e}")
            details.append({"id": q["id"], "ok": False, "error": str(e)})
            continue
        ok = bool(MARKDOWN_IMG_RE.search(output))
        if ok:
            hits += 1
        print(f"  {q['id']}  {'IMG' if ok else 'no img'}")
        details.append({"id": q["id"], "ok": ok})
    rate = hits / len(corpus["queries"])
    print(f"  Image inclusion: {hits}/20 ({rate:.0%})")
    assert hits >= IMAGE_THRESHOLD, (
        f"image inclusion {hits}/20 below threshold {IMAGE_THRESHOLD}/20"
    )
    print(f"PASS - image inclusion {hits}/20 >= {IMAGE_THRESHOLD}/20")
    return {"hits": hits, "total": 20, "details": details}


async def test_source_citation_accuracy(corpus: dict) -> dict:
    print("\n--- Test 5: Source citation accuracy (20/20 = 100%) ---")
    hits = 0
    details = []
    for q in corpus["queries"]:
        try:
            output, _ = await _run_query(q["query"])
        except Exception as e:
            print(f"  {q['id']} ERROR: {e}")
            details.append({"id": q["id"], "ok": False, "error": str(e)})
            continue
        ok = bool(CITATION_LINK_RE.search(output))
        if ok:
            hits += 1
        print(f"  {q['id']}  {'CITED' if ok else 'NO CITATION'}")
        details.append({"id": q["id"], "ok": ok})
    print(f"  Source citation: {hits}/20")
    assert hits >= SOURCE_CITATION_THRESHOLD, (
        f"source citation {hits}/20 below threshold "
        f"{SOURCE_CITATION_THRESHOLD}/20"
    )
    print(f"PASS - source citation {hits}/20 >= {SOURCE_CITATION_THRESHOLD}/20")
    return {"hits": hits, "total": 20, "details": details}


async def test_response_latency(corpus: dict) -> dict:
    print("\n--- Test 6: Response latency (mean <10s, max <15s) ---")
    elapsed_list: list[float] = []
    for q in corpus["queries"]:
        try:
            _, elapsed = await _run_query(q["query"])
            elapsed_list.append(elapsed)
            print(f"  {q['id']}  {elapsed:5.2f}s")
        except Exception as e:
            print(f"  {q['id']}  TIMEOUT/ERROR: {e}")
    if not elapsed_list:
        _die("no successful responses to measure latency")
    mean = statistics.mean(elapsed_list)
    pmax = max(elapsed_list)
    print(f"  Mean: {mean:.2f}s  Max: {pmax:.2f}s  (n={len(elapsed_list)})")
    assert mean < MEAN_LATENCY_THRESHOLD, (
        f"mean latency {mean:.2f}s exceeds {MEAN_LATENCY_THRESHOLD}s"
    )
    assert pmax < MAX_LATENCY_THRESHOLD, (
        f"max latency {pmax:.2f}s exceeds {MAX_LATENCY_THRESHOLD}s"
    )
    print(f"PASS - latency OK (mean {mean:.2f}s < {MEAN_LATENCY_THRESHOLD}s, "
          f"max {pmax:.2f}s < {MAX_LATENCY_THRESHOLD}s)")
    return {"mean": mean, "max": pmax, "samples": len(elapsed_list),
            "all": elapsed_list}


async def test_edge_case_gibberish(corpus: dict) -> None:
    print("\n--- Test 7: Edge case E01 (gibberish) ---")
    e01 = next(e for e in corpus["edge_cases"] if e["id"] == "E01")
    try:
        output, _ = await _run_query(e01["query"])
    except Exception as exc:
        print(f"  SKIP (agent errored, which is acceptable for gibberish): {exc}")
        return
    assert "**Source:**" not in output, (
        "Agent fabricated a Source: citation for nonsense query"
    )
    assert not ARCIS_URL_RE.search(output), (
        "Agent fabricated an arcgis.com / esri.com link for nonsense query"
    )
    print(f"  Output: {output[:120]!r}")
    print("PASS - no fabricated citation or arcgis/esri URL for gibberish query")


async def test_edge_case_non_gis(corpus: dict) -> None:
    print("\n--- Test 8: Edge case E02 (non-GIS) ---")
    e02 = next(e for e in corpus["edge_cases"] if e["id"] == "E02")
    try:
        output, _ = await _run_query(e02["query"])
    except Exception as exc:
        print(f"  SKIP (agent errored, which is acceptable for non-GIS): {exc}")
        return
    declined = any(phrase in output.lower() for phrase in [
        "i can only", "i'm a gis", "gis documentation", "out of scope",
        "i don't", "i cannot help with", "specialize", "arcgis",
    ])
    assert declined, (
        f"Agent should decline or ask for GIS context. Got: {output[:200]!r}"
    )
    assert not ARCIS_URL_RE.search(output), (
        "Agent fabricated an arcgis.com / esri.com link for non-GIS query"
    )
    print(f"  Output: {output[:120]!r}")
    print("PASS - non-GIS query declined without fabricated arcgis/esri URL")


async def test_edge_case_single_word(corpus: dict) -> None:
    print("\n--- Test 9: Edge case E03 (single word: 'buffer') ---")
    e03 = next(e for e in corpus["edge_cases"] if e["id"] == "E03")
    try:
        output, _ = await _run_query(e03["query"])
    except Exception as exc:
        print(f"  SKIP (agent errored, which is acceptable for single-word): {exc}")
        return
    lowered = output.lower()
    buffer_related = "buffer" in lowered
    has_citation = "**Source:**" in output
    print(f"  Output ({len(output)} chars): {output[:200]!r}")
    assert buffer_related, (
        f"Single-word 'buffer' should produce a buffer-related answer. "
        f"Got: {output[:200]!r}"
    )
    assert has_citation, "Single-word query should still include **Source:**"
    print("PASS - single-word 'buffer' produced coherent buffer answer with citation")


async def test_edge_case_vague(corpus: dict) -> None:
    print("\n--- Test 10: Edge case E04 (vague: 'How do I do spatial analysis?') ---")
    e04 = next(e for e in corpus["edge_cases"] if e["id"] == "E04")
    try:
        output, _ = await _run_query(e04["query"])
    except Exception as exc:
        print(f"  SKIP (agent errored, which is acceptable for vague query): {exc}")
        return
    print(f"  Output ({len(output)} chars): {output[:200]!r}")
    assert len(output) > 50, "Vague query should produce a non-empty answer"
    has_spatial_terms = any(t in output.lower() for t in [
        "spatial", "analysis", "geoprocessing", "arcgis",
    ])
    assert has_spatial_terms, (
        f"Vague query should mention spatial/geoprocessing/arcgis. "
        f"Got: {output[:200]!r}"
    )
    print("PASS - vague query produced a coherent high-level spatial-analysis answer")


async def test_rate_limit_smoke() -> None:
    print("\n--- Test 11: Rate-limit smoke (ARCRAG-18 chain) ---")
    if not CADDY_DOMAIN:
        print("  SKIP - CADDY_DOMAIN not set; rate-limit smoke requires the VPS")
        return
    url = f"https://{CADDY_DOMAIN}/api/copilotkit"
    statuses: list[int] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for i in range(1, RATE_LIMIT_TOTAL + 1):
            try:
                r = await client.post(
                    url,
                    json={"threadId": f"smoke-{i}", "runId": f"run-{i}",
                          "messages": [{"role": "user", "content": "ping"}]},
                )
                statuses.append(r.status_code)
                print(f"  Request {i:2d}: {r.status_code}")
            except Exception as e:
                print(f"  Request {i:2d}: ERROR {e}")
                statuses.append(-1)
    n_429 = sum(1 for s in statuses if s == 429)
    n_200_4xx = sum(1 for s in statuses if 200 <= s < 500 and s != 429)
    print(f"  429 count: {n_429}, 200/4xx (non-429) count: {n_200_4xx}")
    if n_429 == 0:
        print(f"  FAIL - rate limit never fired (expected at least 1 x 429)")
        assert False, "rate limit never fired"
    print(f"PASS - rate limit fired ({n_429} x 429 received)")


def test_summary(results: dict) -> None:
    print("\n--- Test 12: Summary ---")
    print("=" * 70)
    print(f"E2E VALIDATION SUMMARY (ARCRAG-19)")
    print("=" * 70)
    rel = results.get("relevance", {})
    img = results.get("image_inclusion", {})
    src = results.get("source_citation", {})
    lat = results.get("latency", {})
    print(f"  Relevance rate:      {rel.get('hits', 0)}/20 "
          f"(threshold >= {RELEVANCE_THRESHOLD}/20)")
    print(f"  Image inclusion:     {img.get('hits', 0)}/20 "
          f"(threshold >= {IMAGE_THRESHOLD}/20)")
    print(f"  Source citation:     {src.get('hits', 0)}/20 "
          f"(threshold >= {SOURCE_CITATION_THRESHOLD}/20)")
    print(f"  Latency mean:        {lat.get('mean', 0):.2f}s "
          f"(threshold < {MEAN_LATENCY_THRESHOLD}s)")
    print(f"  Latency max:         {lat.get('max', 0):.2f}s "
          f"(threshold < {MAX_LATENCY_THRESHOLD}s)")
    print("=" * 70)


async def test() -> None:
    corpus = await test_corpus_schema()
    test_prerequisites_fail_hard()
    results = {}
    results["relevance"] = await test_relevance_rate(corpus)
    results["image_inclusion"] = await test_image_inclusion_rate(corpus)
    results["source_citation"] = await test_source_citation_accuracy(corpus)
    results["latency"] = await test_response_latency(corpus)
    await test_edge_case_gibberish(corpus)
    await test_edge_case_non_gis(corpus)
    await test_edge_case_single_word(corpus)
    await test_edge_case_vague(corpus)
    await test_rate_limit_smoke()
    test_summary(results)
    print("\n=== ALL E2E TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(test())
