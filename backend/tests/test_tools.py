import json
from datetime import date
from types import SimpleNamespace

import pytest
from livekit.agents.llm import ChatContext

from receptionist.tools import (
    TRANSFER_LINE,
    CallState,
    book_appointment,
    check_service_area,
    find_available_slots,
    transfer_to_human,
)

TOMORROW_2_30 = "2026-11-19T14:30"  # today is Wednesday 2026-11-18
DETAILS = {"name": "Dana Smith", "phone": "512-555-0132", "slot_id": TOMORROW_2_30, "issue": "a furnace that won't start"}


class FakeSession:
    """The parts of AgentSession the tools use. The call starts with the caller speaking."""

    def __init__(self):
        self.history = ChatContext()
        self.history.add_message(role="user", content="Hi, my furnace won't start")
        self.said = []
        self.closed = False

    def say(self, text, allow_interruptions=True):
        self.said.append(text)
        self.history.add_message(role="assistant", content=text)

    def shutdown(self):
        self.closed = True


@pytest.fixture
def ctx(tmp_path):
    state = CallState(today=date(2026, 11, 18), bookings_path=tmp_path / "bookings.json")
    return SimpleNamespace(userdata=state, session=FakeSession())


def caller_says(ctx, text):
    ctx.session.history.add_message(role="user", content=text)


async def ask_to_book(ctx, **changes):
    return await book_appointment(ctx, **(DETAILS | changes), caller_confirmed=False)


async def confirm(ctx, **changes):
    return await book_appointment(ctx, **(DETAILS | changes), caller_confirmed=True)


def saved_bookings(ctx):
    path = ctx.userdata.bookings_path
    return json.loads(path.read_text()) if path.exists() else []


async def test_zip_code_needs_five_digits(ctx):
    assert await check_service_area(ctx, "7870") == {"ok": False, "reason": "invalid_zip"}
    assert await check_service_area(ctx, "7 8 7 0 4") == {"ok": True, "covered": True}
    assert ctx.userdata.zip_code == "78704"


async def test_zip_code_outside_the_area_clears_the_last_one(ctx):
    await check_service_area(ctx, "78704")
    assert await check_service_area(ctx, "73301") == {"ok": True, "covered": False}
    assert ctx.userdata.zip_code is None


async def test_one_filler_line_per_caller_turn(ctx):
    caller_says(ctx, "It's 78704")
    await check_service_area(ctx, "78704")
    await find_available_slots(ctx, "heating", "soonest", "any")
    assert len(ctx.session.said) == 1

    caller_says(ctx, "Anything on Friday?")
    await find_available_slots(ctx, "heating", "friday", "any")
    assert len(ctx.session.said) == 2


async def test_slots_on_the_preferred_day(ctx):
    result = await find_available_slots(ctx, "plumbing", "friday", "any")
    assert [slot["slot_id"] for slot in result["slots"]] == ["2026-11-20T09:00", "2026-11-20T11:30", "2026-11-20T14:30"]
    assert result["slots"][0]["spoken"] == "Friday at nine in the morning"
    assert "preferred_day_available" not in result


async def test_preferred_day_without_slots_gives_the_soonest(ctx):
    result = await find_available_slots(ctx, "cooling", "sunday", "any")
    assert result["preferred_day_available"] is False
    assert [slot["slot_id"] for slot in result["slots"]] == ["2026-11-19T09:00", "2026-11-19T11:30", "2026-11-19T14:30"]


async def test_slots_in_the_afternoon_only(ctx):
    result = await find_available_slots(ctx, "cooling", "soonest", "afternoon")
    assert [slot["slot_id"] for slot in result["slots"]] == ["2026-11-19T14:30", "2026-11-20T14:30", "2026-11-23T14:30"]


async def test_booking_needs_the_service_area_check(ctx):
    assert await ask_to_book(ctx) == {"ok": False, "reason": "service_area_not_checked"}


async def test_booking_needs_a_ten_digit_phone(ctx):
    await check_service_area(ctx, "78704")
    assert await ask_to_book(ctx, phone="555 0132") == {"ok": False, "reason": "invalid_phone"}


async def test_booking_needs_an_open_slot(ctx):
    await check_service_area(ctx, "78704")
    assert await ask_to_book(ctx, slot_id="2026-11-18T14:30") == {"ok": False, "reason": "slot_unavailable"}
    assert await ask_to_book(ctx, slot_id="2026-11-19T15:00") == {"ok": False, "reason": "slot_unavailable"}


async def test_emergency_blocks_booking(ctx):
    await check_service_area(ctx, "78704")
    ctx.userdata.emergency = True
    assert await ask_to_book(ctx) == {"ok": False, "reason": "emergency"}


async def test_confirm_without_read_back_is_refused(ctx):
    await check_service_area(ctx, "78704")
    caller_says(ctx, "Yes, book it")
    assert await confirm(ctx) == {"ok": False, "reason": "read_back_required"}
    assert saved_bookings(ctx) == []


async def test_confirm_in_the_same_caller_turn_is_refused(ctx):
    await check_service_area(ctx, "78704")
    caller_says(ctx, "It's Dana Smith, five one two, five five five, zero one three two")
    await ask_to_book(ctx)
    assert await confirm(ctx) == {"ok": False, "reason": "read_back_required"}
    assert saved_bookings(ctx) == []


async def test_changed_details_are_refused(ctx):
    await check_service_area(ctx, "78704")
    await ask_to_book(ctx)
    caller_says(ctx, "Yes, that's right")
    assert await confirm(ctx, slot_id="2026-11-19T09:00") == {"ok": False, "reason": "details_changed"}
    assert saved_bookings(ctx) == []


async def test_reworded_issue_saves_what_was_read_back(ctx):
    await check_service_area(ctx, "78704")
    await ask_to_book(ctx)
    caller_says(ctx, "Yes, that's right")
    assert (await confirm(ctx, issue="furnace not starting"))["status"] == "booked"
    assert saved_bookings(ctx)[0]["issue"] == "a furnace that won't start"


async def test_confirmed_booking_is_saved_once(ctx):
    await check_service_area(ctx, "78704")
    await find_available_slots(ctx, "heating", "soonest", "any")
    result = await ask_to_book(ctx)
    assert result["status"] == "needs_confirmation"
    assert result["read_back"] == (
        "I have Dana Smith down for tomorrow at two thirty in the afternoon, for a furnace that won't start, "
        "and the callback number is five one two, five five five, zero one three two. Is that right?"
    )
    caller_says(ctx, "Yes, that's right")

    assert await confirm(ctx) == {"ok": True, "status": "booked", "spoken": "tomorrow at two thirty in the afternoon"}
    [booking] = saved_bookings(ctx)
    assert booking | {"created_at": None} == {
        "name": "Dana Smith",
        "phone": "5125550132",
        "zip_code": "78704",
        "slot_id": TOMORROW_2_30,
        "issue": "a furnace that won't start",
        "service": "heating",
        "created_at": None,
    }

    # The slot is taken now, so the same confirmation cannot book it twice.
    assert await confirm(ctx) == {"ok": False, "reason": "slot_unavailable"}
    assert len(saved_bookings(ctx)) == 1


async def test_transfer_says_the_handoff_line_and_ends_the_call(ctx):
    assert await transfer_to_human(ctx, "Caller wants a person") is None
    assert ctx.session.said == [TRANSFER_LINE]
    assert ctx.session.closed
