"""The tools the agent can call, and the state one call keeps between them.

To add a tool: write a function with @function_tool and add it to all_tools().
The admin UI lists whatever all_tools() returns, and the config decides which
of them a call gets.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from livekit.agents import RunContext, function_tool
from livekit.agents.beta import EndCallTool
from livekit.agents.llm import FunctionTool

from receptionist import schedule

Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


@dataclass
class CallState:
    """What one call remembers between tool calls."""

    today: date = field(default_factory=date.today)
    bookings_path: Path = schedule.BOOKINGS_PATH
    zip_code: str | None = None  # set once the service area check passes
    pending_booking: dict | None = None  # details read back, waiting for the caller's yes
    emergency: bool = False  # set by the emergency guardrail; blocks booking


@function_tool
async def check_service_area(ctx: RunContext[CallState], zip_code: str) -> dict:
    """Check whether we send technicians to the caller's zip code.

    Call this as soon as the caller gives a zip code, before offering times.

    Args:
        zip_code: Five digits, for example "78704". Convert spoken digits to numerals.
    """
    raise NotImplementedError


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
        preferred_day: A weekday the caller asked for. Leave empty for the soonest times.
    """
    raise NotImplementedError


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

    First call it with caller_confirmed false. Nothing is saved yet. The result has a "read_back" text: say it to the caller and ask if it is right.
    Only after the caller clearly says yes, call it again with the same details and caller_confirmed true.
    If the caller changes anything, start again with caller_confirmed false.

    Args:
        name: The caller's full name.
        phone: Ten digit callback number, digits only.
        slot_id: The "slot_id" of the time the caller picked, from find_available_slots.
        issue: The problem in a few words, the way the caller described it.
        caller_confirmed: True only after the caller said yes to the read-back.
    """
    raise NotImplementedError


@function_tool
async def transfer_to_human(ctx: RunContext[CallState], reason: str) -> None:
    """Hand the call to a person on the team.

    Use it when the caller asks for a person, when the problem cannot wait for the next open time, or after an emergency once the caller is safe.

    Args:
        reason: One short sentence for the person who picks up.
    """
    raise NotImplementedError


def all_tools() -> list[FunctionTool]:
    """Every tool the agent can be given. A tool's id is its function name."""
    return [
        check_service_area,
        find_available_slots,
        book_appointment,
        transfer_to_human,
        *EndCallTool(end_instructions="Say a short goodbye.").tools,
    ]
