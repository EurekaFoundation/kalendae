"""Vista Agenda: elenco dei prossimi eventi o dei risultati di ricerca."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ..database import Database
from ..utils import color_icon, day_start, long_date, time_range

ROLE_OCC = Qt.UserRole + 1


class AgendaView(QWidget):
    eventClicked = Signal(object)
    DAYS = 30

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.current = date.today()
        self.query = ""
        self.heading = QLabel()
        f = self.heading.font()
        f.setPointSize(f.pointSize() + 2)
        f.setBold(True)
        self.heading.setFont(f)
        self.list = QListWidget()
        self.list.setFrameShape(QListWidget.NoFrame)
        self.list.setSpacing(2)
        self.list.itemActivated.connect(self._activated)
        self.list.itemClicked.connect(self._activated)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 6)
        lay.addWidget(self.heading)
        lay.addWidget(self.list)

    def set_date(self, d: date):
        self.current = d
        self.refresh()

    def set_query(self, text: str):
        self.query = text.strip()
        self.refresh()

    def refresh(self):
        if self.query:
            occs = self.db.search(self.query)
            self.heading.setText(f"Risultati per «{self.query}» ({len(occs)})")
        else:
            rs = day_start(self.current)
            occs = self.db.occurrences(rs, rs + timedelta(days=self.DAYS))
            occs.sort(key=lambda o: o.start)
            self.heading.setText(f"Prossimi {self.DAYS} giorni")
        self._populate(occs)

    def _populate(self, occs):
        self.list.clear()
        last_day = None
        bold = QFont(self.font())
        bold.setBold(True)
        if not occs:
            it = QListWidgetItem("Nessun evento.")
            it.setFlags(Qt.NoItemFlags)
            self.list.addItem(it)
            return
        for o in occs:
            d = o.start.date()
            if d != last_day:
                head = QListWidgetItem(long_date(d))
                head.setFont(bold)
                head.setFlags(Qt.ItemIsEnabled)
                if d == date.today():
                    head.setText(long_date(d) + "  ·  oggi")
                self.list.addItem(head)
                last_day = d
            text = f"   {time_range(o):<18}   {o.event.title}"
            if o.event.location:
                text += f"   ·   {o.event.location}"
            if o.is_recurring:
                text += "   ↻"
            it = QListWidgetItem(color_icon(o.color, 12), text)
            it.setData(ROLE_OCC, o)
            self.list.addItem(it)

    def _activated(self, item):
        o = item.data(ROLE_OCC)
        if o is not None:
            self.eventClicked.emit(o)
