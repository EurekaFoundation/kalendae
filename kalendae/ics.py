"""Import/export in formato iCalendar (.ics), compatibile con Google Calendar, Outlook, Thunderbird."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from . import __version__
from .database import Database, Event
from .recurrence import WEEKDAYS, format_byday, parse_byday, until_from_count

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

SUPPORTED_FREQ = {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}


# ------------------------------------------------------------------ utilità
def _esc(t: str) -> str:
    return (t.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
             .replace("\r\n", "\\n").replace("\n", "\\n"))


def _unesc(t: str) -> str:
    out, i = [], 0
    while i < len(t):
        c = t[i]
        if c == "\\" and i + 1 < len(t):
            n = t[i + 1]
            out.append("\n" if n in "nN" else n)
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _fold(line: str) -> list[str]:
    parts = [line[:73]]
    line = line[73:]
    while line:
        parts.append(" " + line[:72])
        line = line[72:]
    return parts


def _fmt(dt: datetime, all_day: bool) -> str:
    return dt.strftime("%Y%m%d") if all_day else dt.strftime("%Y%m%dT%H%M%S")


_DUR = re.compile(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?")


def _parse_duration(v: str) -> timedelta | None:
    m = _DUR.fullmatch(v.strip())
    if not m:
        return None
    sign, w, d, h, mi, s = m.groups()
    td = timedelta(weeks=int(w or 0), days=int(d or 0), hours=int(h or 0),
                   minutes=int(mi or 0), seconds=int(s or 0))
    return -td if sign == "-" else td


def _parse_dt(value: str, params: dict) -> tuple[datetime, bool]:
    value = value.strip()
    if params.get("VALUE") == "DATE" or len(value) == 8:
        return datetime.strptime(value[:8], "%Y%m%d"), True
    utc = value.endswith("Z")
    dt = datetime.strptime(value.rstrip("Z")[:15], "%Y%m%dT%H%M%S")
    if utc:
        dt = dt.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    elif "TZID" in params and ZoneInfo is not None:
        try:
            dt = dt.replace(tzinfo=ZoneInfo(params["TZID"])).astimezone().replace(tzinfo=None)
        except Exception:
            pass  # fuso sconosciuto: si tiene l'ora così com'è
    return dt, False


def _split_line(line: str) -> tuple[str, dict, str]:
    """'DTSTART;TZID=Europe/Rome:20261107T100000' -> nome, parametri, valore."""
    in_q, cut = False, -1
    for i, c in enumerate(line):
        if c == '"':
            in_q = not in_q
        elif c == ":" and not in_q:
            cut = i
            break
    if cut < 0:
        return line.upper(), {}, ""
    head, value = line[:cut], line[cut + 1:]
    bits = head.split(";")
    params = {}
    for b in bits[1:]:
        if "=" in b:
            k, v = b.split("=", 1)
            params[k.upper()] = v.strip('"')
    return bits[0].upper(), params, value


# ------------------------------------------------------------------- export
def export_ics(events: list[Event], path: str | Path, cal_name: str = "Kalendae") -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//Kalendae//Kalendae {__version__}//IT",
             "CALSCALE:GREGORIAN", f"X-WR-CALNAME:{_esc(cal_name)}"]
    by_id = {e.id: e for e in events}
    overridden: dict[int, set[date]] = {}
    for ev in events:
        if ev.parent_id and ev.recurrence_id:
            overridden.setdefault(ev.parent_id, set()).add(ev.recurrence_id.date())
    for ev in events:
        lines += ["BEGIN:VEVENT", f"UID:{ev.uid}", f"DTSTAMP:{stamp}"]
        parent = by_id.get(ev.parent_id) if ev.parent_id else None
        if ev.recurrence_id:
            if parent is not None and parent.all_day:
                lines.append(f"RECURRENCE-ID;VALUE=DATE:{_fmt(ev.recurrence_id, True)}")
            else:
                lines.append(f"RECURRENCE-ID:{_fmt(ev.recurrence_id, False)}")
        if ev.all_day:
            lines.append(f"DTSTART;VALUE=DATE:{_fmt(ev.start, True)}")
            lines.append(f"DTEND;VALUE=DATE:{_fmt(ev.end, True)}")
        else:
            lines.append(f"DTSTART:{_fmt(ev.start, False)}")
            lines.append(f"DTEND:{_fmt(ev.end, False)}")
        lines.append(f"SUMMARY:{_esc(ev.title)}")
        if ev.location:
            lines.append(f"LOCATION:{_esc(ev.location)}")
        if ev.description:
            lines.append(f"DESCRIPTION:{_esc(ev.description)}")
        if ev.recurrence:
            rule = f"FREQ={ev.recurrence}"
            if ev.interval > 1:
                rule += f";INTERVAL={ev.interval}"
            if ev.byday:
                rule += f";BYDAY={ev.byday}"
            if ev.until:
                rule += (f";UNTIL={ev.until.strftime('%Y%m%d')}" if ev.all_day
                         else f";UNTIL={ev.until.strftime('%Y%m%d')}T235959")
            lines.append(f"RRULE:{rule}")
            for d in sorted(ev.exdates - overridden.get(ev.id, set())):
                if ev.all_day:
                    lines.append(f"EXDATE;VALUE=DATE:{d.strftime('%Y%m%d')}")
                else:
                    lines.append(f"EXDATE:{_fmt(datetime.combine(d, ev.start.time()), False)}")
        if ev.reminder >= 0:
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Promemoria",
                      f"TRIGGER:-PT{ev.reminder}M", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    folded = [p for line in lines for p in _fold(line)]
    Path(path).write_text("\r\n".join(folded) + "\r\n", encoding="utf-8")
    return len(events)


# ------------------------------------------------------------------- import
def parse_ics(path: str | Path, calendar_id: int) -> list[Event]:
    raw = Path(path).read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for ln in raw.split("\n"):
        if ln[:1] in (" ", "\t") and lines:
            lines[-1] += ln[1:]
        elif ln:
            lines.append(ln)

    events: list[Event] = []
    cur: dict | None = None
    depth_alarm = False
    for ln in lines:
        name, params, value = _split_line(ln)
        if name == "BEGIN" and value.upper() == "VEVENT":
            cur = {"exdates": set()}
        elif name == "BEGIN" and value.upper() == "VALARM":
            depth_alarm = True
        elif name == "END" and value.upper() == "VALARM":
            depth_alarm = False
        elif name == "END" and value.upper() == "VEVENT" and cur is not None:
            ev = _build_event(cur, calendar_id)
            if ev:
                events.append(ev)
            cur = None
        elif cur is not None:
            if depth_alarm:
                if name == "TRIGGER" and "reminder" not in cur:
                    td = _parse_duration(value)
                    if td is not None and td <= timedelta(0):
                        cur["reminder"] = int(-td.total_seconds() // 60)
                continue
            if name in ("DTSTART", "DTEND", "RECURRENCE-ID"):
                cur[name] = _parse_dt(value, params)
            elif name == "DURATION":
                cur["DURATION"] = _parse_duration(value)
            elif name in ("SUMMARY", "LOCATION", "DESCRIPTION", "UID"):
                cur[name] = _unesc(value)
            elif name == "RRULE":
                cur["RRULE"] = dict(p.split("=", 1) for p in value.split(";") if "=" in p)
            elif name == "EXDATE":
                for v in value.split(","):
                    try:
                        cur["exdates"].add(_parse_dt(v, params)[0].date())
                    except ValueError:
                        pass
    return events


def _convert_byday(freq: str, rule: dict) -> str:
    rules = parse_byday(rule.get("BYDAY", ""))
    if not rules:
        return ""
    if freq == "WEEKLY":
        return ",".join(WEEKDAYS[wd] for wd in sorted({wd for _, wd in rules}))
    if freq == "MONTHLY":
        if "BYSETPOS" in rule and len(rules) == 1 and rules[0][0] is None:  # stile Outlook
            try:
                return format_byday([(int(rule["BYSETPOS"].split(",")[0]), rules[0][1])])
            except ValueError:
                return ""
        nth = [(n, wd) for n, wd in rules if n]
        return format_byday(nth[:1]) if nth else ""
    return ""


def _build_event(c: dict, calendar_id: int) -> Event | None:
    if "DTSTART" not in c:
        return None
    start, all_day = c["DTSTART"]
    if "DTEND" in c:
        end = c["DTEND"][0]
    elif c.get("DURATION"):
        end = start + c["DURATION"]
    else:
        end = start + (timedelta(days=1) if all_day else timedelta(hours=1))
    if end <= start:
        end = start + (timedelta(days=1) if all_day else timedelta(minutes=30))
    ev = Event(None, calendar_id, c.get("SUMMARY", "(Senza titolo)"), start, end, all_day,
               location=c.get("LOCATION", ""), description=c.get("DESCRIPTION", ""),
               reminder=c.get("reminder", -1), uid=c.get("UID", ""))
    if "RECURRENCE-ID" in c:  # eccezione di una serie: la colleghiamo dopo
        ev.recurrence_id = c["RECURRENCE-ID"][0]
        return ev
    rule = c.get("RRULE")
    if rule and rule.get("FREQ", "").upper() in SUPPORTED_FREQ:
        ev.recurrence = rule["FREQ"].upper()
        ev.interval = int(rule.get("INTERVAL", 1) or 1)
        ev.exdates = c["exdates"]
        ev.byday = _convert_byday(ev.recurrence, rule)
        if "UNTIL" in rule:
            try:
                ev.until = _parse_dt(rule["UNTIL"], {})[0].date()
            except ValueError:
                pass
        elif "COUNT" in rule:
            ev.until = until_from_count(ev, int(rule["COUNT"]))
    return ev


def import_into(db: Database, path: str | Path, calendar_id: int) -> tuple[int, int]:
    """Importa un file .ics nel calendario indicato. Restituisce (aggiunti, saltati)."""
    events = parse_ics(path, calendar_id)
    added = skipped = 0
    for ev in [e for e in events if not e.recurrence_id]:
        if ev.uid and db.event_by_uid(ev.uid):
            skipped += 1
            continue
        db.add_event(ev)
        added += 1
    for ov in [e for e in events if e.recurrence_id]:
        parent = db.event_by_uid(ov.uid) if ov.uid else None
        if parent is None or db.override_by_uid(ov.uid, ov.recurrence_id):
            skipped += 1
            continue
        ov.parent_id = parent.id
        db.add_event(ov)
        parent.exdates.add(ov.recurrence_id.date())
        db.update_event(parent)
        added += 1
    return added, skipped
