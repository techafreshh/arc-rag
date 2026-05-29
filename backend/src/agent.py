import os

from dotenv import load_dotenv
from pydantic_ai import Agent

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

if __name__ == "__main__":
    agent.to_cli_sync(prog_name="arcrag")
