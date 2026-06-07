"""Static validation for ARCRAG-17 production compose.

Run on the dev PC (no Docker daemon required). Validates:

  1. frontend/Dockerfile exists with the right structure
  2. frontend/.dockerignore exists and excludes node_modules
  3. frontend/next.config.js exports output == 'standalone'
  4. docker-compose.prod.yml is parseable YAML
  5. The compose has exactly 4 services (no qdrant - external)
  6. backend and frontend have mem_limit
  7. backend and frontend have restart: unless-stopped
  8. inits have restart: "no"
  9. backend has a healthcheck block
 10. frontend.ports is ["3000:3000"]
 11. backend does NOT have a ports: key
 12. frontend.build.args contains NEXT_PUBLIC_BACKEND_URL
 13. arcrag-init-arcmap.depends_on includes arcrag-init with service_completed_successfully
 14. backend.depends_on includes both inits with service_completed_successfully; no qdrant
 15. frontend.depends_on.backend has condition: service_healthy
 16. No qdrant service and no qdrant_data volume
 17. Top-level volumes: declares arcrag_data:
"""

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
FRONTEND_DOCKERFILE = FRONTEND_DIR / "Dockerfile"
FRONTEND_DOCKERIGNORE = FRONTEND_DIR / ".dockerignore"
FRONTEND_NEXT_CONFIG = FRONTEND_DIR / "next.config.js"
PROD_COMPOSE = REPO_ROOT / "docker-compose.prod.yml"

PASS_COUNT = 0
FAIL_COUNT = 0


def _check(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  PASS - {name}")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL - {name}{(': ' + detail) if detail else ''}")


def test_frontend_dockerfile():
    print("--- Test 1: frontend/Dockerfile structure ---")
    assert FRONTEND_DOCKERFILE.exists(), f"missing: {FRONTEND_DOCKERFILE}"
    text = FRONTEND_DOCKERFILE.read_text()
    _check("FROM node:20-alpine AS deps", "FROM node:20-alpine AS deps" in text)
    _check("FROM node:20-alpine AS build", "FROM node:20-alpine AS build" in text)
    _check("FROM node:20-alpine AS runtime", "FROM node:20-alpine AS runtime" in text)
    _check("ARG NEXT_PUBLIC_BACKEND_URL", "ARG NEXT_PUBLIC_BACKEND_URL" in text)
    _check("node + server.js (exec form)",
           'CMD ["node", "server.js"]' in text or 'CMD ["node","server.js"]' in text
           or 'CMD ["node", "server.js"' in text)
    _check("HEALTHCHECK present", "HEALTHCHECK" in text)


def test_frontend_dockerignore():
    print("\n--- Test 2: frontend/.dockerignore ---")
    assert FRONTEND_DOCKERIGNORE.exists(), f"missing: {FRONTEND_DOCKERIGNORE}"
    lines = [l.strip() for l in FRONTEND_DOCKERIGNORE.read_text().splitlines() if l.strip()]
    _check("excludes node_modules", "node_modules" in lines)
    _check("excludes .next", ".next" in lines)


def test_frontend_next_config():
    print("\n--- Test 3: frontend/next.config.js output ---")
    assert FRONTEND_NEXT_CONFIG.exists(), f"missing: {FRONTEND_NEXT_CONFIG}"
    text = FRONTEND_NEXT_CONFIG.read_text()
    import re
    m = re.search(r"output\s*:\s*['\"]([^'\"]+)['\"]", text)
    val = m.group(1) if m else None
    _check("output == 'standalone'", val == "standalone",
           f"got: {val!r}")


