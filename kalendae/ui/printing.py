"""Stampa ed esportazione PDF di giorno, settimana, mese e agenda.

Il disegno usa sempre colori chiari, indipendentemente dal tema dell'interfaccia.
Tutte le misure sono in unità logiche: la larghezza della pagina vale 1000.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPageLayout, QPainter, QPen
from PySide6.QtPrintSupport import QPrinter

from ..database import Database
from ..utils import (
    ACCENT, GIORNI, GIORNI_BREVI, MESI, MESI_BREVI, add_months, day_start, hhmm, long_date,
    text_on, time_range, week_start,
)

INK = QColor("#202124")
MUTED = QColor("#5f6368")
LINE = QColor("#c8cacd")
SHADE = QColor("#f1f3f4")
W = 1000.0


def orientation_for(mode: str) -> QPageLayout.Orientation:
    return QPageLayout.Landscape if mode in ("week", "month") else QPageLayout.Portrait


def period_range(mode: str, d: date) -> tuple[date, date]:
    """Intervallo [inizio, fine) da stampare."""
    if mode == "day":
        return d, d + timedelta(days=1)
    if mode == "week":
        s = week_start(d)
        return s, s + timedelta(days=7)
    if mode == "month":
        first = d.replace(day=1)
        return first, add_months(first, 1)
    return d, d + timedelta(days=30)


def _font(px: float, bold=False) -> QFont:
    f = QFont()
    f.setPixelSize(max(1, int(round(px))))
    f.setBold(bold)
    return f


class _Page:
    """Gestisce scala, margini e salti pagina."""

    def __init__(self, printer: QPrinter, painter: QPainter, title: str):
        self.printer, self.p, self.title = printer, painter, title
        rect = printer.pageLayout().paintRectPixels(printer.resolution())
        self.scale = rect.width() / W
        self.H = rect.height() / self.scale
        self.number = 0
        self._begin()

    def _begin(self):
        self.number += 1
        self.p.resetTransform()
        self.p.scale(self.scale, self.scale)
        self.p.setRenderHint(QPainter.Antialiasing)
        self.p.setFont(_font(26, True))
        self.p.setPen(INK)
        self.p.drawText(QRectF(0, 0, W, 34), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        self.p.setFont(_font(11))
        self.p.setPen(MUTED)
        self.p.drawText(QRectF(0, 0, W, 34), Qt.AlignRight | Qt.AlignVCenter, f"Kalendae · pag. {self.number}")
        self.p.setPen(QPen(LINE, 1))
        self.p.drawLine(QPointF(0, 42), QPointF(W, 42))
        self.top = 54.0

    def new_page(self):
        self.printer.newPage()
        self._begin()


def render(printer: QPrinter, db: Database, mode: str, d: date, title: str) -> None:
    painter = QPainter(printer)
    try:
        page = _Page(printer, painter, title)
        start, end = period_range(mode, d)
        if mode == "month":
            _month(page, db, d)
        elif mode == "week":
            _week(page, db, start)
        else:
            _list(page, db, start, end)
    finally:
        painter.end()


# ------------------------------------------------------------------- mese
def _month(pg: _Page, db: Database, d: date):
    p = pg.p
    first = d.replace(day=1)
    gs = week_start(first)
    rows = 6 if (first - gs).days + (add_months(first, 1) - first).days > 35 else 5
    occs = db.occurrences(day_start(gs), day_start(gs) + timedelta(days=7 * rows))
    by_day = defaultdict(list)
    for o in occs:
        x = max(o.start.date(), gs)
        while x <= (o.end - timedelta(seconds=1)).date() and x < gs + timedelta(days=7 * rows):
            by_day[x].append(o)
            x += timedelta(days=1)

    head = 22
    top = pg.top
    cw = W / 7
    ch = (pg.H - top - head) / rows
    p.setFont(_font(12, True))
    p.setPen(MUTED)
    for c in range(7):
        p.drawText(QRectF(c * cw, top, cw, head), Qt.AlignCenter, GIORNI_BREVI[c])
    line_h = 15
    for idx in range(7 * rows):
        day = gs + timedelta(days=idx)
        r, c = divmod(idx, 7)
        cell = QRectF(c * cw, top + head + r * ch, cw, ch)
        if day.month != d.month:
            p.fillRect(cell, SHADE)
        p.setPen(QPen(LINE, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(cell)
        p.setFont(_font(13, True))
        p.setPen(INK if day.month == d.month else MUTED)
        p.drawText(cell.adjusted(6, 3, -6, 0), Qt.AlignLeft | Qt.AlignTop, str(day.day))
        y = cell.y() + 22
        items = by_day.get(day, [])
        fit = int((cell.bottom() - y - 2) // line_h)
        shown = items if len(items) <= fit else items[:max(0, fit - 1)]
        p.setFont(_font(10.5))
        for o in shown:
            rr = QRectF(cell.x() + 4, y, cw - 8, line_h - 2)
            if o.is_long:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(o.color))
                p.drawRoundedRect(rr, 3, 3)
                p.setPen(text_on(o.color))
                txt = o.event.title
                inner = rr.adjusted(4, 0, -2, 0)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(o.color))
                p.drawEllipse(QPointF(rr.x() + 4, rr.center().y()), 3, 3)
                p.setPen(INK)
                txt = f"{hhmm(o.start)} {o.event.title}"
                inner = rr.adjusted(11, 0, 0, 0)
            p.drawText(inner, Qt.AlignVCenter | Qt.AlignLeft,
                       p.fontMetrics().elidedText(txt, Qt.ElideRight, int(inner.width())))
            y += line_h
        if len(items) > len(shown):
            p.setPen(MUTED)
            p.drawText(QRectF(cell.x() + 6, y, cw - 8, line_h), Qt.AlignVCenter | Qt.AlignLeft,
                       f"+{len(items) - len(shown)} altri")


# --------------------------------------------------------------- settimana
def _week(pg: _Page, db: Database, ws: date):
    """Sette colonne con l'elenco degli eventi di ogni giorno (più leggibile su carta di una griglia oraria)."""
    p = pg.p
    top = pg.top
    cw = W / 7
    head = 34
    occs = db.occurrences(day_start(ws), day_start(ws) + timedelta(days=7))
    for i in range(7):
        day = ws + timedelta(days=i)
        col = QRectF(i * cw, top, cw, pg.H - top)
        p.setPen(QPen(LINE, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(col)
        p.fillRect(QRectF(col.x() + 0.5, col.y() + 0.5, cw - 1, head), SHADE)
        p.setPen(INK)
        p.setFont(_font(13, True))
        p.drawText(QRectF(col.x(), col.y(), cw, head), Qt.AlignCenter,
                   f"{GIORNI[day.weekday()]} {day.day}")
        y = col.y() + head + 6
        ds, de = day_start(day), day_start(day) + timedelta(days=1)
        for o in [o for o in occs if o.start < de and o.end > ds]:
            lines = [o.event.title]
            if not o.event.all_day:
                lines.insert(0, time_range(o) if o.start.date() == o.end.date() else
                             ("dalle " + hhmm(o.start) if o.start >= ds else "fino alle " + hhmm(o.end)))
            if o.event.location:
                lines.append(o.event.location)
            box_h = 6 + 14 * len(lines)
            if y + box_h > col.bottom() - 4:
                p.setPen(MUTED)
                p.setFont(_font(10.5))
                p.drawText(QRectF(col.x() + 6, y, cw - 10, 14), Qt.AlignLeft, "… altri eventi")
                break
            box = QRectF(col.x() + 5, y, cw - 10, box_h)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(o.color))
            p.drawRect(QRectF(box.x(), box.y(), 4, box.height()))
            ty = box.y() + 3
            for j, line in enumerate(lines):
                bold = line == o.event.title
                p.setFont(_font(11, bold))
                p.setPen(INK if bold else MUTED)
                r = QRectF(box.x() + 9, ty, box.width() - 10, 14)
                p.drawText(r, Qt.AlignLeft | Qt.AlignVCenter,
                           p.fontMetrics().elidedText(line, Qt.ElideRight, int(r.width())))
                ty += 14
            y += box_h + 6


# ------------------------------------------------------ giorno e agenda
def _list(pg: _Page, db: Database, start: date, end: date):
    p = pg.p
    occs = sorted(db.occurrences(day_start(start), day_start(end)), key=lambda o: (not o.is_long, o.start))
    by_day = defaultdict(list)
    for o in occs:
        by_day[max(o.start.date(), start)].append(o)
    y = pg.top
    if not occs:
        p.setFont(_font(14))
        p.setPen(MUTED)
        p.drawText(QRectF(0, y, W, 24), Qt.AlignLeft, "Nessun evento in questo periodo.")
        return
    for day in sorted(by_day):
        if y + 30 + 22 > pg.H:
            pg.new_page()
            y = pg.top
        p.setFont(_font(15, True))
        p.setPen(QColor(ACCENT) if day == date.today() else INK)
        p.drawText(QRectF(0, y, W, 26), Qt.AlignLeft | Qt.AlignVCenter, long_date(day))
        y += 30
        for o in by_day[day]:
            row_h = 22 + (16 if o.event.description else 0)
            if y + row_h > pg.H:
                pg.new_page()
                y = pg.top
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(o.color))
            p.drawEllipse(QPointF(10, y + 11), 5, 5)
            p.setFont(_font(12.5))
            p.setPen(MUTED)
            p.drawText(QRectF(24, y, 190, 22), Qt.AlignLeft | Qt.AlignVCenter, time_range(o))
            p.setFont(_font(12.5, True))
            p.setPen(INK)
            title = o.event.title + ("  ↻" if o.is_recurring else "")
            p.drawText(QRectF(220, y, 480, 22), Qt.AlignLeft | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(title, Qt.ElideRight, 480))
            if o.event.location:
                p.setFont(_font(12))
                p.setPen(MUTED)
                p.drawText(QRectF(710, y, 290, 22), Qt.AlignLeft | Qt.AlignVCenter,
                           p.fontMetrics().elidedText(o.event.location, Qt.ElideRight, 290))
            if o.event.description:
                p.setFont(_font(11))
                p.setPen(MUTED)
                first_line = o.event.description.splitlines()[0]
                p.drawText(QRectF(220, y + 20, 780, 16), Qt.AlignLeft | Qt.AlignVCenter,
                           p.fontMetrics().elidedText(first_line, Qt.ElideRight, 780))
            y += row_h + 2
        y += 10
