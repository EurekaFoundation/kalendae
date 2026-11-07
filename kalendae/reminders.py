"""Promemoria: controlla gli eventi in arrivo e mostra una notifica di sistema."""
from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QSystemTrayIcon

from .database import Database, Occurrence
from .utils import time_range


class ReminderService(QObject):
    reminderDue = Signal(object)  # Occurrence

    def __init__(self, db: Database, tray: QSystemTrayIcon | None = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.tray = tray
        self.started = datetime.now() - timedelta(minutes=1)
        self.notified: set[tuple] = set()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check)
        self.timer.start(20_000)
        QTimer.singleShot(1000, self.check)

    def due(self, now: datetime | None = None) -> list[Occurrence]:
        now = now or datetime.now()
        out = []
        for o in self.db.occurrences(now - timedelta(minutes=1), now + timedelta(days=8), only_visible=False):
            if o.event.reminder < 0:
                continue
            trigger = o.start - timedelta(minutes=o.event.reminder)
            key = (o.event.id, o.start)
            if key not in self.notified and self.started <= trigger <= now:
                out.append(o)
        return out

    def check(self):
        for o in self.due():
            self.notified.add((o.event.id, o.start))
            self.notify(o)

    def notify(self, o: Occurrence):
        body = time_range(o)
        if o.event.location:
            body += f" · {o.event.location}"
        if self.tray is not None and self.tray.isVisible():
            self.tray.showMessage(o.event.title, body, QSystemTrayIcon.Information, 15_000)
        self.reminderDue.emit(o)
