"""Vista Giorno/Settimana: griglia oraria con trascinamento degli eventi."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QPen
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from ..database import Database, Occurrence
from ..utils import ACCENT, GIORNI_BREVI, NOW_LINE, day_start, hhmm, text_on

HOUR_H = 48      # altezza di un'ora in pixel
GUTTER = 58      # colonna degli orari a sinistra
SNAP = 15        # minuti di aggancio


def snap_dt(dt: datetime, mode: str = "round") -> datetime:
    mins = dt.hour * 60 + dt.minute + dt.second / 60
    if mode == "floor":
        q = int(mins // SNAP) * SNAP
    else:
        q = int(round(mins / SNAP)) * SNAP
    return datetime.combine(dt.date(), datetime.min.time()) + timedelta(minutes=q)


def layout_columns(items):
    """Dispone in colonne gli eventi sovrapposti. Restituisce [(item, colonna, n_colonne)]."""
    items = sorted(items, key=lambda x: (x[0], -(x[1] - x[0])))
    result, cluster, cols_end, cluster_end = [], [], [], None

    def flush():
        n = len(cols_end)
        result.extend((it, col, n) for it, col in cluster)

    for it in items:
        s, e = it[0], it[1]
        if cluster_end is not None and s >= cluster_end:
            flush()
            cluster, cols_end, cluster_end = [], [], None
        for i, ce in enumerate(cols_end):
            if ce <= s:
                cols_end[i] = e
                col = i
                break
        else:
            cols_end.append(e)
            col = len(cols_end) - 1
        cluster.append((it, col))
        cluster_end = e if cluster_end is None else max(cluster_end, e)
    if cluster:
        flush()
    return result


class WeekView(QWidget):
    eventClicked = Signal(object)                 # Occurrence
    createRequested = Signal(object, object, bool)  # inizio, fine, tutto il giorno
    dayClicked = Signal(object)                   # date
    occurrenceMoved = Signal(object, object, object)  # occorrenza, nuovo inizio, nuova fine

    def __init__(self, db: Database, days: int = 7, parent=None):
        super().__init__(parent)
        self.db = db
        self.n_days = days
        self.current = date.today()
        self.timed: list[list] = [[] for _ in range(days)]
        self.allday: list[tuple] = []
        self.allday_rows = 0

        self.header = _Header(self)
        self.grid = _Grid(self)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.grid)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.header)
        lay.addWidget(self.scroll)

        self._clock = QTimer(self)
        self._clock.timeout.connect(self.grid.update)
        self._clock.start(60_000)
        QTimer.singleShot(0, self.scroll_to_morning)

    # ---------------------------------------------------------- geometria
    @property
    def first_day(self) -> date:
        if self.n_days == 1:
            return self.current
        return self.current - timedelta(days=self.current.weekday())

    def days(self) -> list[date]:
        return [self.first_day + timedelta(days=i) for i in range(self.n_days)]

    def col_width(self) -> float:
        return max(1.0, (self.grid.width() - GUTTER) / self.n_days)

    def col_x(self, i: int) -> float:
        return GUTTER + i * self.col_width()

    def scroll_to_morning(self):
        self.scroll.verticalScrollBar().setValue(7 * HOUR_H)

    # -------------------------------------------------------------- dati
    def set_date(self, d: date):
        self.current = d
        self.refresh()

    def refresh(self):
        fd = self.first_day
        rs = day_start(fd)
        re_ = rs + timedelta(days=self.n_days)
        long_items, per_day = [], [[] for _ in range(self.n_days)]
        for o in self.db.occurrences(rs, re_):
            if o.is_long:
                long_items.append(o)
                continue
            for i in range(self.n_days):  # spezza gli eventi a cavallo di mezzanotte
                ds = rs + timedelta(days=i)
                s, e = max(o.start, ds), min(o.end, ds + timedelta(days=1))
                if s < e:
                    per_day[i].append((s, e, o))
        self.timed = [layout_columns(items) for items in per_day]

        rows_end: list[int] = []
        self.allday = []
        for o in long_items:
            a = max(0, (o.start.date() - fd).days)
            b = min(self.n_days - 1, ((o.end - timedelta(seconds=1)).date() - fd).days)
            for r, end in enumerate(rows_end):
                if end < a:
                    rows_end[r] = b
                    row = r
                    break
            else:
                rows_end.append(b)
                row = len(rows_end) - 1
            self.allday.append((o, a, b, row))
        self.allday_rows = len(rows_end)
        self.header.update_height()
        self.header.update()
        self.grid.update()


def _draw_event_box(p: QPainter, rect: QRectF, o: Occurrence, s: datetime, e: datetime, ghost=False,
                    border: QColor | None = None):
    bg = QColor(o.color)
    if ghost:
        bg.setAlpha(170)
    p.setPen(QPen(border or QColor("white"), 1))
    p.setBrush(bg)
    p.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 4, 4)
    p.setPen(text_on(o.color))
    inner = rect.adjusted(5, 2, -4, -2)
    f = p.font()
    f.setPointSizeF(8.5)
    f.setBold(True)
    p.setFont(f)
    title = o.event.title
    if rect.height() < 34:  # evento corto: tutto su una riga
        el = p.fontMetrics().elidedText(f"{title}, {hhmm(s)}", Qt.ElideRight, int(inner.width()))
        p.drawText(inner, Qt.AlignLeft | Qt.AlignTop, el)
        return
    p.save()
    p.setClipRect(rect)
    fh = p.fontMetrics().height()
    title_h = p.fontMetrics().boundingRect(inner.toRect(), Qt.TextWordWrap, title).height()
    title_h = min(title_h, fh * 2)  # al massimo due righe di titolo
    p.drawText(QRectF(inner.x(), inner.y(), inner.width(), title_h),
               Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, title)
    f.setBold(False)
    p.setFont(f)
    y = inner.y() + title_h
    for line in [f"{hhmm(s)} – {hhmm(e)}", o.event.location]:
        if line and y + fh <= rect.bottom():
            el = p.fontMetrics().elidedText(line, Qt.ElideRight, int(inner.width()))
            p.drawText(QRectF(inner.x(), y, inner.width(), fh), Qt.AlignLeft | Qt.AlignTop, el)
            y += fh
    p.restore()


class _Header(QWidget):
    TOP = 56
    ROW = 22

    def __init__(self, view: WeekView):
        super().__init__(view)
        self.view = view
        self.hits: list[tuple] = []
        self.update_height()

    def update_height(self):
        self.setFixedHeight(self.TOP + max(1, self.view.allday_rows) * self.ROW + 6)

    def paintEvent(self, _):
        v = self.view
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        p.fillRect(self.rect(), pal.color(QPalette.Base))
        today = date.today()
        cw = v.col_width()
        self.hits = []
        base_font = p.font()

        for i, d in enumerate(v.days()):
            x = v.col_x(i)
            is_today = d == today
            f = QFont(base_font)
            f.setPointSizeF(8)
            p.setFont(f)
            p.setPen(QColor(ACCENT) if is_today else pal.color(QPalette.PlaceholderText))
            p.drawText(QRectF(x, 4, cw, 16), Qt.AlignCenter, GIORNI_BREVI[d.weekday()])
            circle = QRectF(x + cw / 2 - 17, 20, 34, 34)
            if is_today:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(ACCENT))
                p.drawEllipse(circle)
            f.setPointSizeF(15)
            p.setFont(f)
            p.setPen(QColor("white") if is_today else pal.color(QPalette.Text))
            p.drawText(circle, Qt.AlignCenter, str(d.day))
            self.hits.append((circle, "day", d))
            p.setPen(pal.color(QPalette.Midlight))
            p.drawLine(QPointF(x, self.TOP), QPointF(x, self.height()))

        f = QFont(base_font)
        f.setPointSizeF(8.5)
        p.setFont(f)
        for o, a, b, row in v.allday:
            r = QRectF(v.col_x(a) + 2, self.TOP + row * self.ROW, (b - a + 1) * cw - 5, self.ROW - 3)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(o.color))
            p.drawRoundedRect(r, 4, 4)
            p.setPen(text_on(o.color))
            label = o.event.title if o.event.all_day else f"{hhmm(o.start)} {o.event.title}"
            p.drawText(r.adjusted(6, 0, -4, 0), Qt.AlignVCenter | Qt.AlignLeft, label)
            self.hits.append((r, "event", o))

        p.setPen(pal.color(QPalette.PlaceholderText))
        f.setPointSizeF(7.5)
        p.setFont(f)
        p.drawText(QRectF(0, self.TOP, GUTTER - 6, self.ROW), Qt.AlignRight | Qt.AlignVCenter, "tutto il g.")
        p.setPen(pal.color(QPalette.Mid))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

    def _hit(self, pos):
        for r, kind, payload in reversed(self.hits):
            if r.contains(pos):
                return kind, payload
        return None, None

    def mousePressEvent(self, e):
        kind, payload = self._hit(e.position())
        if kind == "event":
            self.view.eventClicked.emit(payload)
        elif kind == "day":
            self.view.dayClicked.emit(payload)

    def mouseDoubleClickEvent(self, e):
        kind, _ = self._hit(e.position())
        if kind is None and e.position().y() >= self.TOP and e.position().x() > GUTTER:
            i = int((e.position().x() - GUTTER) // self.view.col_width())
            d = self.view.days()[max(0, min(self.view.n_days - 1, i))]
            self.view.createRequested.emit(day_start(d), day_start(d) + timedelta(days=1), True)


class _Grid(QWidget):
    def __init__(self, view: WeekView):
        super().__init__(view)
        self.view = view
        self.setMinimumHeight(24 * HOUR_H + 1)
        self.setMouseTracking(True)
        self.boxes: list[tuple] = []   # (rect, occurrence, indice giorno)
        self.drag: dict | None = None

    # ---- conversioni coordinate <-> tempo
    def _day_index(self, x: float) -> int:
        i = int((x - GUTTER) // self.view.col_width())
        return max(0, min(self.view.n_days - 1, i))

    def _dt_at(self, pos) -> datetime:
        d = self.view.days()[self._day_index(pos.x())]
        mins = max(0.0, min(24 * 60 - 1, pos.y() * 60 / HOUR_H))
        return day_start(d) + timedelta(minutes=mins)

    def _y(self, dt: datetime, d: date) -> float:
        return (dt - day_start(d)).total_seconds() / 3600 * HOUR_H

    # ---- disegno
    def paintEvent(self, _):
        v = self.view
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        p.fillRect(self.rect(), pal.color(QPalette.Base))
        cw = v.col_width()
        days = v.days()
        today = date.today()

        if today in days:  # colonna di oggi leggermente evidenziata
            tint = QColor(ACCENT)
            tint.setAlpha(14)
            p.fillRect(QRectF(v.col_x(days.index(today)), 0, cw, self.height()), tint)

        f = p.font()
        f.setPointSizeF(7.5)
        p.setFont(f)
        for h in range(24):
            y = h * HOUR_H
            p.setPen(pal.color(QPalette.Midlight))
            p.drawLine(QPointF(GUTTER - 6, y), QPointF(self.width(), y))
            if h:
                p.setPen(pal.color(QPalette.PlaceholderText))
                p.drawText(QRectF(0, y - 8, GUTTER - 10, 16), Qt.AlignRight | Qt.AlignVCenter, f"{h:02d}:00")
        for i in range(v.n_days):
            p.setPen(pal.color(QPalette.Midlight))
            p.drawLine(QPointF(v.col_x(i), 0), QPointF(v.col_x(i), self.height()))

        self.boxes = []
        dragged = self.drag["occ"] if self.drag and self.drag.get("moved") else None
        for i, laid in enumerate(v.timed):
            d = days[i]
            for (s, e, o), col, n in laid:
                w = (cw - 8) / n
                x = v.col_x(i) + 1 + col * w
                y1, y2 = self._y(s, d), self._y(e, d)
                rect = QRectF(x, y1 + 1, w if n == 1 else w + 2, max(20.0, y2 - y1 - 1))
                self.boxes.append((rect, o, i))
                if o is dragged:
                    p.setOpacity(0.35)
                _draw_event_box(p, rect, o, o.start, o.end, border=pal.color(QPalette.Base))
                p.setOpacity(1.0)

        self._paint_drag(p, days, cw)

        if today in days:  # linea dell'ora attuale
            i = days.index(today)
            y = self._y(datetime.now(), today)
            p.setPen(QPen(QColor(NOW_LINE), 2))
            p.drawLine(QPointF(v.col_x(i), y), QPointF(v.col_x(i) + cw, y))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(NOW_LINE))
            p.drawEllipse(QPointF(v.col_x(i), y), 5, 5)

    def _paint_drag(self, p, days, cw):
        dr = self.drag
        if not dr:
            return
        v = self.view
        if dr["mode"] == "create":
            s, e = sorted((dr["a"], dr["b"]))
            if e == s:
                e = s + timedelta(minutes=SNAP)
            i = days.index(s.date())
            r = QRectF(v.col_x(i) + 1, self._y(s, s.date()), cw - 8, self._y(e, s.date()) - self._y(s, s.date()))
            c = QColor(ACCENT)
            c.setAlpha(110)
            p.setPen(QPen(QColor(ACCENT), 1))
            p.setBrush(c)
            p.drawRoundedRect(r, 4, 4)
            p.setPen(QColor("white"))
            p.drawText(r.adjusted(5, 2, -3, 0), Qt.AlignLeft | Qt.AlignTop, f"{hhmm(s)} – {hhmm(e)}")
        elif dr.get("moved"):
            o = dr["occ"]
            s, e = dr["new_start"], dr["new_end"]
            d = s.date()
            if d in days:
                i = days.index(d)
                y2 = self._y(min(e, day_start(d) + timedelta(days=1)), d)
                r = QRectF(v.col_x(i) + 1, self._y(s, d) + 1, cw - 8, max(20.0, y2 - self._y(s, d) - 1))
                _draw_event_box(p, r, o, s, e, ghost=True)

    # ---- mouse
    def _box_at(self, pos):
        for rect, o, i in reversed(self.boxes):
            if rect.contains(pos):
                return rect, o, i
        return None

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        pos = e.position()
        hit = self._box_at(pos)
        if hit:
            rect, o, i = hit
            if pos.y() > rect.bottom() - 6:
                self.drag = {"mode": "resize", "occ": o, "moved": False,
                             "new_start": o.start, "new_end": o.end}
            else:
                self.drag = {"mode": "move", "occ": o, "moved": False,
                             "offset": self._dt_at(pos) - o.start,
                             "new_start": o.start, "new_end": o.end}
        elif pos.x() > GUTTER:
            t = snap_dt(self._dt_at(pos), "floor")
            self.drag = {"mode": "create", "a": t, "b": t}
        self.update()

    def mouseMoveEvent(self, e):
        pos = e.position()
        dr = self.drag
        if not dr:
            hit = self._box_at(pos)
            if hit and pos.y() > hit[0].bottom() - 6:
                self.setCursor(Qt.SizeVerCursor)
            elif hit:
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.unsetCursor()
            return
        o = dr.get("occ")
        if dr["mode"] == "move":
            ns = snap_dt(self._dt_at(pos) - dr["offset"])
            if ns != o.start:
                dr["moved"] = True
            dr["new_start"], dr["new_end"] = ns, ns + (o.end - o.start)
        elif dr["mode"] == "resize":
            d = o.start.date()
            col = self.view.days().index(d) if d in self.view.days() else self._day_index(pos.x())
            t = day_start(self.view.days()[col]) + timedelta(minutes=max(0, pos.y() * 60 / HOUR_H))
            ne = max(o.start + timedelta(minutes=SNAP), snap_dt(t))
            dr["moved"] = ne != o.end
            dr["new_end"] = ne
        elif dr["mode"] == "create":
            a = dr["a"]
            mins = max(0.0, min(24 * 60.0, pos.y() * 60 / HOUR_H))  # resta nello stesso giorno
            t = day_start(a.date()) + timedelta(minutes=mins)
            if t >= a:   # trascinando in giù si arrotonda per eccesso
                q = min(24 * 60, -(-int(mins) // SNAP) * SNAP)
                dr["b"] = day_start(a.date()) + timedelta(minutes=q)
            else:
                dr["b"] = snap_dt(t, "floor")
        self.update()

    def mouseReleaseEvent(self, e):
        dr, self.drag = self.drag, None
        if not dr:
            return
        v = self.view
        if dr["mode"] in ("move", "resize"):
            o = dr["occ"]
            if not dr["moved"]:
                v.eventClicked.emit(o)
            else:
                v.occurrenceMoved.emit(o, dr["new_start"], dr["new_end"])
        elif dr["mode"] == "create":
            s, en = sorted((dr["a"], dr["b"]))
            if (en - s) <= timedelta(minutes=SNAP):  # semplice clic: un'ora
                en = s + timedelta(hours=1)
            v.createRequested.emit(s, en, False)
        self.update()
