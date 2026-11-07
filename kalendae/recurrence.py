"""Espansione degli eventi ricorrenti.

Regole supportate (sottoinsieme di RFC 5545):
- DAILY / WEEKLY / MONTHLY / YEARLY con INTERVAL
- WEEKLY con più giorni della settimana  (byday = "MO,WE,FR")
- MONTHLY con n-esimo giorno della settimana (byday = "2TU", "-1FR" = ultimo venerdì)
- UNTIL (data di fine) ed EXDATE (occorrenze cancellate)
"""
from __future__ import annotations

import calendar as _cal
import re
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from .database import Event

FREQUENZE = {
    "": "Non si ripete",
    "DAILY": "Ogni giorno",
    "WEEKLY": "Ogni settimana",
    "MONTHLY": "Ogni mese",
    "YEARLY": "Ogni anno",
}
UNITA = {"DAILY": "giorni", "WEEKLY": "settimane", "MONTHLY": "mesi", "YEARLY": "anni"}
UNITA_SING = {"DAILY": "giorno", "WEEKLY": "settimana", "MONTHLY": "mese", "YEARLY": "anno"}

WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
GIORNI_MIN = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
ORDINALI = {1: "primo", 2: "secondo", 3: "terzo", 4: "quarto", 5: "quinto", -1: "ultimo"}
_MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
         "agosto", "settembre", "ottobre", "novembre", "dicembre"]

_MAX_ITER = 100_000
_BYDAY_RE = re.compile(r"([+-]?\d{1,2})?(MO|TU|WE|TH|FR|SA|SU)")


# ------------------------------------------------------------------ BYDAY
def parse_byday(text: str) -> list[tuple[int | None, int]]:
    """'MO,WE' -> [(None,0),(None,2)];  '-1FR' -> [(-1,4)]"""
    out = []
    for item in (text or "").upper().split(","):
        m = _BYDAY_RE.fullmatch(item.strip())
        if m:
            out.append((int(m.group(1)) if m.group(1) else None, WEEKDAYS.index(m.group(2))))
    return out


def format_byday(rules: list[tuple[int | None, int]]) -> str:
    return ",".join(f"{n if n else ''}{WEEKDAYS[wd]}" for n, wd in rules)


def nth_weekday(year: int, month: int, n: int, wd: int) -> date | None:
    """n-esimo giorno della settimana `wd` del mese (n<0 conta dalla fine). None se non esiste."""
    last = _cal.monthrange(year, month)[1]
    if n > 0:
        first = date(year, month, 1)
        day = 1 + (wd - first.weekday()) % 7 + (n - 1) * 7
    else:
        ld = date(year, month, last)
        day = last - (ld.weekday() - wd) % 7 - (-n - 1) * 7
    return date(year, month, day) if 1 <= day <= last else None


def monthly_position(d: date) -> tuple[int, bool]:
    """(numero d'ordine del giorno della settimana nel mese, True se è anche l'ultimo)."""
    nth = (d.day - 1) // 7 + 1
    is_last = d.day + 7 > _cal.monthrange(d.year, d.month)[1]
    return nth, is_last


# ------------------------------------------------------------- espansione
def _add_months(dt: datetime, months: int) -> datetime | None:
    """Somma mesi; None se il giorno non esiste (es. 31 aprile), come da RFC 5545."""
    m = dt.month - 1 + months
    y, m = dt.year + m // 12, m % 12 + 1
    if dt.day > _cal.monthrange(y, m)[1]:
        return None
    return dt.replace(year=y, month=m)


def _ym(dt: datetime, months: int) -> tuple[int, int]:
    m = dt.month - 1 + months
    return dt.year + m // 12, m % 12 + 1


def _anchor(ev: "Event", k: int) -> datetime:
    """Inizio del k-esimo periodo (giorno, settimana, mese, anno)."""
    n = k * max(1, ev.interval)
    midnight = datetime.combine(ev.start.date(), datetime.min.time())
    if ev.recurrence == "DAILY":
        return ev.start + timedelta(days=n)
    if ev.recurrence == "WEEKLY":
        return midnight - timedelta(days=ev.start.weekday()) + timedelta(weeks=n)
    if ev.recurrence == "MONTHLY":
        y, m = _ym(ev.start, n)
        return datetime(y, m, 1)
    if ev.recurrence == "YEARLY":
        return datetime(ev.start.year + n, 1, 1)
    raise ValueError(f"Frequenza non supportata: {ev.recurrence}")


