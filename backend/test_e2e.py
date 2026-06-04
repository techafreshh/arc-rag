import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from src.agent import agent

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


async def test():
    if not OPENROUTER_API_KEY:
        print("SKIP - OPENROUTER_API_KEY not set in .env")
        return

    result = await asyncio.wait_for(
        agent.run("What is the Buffer tool in ArcGIS Pro?"),
        timeout=30.0,
    )

    output = result.output if hasattr(result, "output") else str(result)
    print("--- Response ---")
    print(output)
    print("--- End Response ---")

    assert "![" in output, "Response does not contain markdown image syntax"
    print("Images found in response")

    assert "Source:" in output or "Source" in output, "Response does not contain a source citation"
    print("Source citation found in response")

    print("PASS - E2E tool flow")


if __name__ == "__main__":
    asyncio.run(test())
