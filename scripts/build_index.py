import argparse
import asyncio
import json
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
(PROJECT_DIR / "data").mkdir(exist_ok=True)


SOURCES = {
    "arcpro": {
        "urls_json": str(PROJECT_DIR / "data/arcpro_urls.json"),
        "output": str(PROJECT_DIR / "data/arcpro_index.json"),
        "checkpoint": str(PROJECT_DIR / "data/.checkpoint_arcpro_index.json"),
        "source": "arcpro",
    },
    "arcmap": {
        "urls_json": str(PROJECT_DIR / "data/arcmap_urls.json"),
        "output": str(PROJECT_DIR / "data/arcmap_index.json"),
        "checkpoint": str(PROJECT_DIR / "data/.checkpoint_arcmap_index.json"),
        "source": "arcmap",
    },
}


async def fetch_html(client: httpx.AsyncClient, url: str) -> str | None:
    for attempt in range(2):
        try:
            resp = await client.get(url)
        except Exception as e:
            print(f" FAILED: {e}", flush=True)
            return None
        if resp.status_code == 429 and attempt == 0:
            print(f" HTTP 429 (rate limited), sleeping 5s and retrying", flush=True)
            await asyncio.sleep(5)
            continue
        if resp.status_code != 200:
            print(f" HTTP {resp.status_code}", flush=True)
            return None
        # Handle meta refresh redirects
        if 'http-equiv="refresh"' in resp.text.lower() or "http-equiv='refresh'" in resp.text.lower():
            import re
            match = re.search(r'url=([^"\'>\s]+)', resp.text, re.IGNORECASE)
            if match:
                redirect_url = match.group(1).strip()
                if redirect_url.startswith('/'):
                    from urllib.parse import urljoin
                    redirect_url = urljoin(str(resp.url), redirect_url)
                try:
                    resp2 = await client.get(redirect_url)
                    if resp2.status_code == 200:
                        return resp2.text
                except Exception:
                    pass
        # Check if content has main/article tags
        has_main = '<main' in resp.text
        has_article = '<article' in resp.text
        if not has_main and not has_article:
            print(f" NO_MAIN: {url[:60]} len={len(resp.text)}", flush=True)
        return resp.text
    return None


def extract_title(article: Tag) -> str:
    title_tag = article.find("h1")
    return title_tag.get_text(strip=True) if title_tag else ""


def extract_summary(article: Tag) -> str:
    for el in article.descendants:
        if not isinstance(el, Tag):
            continue
        if el.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            return ""
        if el.name == "p":
            text = el.get_text(strip=True)
            if len(text) > 40:
                return text
    return ""


def extract_sections(article: Tag) -> list[dict]:
    sections: list[dict] = []
    for heading in article.find_all(["h2", "h3"]):
        parts: list[str] = []
        for sib in heading.next_siblings:
            if not isinstance(sib, Tag):
                continue
            if sib.name in ("h2", "h3"):
                break
            text = sib.get_text(separator="\n", strip=True) if hasattr(sib, "get_text") else str(sib).strip()
            if text:
                parts.append(text)
        brief = "\n".join(parts).strip()
        if not brief:
            continue
        sections.append({
            "heading": heading.get_text(strip=True),
            "level": int(heading.name[1]),
            "brief_text": brief,
        })
    return sections


def extract_breadcrumb(soup: BeautifulSoup, url: str) -> list[str]:
    nav = soup.find("nav", attrs={"aria-label": "breadcrumb"})
    if not nav:
        nav = soup.select_one(".breadcrumb")
    if nav:
        items: list[str] = []
        for child in nav.find_all(["a", "li", "span"]):
            text = child.get_text(strip=True)
            if text and text not in items:
                items.append(text)
        if items:
            return items
    parts = [p for p in urlparse(url).path.split("/") if p]
    cleaned: list[str] = []
    for p in parts:
        if p == "en":
            continue
        if p.isdigit() or (p.replace(".", "").isdigit() and p[0].isdigit()):
            continue
        cleaned.append(p)
    return cleaned


def extract_images(article: Tag, base_url: str) -> list[dict]:
    images: list[dict] = []
    for img in article.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        absolute = urljoin(base_url, src)
        if not absolute:
            continue
        images.append({
            "url": absolute,
            "alt": img.get("alt", ""),
        })
    return images


