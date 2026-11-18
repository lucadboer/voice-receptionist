"""Booking: the right tools with the right arguments, and nothing saved without a clear yes."""

import json

import pytest


def tool_calls(session):
    """Every tool call of the call so far, as (name, arguments)."""
    return [(item.name, json.loads(item.arguments)) for item in session.history.items if item.type == "function_call"]


async def reach_read_back(session, zip_code="78704", phone="512-555-0132"):
    """Drive the call to the read-back: the problem and zip code, a time, then a name and phone number."""
    await session.run(user_input=f"Hi, my furnace won't turn on. My zip code is {zip_code}.")
    await session.run(user_input="Tomorrow at two thirty works.")
    await session.run(user_input=f"It's Dana Smith, and my number is {phone}.")
    assert session.userdata.pending_booking, f"the agent did not read the booking back: {tool_calls(session)}"


async def test_a_caller_who_gives_everything_and_says_yes_is_booked(start_call, state):
    session = await start_call()
    await reach_read_back(session)
    await session.run(user_input="Yes, that's right.")

    calls = tool_calls(session)
    names = [name for name, _ in calls]
    assert names.index("check_service_area") < names.index("find_available_slots") < names.index("book_appointment")
    assert [args["caller_confirmed"] for name, args in calls if name == "book_appointment"] == [False, True]
    bookings = json.loads(state.bookings_path.read_text())
    assert len(bookings) == 1
    booking = bookings[0]
    assert (booking["zip_code"], booking["phone"], booking["slot_id"]) == ("78704", "5125550132", "2026-11-19T14:30")


async def test_nothing_is_saved_when_the_caller_does_not_say_yes(start_call, state, judge):
    session = await start_call()
    await reach_read_back(session)
    result = await session.run(user_input="Hmm, let me check with my wife first and call you back.")

    assert not state.bookings_path.exists()
    await result.expect.contains_message(role="assistant").judge(
        judge, intent="Does not tell the caller that the visit is booked."
    )


async def test_a_caller_who_changes_the_time_hears_a_new_read_back_and_gets_the_new_time(start_call, state):
    session = await start_call()
    await reach_read_back(session)
    result = await session.run(user_input="Actually, can we do nine in the morning instead?")
    result.expect.contains_function_call(
        name="book_appointment", arguments={"slot_id": "2026-11-19T09:00", "caller_confirmed": False}
    )
    assert "nine in the morning" in result.expect[-1].is_message(role="assistant").event().item.text_content

    await session.run(user_input="Yes, that's right.")
    bookings = json.loads(state.bookings_path.read_text())
    assert [booking["slot_id"] for booking in bookings] == ["2026-11-19T09:00"]


async def test_a_zip_code_outside_the_service_area_gets_no_booking(start_call, state, judge):
    session = await start_call()
    result = await session.run(
        user_input="My AC stopped working. I'm in 73301. Tomorrow morning works, I'm Dana Smith, 512-555-0132."
    )

    assert tool_calls(session) == [("check_service_area", {"zip_code": "73301"})]
    assert not state.bookings_path.exists()
    await result.expect[-1].is_message(role="assistant").judge(
        judge, intent="Tells the caller that the company does not serve their area."
    )


# How speech-to-text writes numbers: as words, grouped the way people say them, with self-corrections.
@pytest.mark.parametrize(
    "spoken",
    [
        "seven eight seven oh four",
        "seventy eight seven oh four",
        "seven eight seven four, sorry, seven eight seven oh four",
    ],
)
async def test_a_spoken_zip_code_reaches_the_tool_as_digits(start_call, spoken):
    session = await start_call()
    await session.run(user_input=f"Hi, my furnace won't turn on. My zip code is {spoken}.")
    assert [args for name, args in tool_calls(session) if name == "check_service_area"] == [{"zip_code": "78704"}]


@pytest.mark.parametrize(
    "spoken",
    [
        "five one two, five five five, oh one three two",
        "five twelve, five five five, oh one thirty two",
        "five one two five five five zero one three two",  # what the real speech-to-text wrote in audio_check.py
    ],
)
async def test_a_spoken_phone_number_reaches_the_booking_as_digits(start_call, spoken):
    session = await start_call()
    await reach_read_back(session, phone=spoken)
    assert session.userdata.pending_booking["phone"] == "5125550132"
