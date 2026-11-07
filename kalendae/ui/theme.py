"""Tema chiaro / scuro / come il sistema."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

THEMES = {"system": "Come il sistema", "light": "Chiaro", "dark": "Scuro"}


def dark_palette() -> QPalette:
    p = QPalette()
    c = QColor
    roles = {
        QPalette.Window: c("#202124"),
        QPalette.WindowText: c("#e8eaed"),
        QPalette.Base: c("#1b1c1f"),
        QPalette.AlternateBase: c("#25262a"),
        QPalette.ToolTipBase: c("#303134"),
        QPalette.ToolTipText: c("#e8eaed"),
        QPalette.PlaceholderText: c("#9aa0a6"),
        QPalette.Text: c("#e8eaed"),
        QPalette.Button: c("#2d2e31"),
        QPalette.ButtonText: c("#e8eaed"),
        QPalette.BrightText: c("#ff6e6e"),
        QPalette.Light: c("#3c4043"),
        QPalette.Midlight: c("#33353a"),
        QPalette.Mid: c("#4a4d52"),
        QPalette.Dark: c("#151618"),
        QPalette.Shadow: c("#000000"),
        QPalette.Highlight: c("#1a73e8"),
        QPalette.HighlightedText: c("#ffffff"),
        QPalette.Link: c("#8ab4f8"),
        QPalette.LinkVisited: c("#c58af9"),
    }
    for role, color in roles.items():
        p.setColor(role, color)
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, c("#6f7378"))
    return p


def system_is_dark() -> bool:
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # Qt < 6.5
        return False


def is_dark(mode: str) -> bool:
    return mode == "dark" or (mode == "system" and system_is_dark())


def apply_theme(mode: str) -> None:
    app = QApplication.instance()
    app.setPalette(dark_palette() if is_dark(mode) else app.style().standardPalette())
    for w in app.allWidgets():  # i widget disegnati a mano si ridisegnano con i nuovi colori
        w.update()
