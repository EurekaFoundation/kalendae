"""Nomi italiani, formattazione di date e icone disegnate al volo."""
from __future__ import annotations

import calendar as _cal
from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

GIORNI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
GIORNI_BREVI = ["LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]
MESI_BREVI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]

ACCENT = "#1a73e8"
NOW_LINE = "#ea4335"


def day_start(d: date) -> datetime:
    return datetime.combine(d, time())


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, _cal.monthrange(y, m)[1]))


def hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def long_date(d: date) -> str:
    return f"{GIORNI[d.weekday()]} {d.day} {MESI[d.month - 1]} {d.year}"


def time_range(o) -> str:
    """Testo orario di un'occorrenza, es. '09:00 – 10:30' o 'Tutto il giorno'."""
    if o.event.all_day:
        return "Tutto il giorno"
    if o.start.date() == o.end.date() or o.end == day_start(o.start.date() + timedelta(days=1)):
        return f"{hhmm(o.start)} – {hhmm(o.end)}"
    return f"{o.start.day} {MESI_BREVI[o.start.month - 1]} {hhmm(o.start)} – " \
           f"{o.end.day} {MESI_BREVI[o.end.month - 1]} {hhmm(o.end)}"


def text_on(color: str) -> QColor:
    """Colore del testo leggibile sopra uno sfondo dato."""
    c = QColor(color)
    lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return QColor("#202124") if lum > 165 else QColor("#ffffff")


def color_icon(color: str, size: int = 14) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), 3, 3)
    p.end()
    return QIcon(pm)


def app_icon() -> QIcon:
    """Icona del programma: un foglio di calendario con il giorno di oggi."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(size * 0.08, size * 0.10, size * 0.84, size * 0.82)
        rad = size * 0.12
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(ACCENT))
        p.drawRoundedRect(r, rad, rad)
        body = QRectF(r.x() + size * 0.05, r.y() + r.height() * 0.30,
                      r.width() - size * 0.10, r.height() * 0.64)
        p.setBrush(QColor("white"))
        p.drawRoundedRect(body, rad * 0.6, rad * 0.6)
        f = QFont()
        f.setBold(True)
        f.setPixelSize(max(6, int(size * 0.38)))
        p.setFont(f)
        p.setPen(QColor(ACCENT))
        p.drawText(body, Qt.AlignCenter, str(date.today().day))
        p.end()
        icon.addPixmap(pm)
    return icon
