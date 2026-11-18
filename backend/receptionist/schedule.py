"""Service area, open slots and bookings, backed by the JSON files in data/.

Plain Python with no LiveKit imports, so it can be tested on its own.
"""

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BOOKINGS_PATH = DATA_DIR / "bookings.json"

DIGIT_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
HOUR_WORDS = ["twelve", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven"]
MINUTE_WORDS = {15: "fifteen", 30: "thirty", 45: "forty five"}


def slot_id(slot: datetime) -> str:
    return slot.isoformat(timespec="minutes")


def is_covered(zip_code: str) -> bool:
    """True when the zip code is in the service area file."""
    return zip_code in json.loads((DATA_DIR / "service_area.json").read_text())


def open_slots(today: date, bookings_path: Path) -> list[datetime]:
    """Open visit slots from tomorrow through seven days out, in order."""
    weekly = json.loads((DATA_DIR / "weekly_slots.json").read_text())
    booked = {b["slot_id"] for b in _read_bookings(bookings_path)}
    slots = []
    for days_ahead in range(1, 8):
        day = today + timedelta(days=days_ahead)
        for start in weekly.get(day.strftime("%A").lower(), []):
            slot = datetime.combine(day, datetime.strptime(start, "%H:%M").time())
            if slot_id(slot) not in booked:
                slots.append(slot)
    return slots


def spoken_time(slot: datetime, today: date) -> str:
    """How a person says the slot on the phone."""
    day = "tomorrow" if slot.date() == today + timedelta(days=1) else slot.strftime("%A")
    words = [HOUR_WORDS[slot.hour % 12]]
    if slot.minute:
        words.append(MINUTE_WORDS[slot.minute])
    if slot.hour < 12:
        period = "in the morning"
    elif slot.hour < 17:
        period = "in the afternoon"
    else:
        period = "in the evening"
    return f"{day} at {' '.join(words)} {period}"


def spoken_digits(digits: str) -> str:
    """Digits as words for text to speech, phone numbers grouped 3, 3, 4."""
    if len(digits) == 10:
        groups = [digits[:3], digits[3:6], digits[6:]]
    else:
        groups = [digits]
    return ", ".join(" ".join(DIGIT_WORDS[int(d)] for d in group) for group in groups)


def save_booking(bookings_path: Path, booking: dict) -> None:
    """Append a booking to the file, replacing it in one step."""
    bookings = _read_bookings(bookings_path) + [booking]
    bookings_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = bookings_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(bookings, indent=2))
    os.replace(temp_path, bookings_path)


def _read_bookings(bookings_path: Path) -> list[dict]:
    if not bookings_path.exists():
        return []
    return json.loads(bookings_path.read_text())
