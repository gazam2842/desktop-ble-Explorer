"""Apply theme (QSS) + persist via QSettings."""

from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

_THEME_DIR = Path(__file__).resolve().parent / "theme"
THEMES = ("dark", "light")


def _settings() -> QSettings:
    return QSettings("BLEExplorer", "ble_explorer")


def saved_theme() -> str:
    value = str(_settings().value("theme", "dark"))
    return value if value in THEMES else "dark"


def apply_theme(app: QApplication, name: str) -> None:
    qss = (_THEME_DIR / f"{name}.qss").read_text(encoding="utf-8")
    app.setStyleSheet(qss)
    _settings().setValue("theme", name)
