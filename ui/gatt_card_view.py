"""GATT view with service cards + characteristic rows (collapsed/expanded)."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QMenu, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ble.char_parsers import has_parser, parse_value
from ble.codec import InvalidFormatError, decode, encode
from ble.uuid_names import AliasStore, format_uuid, normalize, resolve_name

# properties value → chip label
_PROP_LABELS = {
    "read": "Read",
    "write": "Write",
    "write-without-response": "WriteNR",
    "notify": "Notify",
    "indicate": "Indicate",
}


def _display_name(uuid: str, aliases: dict[str, str], fallback: str) -> str:
    named = resolve_name(uuid, aliases)
    return named[0] if named else fallback


def _uuid_menu(widget, event, uuid: str, on_alias) -> None:
    """Context menu for copying UUID + setting alias (shared by ServiceCard/CharRow)."""
    menu = QMenu(widget)
    copy_action = menu.addAction("Copy UUID")
    alias_action = menu.addAction("Set Alias…")
    chosen = menu.exec(event.globalPos())
    if chosen == copy_action:
        QApplication.clipboard().setText(normalize(uuid))
    elif chosen == alias_action:
        on_alias(uuid)


class CharRow(QFrame):
    """A single characteristic — collapsed (summary) / expanded (control area)."""

    read_requested = pyqtSignal(str)
    write_requested = pyqtSignal(str, bytes, list)
    notify_toggled = pyqtSignal(str, bool)
    invalid_input = pyqtSignal(str)
    alias_edit_requested = pyqtSignal(str)

    def __init__(self, uuid: str, properties: list[str], alias_store: AliasStore) -> None:
        super().__init__()
        self.setObjectName("CharRow")
        self.uuid = uuid
        self._properties = properties
        self._store = alias_store
        self._last_value: bytes | None = None
        self._expanded = False
        self._build()
        self._set_expanded(False)

    # ---- Setup ----
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 4, 8, 4)
        outer.setSpacing(4)

        # Header (click to collapse/expand)
        self._arrow = QLabel("▸")
        self._name = QLabel()
        self._name.setObjectName("CharName")
        self._uuid_label = QLabel(format_uuid(self.uuid))
        self._uuid_label.setObjectName("UuidLabel")
        self._uuid_label.setToolTip(normalize(self.uuid))  # Allow checking the full UUID even when abbreviated
        self._summary = QLabel("")
        self._summary.setObjectName("ValueLabel")
        self._summary.hide()

        self._can_read = "read" in self._properties
        self._can_write = (
            "write" in self._properties or "write-without-response" in self._properties
        )
        self._can_notify = "notify" in self._properties or "indicate" in self._properties

        header = QHBoxLayout()
        header.addWidget(self._arrow)
        header.addWidget(self._name)
        header.addWidget(self._uuid_label)
        header.addStretch()
        header.addWidget(self._summary)
        for prop in self._properties:
            if prop in ("notify", "indicate"):
                continue  # Shown as a play/pause toggle button instead of a chip
            label = _PROP_LABELS.get(prop)
            if label:
                chip = QLabel(label)
                chip.setObjectName("PropChip")
                header.addWidget(chip)
        if self._can_notify:
            self._notify_btn = QPushButton("▶")
            self._notify_btn.setObjectName("NotifyToggle")
            self._notify_btn.setCheckable(True)
            self._notify_btn.setFixedSize(26, 22)
            self._notify_btn.setToolTip("Start/stop Notify subscription")
            self._notify_btn.toggled.connect(self._on_notify_toggled)
            header.addWidget(self._notify_btn)
        else:
            self._notify_btn = None
        self._header_widget = QWidget()
        self._header_widget.setLayout(header)
        self._header_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header_widget.mousePressEvent = self._on_header_click  # type: ignore[method-assign]
        outer.addWidget(self._header_widget)

        # Expanded area
        self._body = QWidget()
        body = QVBoxLayout(self._body)
        body.setContentsMargins(20, 0, 0, 4)
        body.setSpacing(4)

        # Value display + format + Read
        self._fmt = QComboBox()
        formats = (["parsed"] if has_parser(self.uuid) else []) + ["hex", "string", "byte"]
        self._fmt.addItems(formats)
        self._fmt.currentTextChanged.connect(self._refresh_value)
        self._value = QLineEdit()
        self._value.setReadOnly(True)
        value_row = QHBoxLayout()
        value_row.addWidget(QLabel("Value:"))
        value_row.addWidget(self._value, stretch=1)
        value_row.addWidget(self._fmt)
        if self._can_read:
            read_btn = QPushButton("Read")
            read_btn.clicked.connect(lambda: self.read_requested.emit(self.uuid))
            value_row.addWidget(read_btn)
        body.addLayout(value_row)

        # Write
        if self._can_write:
            self._input = QLineEdit()
            self._input.setPlaceholderText("Value to write (current format; parsed is interpreted as hex)")
            write_btn = QPushButton("Write")
            write_btn.clicked.connect(self._on_write)
            write_row = QHBoxLayout()
            write_row.addWidget(QLabel("Input:"))
            write_row.addWidget(self._input, stretch=1)
            write_row.addWidget(write_btn)
            body.addLayout(write_row)

        outer.addWidget(self._body)
        self.refresh_name()

    # ---- Display ----
    def refresh_name(self) -> None:
        self._name.setText(_display_name(self.uuid, self._store.aliases, "Unknown Characteristic"))

    def _format_bytes(self, data: bytes) -> str:
        fmt = self._fmt.currentText()
        if fmt == "parsed":
            parsed = parse_value(self.uuid, data)
            hex_str = decode(data, "hex")
            return f"{parsed} ({hex_str})" if parsed is not None else hex_str
        return decode(data, fmt)

    def _refresh_value(self) -> None:
        if self._last_value is None:
            return
        text = self._format_bytes(self._last_value)
        self._value.setText(text)
        self._summary.setText(text)
        self._summary.setVisible(not self._expanded)

    def show_value(self, data: bytes) -> None:
        self._last_value = bytes(data)
        self._refresh_value()

    def push_notify(self, data: bytes, _ts: str) -> None:
        # Only show the latest notify value (history is available in the log panel)
        self.show_value(data)

    def reset_notify_state(self) -> None:
        """Reset only the subscribe button on disconnect (does not emit a signal)."""
        if self._notify_btn is not None:
            self._notify_btn.blockSignals(True)
            self._notify_btn.setChecked(False)
            self._notify_btn.blockSignals(False)
            self._notify_btn.setText("▶")

    # ---- Actions ----
    def _on_header_click(self, _event) -> None:
        expanding = not self._expanded
        self._set_expanded(expanding)
        # For readable characteristics, read immediately upon expanding
        if expanding and self._can_read:
            self.read_requested.emit(self.uuid)

    def _set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self._body.setVisible(expanded)
        self._arrow.setText("▾" if expanded else "▸")
        self._summary.setVisible(not expanded and self._last_value is not None)
        # For the QSS [expanded="true"] selector
        self.setProperty("expanded", "true" if expanded else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def _on_write(self) -> None:
        fmt = self._fmt.currentText()
        if fmt == "parsed":
            fmt = "hex"  # Writing only supports raw formats
        try:
            data = encode(self._input.text(), fmt)
        except InvalidFormatError as exc:
            self.invalid_input.emit(str(exc))
            return
        self.write_requested.emit(self.uuid, data, self._properties)

    def _on_notify_toggled(self, checked: bool) -> None:
        self._notify_btn.setText("⏸" if checked else "▶")
        self.notify_toggled.emit(self.uuid, checked)

    def contextMenuEvent(self, event) -> None:
        _uuid_menu(self, event, self.uuid, self.alias_edit_requested.emit)


class ServiceCard(QFrame):
    alias_edit_requested = pyqtSignal(str)

    def __init__(self, uuid: str, alias_store: AliasStore) -> None:
        super().__init__()
        self.setObjectName("ServiceCard")
        self.uuid = uuid
        self._store = alias_store
        self.rows: list[CharRow] = []

        self._name = QLabel()
        self._name.setObjectName("ServiceName")
        uuid_label = QLabel(format_uuid(uuid))
        uuid_label.setObjectName("UuidLabel")
        uuid_label.setToolTip(normalize(uuid))  # Allow checking the full UUID even when abbreviated

        header = QHBoxLayout()
        header.addWidget(self._name)
        header.addWidget(uuid_label)
        header.addStretch()
        header_widget = QWidget()
        header_widget.setObjectName("ServiceCardHeader")
        header_widget.setLayout(header)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 8, 10, 8)
        self._layout.setSpacing(0)
        self._layout.addWidget(header_widget)
        self.refresh_name()

    def add_row(self, row: CharRow) -> None:
        self.rows.append(row)
        self._layout.addWidget(row)

    def refresh_name(self) -> None:
        self._name.setText(_display_name(self.uuid, self._store.aliases, "Unknown Service"))

    def contextMenuEvent(self, event) -> None:
        _uuid_menu(self, event, self.uuid, self.alias_edit_requested.emit)


class GattCardView(QScrollArea):
    """Scrollable container of service cards. 1:1 with a single session."""

    read_requested = pyqtSignal(str)
    write_requested = pyqtSignal(str, bytes, list)
    notify_toggled = pyqtSignal(str, bool)
    invalid_input = pyqtSignal(str)

    def __init__(self, alias_store: AliasStore) -> None:
        super().__init__()
        self._store = alias_store
        self.setWidgetResizable(True)
        self._cards: list[ServiceCard] = []
        self._rows: dict[str, list[CharRow]] = {}  # char uuid → rows (handles duplicate uuids)
        self._host = QWidget()
        self._host_layout = QVBoxLayout(self._host)
        self._host_layout.setSpacing(8)
        self._host_layout.addStretch()
        self.setWidget(self._host)

    def populate(self, services: list) -> None:
        self.clear_view()
        for service in services:
            card = ServiceCard(service["uuid"], self._store)
            card.alias_edit_requested.connect(self._edit_alias)
            for ch in service["chars"]:
                row = CharRow(ch["uuid"], ch["properties"], self._store)
                row.read_requested.connect(self.read_requested)
                row.write_requested.connect(self.write_requested)
                row.notify_toggled.connect(self.notify_toggled)
                row.invalid_input.connect(self.invalid_input)
                row.alias_edit_requested.connect(self._edit_alias)
                card.add_row(row)
                self._rows.setdefault(ch["uuid"], []).append(row)
            self._cards.append(card)
            self._host_layout.insertWidget(self._host_layout.count() - 1, card)

    def clear_view(self) -> None:
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()
        self._rows.clear()

    def display_read(self, uuid: str, data: bytes) -> None:
        for row in self._rows.get(uuid, []):
            row.show_value(data)

    def push_notify(self, uuid: str, data: bytes, ts: str) -> None:
        for row in self._rows.get(uuid, []):
            row.push_notify(data, ts)

    def reset_notify_states(self) -> None:
        for rows in self._rows.values():
            for row in rows:
                row.reset_notify_state()

    def _edit_alias(self, uuid: str) -> None:
        current = self._store.get(uuid) or ""
        name, ok = QInputDialog.getText(
            self, "Set Alias", f"Alias for {format_uuid(uuid)}:", text=current
        )
        if not ok:
            return
        if name.strip():
            self._store.set(uuid, name.strip())
        else:
            self._store.remove(uuid)
        for card in self._cards:
            card.refresh_name()
            for row in card.rows:
                row.refresh_name()
