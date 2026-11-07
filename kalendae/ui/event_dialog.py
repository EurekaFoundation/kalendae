"""Finestra di creazione e modifica di un evento, e scelta dell'ambito per gli eventi ricorrenti."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QDate, QTime, Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton,
    QSpinBox, QTimeEdit, QToolButton, QVBoxLayout, QWidget,
)

from ..database import Database, Event
from ..recurrence import (
    FREQUENZE, GIORNI_MIN, ORDINALI, UNITA, UNITA_SING, WEEKDAYS, describe, format_byday,
    monthly_position, parse_byday, until_from_count,
)
from ..series import ALL, FOLLOWING, ONE, SCOPE_LABELS
from ..utils import color_icon

PROMEMORIA = [
    (-1, "Nessun promemoria"), (0, "All'inizio dell'evento"), (5, "5 minuti prima"),
    (10, "10 minuti prima"), (15, "15 minuti prima"), (30, "30 minuti prima"),
    (60, "1 ora prima"), (120, "2 ore prima"), (1440, "1 giorno prima"), (10080, "1 settimana prima"),
]
INIZIALI = ["L", "M", "M", "G", "V", "S", "D"]


def _qd(d):
    return QDate(d.year, d.month, d.day)


def _qt(t):
    return QTime(t.hour, t.minute)


class ScopeDialog(QDialog):
    """Chiede a quali occorrenze di una serie applicare una modifica o un'eliminazione."""

    def __init__(self, title: str, parent=None, default: str = ONE):
        super().__init__(parent)
        self.setWindowTitle(title)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<b>{title}</b>"))
        self.group = QButtonGroup(self)
        for key in (ONE, FOLLOWING, ALL):
            rb = QRadioButton(SCOPE_LABELS[key])
            rb.setProperty("scope", key)
            rb.setChecked(key == default)
            self.group.addButton(rb)
            lay.addWidget(rb)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("OK")
        bb.button(QDialogButtonBox.Cancel).setText("Annulla")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def scope(self) -> str:
        return self.group.checkedButton().property("scope")

    @staticmethod
    def ask(title: str, parent=None) -> str | None:
        dlg = ScopeDialog(title, parent)
        return dlg.scope() if dlg.exec() else None


