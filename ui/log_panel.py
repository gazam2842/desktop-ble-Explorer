"""Log panel filterable by source (scanner/device)."""

from collections import deque
from datetime import datetime

from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget,
)

_ALL = "All"
MAX_LINES = 5000


class LogPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._lines: deque[tuple[str, str]] = deque(maxlen=MAX_LINES)  # (source, line)

        self._filter = QComboBox()
        self._filter.addItem(_ALL)
        self._filter.currentTextChanged.connect(self._rebuild)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_log)
        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self._on_export)

        header = QHBoxLayout()
        header.addWidget(QLabel("Log"))
        header.addStretch()
        header.addWidget(self._filter)
        header.addWidget(export_btn)
        header.addWidget(clear_btn)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(MAX_LINES)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(header)
        layout.addWidget(self._text)

    def add_source(self, source: str) -> None:
        if self._filter.findText(source) < 0:
            self._filter.addItem(source)

    def remove_source(self, source: str) -> None:
        idx = self._filter.findText(source)
        if idx > 0:  # _ALL cannot be removed
            if self._filter.currentIndex() == idx:
                self._filter.setCurrentIndex(0)
            self._filter.removeItem(idx)

    def append_line(self, source: str, text: str) -> None:
        self._lines.append((source, text))
        current = self._filter.currentText()
        if current == _ALL or current == source:
            self._text.appendPlainText(f"[{source}] {text}")

    def clear_log(self) -> None:
        self._lines.clear()
        self._text.clear()

    def _on_export(self) -> None:
        """Save the log to a text file based on the current filter."""
        selected = self._filter.currentText()
        default_name = f"ble_log_{datetime.now():%Y%m%d_%H%M%S}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Log", default_name, "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        lines = [
            f"[{source}] {text}"
            for source, text in self._lines
            if selected == _ALL or selected == source
        ]
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + ("\n" if lines else ""))
        except OSError as exc:
            self.append_line(_ALL, f"[Error] Log export failed: {exc}")

    def _rebuild(self, selected: str) -> None:
        self._text.clear()
        for source, text in self._lines:
            if selected == _ALL or selected == source:
                self._text.appendPlainText(f"[{source}] {text}")
