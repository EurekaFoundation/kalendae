"""Avvio: python -m kalendae  (opzionale: --db percorso/file.db)"""
import argparse
import sys

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication

from .database import Database
from .ui.main_window import MainWindow
from .utils import app_icon


def main():
    parser = argparse.ArgumentParser(prog="kalendae", description="Kalendae, calendario open source")
    parser.add_argument("--db", help="percorso di un database alternativo")
    args, qt_args = parser.parse_known_args()

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("Kalendae")
    app.setApplicationDisplayName("Kalendae")
    app.setDesktopFileName("kalendae")
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)  # resta attivo nell'area di notifica
    QLocale.setDefault(QLocale(QLocale.Italian, QLocale.Italy))

    db = Database(args.db)
    win = MainWindow(db)
    if win.tray is None:
        app.setQuitOnLastWindowClosed(True)
    win.show()
    code = app.exec()
    db.close()
    sys.exit(code)


if __name__ == "__main__":
    main()
