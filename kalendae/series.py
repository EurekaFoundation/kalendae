"""Modifica ed eliminazione di eventi ricorrenti con ambito, come in Google Calendar:
solo questo evento, questo e i successivi, tutti gli eventi."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from .database import Database, Event, Occurrence
from .recurrence import WEEKDAYS, parse_byday

ONE = "one"
FOLLOWING = "following"
ALL = "all"

SCOPE_LABELS = {
    ONE: "Questo evento",
    FOLLOWING: "Questo e tutti gli eventi successivi",
    ALL: "Tutti gli eventi",
}


def _follow_weekday(new: Event, old_start: datetime) -> Event:
    """Se una serie settimanale su un solo giorno viene spostata a un altro giorno, aggiorna BYDAY."""
    rules = parse_byday(new.byday)
    if new.recurrence == "WEEKLY" and len(rules) == 1 and rules[0][1] == old_start.weekday() \
            and new.start.weekday() != old_start.weekday():
        return replace(new, byday=WEEKDAYS[new.start.weekday()])
    return new


def is_series_occurrence(db: Database, occ: Occurrence) -> bool:
    ev = db.get_event(occ.event.id)
    return bool(ev and ev.recurrence)


def edit_occurrence(db: Database, occ: Occurrence, new: Event, scope: str = ALL) -> None:
    """Applica `new` (l'occorrenza come modificata dall'utente) secondo l'ambito scelto."""
    parent = db.get_event(occ.event.id)
    if parent is None:
        return
    if not parent.recurrence:  # evento singolo o eccezione già separata
        db.update_event(replace(new, id=parent.id, uid=parent.uid,
                                parent_id=parent.parent_id, recurrence_id=parent.recurrence_id))
        return

    if scope == FOLLOWING and occ.start <= parent.start:
        scope = ALL  # "questo e successivi" sulla prima occorrenza = tutta la serie

    if scope == ONE:
        parent.exdates.add(occ.start.date())
        db.update_event(parent)
        db.add_event(replace(new, id=None, uid=parent.uid, recurrence="", interval=1, byday="",
                             until=None, exdates=set(), parent_id=parent.id, recurrence_id=occ.start))
    elif scope == ALL:
        dur = new.end - new.start
        if new.recurrence:
            start = parent.start + (new.start - occ.start)
        else:  # ripetizione tolta: resta solo l'occorrenza che si stava guardando
            start = new.start
            for ov in db.overrides(parent.id):
                db.delete_event(ov.id)
        upd = replace(new, id=parent.id, uid=parent.uid, start=start, end=start + dur,
                      exdates=set(parent.exdates) if new.recurrence else set())
        db.update_event(_follow_weekday(upd, parent.start))
    elif scope == FOLLOWING:
        cut = occ.start.date()
        parent.until = cut - timedelta(days=1)
        db.update_event(parent)
        for ov in db.overrides(parent.id):  # le eccezioni future passano alla nuova serie
            if ov.recurrence_id and ov.recurrence_id >= occ.start:
                db.delete_event(ov.id)
        tail = replace(new, id=None, uid="", parent_id=None, recurrence_id=None,
                       exdates={d for d in parent.exdates if d >= cut} if new.recurrence else set())
        db.add_event(_follow_weekday(tail, occ.start))


def delete_occurrence(db: Database, occ: Occurrence, scope: str = ALL) -> None:
    parent = db.get_event(occ.event.id)
    if parent is None:
        return
    if not parent.recurrence or scope == ALL or (scope == FOLLOWING and occ.start <= parent.start):
        db.delete_event(parent.id)
    elif scope == ONE:
        db.delete_occurrence(parent, occ.start.date())
    elif scope == FOLLOWING:
        parent.until = occ.start.date() - timedelta(days=1)
        db.update_event(parent)
        for ov in db.overrides(parent.id):
            if ov.recurrence_id and ov.recurrence_id >= occ.start:
                db.delete_event(ov.id)
