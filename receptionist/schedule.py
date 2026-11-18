"""Service area, open slots and bookings, backed by the JSON files in data/.

Plain Python with no LiveKit imports, so it can be tested on its own.
"""

from datetime import date, datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BOOKINGS_PATH = DATA_DIR / "bookings.json"


def is_covered(zip_code: str) -> bool:
    raise NotImplementedError


def open_slots(today: date, bookings_path: Path) -> list[datetime]:
    raise NotImplementedError


def spoken_time(slot: datetime, today: date) -> str:
    raise NotImplementedError


def spoken_digits(digits: str) -> str:
    raise NotImplementedError


def save_booking(bookings_path: Path, booking: dict) -> None:
    raise NotImplementedError