def _period_starts(ev: "Event", k: int) -> list[datetime]:
    n = k * max(1, ev.interval)
    rules = parse_byday(ev.byday)
    t = ev.start.time()
    if ev.recurrence == "WEEKLY" and rules:
        ws = _anchor(ev, k).date()
        return [datetime.combine(ws + timedelta(days=wd), t) for wd in sorted({wd for _, wd in rules})]
    if ev.recurrence == "MONTHLY" and any(nth for nth, _ in rules):
        y, m = _ym(ev.start, n)
        days = {nth_weekday(y, m, nth, wd) for nth, wd in rules if nth}
        return sorted(datetime.combine(d, t) for d in days if d)
    if ev.recurrence == "DAILY":
        return [ev.start + timedelta(days=n)]
    if ev.recurrence == "WEEKLY":
        return [ev.start + timedelta(weeks=n)]
    s = _add_months(ev.start, n if ev.recurrence == "MONTHLY" else 12 * n)
    return [s] if s else []


def _periods(ev: "Event", k0: int = 0) -> Iterator[tuple[datetime, list[datetime]]]:
    k = k0
    for _ in range(_MAX_ITER):
        anchor = _anchor(ev, k)
        if ev.until and anchor.date() > ev.until:
            return
        starts = [s for s in _period_starts(ev, k) if s >= ev.start]
        k += 1
        yield anchor, starts


def expand(ev: "Event", range_start: datetime, range_end: datetime) -> Iterator[tuple[datetime, datetime]]:
    """Genera (inizio, fine) di ogni occorrenza che tocca [range_start, range_end)."""
    dur = ev.end - ev.start
    if not ev.recurrence:
        if ev.start < range_end and ev.end > range_start:
            yield ev.start, ev.end
        return

    k0 = 0
    step_days = {"DAILY": 1, "WEEKLY": 7}.get(ev.recurrence)
    if step_days:  # salto diretto vicino all'intervallo richiesto
        gap = (range_start - dur - ev.start).days
        if gap > 0:
            k0 = max(0, gap // (step_days * max(1, ev.interval)) - 1)

    for anchor, starts in _periods(ev, k0):
        if anchor >= range_end:
            return
        for s in starts:
            if s >= range_end or (ev.until and s.date() > ev.until):
                return
            e = s + dur
            if e > range_start and s.date() not in ev.exdates:
                yield s, e


def first_occurrence(ev: "Event") -> datetime | None:
    for _, starts in _periods(ev):
        if starts:
            return starts[0]
    return None


def until_from_count(ev: "Event", count: int) -> date | None:
    """Converte un numero di occorrenze (COUNT di iCalendar) nella data dell'ultima."""
    found = 0
    for _, starts in _periods(ev):
        for s in starts:
            found += 1
            if found >= count:
                return s.date()
    return None


# ------------------------------------------------------------- descrizione
def describe(ev: "Event") -> str:
    """Testo leggibile della regola, es. 'Ogni 2 settimane il lunedì e il mercoledì'."""
    f = ev.recurrence
    if not f:
        return FREQUENZE[""]
    n = max(1, ev.interval)
    base = FREQUENZE[f] if n == 1 else f"Ogni {n} {UNITA[f]}"
    rules = parse_byday(ev.byday)
    if f == "WEEKLY":
        wds = sorted({wd for _, wd in rules}) or [ev.start.weekday()]
        if wds == [0, 1, 2, 3, 4]:
            base += " dal lunedì al venerdì"
        else:
            nomi = [GIORNI_MIN[w] for w in wds]
            base += " il " + (", ".join(nomi[:-1]) + " e " + nomi[-1] if len(nomi) > 1 else nomi[0])
    elif f == "MONTHLY":
        nth_rules = [(nth, wd) for nth, wd in rules if nth]
        if nth_rules:
            nth, wd = nth_rules[0]
            art = "l'" if nth == -1 else "il "
            base += f" {art}{ORDINALI.get(nth, f'{nth}°')} {GIORNI_MIN[wd]}"
        else:
            base += f" il giorno {ev.start.day}"
    elif f == "YEARLY":
        base += f" il {ev.start.day} {_MESI[ev.start.month - 1]}"
    if ev.until:
        base += f", fino al {ev.until.day} {_MESI[ev.until.month - 1]} {ev.until.year}"
    return base