class EventDialog(QDialog):
    def __init__(self, db: Database, event: Event, parent=None):
        """`event` è l'evento da modificare; per una serie, con inizio/fine dell'occorrenza aperta."""
        super().__init__(parent)
        self.db = db
        self._ev = event
        self.deleted = False
        is_new = event.id is None
        self.setWindowTitle("Nuovo evento" if is_new else "Modifica evento")
        self.setMinimumWidth(560)

        self.title = QLineEdit(event.title)
        self.title.setPlaceholderText("Aggiungi titolo")
        f = self.title.font()
        f.setPointSize(f.pointSize() + 5)
        self.title.setFont(f)

        self.calendar = QComboBox()
        for c in db.calendars():
            self.calendar.addItem(color_icon(c.color), c.name, c.id)
        self.calendar.setCurrentIndex(max(0, self.calendar.findData(event.calendar_id)))

        self.all_day = QCheckBox("Tutto il giorno")
        self.all_day.setChecked(event.all_day)
        self.start_date, self.start_time = self._date_edit(), self._time_edit()
        self.end_date, self.end_time = self._date_edit(), self._time_edit()

        self._build_recurrence_widgets(event)

        self.reminder = QComboBox()
        options = list(PROMEMORIA)
        if event.reminder not in dict(options):
            options.append((event.reminder, f"{event.reminder} minuti prima"))
        for k, v in options:
            self.reminder.addItem(v, k)
        self.reminder.setCurrentIndex(self.reminder.findData(event.reminder))

        self.location = QLineEdit(event.location)
        self.location.setPlaceholderText("Aggiungi luogo")
        self.description = QPlainTextEdit(event.description)
        self.description.setPlaceholderText("Aggiungi descrizione")
        self.description.setFixedHeight(90)

        form = QFormLayout()
        form.addRow("Calendario", self.calendar)
        form.addRow("", self.all_day)
        form.addRow("Inizio", self._row(self.start_date, self.start_time))
        form.addRow("Fine", self._row(self.end_date, self.end_time))
        form.addRow("Ripetizione", self._row(self.repeat, self.summary))
        form.addRow("", self.repeat_box)
        form.addRow("Promemoria", self.reminder)
        form.addRow("Luogo", self.location)
        form.addRow("Descrizione", self.description)

        lay = QVBoxLayout(self)
        lay.addWidget(self.title)
        lay.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Salva")
        buttons.button(QDialogButtonBox.Cancel).setText("Annulla")
        if not is_new:
            delete = QPushButton("Elimina")
            buttons.addButton(delete, QDialogButtonBox.DestructiveRole)
            delete.clicked.connect(self._delete)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        # valori iniziali e collegamenti
        self._set_start(event.start)
        self._set_end(event.end)
        self._duration = event.end - event.start
        self._last_weekday = event.start.weekday()
        self._apply_all_day()
        self._refresh_monthly_options()
        self._apply_repeat()
        self.start_date.dateChanged.connect(self._start_changed)
        self.start_time.timeChanged.connect(self._start_changed)
        self.end_date.dateChanged.connect(self._end_changed)
        self.end_time.timeChanged.connect(self._end_changed)
        self.all_day.toggled.connect(self._all_day_toggled)
        self.title.setFocus()

    # ---------------------------------------------------------- ricorrenza
    def _build_recurrence_widgets(self, ev: Event):
        self.repeat = QComboBox()
        for k, v in FREQUENZE.items():
            self.repeat.addItem(v, k)
        self.repeat.setCurrentIndex(max(0, self.repeat.findData(ev.recurrence)))
        self.summary = QLabel()
        self.summary.setStyleSheet("color: #8a8f98;")
        self.summary.setWordWrap(True)

        self.interval = QSpinBox()
        self.interval.setRange(1, 99)
        self.interval.setValue(max(1, ev.interval))
        self.unit = QLabel()

        # giorni della settimana
        self.day_buttons: list[QToolButton] = []
        rules = parse_byday(ev.byday)
        chosen = {wd for _, wd in rules} if ev.recurrence == "WEEKLY" and rules else {ev.start.weekday()}
        days_box = QWidget()
        dl = QHBoxLayout(days_box)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(4)
        for i, letter in enumerate(INIZIALI):
            b = QToolButton()
            b.setText(letter)
            b.setToolTip(GIORNI_MIN[i])
            b.setCheckable(True)
            b.setChecked(i in chosen)
            b.setFixedSize(30, 30)
            b.setStyleSheet("QToolButton { border-radius: 15px; border: 1px solid palette(mid); }"
                            "QToolButton:checked { background: #1a73e8; color: white; border: none; }")
            b.toggled.connect(self._update_summary)
            self.day_buttons.append(b)
            dl.addWidget(b)
        dl.addStretch()
        self.days_box = days_box

        # mensile: giorno del mese o n-esimo giorno della settimana
        self.monthly = QComboBox()
        self._monthly_kind = "day"
        nth_rules = [(n, wd) for n, wd in rules if n] if ev.recurrence == "MONTHLY" else []
        if nth_rules:
            self._monthly_kind = "last" if nth_rules[0][0] == -1 else "nth"
        self.monthly.currentIndexChanged.connect(self._monthly_changed)

        # fine della ripetizione
        self.end_mode = QComboBox()
        self.end_mode.addItem("Mai", "never")
        self.end_mode.addItem("Il giorno", "until")
        self.end_mode.addItem("Dopo", "count")
        self.until = self._date_edit()
        self.until.setDate(_qd(ev.until or (ev.start.date() + timedelta(days=90))))
        self.count = QSpinBox()
        self.count.setRange(1, 999)
        self.count.setValue(10)
        self.count.setSuffix(" volte")
        self.end_mode.setCurrentIndex(1 if ev.until else 0)

        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        self.row_interval = self._row(QLabel("Ogni"), self.interval, self.unit)
        self.row_days = self._row(QLabel("Nei giorni"), self.days_box)
        self.row_monthly = self._row(self.monthly)
        self.row_end = self._row(QLabel("Termina"), self.end_mode, self.until, self.count)
        for r in (self.row_interval, self.row_days, self.row_monthly, self.row_end):
            v.addWidget(r)
        self.repeat_box = box

        self.repeat.currentIndexChanged.connect(self._apply_repeat)
        self.interval.valueChanged.connect(self._apply_repeat)
        self.end_mode.currentIndexChanged.connect(self._apply_repeat)
        self.until.dateChanged.connect(self._update_summary)
        self.count.valueChanged.connect(self._update_summary)

    def _refresh_monthly_options(self):
        d = self.start_date.date().toPython()
        nth, is_last = monthly_position(d)
        wd = d.weekday()
        self.monthly.blockSignals(True)
        self.monthly.clear()
        self.monthly.addItem(f"Il giorno {d.day} di ogni mese", "day")
        if nth <= 4:
            self.monthly.addItem(f"Il {ORDINALI[nth]} {GIORNI_MIN[wd]} del mese", "nth")
        if is_last:
            self.monthly.addItem(f"L'ultimo {GIORNI_MIN[wd]} del mese", "last")
        idx = self.monthly.findData(self._monthly_kind)
        self.monthly.setCurrentIndex(idx if idx >= 0 else 0)
        self._monthly_kind = self.monthly.currentData()
        self.monthly.blockSignals(False)

    def _monthly_changed(self):
        self._monthly_kind = self.monthly.currentData()
        self._update_summary()

    def _apply_repeat(self):
        freq = self.repeat.currentData()
        self.repeat_box.setVisible(bool(freq))
        n = self.interval.value()
        self.unit.setText(UNITA_SING.get(freq, "") if n == 1 else UNITA.get(freq, ""))
        self.row_days.setVisible(freq == "WEEKLY")
        self.row_monthly.setVisible(freq == "MONTHLY")
        mode = self.end_mode.currentData()
        self.until.setVisible(mode == "until")
        self.count.setVisible(mode == "count")
        self._update_summary()

    def _byday(self, freq: str) -> str:
        d = self.start_date.date().toPython()
        if freq == "WEEKLY":
            days = [i for i, b in enumerate(self.day_buttons) if b.isChecked()] or [d.weekday()]
            return ",".join(WEEKDAYS[i] for i in days)
        if freq == "MONTHLY":
            kind = self.monthly.currentData()
            if kind == "nth":
                return format_byday([(monthly_position(d)[0], d.weekday())])
            if kind == "last":
                return format_byday([(-1, d.weekday())])
        return ""

    def _draft(self) -> Event:
        """Evento con la regola attuale (senza 'fine'), usato per anteprima e conteggio."""
        freq = self.repeat.currentData()
        return replace(self._ev, start=self._start_dt(), end=self._end_dt(), recurrence=freq,
                       interval=self.interval.value(), byday=self._byday(freq), until=None)

    def _until_value(self, draft: Event) -> date | None:
        mode = self.end_mode.currentData()
        if mode == "until":
            return self.until.date().toPython()
        if mode == "count":
            return until_from_count(draft, self.count.value())
        return None

    def _update_summary(self):
        freq = self.repeat.currentData()
        if not freq:
            self.summary.setText("")
            return
        draft = self._draft()
        draft.until = self._until_value(draft)
        self.summary.setText(describe(draft))

    # ------------------------------------------------------------ helper UI
    @staticmethod
    def _date_edit():
        w = QDateEdit()
        w.setCalendarPopup(True)
        w.setDisplayFormat("ddd d MMM yyyy")
        return w

    @staticmethod
    def _time_edit():
        w = QTimeEdit()
        w.setDisplayFormat("HH:mm")
        return w

    @staticmethod
    def _row(*widgets):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        for w in widgets:
            h.addWidget(w)
        h.addStretch()
        return box

    # ------------------------------------------------- lettura/scrittura date
    def _start_dt(self) -> datetime:
        d = self.start_date.date().toPython()
        t = time() if self.all_day.isChecked() else self.start_time.time().toPython()
        return datetime.combine(d, t)

    def _end_dt(self) -> datetime:
        d = self.end_date.date().toPython()
        if self.all_day.isChecked():  # in vista la data finale è inclusa
            return datetime.combine(d + timedelta(days=1), time())
        return datetime.combine(d, self.end_time.time().toPython())

    def _set_start(self, dt):
        for w in (self.start_date, self.start_time):
            w.blockSignals(True)
        self.start_date.setDate(_qd(dt))
        self.start_time.setTime(_qt(dt))
        for w in (self.start_date, self.start_time):
            w.blockSignals(False)

    def _set_end(self, dt):
        for w in (self.end_date, self.end_time):
            w.blockSignals(True)
        shown = dt - timedelta(days=1) if self.all_day.isChecked() else dt
        self.end_date.setDate(_qd(shown))
        self.end_time.setTime(_qt(dt))
        for w in (self.end_date, self.end_time):
            w.blockSignals(False)

    def _start_changed(self):
        self._set_end(self._start_dt() + self._duration)
        wd = self.start_date.date().toPython().weekday()
        checked = [i for i, b in enumerate(self.day_buttons) if b.isChecked()]
        if wd != self._last_weekday and checked == [self._last_weekday]:  # segue il giorno scelto
            self.day_buttons[self._last_weekday].setChecked(False)
            self.day_buttons[wd].setChecked(True)
        self._last_weekday = wd
        self._refresh_monthly_options()
        self._update_summary()

    def _end_changed(self):
        dur = self._end_dt() - self._start_dt()
        if dur.total_seconds() > 0:
            self._duration = dur

    def _all_day_toggled(self, checked):
        start = self._start_dt()
        if checked:
            days = max(1, (self.end_date.date().toPython() - start.date()).days + 1)
            self._duration = timedelta(days=days)
        else:
            if self.start_time.time() == QTime(0, 0):
                self.start_time.blockSignals(True)
                self.start_time.setTime(QTime(9, 0))
                self.start_time.blockSignals(False)
            self._duration = timedelta(hours=1)
        self._apply_all_day()
        self._set_end(self._start_dt() + self._duration)

    def _apply_all_day(self):
        timed = not self.all_day.isChecked()
        self.start_time.setVisible(timed)
        self.end_time.setVisible(timed)

    # --------------------------------------------------------------- azioni
    def _save(self):
        if self._end_dt() <= self._start_dt():
            QMessageBox.warning(self, "Orario non valido", "La fine deve essere successiva all'inizio.")
            return
        self.accept()

    def _delete(self):
        self.deleted = True
        self.accept()

    def result_event(self) -> Event:
        draft = self._draft()
        freq = draft.recurrence
        return replace(
            draft,
            title=self.title.text().strip() or "(Senza titolo)",
            calendar_id=self.calendar.currentData(),
            all_day=self.all_day.isChecked(),
            interval=self.interval.value() if freq else 1,
            byday=draft.byday if freq else "",
            until=self._until_value(draft) if freq else None,
            exdates=set(self._ev.exdates) if freq else set(),
            reminder=self.reminder.currentData(),
            location=self.location.text().strip(),
            description=self.description.toPlainText().strip(),
        )
