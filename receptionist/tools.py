"""The tools the agent can call, and the state one call keeps between them.

To add a tool: write a function with @function_tool and add it to all_tools().
The admin UI lists whatever all_tools() returns, and the config decides which
of them a call gets.
"""

import logging
import random
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from livekit.agents import RunContext, function_tool
from livekit.agents.beta import EndCallTool
from livekit.agents.llm import FunctionTool

from receptionist import schedule

logger = logging.getLogger("receptionist")

Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

TRANSFER_LINE = "Okay, I'm connecting you with someone on our team now."


@dataclass
class CallState:
    """What one call remembers between tool calls."""

    today: date = field(default_factory=date.today)
    bookings_path: Path = schedule.BOOKINGS_PATH
    zip_code: str | None = None  # set once the service area check passes
    service: str | None = None  # from the last slot lookup, saved with the booking
    pending_booking: dict | None = None  # details read back, waiting for the caller's yes
    read_back_turn: int = 0  # caller messages in the history when the read-back was given
    emergency: bool = False  # set by the emergency guardrail; blocks booking


def caller_turns(ctx: RunContext[CallState]) -> int:
    """How many times the caller has spoken so far in this call."""
    return sum(1 for message in ctx.session.history.messages() if message.role == "user")


def say_filler(ctx: RunContext[CallState], lines: list[str]) -> None:
    """Say a short line while the model writes its answer, unless the agent already spoke this turn."""
    if ctx.session.history.messages()[-1].role == "user":
        ctx.session.say(random.choice(lines))


@function_tool
async def check_service_area(ctx: RunContext[CallState], zip_code: str) -> dict:
    """Check whether we send technicians to the caller's zip code.

    Call this as soon as the caller gives a zip code, before offering times.

    Args:
        zip_code: Five digits, for example "78704". Convert spoken digits to numerals.
    """
    digits = re.sub(r"\D", "", zip_code)
    if len(digits) != 5:
        return {"ok": False, "reason": "invalid_zip"}
    say_filler(ctx, ["Let me check that zip code.", "Okay, let me check that area."])
    covered = schedule.is_covered(digits)
    ctx.userdata.zip_code = digits if covered else None
    return {"ok": True, "covered": covered}


@function_tool
async def find_available_slots(
    ctx: RunContext[CallState],
    service: Literal["heating", "cooling", "plumbing"],
    preferred_day: Weekday | None = None,
) -> dict:
    """Look up open visit times in the next seven days.

    Returns up to three slots. Each has a "slot_id" to book with and a "spoken" text to say to the caller.

    Args:
        service: The kind of problem.
        preferred_day: Only a weekday the caller named, never today's. Leave it null for the soonest times.
    """
    state = ctx.userdata
    state.service = service
    say_filler(ctx, ["Let me pull up the schedule.", "Let me see what we have open."])
    slots = schedule.open_slots(state.today, state.bookings_path)
    on_day = [slot for slot in slots if slot.strftime("%A").lower() == preferred_day]
    result = {
        "ok": True,
        "slots": [
            {"slot_id": schedule.slot_id(slot), "spoken": schedule.spoken_time(slot, state.today)}
            for slot in (on_day or slots)[:3]
        ],
    }
    if preferred_day and not on_day:
        result["preferred_day_available"] = False
    return result


@function_tool
async def book_appointment(
    ctx: RunContext[CallState],
    name: str,
    phone: str,
    slot_id: str,
    issue: str,
    caller_confirmed: bool,
) -> dict:
    """Book a technician visit. It takes two calls.

    First call it with caller_confirmed false. Nothing is saved yet. The result has a "read_back" text that ends with a question: say it to the caller and wait for the answer.
    Only after the caller clearly says yes, call it again with the same details and caller_confirmed true.
    If the caller changes anything, start again with caller_confirmed false.

    Args:
        name: The caller's full name.
        phone: Ten digit callback number, digits only.
        slot_id: The "slot_id" of the time the caller picked, from find_available_slots.
        issue: The problem as a short phrase that reads well after "for", like "a furnace that won't turn on".
        caller_confirmed: True only after the caller said yes to the read-back.
    """
    state = ctx.userdata
    phone = re.sub(r"\D", "", phone)
    if state.emergency:
        return {"ok": False, "reason": "emergency"}
    if state.zip_code is None:
        return {"ok": False, "reason": "service_area_not_checked"}
    if len(phone) != 10:
        return {"ok": False, "reason": "invalid_phone"}
    open_ids = {schedule.slot_id(slot): slot for slot in schedule.open_slots(state.today, state.bookings_path)}
    if slot_id not in open_ids:
        return {"ok": False, "reason": "slot_unavailable"}

    details = {
        "name": name,
        "phone": phone,
        "zip_code": state.zip_code,
        "slot_id": slot_id,
        "issue": issue,
        "service": state.service,
    }
    when = schedule.spoken_time(open_ids[slot_id], state.today)
    if not caller_confirmed:
        state.pending_booking = details
        state.read_back_turn = caller_turns(ctx)
        read_back = (
            f"I have {name} down for {when}, for {issue}, "
            f"and the callback number is {schedule.spoken_digits(phone)}. Is that right?"
        )
        return {"ok": True, "status": "needs_confirmation", "read_back": read_back}

    # The caller must have spoken since the read-back, so the model cannot say yes on their behalf.
    pending = state.pending_booking
    if pending is None or caller_turns(ctx) == state.read_back_turn:
        return {"ok": False, "reason": "read_back_required"}
    if (name.casefold(), phone, slot_id) != (pending["name"].casefold(), pending["phone"], pending["slot_id"]):
        return {"ok": False, "reason": "details_changed"}

    # Save what was read back, even if the model words the issue differently the second time.
    booking = {**pending, "created_at": datetime.now().isoformat(timespec="seconds")}
    schedule.save_booking(state.bookings_path, booking)
    state.pending_booking = None
    return {"ok": True, "status": "booked", "spoken": when}


@function_tool
async def transfer_to_human(ctx: RunContext[CallState], reason: str) -> None:
    """Hand the call to a person on the team.

    Use it when the caller asks for a person, when the problem cannot wait for the next open time, or after an emergency once the caller is safe.
    It tells the caller they are being connected, so call it right away instead of announcing it.

    Args:
        reason: One short sentence for the person who picks up.
    """
    logger.info("transfer to a person: %s", reason)
    # Not interruptible: the call ends right after, so the caller must hear why.
    ctx.session.say(TRANSFER_LINE, allow_interruptions=False)
    # On a SIP call, get_job_context().transfer_sip_participant(caller, "tel:+1...") goes here instead of the hang-up.
    ctx.session.shutdown()


# A tool that cannot work without others. The API refuses a config that enables it alone.
REQUIRES = {"book_appointment": {"check_service_area", "find_available_slots"}}


def all_tools() -> list[FunctionTool]:
    """Every tool the agent can be given. A tool's id is its function name."""
    return [
        check_service_area,
        find_available_slots,
        book_appointment,
        transfer_to_human,
        # No reply after the tool: the agent says goodbye in the same turn, and a second reply came out as fragments.
        *EndCallTool(end_instructions=None).tools,
    ]
