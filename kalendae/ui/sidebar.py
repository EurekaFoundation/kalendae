"""Barra laterale: pulsante Crea, mini calendario ed elenco dei calendari."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QLocale, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCalendarWidget, QColorDialog, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from ..database import DEFAULT_COLORS, Calendar, Database
from ..utils import ACCENT, color_icon


class CalendarDialog(QDialog):
    def __init__(self, cal: Calendar, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calendario")
        self.cal = cal
        self.color = cal.color
        self.name = QLineEdit(cal.name)
        self.name.setPlaceholderText("Nome del calendario")
        self.color_btn = QPushButton()
        self.color_btn.clicked.connect(self._pick)
        swatches = QHBoxLayout()
        for c in DEFAULT_COLORS:
            b = QPushButton()
            b.setFixedSize(22, 22)
            b.setStyleSheet(f"background:{c}; border-radius:11px; border:none;")
            b.clicked.connect(lambda _=False, c=c: self._set_color(c))
            swatches.addWidget(b)
        swatches.addWidget(self.color_btn)
        self._set_color(self.color)
        form = QFormLayout(self)
        form.addRow("Nome", self.name)
        form.addRow("Colore", swatches)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Salva")
        bb.button(QDialogButtonBox.Cancel).setText("Annulla")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _set_color(self, c):
        self.color = c
        self.color_btn.setIcon(color_icon(c, 16))
        self.color_btn.setText("Altro…")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self.color), self, "Scegli un colore")
        if c.isValid():
            self._set_color(c.name())

    def result_calendar(self) -> Calendar:
        return Calendar(self.cal.id, self.name.text().strip() or "Senza nome", self.color, self.cal.visible)


class Sidebar(QWidget):
    dateSelected = Signal(object)
    calendarsChanged = Signal()
    createRequested = Signal()

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setMinimumWidth(250)
        self.setMaximumWidth(330)

        create = QPushButton("＋  Crea")
        create.setMinimumHeight(44)
        create.setCursor(Qt.PointingHandCursor)
        create.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:white; border:none; border-radius:22px;"
            f" font-size:14px; font-weight:600; padding:0 22px; }}"
            f"QPushButton:hover {{ background:#1765cc; }}")
        create.clicked.connect(self.createRequested.emit)

        self.mini = QCalendarWidget()
        self.mini.setLocale(QLocale(QLocale.Italian, QLocale.Italy))
        self.mini.setFirstDayOfWeek(Qt.Monday)
        self.mini.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.mini.setGridVisible(False)
        self.mini.setFixedHeight(220)
        self.mini.clicked.connect(lambda qd: self.dateSelected.emit(qd.toPython()))

        title = QLabel("I miei calendari")
        f = title.font()
        f.setBold(True)
        title.setFont(f)

        self.list = QListWidget()
        self.list.setFrameShape(QListWidget.NoFrame)
        self.list.itemChanged.connect(self._toggled)
        self.list.itemDoubleClicked.connect(lambda _: self._edit())

        btns = QHBoxLayout()
        for text, slot, tip in (("＋", self._add, "Nuovo calendario"),
                                ("✎", self._edit, "Modifica calendario"),
                                ("🗑", self._delete, "Elimina calendario")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setFixedWidth(40)
            b.clicked.connect(slot)
            btns.addWidget(b)
        btns.addStretch()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 8, 8)
        lay.addWidget(create, alignment=Qt.AlignLeft)
        lay.addSpacing(8)
        lay.addWidget(self.mini)
        lay.addSpacing(8)
        lay.addWidget(title)
        lay.addWidget(self.list, 1)
        lay.addLayout(btns)
        self.reload()

    def set_date(self, d: date):
        self.mini.setSelectedDate(QDate(d.year, d.month, d.day))

    def reload(self):
        self.list.blockSignals(True)
        self.list.clear()
        for c in self.db.calendars():
            it = QListWidgetItem(color_icon(c.color, 16), c.name)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if c.visible else Qt.Unchecked)
            it.setData(Qt.UserRole, c.id)
            self.list.addItem(it)
        self.list.blockSignals(False)

    def _selected(self) -> Calendar | None:
        it = self.list.currentItem()
        if not it:
            return None
        cid = it.data(Qt.UserRole)
        return next((c for c in self.db.calendars() if c.id == cid), None)

    def _toggled(self, item):
        cal = next((c for c in self.db.calendars() if c.id == item.data(Qt.UserRole)), None)
        if cal:
            cal.visible = item.checkState() == Qt.Checked
            self.db.update_calendar(cal)
            self.calendarsChanged.emit()

    def _add(self):
        used = {c.color for c in self.db.calendars()}
        color = next((c for c in DEFAULT_COLORS if c not in used), DEFAULT_COLORS[0])
        dlg = CalendarDialog(Calendar(None, "", color), self)
        if dlg.exec():
            self.db.add_calendar(dlg.result_calendar())
            self.reload()
            self.calendarsChanged.emit()

    def _edit(self):
        cal = self._selected()
        if not cal:
            QMessageBox.information(self, "Calendari", "Seleziona prima un calendario dall'elenco.")
            return
        dlg = CalendarDialog(cal, self)
        if dlg.exec():
            self.db.update_calendar(dlg.result_calendar())
            self.reload()
            self.calendarsChanged.emit()

    def _delete(self):
        cal = self._selected()
        if not cal:
            QMessageBox.information(self, "Calendari", "Seleziona prima un calendario dall'elenco.")
            return
        if len(self.db.calendars()) <= 1:
            QMessageBox.information(self, "Calendari", "Deve restare almeno un calendario.")
            return
        ok = QMessageBox.question(
            self, "Elimina calendario",
            f"Eliminare il calendario «{cal.name}» e tutti i suoi eventi?\nL'operazione non si può annullare.")
        if ok == QMessageBox.Yes:
            self.db.delete_calendar(cal.id)
            self.reload()
            self.calendarsChanged.emit()
