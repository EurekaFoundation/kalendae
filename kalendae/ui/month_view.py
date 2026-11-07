"""Vista Mese: griglia di 6 settimane."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPalette
from PySide6.QtWidgets import QWidget

from ..database import Database
from ..utils import ACCENT, GIORNI_BREVI, MESI_BREVI, day_start, hhmm, text_on


class MonthView(QWidget):
    eventClicked = Signal(object)
    dayClicked = Signal(object)
    createRequested = Signal(object, object, bool)

    HEAD = 26
    CHIP = 18

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.current = date.today()
        self.grid_start = self.current
        self.by_day: dict[date, list] = {}
        self.hits: list[tuple] = []
        self.setMouseTracking(True)
        self.setMinimumSize(480, 380)

    def set_date(self, d: date):
        self.current = d
        self.refresh()

    def refresh(self):
        first = self.current.replace(day=1)
        self.grid_start = first - timedelta(days=first.weekday())
        rs = day_start(self.grid_start)
        re_ = rs + timedelta(days=42)
        by_day = defaultdict(list)
        last_cell = self.grid_start + timedelta(days=41)
        for o in self.db.occurrences(rs, re_):
            d = max(o.start.date(), self.grid_start)
            last = min((o.end - timedelta(seconds=1)).date(), last_cell)
            while d <= last:
                by_day[d].append(o)
                d += timedelta(days=1)
        self.by_day = by_day
        self.update()

    def _cell(self, idx: int) -> QRectF:
        cw = self.width() / 7
        ch = (self.height() - self.HEAD) / 6
        r, c = divmod(idx, 7)
        return QRectF(c * cw, self.HEAD + r * ch, cw, ch)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        p.fillRect(self.rect(), pal.color(QPalette.Base))
        base = QFont(p.font())
        today = date.today()
        cw = self.width() / 7
        self.hits = []

        f = QFont(base)
        f.setPointSizeF(8)
        p.setFont(f)
        p.setPen(pal.color(QPalette.PlaceholderText))
        for c in range(7):
            p.drawText(QRectF(c * cw, 0, cw, self.HEAD), Qt.AlignCenter, GIORNI_BREVI[c])

        for idx in range(42):
            d = self.grid_start + timedelta(days=idx)
            cell = self._cell(idx)
            if d.month != self.current.month:
                p.fillRect(cell, pal.color(QPalette.AlternateBase))
            p.setPen(pal.color(QPalette.Midlight))
            p.drawLine(cell.topLeft(), cell.topRight())
            p.drawLine(cell.topLeft(), cell.bottomLeft())

            # numero del giorno
            label = str(d.day) if d.day != 1 else f"{d.day} {MESI_BREVI[d.month - 1]}"
            f = QFont(base)
            f.setPointSizeF(9)
            p.setFont(f)
            tw = max(24, p.fontMetrics().horizontalAdvance(label) + 12)
            num = QRectF(cell.center().x() - tw / 2, cell.y() + 3, tw, 22)
            if d == today:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(ACCENT))
                p.drawRoundedRect(num, 11, 11)
                p.setPen(QColor("white"))
            else:
                other = d.month != self.current.month
                p.setPen(pal.color(QPalette.PlaceholderText) if other else pal.color(QPalette.Text))
            p.drawText(num, Qt.AlignCenter, label)
            self.hits.append((num, "day", d))

            # eventi
            items = self.by_day.get(d, [])
            avail = max(0, int((cell.height() - 30) // (self.CHIP + 2)))
            show = items if len(items) <= avail else items[:max(0, avail - 1)]
            y = cell.y() + 28
            f.setPointSizeF(8.5)
            p.setFont(f)
            for o in show:
                r = QRectF(cell.x() + 3, y, cell.width() - 6, self.CHIP)
                if o.is_long:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(o.color))
                    p.drawRoundedRect(r, 4, 4)
                    p.setPen(text_on(o.color))
                    p.drawText(r.adjusted(6, 0, -3, 0), Qt.AlignVCenter | Qt.AlignLeft, o.event.title)
                else:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(o.color))
                    p.drawEllipse(QPointF(r.x() + 7, r.center().y()), 4, 4)
                    p.setPen(pal.color(QPalette.Text))
                    text = f"{hhmm(o.start)}  {o.event.title}"
                    el = p.fontMetrics().elidedText(text, Qt.ElideRight, int(r.width() - 18))
                    p.drawText(r.adjusted(16, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, el)
                self.hits.append((r, "event", o))
                y += self.CHIP + 2
            hidden = len(items) - len(show)
            if hidden > 0:
                r = QRectF(cell.x() + 3, y, cell.width() - 6, self.CHIP)
                f.setBold(True)
                p.setFont(f)
                p.setPen(pal.color(QPalette.Text))
                p.drawText(r.adjusted(6, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, f"+{hidden} altri")
                f.setBold(False)
                p.setFont(f)
                self.hits.append((r, "day", d))

    def _hit(self, pos):
        for r, kind, payload in reversed(self.hits):
            if r.contains(pos):
                return kind, payload
        return None, None

    def _date_at(self, pos) -> date | None:
        for idx in range(42):
            if self._cell(idx).contains(pos):
                return self.grid_start + timedelta(days=idx)
        return None

    def mouseMoveEvent(self, e):
        kind, _ = self._hit(e.position())
        self.setCursor(Qt.PointingHandCursor if kind else Qt.ArrowCursor)

    def mousePressEvent(self, e):
        kind, payload = self._hit(e.position())
        if kind == "event":
            self.eventClicked.emit(payload)
        elif kind == "day":
            self.dayClicked.emit(payload)

    def mouseDoubleClickEvent(self, e):
        kind, _ = self._hit(e.position())
        d = self._date_at(e.position())
        if kind is None and d:
            s = day_start(d) + timedelta(hours=9)
            self.createRequested.emit(s, s + timedelta(hours=1), False)
