"""A whole call: a second model plays a caller with a goal, and the eval checks how the call ends."""

import json
from datetime import datetime

from livekit.agents import llm
from livekit.plugins import anthropic

CALLER_MODEL = "claude-sonnet-5-5"  # not the agent's model, so the caller does not mirror the agent
CALLER = """You are on the phone with the receptionist of a heating and plumbing company. Your water heater is leaking
and you want a technician to come out. An afternoon visit suits you best.
Your name is Jordan Lee, your zip code is seven eight seven four five, and your phone number is
five one two, five five five, oh one nine eight. Give each of these only when the receptionist asks for it.
Say one short sentence at a time, the way people talk on the phone, and say numbers in words as written here.
Once the visit is booked and you need nothing else, say goodbye."""
MAX_TURNS = 12


async def caller_line(caller, session):
    """The caller's next line: the call so far with the roles swapped, so the caller model answers the agent."""
    chat = llm.ChatContext()
    chat.add_message(role="system", content=CALLER)
    for message in session.history.messages():
        chat.add_message(role="user" if message.role == "assistant" else "assistant", content=message.text_content)
    return (await caller.chat(chat_ctx=chat).collect()).text


async def test_a_simulated_caller_ends_up_with_an_afternoon_booking(start_call, state):
    session = await start_call()
    async with anthropic.LLM(model=CALLER_MODEL) as caller:
        for _ in range(MAX_TURNS):
            result = await session.run(user_input=await caller_line(caller, session))
            if any(event.type == "function_call" and event.item.name == "end_call" for event in result.events):
                break

    bookings = json.loads(state.bookings_path.read_text())
    assert len(bookings) == 1
    booking = bookings[0]
    assert (booking["name"], booking["phone"], booking["zip_code"]) == ("Jordan Lee", "5125550198", "78745")
    assert datetime.fromisoformat(booking["slot_id"]).hour >= 12