def parse_page(html: str, url: str, source: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find("article", id="main") or soup.find("main") or soup.find("article")
    if not article:
        return None
    for tag in article.find_all(["nav", "footer", "script", "style"]):
        tag.decompose()
    return {
        "url": url,
        "source": source,
        "title": extract_title(article),
        "summary": extract_summary(article),
        "breadcrumb": extract_breadcrumb(soup, url),
        "sections": extract_sections(article),
        "images": extract_images(article, url),
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def load_checkpoint(path: str) -> tuple[set[str], list[dict], set[str]]:
    p = Path(path)
    if not p.exists():
        return set(), [], set()
    data = json.loads(p.read_text())
    if isinstance(data, dict):
        return set(data.get("done_urls", [])), data.get("pages", []), set(data.get("failed_urls", []))
    return set(), [], set()


def save_checkpoint(path: str, done_urls: set[str], pages: list[dict], failed_urls: set[str]):
    Path(path).write_text(json.dumps({
        "done_urls": sorted(done_urls),
        "pages": pages,
        "failed_urls": sorted(failed_urls),
    }, indent=2))


async def build_index(source: str, limit: int | None = None, concurrency: int = 5, delay: float = 0.2):
    config = SOURCES[source]
    done_urls, pages, failed_urls = load_checkpoint(config["checkpoint"])
    if done_urls:
        print(f"[{source}] Resuming from checkpoint: {len(done_urls)} URLs done, {len(pages)} pages")

    all_urls = json.loads(Path(config["urls_json"]).read_text())
    scope = all_urls[:limit] if limit is not None else all_urls
    remaining = [u for u in scope if u not in done_urls]

    total = len(remaining)
    if total == 0:
        print(f"[{source}] Nothing to do. {len(pages)} pages, {len(failed_urls)} failed")
        Path(config["output"]).write_text(json.dumps(pages, indent=2, ensure_ascii=False))
        return

    print(f"[{source}] Processing {total} URLs (concurrency={concurrency}, delay={delay}s)")

    semaphore = asyncio.Semaphore(concurrency)

    async def process(url: str):
        async with semaphore:
            await asyncio.sleep(delay)
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                html = await fetch_html(client, url)
            if html is None:
                failed_urls.add(url)
                done_urls.add(url)
                n = len(done_urls)
                if n % 100 == 0:
                    save_checkpoint(config["checkpoint"], done_urls, pages, failed_urls)
                return
            page = parse_page(html, url, source)
            if page is None or not page["title"]:
                failed_urls.add(url)
                done_urls.add(url)
                n = len(done_urls)
                if n % 100 == 0:
                    save_checkpoint(config["checkpoint"], done_urls, pages, failed_urls)
                return
            pages.append(page)
            done_urls.add(url)
            n = len(done_urls)
            if n % 25 == 0:
                save_checkpoint(config["checkpoint"], done_urls, pages, failed_urls)
            print(f"[{source}] {n}/{total} {url} -> {page['title'][:60]}", flush=True)

    batch_size = concurrency * 10
    for i in range(0, len(remaining), batch_size):
        batch = remaining[i:i + batch_size]
        print(f"[{source}] Processing batch {i//batch_size + 1} ({len(batch)} URLs)...", flush=True)
        await asyncio.gather(*(process(u) for u in batch))
        print(f"[{source}] Batch {i//batch_size + 1} done. Total: {len(done_urls)}/{total}", flush=True)

    save_checkpoint(config["checkpoint"], done_urls, pages, failed_urls)
    Path(config["output"]).write_text(json.dumps(pages, indent=2, ensure_ascii=False))
    print(f"[{source}] Done. {len(pages)} pages indexed, {len(failed_urls)} failed -> {config['output']}")


def main():
    parser = argparse.ArgumentParser(description="Build documentation index from URL list")
    parser.add_argument("--source", required=True, choices=["arcpro", "arcmap"])
    parser.add_argument("--limit", type=int, default=None, help="Process only first N URLs (for testing)")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--delay", type=float, default=0.2, help="Seconds to sleep after each fetch")
    args = parser.parse_args()
    asyncio.run(build_index(args.source, args.limit, args.concurrency, args.delay))


if __name__ == "__main__":
    main()
