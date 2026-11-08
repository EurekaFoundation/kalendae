"""Avvio: python -m kalendae  (opzionale: --db percorso/file.db)"""
import argparse
import sys

from PySide6.QtCore import QByteArray, QLocale, QSettings

from eureka_core import EurekaApp

from . import __version__
from .database import Database
from .ui.main_window import MainWindow
from .utils import app_icon


def migrate_old_settings(app: EurekaApp) -> None:
    """Una sola volta: porta le impostazioni delle versioni ≤ 0.2 (QSettings) in Eureka Suite."""
    if app.settings.app.get("migrated_from_qsettings"):
        return
    old = QSettings("Kalendae", "Kalendae")
    if old.contains("view"):
        app.settings.app["view"] = old.value("view")
    geo = old.value("geometry")
    if isinstance(geo, QByteArray) and not geo.isEmpty():
        app.settings.app["geometry"] = bytes(geo.toBase64()).decode("ascii")
    # Il tema ora è comune a tutta la suite: lo importiamo solo se non è già stato scelto.
    theme = old.value("theme")
    if theme in ("light", "dark") and app.settings.suite.get("theme") == "system":
        app.apply_theme(theme)
    app.settings.app["migrated_from_qsettings"] = True
    app.settings.save()


def main():
    parser = argparse.ArgumentParser(prog="kalendae", description="Kalendae, calendario open source")
    parser.add_argument("--db", help="percorso di un database alternativo")
    args, qt_args = parser.parse_known_args()

    app = EurekaApp(
        "kalendae",
        version=__version__,
        argv=[sys.argv[0], *qt_args],
        app_defaults={"view": "week"},
    )
    app.setApplicationDisplayName("Kalendae")
    app.setDesktopFileName("kalendae")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)  # resta attivo nell'area di notifica
    QLocale.setDefault(QLocale(QLocale.Italian, QLocale.Italy))
    migrate_old_settings(app)

    db = Database(args.db)
    win = MainWindow(db)
    if win.tray is None:
        app.setQuitOnLastWindowClosed(True)
    win.show()
    app.check_updates_later(win)
    code = app.exec()
    db.close()
    sys.exit(code)


if __name__ == "__main__":
    main()
