import os

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext

from src.tools.fetch import PageContent, fetch_page as _fetch_page
from src.tools.lookup import lookup_url as _lookup_url

load_dotenv()

model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")

agent = Agent(
    f"openrouter:{model}",
    instructions=(
        "You are a GIS documentation assistant helping students learn ArcGIS Pro and ArcMap. "
        "Answer questions clearly and concisely, using technical terminology appropriate for "
        "GIS students. "
        "When asked about a specific ArcGIS tool or concept: call lookup_url first to find the "
        "documentation URL, then call fetch_page with that URL to get the full content. "
        "Always include relevant images from the fetched page using markdown ![alt](url) syntax. "
        "Always end responses with a source citation: **Source:** [Page Title](url). "
        "If lookup_url returns no URL, tell the student you don't have that specific tool in "
        "your reference set yet. If you are unsure about something, say so rather than guessing."
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


if __name__ == "__main__":
    agent.to_cli_sync(prog_name="arcrag")
