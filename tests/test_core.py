"""Test del nucleo (senza interfaccia): python -m pytest tests"""
from datetime import date, datetime, timedelta

from kalendae.database import Database, Event
from kalendae.ics import export_ics, parse_ics
from kalendae.recurrence import expand


def make_db(tmp_path):
    return Database(tmp_path / "test.db")


def test_default_calendars(tmp_path):
    db = make_db(tmp_path)
    assert [c.name for c in db.calendars()] == ["Personale", "Lavoro"]


def test_crud_and_range(tmp_path):
    db = make_db(tmp_path)
    cid = db.calendars()[0].id
    ev = Event(None, cid, "Consiglio di classe", datetime(2026, 11, 10, 15), datetime(2026, 11, 10, 17))
    db.add_event(ev)
    occ = db.occurrences(datetime(2026, 11, 9), datetime(2026, 11, 16))
    assert len(occ) == 1 and occ[0].event.title == "Consiglio di classe"
    assert db.occurrences(datetime(2026, 11, 11), datetime(2026, 11, 12)) == []
    ev.title = "Scrutini"
    db.update_event(ev)
    assert db.get_event(ev.id).title == "Scrutini"
    db.delete_event(ev.id)
    assert db.get_event(ev.id) is None


def test_weekly_recurrence_with_exdate_and_until(tmp_path):
    db = make_db(tmp_path)
    cid = db.calendars()[0].id
    ev = Event(None, cid, "Lezione TIC", datetime(2026, 9, 16, 8), datetime(2026, 9, 16, 10),
               recurrence="WEEKLY", until=date(2026, 12, 23))
    db.add_event(ev)
    db.delete_occurrence(ev, date(2026, 11, 4))
    occ = db.occurrences(datetime(2026, 11, 1), datetime(2026, 12, 1))
    assert [o.start.day for o in occ] == [11, 18, 25]
    assert db.occurrences(datetime(2027, 1, 1), datetime(2027, 2, 1)) == []


def test_monthly_skips_missing_days():
    ev = Event(None, 1, "Fine mese", datetime(2026, 1, 31, 9), datetime(2026, 1, 31, 10), recurrence="MONTHLY")
    months = [s.month for s, _ in expand(ev, datetime(2026, 1, 1), datetime(2026, 8, 1))]
    assert months == [1, 3, 5, 7]


def test_daily_jump_is_fast_and_correct():
    ev = Event(None, 1, "x", datetime(2000, 1, 1, 7), datetime(2000, 1, 1, 8), recurrence="DAILY", interval=3)
    occ = list(expand(ev, datetime(2026, 11, 1), datetime(2026, 11, 8)))
    assert all((s - ev.start).days % 3 == 0 for s, _ in occ)
    assert len(occ) in (2, 3)


def test_ics_roundtrip(tmp_path):
    db = make_db(tmp_path)
    cid = db.calendars()[0].id
    evs = [
        Event(None, cid, "Gita, a Matera; partenza", datetime(2026, 11, 20, 7, 30), datetime(2026, 11, 20, 19),
              location="Piazza", description="Riga 1\nRiga 2", reminder=60),
        Event(None, cid, "Ponte", datetime(2026, 12, 7), datetime(2026, 12, 9), all_day=True),
        Event(None, cid, "Riunione", datetime(2026, 11, 2, 15), datetime(2026, 11, 2, 16),
              recurrence="WEEKLY", interval=2, until=date(2027, 1, 31), exdates={date(2026, 11, 16)}),
    ]
    for e in evs:
        db.add_event(e)
    path = tmp_path / "out.ics"
    export_ics(db.all_events(), path)
    back = {e.title: e for e in parse_ics(path, cid)}
    g = back["Gita, a Matera; partenza"]
    assert g.description == "Riga 1\nRiga 2" and g.reminder == 60 and g.start == evs[0].start
    assert back["Ponte"].all_day and back["Ponte"].end == datetime(2026, 12, 9)
    r = back["Riunione"]
    assert (r.recurrence, r.interval, r.until, r.exdates) == ("WEEKLY", 2, date(2027, 1, 31), {date(2026, 11, 16)})


def test_ics_google_style(tmp_path):
    text = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n"
        "DTSTART;TZID=Europe/Rome:20261110T090000\r\nDTEND;TZID=Europe/Rome:20261110T100000\r\n"
        "RRULE:FREQ=DAILY;COUNT=5\r\nSUMMARY:Evento con una descrizione molto lunga che viene \r\n"
        " spezzata su due righe\r\nUID:abc@google.com\r\n"
        "BEGIN:VALARM\r\nTRIGGER:-P1D\r\nACTION:DISPLAY\r\nEND:VALARM\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
    p = tmp_path / "g.ics"
    p.write_text(text)
    (ev,) = parse_ics(p, 1)
    assert ev.title.endswith("spezzata su due righe")
    assert ev.until == date(2026, 11, 14) and ev.reminder == 1440 and ev.uid == "abc@google.com"


