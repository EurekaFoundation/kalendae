"""Finestra principale di Kalendae."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QKeySequence, QPalette
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QPushButton, QSplitter, QStackedWidget, QSystemTrayIcon,
    QToolButton, QVBoxLayout, QWidget,
)

from .. import __version__
from .. import series
from ..database import Database, Event
from ..ics import export_ics, import_into
from ..reminders import ReminderService
from ..utils import MESI, add_months, app_icon, long_date, time_range
from .agenda_view import AgendaView
from . import printing
from .event_dialog import EventDialog, ScopeDialog
from .month_view import MonthView
from .sidebar import Sidebar
from .theme import THEMES, apply_theme
from .week_view import WeekView

VIEWS = [("day", "Giorno", "D"), ("week", "Settimana", "W"), ("month", "Mese", "M"), ("agenda", "Agenda", "A")]


class MainWindow(QMainWindow):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.current = date.today()
        self.settings = QSettings("Kalendae", "Kalendae")
        self.mode = self.settings.value("view", "week")
        if self.mode not in dict((k, 1) for k, _, _ in VIEWS):
            self.mode = "week"
        self.theme = self.settings.value("theme", "system")
        self._quitting = False
        self.setWindowTitle("Kalendae")
        self.setWindowIcon(app_icon())
        self.resize(1280, 820)

        # ---- viste
        self.views = {
            "day": WeekView(db, days=1),
            "week": WeekView(db, days=7),
            "month": MonthView(db),
            "agenda": AgendaView(db),
        }
        self.stack = QStackedWidget()
        for v in self.views.values():
            self.stack.addWidget(v)
            v.eventClicked.connect(self.open_event)
            if hasattr(v, "createRequested"):
                v.createRequested.connect(self.new_event)
            if hasattr(v, "dayClicked"):
                v.dayClicked.connect(self.go_to_day)
            if hasattr(v, "occurrenceMoved"):
                v.occurrenceMoved.connect(self.move_occurrence)

        self.sidebar = Sidebar(db)
        self.sidebar.dateSelected.connect(self.set_date)
        self.sidebar.calendarsChanged.connect(self.refresh)
        self.sidebar.createRequested.connect(lambda: self.new_event())

        # ---- barra superiore
        top = QWidget()
        top.setObjectName("topbar")
        h = QHBoxLayout(top)
        h.setContentsMargins(12, 8, 12, 8)
        today_btn = QPushButton("Oggi")
        today_btn.clicked.connect(lambda: self.set_date(date.today()))
        prev_btn, next_btn = QToolButton(), QToolButton()
        prev_btn.setText("‹")
        next_btn.setText("›")
        for b, step in ((prev_btn, -1), (next_btn, 1)):
            b.setAutoRaise(True)
            bf = b.font()
            bf.setPointSize(bf.pointSize() + 7)
            b.setFont(bf)
            b.clicked.connect(lambda _=False, s=step: self.navigate(s))
        self.period = QLabel()
        f = self.period.font()
        f.setPointSize(f.pointSize() + 6)
        self.period.setFont(f)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Cerca eventi…")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(280)
        self.search.returnPressed.connect(self.do_search)
        self.search.textChanged.connect(lambda t: None if t else self._clear_search())

        self.view_buttons = QButtonGroup(self)
        seg = QHBoxLayout()
        seg.setSpacing(0)
        for key, label, _ in VIEWS:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setProperty("view", key)
            self.view_buttons.addButton(b)
            seg.addWidget(b)
            b.clicked.connect(lambda _=False, k=key: self.set_mode(k))

        h.addWidget(today_btn)
        h.addWidget(prev_btn)
        h.addWidget(next_btn)
        h.addSpacing(8)
        h.addWidget(self.period)
        h.addStretch()
        h.addWidget(self.search)
        h.addSpacing(12)
        h.addLayout(seg)

        splitter = QSplitter()
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([270, 1010])

        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(top)
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Plain)
        sep.setForegroundRole(QPalette.Mid)
        v.addWidget(sep)
        v.addWidget(splitter, 1)
        self.setCentralWidget(central)

        self._build_menu()
        self._build_tray()
        self.reminders = ReminderService(db, self.tray, self)
        self.reminders.reminderDue.connect(self._reminder_popup)

        # aggiorna a mezzanotte (cambio giorno) e ogni ora
        self._day = date.today()
        self._daily = QTimer(self)
        self._daily.timeout.connect(self._tick)
        self._daily.start(60_000)

        apply_theme(self.theme)
        try:  # segue il sistema quando cambia tema chiaro/scuro
            QGuiApplication.styleHints().colorSchemeChanged.connect(
                lambda _: apply_theme(self.theme) if self.theme == "system" else None)
        except AttributeError:
            pass
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self.set_mode(self.mode)

    # -------------------------------------------------------------- menu
    def _build_menu(self):
        mb = self.menuBar()
        m_file = mb.addMenu("&File")
        self._act(m_file, "Nuovo evento", "Ctrl+N", lambda: self.new_event())
        m_file.addSeparator()
        self._act(m_file, "Importa da file .ics…", "Ctrl+I", self.import_ics)
        self._act(m_file, "Esporta in file .ics…", "Ctrl+E", self.export_ics)
        m_file.addSeparator()
        self._act(m_file, "Stampa…", "Ctrl+P", self.print_preview)
        self._act(m_file, "Esporta in PDF…", "Ctrl+Shift+P", self.export_pdf)
        m_file.addSeparator()
        self._act(m_file, "Esci", "Ctrl+Q", self.quit_app)

        m_view = mb.addMenu("&Visualizza")
        group = QActionGroup(self)
        self.view_actions = {}
        for key, label, sc in VIEWS:
            a = self._act(m_view, label, sc, lambda _=False, k=key: self.set_mode(k))
            a.setCheckable(True)
            group.addAction(a)
            self.view_actions[key] = a
        m_view.addSeparator()
        self._act(m_view, "Oggi", "T", lambda: self.set_date(date.today()))
        self._act(m_view, "Periodo successivo", "J", lambda: self.navigate(1))
        self._act(m_view, "Periodo precedente", "K", lambda: self.navigate(-1))
        self._act(m_view, "Cerca", "Ctrl+F", lambda: (self.search.setFocus(), self.search.selectAll()))
        m_view.addSeparator()
        m_theme = m_view.addMenu("Tema")
        tgroup = QActionGroup(self)
        for key, label in THEMES.items():
            a = QAction(label, self, checkable=True)
            a.setChecked(key == self.theme)
            a.triggered.connect(lambda _=False, k=key: self.set_theme(k))
            tgroup.addAction(a)
            m_theme.addAction(a)

        m_help = mb.addMenu("&Aiuto")
        self._act(m_help, "Scorciatoie da tastiera", "F1", self.show_shortcuts)
        self._act(m_help, "Informazioni su Kalendae", None, self.show_about)

    def _act(self, menu, text, shortcut, slot) -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(slot)
        menu.addAction(a)
        return a

    def _build_tray(self):
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(app_icon(), self)
            self.tray.setToolTip("Kalendae")
            menu = QMenu()
            menu.addAction("Apri Kalendae", self._show_from_tray)
            menu.addAction("Nuovo evento", lambda: (self._show_from_tray(), self.new_event()))
            menu.addSeparator()
            menu.addAction("Esci", self.quit_app)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(
                lambda r: self._show_from_tray() if r == QSystemTrayIcon.Trigger else None)
            self.tray.show()

    # -------------------------------------------------------- navigazione
    def set_theme(self, mode: str):
        self.theme = mode
        self.settings.setValue("theme", mode)
        apply_theme(mode)

    def set_mode(self, mode: str):
        self.mode = mode
        self.settings.setValue("view", mode)
        self.stack.setCurrentWidget(self.views[mode])
        for b in self.view_buttons.buttons():
            b.setChecked(b.property("view") == mode)
        self.view_actions[mode].setChecked(True)
        if mode != "agenda" and self.search.text():
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
            self.views["agenda"].set_query("")
        self.refresh()

    def set_date(self, d: date):
        self.current = d
        self.refresh()

    def go_to_day(self, d: date):
        self.current = d
        self.set_mode("day")

    def navigate(self, step: int):
        if self.mode == "day":
            self.current += timedelta(days=step)
        elif self.mode == "week":
            self.current += timedelta(weeks=step)
        elif self.mode == "month":
            self.current = add_months(self.current, step)
        else:
            self.current += timedelta(days=step * AgendaView.DAYS)
        self.refresh()

    def refresh(self):
        view = self.views[self.mode]
        view.set_date(self.current)
        self.sidebar.set_date(self.current)
        self.period.setText(self._period_text())

    def _period_text(self) -> str:
        d = self.current
        if self.mode == "day":
            return long_date(d)
        if self.mode == "month":
            return f"{MESI[d.month - 1].capitalize()} {d.year}"
        if self.mode == "agenda":
            e = d + timedelta(days=AgendaView.DAYS - 1)
            return f"{d.day} {MESI[d.month - 1]} – {e.day} {MESI[e.month - 1]} {e.year}"
        s = d - timedelta(days=d.weekday())
        e = s + timedelta(days=6)
        if s.month == e.month:
            return f"{s.day} – {e.day} {MESI[s.month - 1]} {s.year}"
        if s.year == e.year:
            return f"{s.day} {MESI[s.month - 1][:3]} – {e.day} {MESI[e.month - 1][:3]} {e.year}"
        return f"{s.day} {MESI[s.month - 1][:3]} {s.year} – {e.day} {MESI[e.month - 1][:3]} {e.year}"

    def do_search(self):
        text = self.search.text().strip()
        if not text:
            return
        self.mode = "agenda"
        self.stack.setCurrentWidget(self.views["agenda"])
        for b in self.view_buttons.buttons():
            b.setChecked(b.property("view") == "agenda")
        self.view_actions["agenda"].setChecked(True)
        self.views["agenda"].set_query(text)
        self.period.setText("Ricerca")

    def _clear_search(self):
        if self.views["agenda"].query:
            self.views["agenda"].set_query("")
            self.refresh()

    def _tick(self):
        if date.today() != self._day:
            self._day = date.today()
            self.setWindowIcon(app_icon())
            if self.tray:
                self.tray.setIcon(app_icon())
            self.refresh()

    # ------------------------------------------------------------ eventi
    def _default_calendar_id(self) -> int:
        cals = self.db.calendars()
        visible = [c for c in cals if c.visible]
        return (visible or cals)[0].id

    def new_event(self, start: datetime | None = None, end: datetime | None = None, all_day: bool = False):
        if start is None:
            # oggi: l'ora piena successiva; altri giorni: alle 9:00
            base = datetime.now() if self.current == date.today() \
                else datetime.combine(self.current, datetime.min.time()).replace(hour=8)
            start = base.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            end = start + timedelta(hours=1)
        ev = Event(None, self._default_calendar_id(), "", start, end, all_day)
        dlg = EventDialog(self.db, ev, self)
        if dlg.exec() and not dlg.deleted:
            self.db.add_event(dlg.result_event())
            self.refresh()

    def open_event(self, occ):
        ev = self.db.get_event(occ.event.id)
        if ev is None:
            return
        is_series = bool(ev.recurrence)
        shown = replace(ev, start=occ.start, end=occ.end) if is_series else ev
        dlg = EventDialog(self.db, shown, self)
        if not dlg.exec():
            return
        if dlg.deleted:
            self._delete(occ, is_series, ev.title)
        else:
            new = dlg.result_event()
            if is_series:
                if new == shown:
                    return
                scope = ScopeDialog.ask("Modifica evento ricorrente", self)
                if scope is None:
                    return
                series.edit_occurrence(self.db, occ, new, scope)
            else:
                self.db.update_event(new)
        self.refresh()
        if self.views["agenda"].query:
            self.views["agenda"].refresh()

    def move_occurrence(self, occ, new_start: datetime, new_end: datetime):
        """Chiamato quando un evento viene trascinato nella griglia oraria."""
        ev = self.db.get_event(occ.event.id)
        if ev is None:
            return
        scope = series.ALL
        if ev.recurrence:
            scope = ScopeDialog.ask("Sposta evento ricorrente", self)
            if scope is None:
                self.refresh()  # annulla: l'evento torna al suo posto
                return
        series.edit_occurrence(self.db, occ, replace(ev, start=new_start, end=new_end), scope)
        self.refresh()

    def _delete(self, occ, is_series: bool, title: str):
        if is_series:
            scope = ScopeDialog.ask("Elimina evento ricorrente", self)
            if scope is not None:
                series.delete_occurrence(self.db, occ, scope)
        elif QMessageBox.question(self, "Elimina evento", f"Eliminare «{title}»?") == QMessageBox.Yes:
            self.db.delete_event(occ.event.id)

    def _reminder_popup(self, occ):
        QApplication.beep()
        if self.tray is None or not self.tray.isVisible():
            box = QMessageBox(QMessageBox.Information, "Promemoria",
                              f"<b>{occ.event.title}</b><br>{time_range(occ)}"
                              + (f"<br>{occ.event.location}" if occ.event.location else ""),
                              QMessageBox.Ok, self)
            box.setWindowModality(Qt.NonModal)
            box.show()

    # -------------------------------------------------------- import/export
    def import_ics(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importa calendario", "", "iCalendar (*.ics);;Tutti i file (*)")
        if not path:
            return
        cals = self.db.calendars()
        name, ok = QInputDialog.getItem(self, "Importa", "Importa nel calendario:",
                                        [c.name for c in cals], 0, False)
        if not ok:
            return
        cal = next(c for c in cals if c.name == name)
        try:
            added, skipped = import_into(self.db, path, cal.id)
        except Exception as exc:  # file malformato
            QMessageBox.critical(self, "Importazione non riuscita", f"Impossibile leggere il file:\n{exc}")
            return
        self.refresh()
        msg = f"Importati {added} eventi in «{cal.name}»."
        if skipped:
            msg += f"\n{skipped} erano già presenti e sono stati saltati."
        QMessageBox.information(self, "Importazione completata", msg)

    def export_ics(self):
        path, _ = QFileDialog.getSaveFileName(self, "Esporta calendario", "kalendae.ics", "iCalendar (*.ics)")
        if not path:
            return
        if not path.lower().endswith(".ics"):
            path += ".ics"
        ids = [c.id for c in self.db.calendars() if c.visible]
        n = export_ics(self.db.all_events(ids), path)
        QMessageBox.information(self, "Esportazione completata",
                                f"Esportati {n} eventi dei calendari visibili in:\n{path}")

    # ---------------------------------------------------------------- stampa
    def _print_args(self):
        mode = self.mode if not self.views["agenda"].query else "agenda"
        return mode, self.current, self._period_text()

    def _make_printer(self, mode) -> QPrinter:
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageOrientation(printing.orientation_for(mode))
        printer.setDocName(f"Kalendae - {self._period_text()}")
        return printer

    def print_preview(self):
        mode, d, title = self._print_args()
        printer = self._make_printer(mode)
        dlg = QPrintPreviewDialog(printer, self)
        dlg.setWindowTitle("Anteprima di stampa")
        dlg.paintRequested.connect(lambda pr: printing.render(pr, self.db, mode, d, title))
        dlg.resize(1100, 800)
        dlg.exec()

    def export_pdf(self):
        mode, d, title = self._print_args()
        name = f"Kalendae {title}.pdf".replace("/", "-")
        path, _ = QFileDialog.getSaveFileName(self, "Esporta in PDF", name, "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        printer = self._make_printer(mode)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(path)
        printing.render(printer, self.db, mode, d, title)
        self.statusBar().showMessage(f"PDF salvato in {path}", 6000)

    # ---------------------------------------------------------------- aiuto
    def show_shortcuts(self):
        QMessageBox.information(self, "Scorciatoie da tastiera", (
            "<table cellpadding=3>"
            "<tr><td><b>Ctrl+N</b></td><td>Nuovo evento</td></tr>"
            "<tr><td><b>D / W / M / A</b></td><td>Giorno / Settimana / Mese / Agenda</td></tr>"
            "<tr><td><b>T</b></td><td>Vai a oggi</td></tr>"
            "<tr><td><b>J / K</b></td><td>Periodo successivo / precedente</td></tr>"
            "<tr><td><b>Ctrl+F</b></td><td>Cerca</td></tr>"
            "<tr><td><b>Ctrl+I / Ctrl+E</b></td><td>Importa / Esporta .ics</td></tr>"
            "<tr><td><b>Ctrl+P</b></td><td>Stampa (con anteprima)</td></tr>"
            "</table><br>Nella griglia oraria: trascina su uno spazio vuoto per creare un evento, "
            "trascina un evento per spostarlo, trascina il bordo inferiore per cambiarne la durata."))

    def show_about(self):
        QMessageBox.about(self, "Informazioni su Kalendae", (
            f"<h3>Kalendae {__version__}</h3>"
            "<p>Calendario libero e open source, scritto in Python con Qt (PySide6).</p>"
            "<p>Le <i>Kalendae</i> (calende) erano il primo giorno di ogni mese nel calendario romano: da qui viene la parola «calendario».</p>"
            f"<p>Dati salvati in:<br><code>{self.db.path}</code></p>"))

    # ------------------------------------------------------------ chiusura
    def _show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):
        self.settings.setValue("geometry", self.saveGeometry())
        if self.tray is not None and not self._quitting:
            e.ignore()
            self.hide()
            if not getattr(self, "_told", False):
                self.tray.showMessage("Kalendae", "Kalendae resta attivo nell'area di notifica per i promemoria.",
                                      QSystemTrayIcon.Information, 5000)
                self._told = True
            return
        e.accept()

    def quit_app(self):
        self._quitting = True
        if self.tray:
            self.tray.hide()
        QApplication.quit()
