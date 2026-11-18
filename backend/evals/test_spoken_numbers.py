"""Numbers the way the real speech-to-text hears them.

The other evals hand the model text that I typed. Here a voice says the caller's line,
Deepgram transcribes the audio, and the agent gets that transcript.
"""

import os

import httpx
import pytest

DEEPGRAM = "https://api.deepgram.com/v1"

pytestmark = pytest.mark.skipif(not os.getenv("DEEPGRAM_API_KEY"), reason="set DEEPGRAM_API_KEY")


async def heard(line):
    """What speech-to-text writes when a voice says the line."""
    headers = {"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}"}
    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        audio = await client.post(f"{DEEPGRAM}/speak", params={"model": "aura-2-apollo-en"}, json={"text": line})
        audio.raise_for_status()
        text = await client.post(
            f"{DEEPGRAM}/listen", params={"model": "nova-3", "punctuate": "true"}, content=audio.content
        )
        text.raise_for_status()
    transcript = text.json()["results"]["channels"][0]["alternatives"][0]["transcript"]
    print(f"said:  {line}\nheard: {transcript}")
    return transcript


async def test_a_spoken_zip_code_and_phone_number_reach_the_tools_as_digits(start_call):
    session = await start_call()
    await session.run(user_input=await heard("Hi, my furnace won't turn on. My zip code is seven eight seven oh four."))
    await session.run(user_input=await heard("Tomorrow at two thirty works."))
    await session.run(
        user_input=await heard("It's Dana Smith, and my number is five one two, five five five, oh one three two.")
    )
    assert session.userdata.zip_code == "78704"
    assert session.userdata.pending_booking["phone"] == "5125550132"
