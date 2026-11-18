import json
from datetime import date, datetime

from receptionist import schedule

TODAY = date(2026, 11, 18)  # a Wednesday


def test_slots_never_include_today(tmp_path):
    slots = schedule.open_slots(TODAY, tmp_path / "bookings.json")
    assert all(slot.date() > TODAY for slot in slots)


def test_slots_stop_after_seven_days(tmp_path):
    slots = schedule.open_slots(TODAY, tmp_path / "bookings.json")
    assert max(slot.date() for slot in slots) == date(2026, 11, 25)


def test_sunday_has_no_slots(tmp_path):
    slots = schedule.open_slots(TODAY, tmp_path / "bookings.json")
    assert not [slot for slot in slots if slot.weekday() == 6]


def test_slots_are_in_order(tmp_path):
    slots = schedule.open_slots(TODAY, tmp_path / "bookings.json")
    assert slots == sorted(slots)
    assert slots[0] == datetime(2026, 11, 19, 9, 0)


def test_booked_slot_is_not_open(tmp_path):
    path = tmp_path / "bookings.json"
    path.write_text(json.dumps([{"slot_id": "2026-11-19T14:30"}]))
    slots = schedule.open_slots(TODAY, path)
    assert datetime(2026, 11, 19, 14, 30) not in slots
    assert datetime(2026, 11, 19, 11, 30) in slots


def test_spoken_time_tomorrow_morning():
    assert schedule.spoken_time(datetime(2026, 11, 19, 9, 0), TODAY) == "tomorrow at nine in the morning"


def test_spoken_time_tomorrow_afternoon():
    assert schedule.spoken_time(datetime(2026, 11, 19, 14, 30), TODAY) == "tomorrow at two thirty in the afternoon"


def test_spoken_time_uses_weekday():
    assert schedule.spoken_time(datetime(2026, 11, 20, 11, 30), TODAY) == "Friday at eleven thirty in the morning"


def test_spoken_time_evening_quarter_hour():
    assert schedule.spoken_time(datetime(2026, 11, 21, 17, 15), TODAY) == "Saturday at five fifteen in the evening"


def test_spoken_digits_phone_number():
    assert schedule.spoken_digits("5125550132") == "five one two, five five five, zero one three two"


def test_spoken_digits_zip_code():
    assert schedule.spoken_digits("78704") == "seven eight seven zero four"


def test_save_booking_creates_file(tmp_path):
    path = tmp_path / "data" / "bookings.json"
    schedule.save_booking(path, {"slot_id": "2026-11-19T09:00"})
    assert json.loads(path.read_text()) == [{"slot_id": "2026-11-19T09:00"}]


def test_save_booking_appends(tmp_path):
    path = tmp_path / "bookings.json"
    schedule.save_booking(path, {"slot_id": "2026-11-19T09:00"})
    schedule.save_booking(path, {"slot_id": "2026-11-19T11:30"})
    assert [b["slot_id"] for b in json.loads(path.read_text())] == ["2026-11-19T09:00", "2026-11-19T11:30"]


def test_covered_zip_code():
    assert schedule.is_covered("78704")
    assert schedule.is_covered("78745")


def test_uncovered_zip_code():
    assert not schedule.is_covered("73301")
