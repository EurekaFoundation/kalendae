"""Test delle funzioni della versione 0.2: ricorrenze avanzate ed eccezioni."""
import sqlite3
from dataclasses import replace
from datetime import date, datetime, timedelta

from kalendae import series
from kalendae.database import Database, Event, Occurrence
from kalendae.ics import export_ics, import_into, parse_ics
from kalendae.recurrence import describe, expand, nth_weekday, until_from_count


def db_and_cal(tmp_path):
    db = Database(tmp_path / "t.db")
    return db, db.calendars()[0].id


def starts(ev, a, b):
    return [s for s, _ in expand(ev, a, b)]


def test_weekly_multiple_days():
    ev = Event(None, 1, "Lezioni", datetime(2026, 11, 4, 8), datetime(2026, 11, 4, 10),
               recurrence="WEEKLY", byday="MO,WE,FR")
    got = starts(ev, datetime(2026, 11, 1), datetime(2026, 11, 15))
    # parte da mercoledì 4: niente lunedì 2
    assert [s.day for s in got] == [4, 6, 9, 11, 13]


def test_weekly_every_two_weeks_jump_far_future():
    ev = Event(None, 1, "x", datetime(2020, 1, 6, 9), datetime(2020, 1, 6, 10),
               recurrence="WEEKLY", interval=2, byday="MO,TH")
    got = starts(ev, datetime(2026, 11, 1), datetime(2026, 11, 30))
    assert got and all(s.weekday() in (0, 3) for s in got)
    weeks = {(s.date() - date(2020, 1, 6)).days // 7 for s in got}
    assert all(w % 2 == 0 for w in weeks)


def test_monthly_nth_and_last_weekday():
    second_tue = Event(None, 1, "x", datetime(2026, 11, 10, 15), datetime(2026, 11, 10, 16),
                       recurrence="MONTHLY", byday="2TU")
    assert [s.date() for s in starts(second_tue, datetime(2026, 11, 1), datetime(2027, 2, 1))] == \
           [date(2026, 11, 10), date(2026, 12, 8), date(2027, 1, 12)]
    last_fri = Event(None, 1, "x", datetime(2026, 11, 27, 9), datetime(2026, 11, 27, 10),
                     recurrence="MONTHLY", byday="-1FR")
    assert [s.date() for s in starts(last_fri, datetime(2026, 11, 1), datetime(2027, 2, 1))] == \
           [date(2026, 11, 27), date(2026, 12, 25), date(2027, 1, 29)]
    assert nth_weekday(2026, 2, 5, 0) is None


def test_count_and_describe():
    ev = Event(None, 1, "x", datetime(2026, 11, 2, 9), datetime(2026, 11, 2, 10),
               recurrence="WEEKLY", byday="MO,WE")
    assert until_from_count(ev, 5) == date(2026, 11, 16)
    ev.until = date(2026, 12, 23)
    assert describe(ev) == "Ogni settimana il lunedì e mercoledì, fino al 23 dicembre 2026"
    ev2 = Event(None, 1, "x", datetime(2026, 11, 27, 9), datetime(2026, 11, 27, 10),
                recurrence="MONTHLY", interval=2, byday="-1FR")
    assert describe(ev2) == "Ogni 2 mesi l'ultimo venerdì"


def test_migration_from_v01(tmp_path):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE calendars (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, color TEXT NOT NULL, visible INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, calendar_id INTEGER NOT NULL, uid TEXT NOT NULL,
      title TEXT NOT NULL, start_at TEXT NOT NULL, end_at TEXT NOT NULL, all_day INTEGER NOT NULL DEFAULT 0,
      location TEXT DEFAULT '', description TEXT DEFAULT '', recurrence TEXT DEFAULT '', interval INTEGER DEFAULT 1,
      until TEXT, exdates TEXT DEFAULT '', reminder INTEGER DEFAULT -1);
    INSERT INTO calendars(name,color) VALUES ('Vecchio','#123456');
    INSERT INTO events(calendar_id,uid,title,start_at,end_at) VALUES (1,'u1','Vecchio evento','2026-11-02T09:00:00','2026-11-02T10:00:00');
    """)
    con.commit()
    con.close()
    db = Database(path)
    (ev,) = db.all_events()
    assert ev.title == "Vecchio evento" and ev.byday == "" and ev.parent_id is None


def _occ(db, title, day):
    a = datetime.combine(day, datetime.min.time())
    return next(o for o in db.occurrences(a, a + timedelta(days=1)) if o.event.title == title)


def test_edit_only_this_occurrence(tmp_path):
    db, cid = db_and_cal(tmp_path)
    db.add_event(Event(None, cid, "Lezione", datetime(2026, 11, 4, 8), datetime(2026, 11, 4, 10), recurrence="WEEKLY"))
    occ = _occ(db, "Lezione", date(2026, 11, 18))
    new = replace(db.get_event(occ.event.id), start=occ.start + timedelta(hours=3), end=occ.end + timedelta(hours=3),
                  title="Lezione spostata")
    series.edit_occurrence(db, occ, new, series.ONE)
    occs = db.occurrences(datetime(2026, 11, 1), datetime(2026, 12, 1))
    assert [(o.start.day, o.start.hour, o.event.title) for o in occs] == [
        (4, 8, "Lezione"), (11, 8, "Lezione"), (18, 11, "Lezione spostata"), (25, 8, "Lezione")]
    # eliminando la serie spariscono anche le eccezioni
    series.delete_occurrence(db, _occ(db, "Lezione", date(2026, 11, 25)), series.ALL)
    assert db.all_events() == []


def test_edit_this_and_following(tmp_path):
    db, cid = db_and_cal(tmp_path)
    db.add_event(Event(None, cid, "Corso", datetime(2026, 11, 2, 17), datetime(2026, 11, 2, 18), recurrence="WEEKLY"))
    occ = _occ(db, "Corso", date(2026, 11, 16))
    new = replace(db.get_event(occ.event.id), start=occ.start + timedelta(days=1), end=occ.end + timedelta(days=1),
                  title="Corso (martedì)")
    series.edit_occurrence(db, occ, new, series.FOLLOWING)
    occs = db.occurrences(datetime(2026, 11, 1), datetime(2026, 12, 1))
    assert [(o.start.day, o.event.title) for o in occs] == [
        (2, "Corso"), (9, "Corso"), (17, "Corso (martedì)"), (24, "Corso (martedì)")]


def test_edit_all_keeps_series_start(tmp_path):
    db, cid = db_and_cal(tmp_path)
    db.add_event(Event(None, cid, "Palestra", datetime(2026, 11, 2, 19), datetime(2026, 11, 2, 20),
                       recurrence="WEEKLY", byday="MO"))
    occ = _occ(db, "Palestra", date(2026, 11, 16))
    new = replace(db.get_event(occ.event.id), start=occ.start + timedelta(days=1, hours=1),
                  end=occ.end + timedelta(days=1, hours=1))
    series.edit_occurrence(db, occ, new, series.ALL)
    ev = db.all_events()[0]
    assert ev.start == datetime(2026, 11, 3, 20) and ev.byday == "TU"
    assert len(db.occurrences(datetime(2026, 11, 1), datetime(2026, 12, 1))) == 4


def test_delete_following(tmp_path):
    db, cid = db_and_cal(tmp_path)
    db.add_event(Event(None, cid, "D", datetime(2026, 11, 1, 9), datetime(2026, 11, 1, 10), recurrence="DAILY"))
    series.delete_occurrence(db, _occ(db, "D", date(2026, 11, 5)), series.FOLLOWING)
    assert len(db.occurrences(datetime(2026, 11, 1), datetime(2026, 12, 1))) == 4


def test_ics_byday_and_override_roundtrip(tmp_path):
    db, cid = db_and_cal(tmp_path)
    db.add_event(Event(None, cid, "Orario", datetime(2026, 11, 2, 8), datetime(2026, 11, 2, 9),
                       recurrence="WEEKLY", byday="MO,WE,FR", until=date(2026, 12, 31)))
    db.add_event(Event(None, cid, "Collegio", datetime(2026, 11, 27, 15), datetime(2026, 11, 27, 17),
                       recurrence="MONTHLY", byday="-1FR"))
    occ = _occ(db, "Orario", date(2026, 11, 11))
    series.edit_occurrence(db, occ, replace(db.get_event(occ.event.id), start=occ.start.replace(hour=10),
                                            end=occ.end.replace(hour=11), title="Orario (cambio)"), series.ONE)
    path = tmp_path / "x.ics"
    export_ics(db.all_events(), path)
    text = path.read_text()
    assert "BYDAY=MO,WE,FR" in text and "BYDAY=-1FR" in text and "RECURRENCE-ID:20261111T080000" in text
    assert "EXDATE" not in text  # l'occorrenza sostituita non è anche esclusa

    db2 = Database(tmp_path / "y.db")
    added, skipped = import_into(db2, path, db2.calendars()[0].id)
    assert (added, skipped) == (3, 0)
    a = db.occurrences(datetime(2026, 11, 1), datetime(2027, 1, 1))
    b = db2.occurrences(datetime(2026, 11, 1), datetime(2027, 1, 1))
    assert [(o.start, o.event.title) for o in a] == [(o.start, o.event.title) for o in b]
    assert import_into(db2, path, db2.calendars()[0].id) == (0, 3)


def test_ics_outlook_bysetpos(tmp_path):
    p = tmp_path / "o.ics"
    p.write_text("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:o1\nDTSTART:20261103T100000\nDTEND:20261103T110000\n"
                 "RRULE:FREQ=MONTHLY;BYDAY=TU;BYSETPOS=1\nSUMMARY:Primo martedì\nEND:VEVENT\nEND:VCALENDAR\n")
    (ev,) = parse_ics(p, 1)
    assert ev.byday == "1TU"
