import os

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext

from src.tools.fetch import PageContent, fetch_page as _fetch_page

load_dotenv()

model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")

agent = Agent(
    f"openrouter:{model}",
    instructions=(
        "You are a GIS documentation assistant helping students learn ArcGIS Pro and ArcMap. "
        "Answer questions clearly and concisely, using technical terminology appropriate for "
        "GIS students. When tools are available, include relevant images and cite documentation "
        "sources. If you are unsure about something, say so rather than guessing."
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


if __name__ == "__main__":
    agent.to_cli_sync(prog_name="arcrag")
