"""Time to first output for several LLMs on LiveKit Inference: a plain reply and a tool call.

Run it with `uv run python scripts/time_llms.py`. It needs the LiveKit keys in .env and uses a few cents of credit.
"""

import asyncio
import statistics
import time

from dotenv import load_dotenv
from livekit.agents import RunContext, function_tool, inference
from livekit.agents.llm import ChatContext

MODELS = [
    "google/gemma-4-31b-it",
    "openai/gpt-5.4-mini",
    "openai/gpt-6-luna",
    "google/gemini-3.8-flash",
    "google/gemini-3.5-flash-lite",
    "openai/gpt-oss-120b",
]
SYSTEM = (
    "You are Riley, the phone receptionist for a heating and plumbing company. "
    "Speak in one or two short sentences. When the caller gives a zip code, call check_service_area."
)
PLAIN = "Hi, my water heater is leaking a little."
TOOL = "My zip code is seven eight seven oh four."
ROUNDS = 5


@function_tool
async def check_service_area(ctx: RunContext, zip_code: str) -> dict:
    """Check whether technicians cover a zip code.

    Args:
        zip_code: Five digit US zip code, digits only.
    """
    return {"covered": True}


async def first_output(model: inference.LLM, caller: str) -> float:
    """Milliseconds until the first text or tool call arrives."""
    chat = ChatContext()
    chat.add_message(role="system", content=SYSTEM)
    chat.add_message(role="user", content=caller)
    start = time.perf_counter()
    async for chunk in model.chat(chat_ctx=chat, tools=[check_service_area]):
        if chunk.delta and (chunk.delta.content or chunk.delta.tool_calls):
            break
    return (time.perf_counter() - start) * 1000


async def main() -> None:
    for name in MODELS:
        async with inference.LLM(name) as model:
            await first_output(model, "Hello?")  # open the connection before timing
            plain = [await first_output(model, PLAIN) for _ in range(ROUNDS)]
            tool = [await first_output(model, TOOL) for _ in range(ROUNDS)]
        print(f"{name:30s} plain {statistics.median(plain):5.0f} ms   tool call {statistics.median(tool):5.0f} ms")


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