def test_prod_compose():
    print("\n--- Test 4: docker-compose.prod.yml structure ---")
    assert PROD_COMPOSE.exists(), f"missing: {PROD_COMPOSE}"
    try:
        d = yaml.safe_load(PROD_COMPOSE.read_text())
    except yaml.YAMLError as e:
        _check("parses as YAML", False, str(e))
        return
    _check("parses as YAML", True)

    svcs = d.get("services", {})
    expected = {"arcrag-init", "arcrag-init-arcmap", "backend", "frontend"}
    _check("exactly 4 expected services", set(svcs.keys()) == expected,
           f"got: {set(svcs.keys())}")
    _check("no qdrant service (external)", "qdrant" not in svcs)

    vols = d.get("volumes", {}) or {}
    _check("no qdrant_data volume (external)", "qdrant_data" not in vols)
    _check("arcrag_data volume declared", "arcrag_data" in vols)

    backend = svcs.get("backend", {})
    frontend = svcs.get("frontend", {})
    arcrag_init = svcs.get("arcrag-init", {})
    arcrag_init_arcmap = svcs.get("arcrag-init-arcmap", {})

    _check("backend.mem_limit == 1g", backend.get("mem_limit") == "1g",
           f"got: {backend.get('mem_limit')!r}")
    _check("frontend.mem_limit == 512m", frontend.get("mem_limit") == "512m",
           f"got: {frontend.get('mem_limit')!r}")
    _check("backend.restart == unless-stopped", backend.get("restart") == "unless-stopped",
           f"got: {backend.get('restart')!r}")
    _check("frontend.restart == unless-stopped", frontend.get("restart") == "unless-stopped",
           f"got: {frontend.get('restart')!r}")
    _check("arcrag-init.restart == 'no'", arcrag_init.get("restart") == "no",
           f"got: {arcrag_init.get('restart')!r}")
    _check("arcrag-init-arcmap.restart == 'no'", arcrag_init_arcmap.get("restart") == "no",
           f"got: {arcrag_init_arcmap.get('restart')!r}")

    _check("backend has healthcheck", "healthcheck" in backend)

    _check("frontend.ports == ['3000:3000']", frontend.get("ports") == ["3000:3000"],
           f"got: {frontend.get('ports')!r}")
    _check("backend has NO ports: key (internal-only)", "ports" not in backend)

    fe_args = frontend.get("build", {}).get("args", {})
    if isinstance(fe_args, dict):
        has_burl = "NEXT_PUBLIC_BACKEND_URL" in fe_args
    else:
        has_burl = any("NEXT_PUBLIC_BACKEND_URL" in str(a) for a in (fe_args or []))
    _check("frontend.build.args has NEXT_PUBLIC_BACKEND_URL", has_burl)

    init_deps = arcrag_init_arcmap.get("depends_on", {}) or {}
    _check(
        "arcrag-init-arcmap.depends_on includes arcrag-init with service_completed_successfully",
        isinstance(init_deps, dict)
        and init_deps.get("arcrag-init", {}).get("condition") == "service_completed_successfully",
        f"got: {init_deps!r}",
    )

    be_deps = backend.get("depends_on", {}) or {}
    _check(
        "backend.depends_on includes arcrag-init with service_completed_successfully",
        isinstance(be_deps, dict)
        and be_deps.get("arcrag-init", {}).get("condition") == "service_completed_successfully",
        f"got: {be_deps!r}",
    )
    _check(
        "backend.depends_on includes arcrag-init-arcmap with service_completed_successfully",
        isinstance(be_deps, dict)
        and be_deps.get("arcrag-init-arcmap", {}).get("condition") == "service_completed_successfully",
        f"got: {be_deps!r}",
    )
    _check(
        "backend.depends_on does NOT contain qdrant (external)",
        "qdrant" not in (be_deps or {}),
        f"got: {be_deps!r}",
    )

    fe_deps = frontend.get("depends_on", {}) or {}
    _check(
        "frontend.depends_on.backend has condition: service_healthy",
        isinstance(fe_deps, dict)
        and fe_deps.get("backend", {}).get("condition") == "service_healthy",
        f"got: {fe_deps!r}",
    )


async def test():
    test_frontend_dockerfile()
    test_frontend_dockerignore()
    test_frontend_next_config()
    test_prod_compose()
    print(f"\nResults: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    if FAIL_COUNT:
        print("SOME TESTS FAILED")
        sys.exit(1)
    print("ALL TESTS PASS")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test())
