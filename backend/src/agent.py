import os

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext

from src.tools.fetch import PageContent, fetch_page as _fetch_page
from src.tools.lookup import lookup_url as _lookup_url
from src.tools.search import SearchResults, search_index as _search_index

load_dotenv()

model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")

agent = Agent(
    f"openrouter:{model}",
    instructions=(
        "You are a GIS documentation assistant helping students learn ArcGIS Pro and ArcMap. "
        "Answer questions clearly and concisely, using technical terminology appropriate for "
        "GIS students. "
        "When asked about a specific ArcGIS tool or concept: call search_index with the student's "
        "question first to find the most relevant documentation pages, then call fetch_page on the "
        "best 1-2 URLs to get the full content. "
        "You may also call lookup_url for quick lookups of well-known tool names, but prefer "
        "search_index for any non-trivial question. "
        "Always include relevant images from the fetched page using markdown ![alt](url) syntax. "
        "Always end responses with a source citation: **Source:** [Page Title](url). "
        "If search_index returns no relevant results, tell the student you don't have "
        "documentation on that topic. If you are unsure about something, say so rather than guessing."
    ),
)


@agent.tool
async def fetch_page(ctx: RunContext, url: str) -> str:
    """Fetch and parse an ArcGIS documentation page. Returns the page content including text sections, images, and code blocks."""
    result = await _fetch_page(url)
    if result.error:
        return f"Error fetching {url}: {result.error}"
    parts = [f"# {result.title}", ""]
    for section in result.sections:
        parts.append(f"## {section.heading}")
        parts.append(section.content)
        parts.append("")
    if result.code_blocks:
        parts.append("## Code Examples")
        for code in result.code_blocks:
            parts.append(f"```python\n{code}\n```")
        parts.append("")
    if result.images:
        parts.append("## Images")
        for img in result.images:
            parts.append(f"![{img.alt}]({img.url})")
        parts.append("")
    parts.append(f"Source: {result.url}")
    return "\n".join(parts)


@agent.tool
async def lookup_url(ctx: RunContext, topic: str) -> str:
    """Look up the ArcGIS documentation URL for a given GIS topic or tool name (e.g. 'buffer', 'clip', 'geodatabase'). Use this BEFORE calling fetch_page to find the correct URL."""
    result = _lookup_url(topic)
    if result is None:
        return f"No URL found for topic: {topic}"
    return f"URL: {result.url}\nTitle: {result.title}"


@agent.tool
async def search_index(ctx: RunContext, query: str, top_k: int = 5) -> str:
    """Search the ArcGIS documentation index for pages matching a student's question. Returns ranked results with URLs, titles, summaries, and relevance scores. Use this FIRST when a student asks about an ArcGIS tool, workflow, or concept — then call fetch_page on the best 1-2 URLs to get the full content. Pass the student's original question as the query."""
    result = await _search_index(query, top_k=top_k)
    if result.error:
        return f"Search error: {result.error}"
    if not result.results:
        return "No relevant documentation found for that query."
    parts = [f"Found {len(result.results)} relevant documentation pages:"]
    for i, r in enumerate(result.results, 1):
        heading = f" — {r.section}" if r.section else ""
        parts.append(f"{i}. [{r.title}{heading}]({r.url}) (source: {r.source}, score: {r.score:.2f})")
        if r.summary:
            parts.append(f"   {r.summary[:200]}")
    return "\n".join(parts)


if __name__ == "__main__":
    agent.to_cli_sync(prog_name="arcrag")
