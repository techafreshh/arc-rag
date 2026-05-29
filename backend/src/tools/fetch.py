from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from cachetools import TTLCache
from pydantic import BaseModel

_cache: TTLCache = TTLCache(maxsize=100, ttl=300)


class ImageInfo(BaseModel):
    url: str
    alt: str


class Section(BaseModel):
    heading: str
    content: str


class PageContent(BaseModel):
    url: str
    title: str
    sections: list[Section]
    images: list[ImageInfo]
    code_blocks: list[str]
    error: str | None = None


async def fetch_page(url: str) -> PageContent:
    """Fetch and parse an ArcGIS documentation page, returning structured content."""
    if url in _cache:
        return _cache[url]

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            resp = await client.get(url)
    except httpx.TimeoutException:
        return PageContent(url=url, title="", sections=[], images=[], code_blocks=[], error="Timeout fetching page")
    except Exception as e:
        return PageContent(url=url, title="", sections=[], images=[], code_blocks=[], error=str(e))

    if resp.status_code != 200:
        return PageContent(url=url, title="", sections=[], images=[], code_blocks=[], error=f"HTTP {resp.status_code}")

    base_url = str(resp.url)
    soup = BeautifulSoup(resp.text, "html.parser")

    article = soup.find("article", id="main") or soup.find("main") or soup.find("article")
    if not article:
        return PageContent(url=base_url, title="", sections=[], images=[], code_blocks=[], error="No main content found")

    for tag in article.find_all(["nav", "footer"]):
        tag.decompose()

    title_tag = article.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else ""

    images = [
        ImageInfo(url=urljoin(base_url, img.get("src", "")), alt=img.get("alt", ""))
        for img in article.find_all("img") if img.get("src")
    ]

    code_blocks = [pre.get_text() for pre in article.find_all("pre")]

    sections: list[Section] = []
    for h2 in article.find_all("h2"):
        parts = []
        for sib in h2.next_siblings:
            if sib.name == "h2":
                break
            text = sib.get_text(separator="\n", strip=True) if hasattr(sib, "get_text") else str(sib).strip()
            if text:
                parts.append(text)
        sections.append(Section(heading=h2.get_text(strip=True), content="\n".join(parts)))

    result = PageContent(url=base_url, title=title, sections=sections, images=images, code_blocks=code_blocks)
    _cache[url] = result
    return result
