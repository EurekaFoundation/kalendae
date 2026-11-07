"""Archiviazione locale di calendari ed eventi su SQLite."""
from __future__ import annotations

import os
import sqlite3
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .recurrence import expand

DEFAULT_COLORS = [
    "#1a73e8", "#33b679", "#f4511e", "#8e24aa",
    "#f6bf26", "#d50000", "#039be5", "#616161",
]


def default_db_path() -> Path:
    """Percorso del database nella cartella dati dell'utente."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    folder = base / "Kalendae"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "kalendae.db"


@dataclass
class Calendar:
    id: int | None
    name: str
    color: str
    visible: bool = True


@dataclass
class Event:
    id: int | None
    calendar_id: int
    title: str
    start: datetime
    end: datetime                      # esclusiva (per gli eventi "tutto il giorno": mezzanotte del giorno dopo)
    all_day: bool = False
    location: str = ""
    description: str = ""
    recurrence: str = ""               # "", DAILY, WEEKLY, MONTHLY, YEARLY
    interval: int = 1
    until: date | None = None          # ultima data inclusa
    exdates: set[date] = field(default_factory=set)  # occorrenze cancellate
    reminder: int = -1                 # minuti prima; -1 = nessuno
    uid: str = ""
    byday: str = ""                    # "MO,WE" (settimanale) o "2TU" / "-1FR" (mensile)
    parent_id: int | None = None       # eccezione: id della serie a cui appartiene
    recurrence_id: datetime | None = None  # eccezione: inizio originale dell'occorrenza sostituita


@dataclass
class Occurrence:
    """Una singola comparsa di un evento (gli eventi ricorrenti ne hanno molte)."""
    event: Event
    start: datetime
    end: datetime
    color: str = DEFAULT_COLORS[0]

    @property
    def is_recurring(self) -> bool:
        return bool(self.event.recurrence)

    @property
    def is_long(self) -> bool:
        """Vero se va mostrato nella fascia "tutto il giorno"."""
        return self.event.all_day or (self.end - self.start).total_seconds() >= 86400


SCHEMA = """
CREATE TABLE IF NOT EXISTS calendars (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL,
    color    TEXT NOT NULL,
    visible  INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    calendar_id INTEGER NOT NULL REFERENCES calendars(id) ON DELETE CASCADE,
    uid         TEXT NOT NULL,
    title       TEXT NOT NULL,
    start_at    TEXT NOT NULL,
    end_at      TEXT NOT NULL,
    all_day     INTEGER NOT NULL DEFAULT 0,
    location    TEXT DEFAULT '',
    description TEXT DEFAULT '',
    recurrence  TEXT DEFAULT '',
    interval    INTEGER DEFAULT 1,
    until       TEXT,
    exdates     TEXT DEFAULT '',
    reminder    INTEGER DEFAULT -1
);
CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_at);
CREATE INDEX IF NOT EXISTS idx_events_uid ON events(uid);
"""

# colonne aggiunte nelle versioni successive alla 0.1 (migrazione automatica)
MIGRATIONS = [
    ("byday", "TEXT DEFAULT ''"),
    ("parent_id", "INTEGER"),
    ("recurrence_id", "TEXT"),
]


class Database:
    def __init__(self, path: str | Path | None = None):
        self.path = str(path or default_db_path())
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self._migrate()
        if not self.calendars():
            self.add_calendar(Calendar(None, "Personale", DEFAULT_COLORS[0]))
            self.add_calendar(Calendar(None, "Lavoro", DEFAULT_COLORS[1]))

    def close(self):
        self.conn.close()

    def _migrate(self):
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(events)")}
        for name, ddl in MIGRATIONS:
            if name not in cols:
                self.conn.execute(f"ALTER TABLE events ADD COLUMN {name} {ddl}")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_events_parent ON events(parent_id)")
        self.conn.commit()

    # ------------------------------------------------------------ calendari
    def calendars(self) -> list[Calendar]:
        rows = self.conn.execute("SELECT * FROM calendars ORDER BY id").fetchall()
        return [Calendar(r["id"], r["name"], r["color"], bool(r["visible"])) for r in rows]

    def add_calendar(self, cal: Calendar) -> int:
        cur = self.conn.execute(
            "INSERT INTO calendars(name, color, visible) VALUES (?,?,?)",
            (cal.name, cal.color, int(cal.visible)))
        self.conn.commit()
        cal.id = cur.lastrowid
        return cal.id

    def update_calendar(self, cal: Calendar):
        self.conn.execute("UPDATE calendars SET name=?, color=?, visible=? WHERE id=?",
                          (cal.name, cal.color, int(cal.visible), cal.id))
        self.conn.commit()

    def delete_calendar(self, cal_id: int):
        self.conn.execute("DELETE FROM calendars WHERE id=?", (cal_id,))
        self.conn.commit()

    # -------------------------------------------------------------- eventi
    @staticmethod
    def _row_to_event(r: sqlite3.Row) -> Event:
        return Event(
            id=r["id"], calendar_id=r["calendar_id"], title=r["title"],
            start=datetime.fromisoformat(r["start_at"]),
            end=datetime.fromisoformat(r["end_at"]),
            all_day=bool(r["all_day"]),
            location=r["location"] or "", description=r["description"] or "",
            recurrence=r["recurrence"] or "", interval=r["interval"] or 1,
            until=date.fromisoformat(r["until"]) if r["until"] else None,
            exdates={date.fromisoformat(x) for x in (r["exdates"] or "").split(",") if x},
            reminder=r["reminder"] if r["reminder"] is not None else -1,
            uid=r["uid"],
            byday=r["byday"] or "",
            parent_id=r["parent_id"],
            recurrence_id=datetime.fromisoformat(r["recurrence_id"]) if r["recurrence_id"] else None,
        )

    @staticmethod
    def _params(ev: Event) -> tuple:
        if not ev.uid:
            ev.uid = f"{uuid.uuid4()}@kalendae"
        return (
            ev.calendar_id, ev.uid, ev.title,
            ev.start.isoformat(timespec="seconds"), ev.end.isoformat(timespec="seconds"),
            int(ev.all_day), ev.location, ev.description,
            ev.recurrence, max(1, ev.interval),
            ev.until.isoformat() if ev.until else None,
            ",".join(sorted(d.isoformat() for d in ev.exdates)),
            ev.reminder,
            ev.byday if ev.recurrence else "",
            ev.parent_id,
            ev.recurrence_id.isoformat(timespec="seconds") if ev.recurrence_id else None,
        )

    _COLS = ("calendar_id, uid, title, start_at, end_at, all_day, location, description, "
             "recurrence, interval, until, exdates, reminder, byday, parent_id, recurrence_id")

    def add_event(self, ev: Event) -> int:
        cur = self.conn.execute(
            f"INSERT INTO events({self._COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(ev))
        self.conn.commit()
        ev.id = cur.lastrowid
        return ev.id

    def update_event(self, ev: Event):
        sets = ", ".join(f"{c.strip()}=?" for c in self._COLS.split(","))
        self.conn.execute(f"UPDATE events SET {sets} WHERE id=?", self._params(ev) + (ev.id,))
        self.conn.commit()

    def delete_event(self, event_id: int):
        """Elimina un evento; se è una serie, anche le sue eccezioni."""
        self.conn.execute("DELETE FROM events WHERE id=? OR parent_id=?", (event_id, event_id))
        self.conn.commit()

    def overrides(self, parent_id: int) -> list[Event]:
        rows = self.conn.execute("SELECT * FROM events WHERE parent_id=? ORDER BY recurrence_id",
                                 (parent_id,)).fetchall()
        return [self._row_to_event(r) for r in rows]

    def delete_occurrence(self, ev: Event, day: date):
        """Cancella una sola occorrenza di un evento ricorrente."""
        ev.exdates.add(day)
        self.update_event(ev)

    def get_event(self, event_id: int) -> Event | None:
        r = self.conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        return self._row_to_event(r) if r else None

    def event_by_uid(self, uid: str) -> Event | None:
        """La serie (o l'evento singolo) con questo UID, escluse le eccezioni."""
        r = self.conn.execute("SELECT * FROM events WHERE uid=? AND parent_id IS NULL", (uid,)).fetchone()
        return self._row_to_event(r) if r else None

    def override_by_uid(self, uid: str, recurrence_id: datetime) -> Event | None:
        r = self.conn.execute("SELECT * FROM events WHERE uid=? AND recurrence_id=?",
                              (uid, recurrence_id.isoformat(timespec="seconds"))).fetchone()
        return self._row_to_event(r) if r else None

    def all_events(self, calendar_ids: list[int] | None = None) -> list[Event]:
        rows = self.conn.execute("SELECT * FROM events ORDER BY start_at").fetchall()
        evs = [self._row_to_event(r) for r in rows]
        if calendar_ids is not None:
            evs = [e for e in evs if e.calendar_id in calendar_ids]
        return evs

    def occurrences(self, range_start: datetime, range_end: datetime,
                    only_visible: bool = True) -> list[Occurrence]:
        """Tutte le occorrenze che si sovrappongono all'intervallo [start, end)."""
        cals = {c.id: c for c in self.calendars()}
        rs, re_ = range_start.isoformat(timespec="seconds"), range_end.isoformat(timespec="seconds")
        rows = self.conn.execute(
            "SELECT * FROM events WHERE (recurrence != '' AND start_at < ?) "
            "OR (start_at < ? AND end_at > ?)", (re_, re_, rs)).fetchall()
        out: list[Occurrence] = []
        for r in rows:
            ev = self._row_to_event(r)
            cal = cals.get(ev.calendar_id)
            if cal is None or (only_visible and not cal.visible):
                continue
            for s, e in expand(ev, range_start, range_end):
                out.append(Occurrence(ev, s, e, cal.color))
        out.sort(key=lambda o: (not o.is_long, o.start, -(o.end - o.start).total_seconds(), o.event.title))
        return out

    def search(self, text: str) -> list[Occurrence]:
        like = f"%{text}%"
        rows = self.conn.execute(
            "SELECT * FROM events WHERE title LIKE ? OR location LIKE ? OR description LIKE ? "
            "ORDER BY start_at DESC LIMIT 300", (like, like, like)).fetchall()
        cals = {c.id: c for c in self.calendars()}
        out = []
        for r in rows:
            ev = self._row_to_event(r)
            cal = cals.get(ev.calendar_id)
            if cal:
                out.append(Occurrence(ev, ev.start, ev.end, cal.color))
        return out
