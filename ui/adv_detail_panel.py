"""Accordion detail panel for the selected device's advertisement packet (scanner tab)."""

import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from ble.adv_decode import AdvInfo
from ble.uuid_names import format_uuid, resolve_name

_REBUILD_MIN_INTERVAL = 0.5  # Minimum interval between rebuilds for updates to the same device (seconds)


def _hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


class _Section(QFrame):
    """Collapsible section. Collapsed state is stored in the panel's shared dict."""

    def __init__(self, key: str, title: str, subtitle: str,
                 collapsed_map: dict[str, bool]) -> None:
        super().__init__()
        self.setObjectName("AdvSection")
        self._key = key
        self._map = collapsed_map

        self._arrow = QLabel()
        title_label = QLabel(title)
        title_label.setObjectName("AdvSectionTitle")
        sub = QLabel(subtitle)
        sub.setObjectName("UuidLabel")
        header = QHBoxLayout()
        header.addWidget(self._arrow)
        header.addWidget(title_label)
        header.addWidget(sub)
        header.addStretch()
        self._header = QWidget()
        self._header.setObjectName("AdvSectionHeader")
        self._header.setLayout(header)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.mousePressEvent = self._toggle  # type: ignore[method-assign]

        self._body = QWidget()
        self.body_layout = QVBoxLayout(self._body)
        self.body_layout.setContentsMargins(20, 2, 8, 6)
        self.body_layout.setSpacing(2)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 4, 8, 4)
        outer.setSpacing(2)
        outer.addWidget(self._header)
        outer.addWidget(self._body)
        self._apply()

    def _toggle(self, _event) -> None:
        self._map[self._key] = not self._map.get(self._key, False)
        self._apply()

    def _apply(self) -> None:
        collapsed = self._map.get(self._key, False)
        self._body.setVisible(not collapsed)
        self._arrow.setText("▸" if collapsed else "▾")

    def add_kv(self, key: str, value: str) -> None:
        row = QHBoxLayout()
        k = QLabel(key)
        k.setObjectName("AdvFieldName")
        k.setMinimumWidth(110)
        k.setAlignment(Qt.AlignmentFlag.AlignTop)
        v = QLabel(value)
        v.setObjectName("AdvFieldValue")
        v.setWordWrap(True)
        v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(k)
        row.addWidget(v, stretch=1)
        self.body_layout.addLayout(row)

    def add_line(self, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("AdvFieldValue")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body_layout.addWidget(label)


class AdvDetailPanel(QScrollArea):
    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self._aliases: dict[str, str] = {}
        self._collapsed: dict[str, bool] = {}  # section key → collapsed (persists across device switches)
        self._current_address: str | None = None
        self._last_rebuild = 0.0

        self._host = QWidget()
        self._layout = QVBoxLayout(self._host)
        self._title = QLabel("(Select a device)")
        self._title.setObjectName("DeviceTitle")
        self._timing = QLabel("")
        self._timing.setObjectName("UuidLabel")
        self._layout.addWidget(self._title)
        self._layout.addWidget(self._timing)
        self._sections_host = QVBoxLayout()
        self._layout.addLayout(self._sections_host)
        self._layout.addStretch()
        self.setWidget(self._host)
        self._sections: list[_Section] = []

    def set_aliases(self, aliases: dict[str, str]) -> None:
        self._aliases = aliases

    def show_device(self, name: str, address: str, rssi: int, info: object) -> None:
        now = time.monotonic()
        same_device = address == self._current_address
        # Throttle frequent advertisement updates for the same device to 0.5s (prevents flicker)
        if same_device and now - self._last_rebuild < _REBUILD_MIN_INTERVAL:
            return
        self._current_address = address
        self._last_rebuild = now

        self._title.setText(f"{name}  ·  {address}  ·  {rssi} dBm")
        if not isinstance(info, AdvInfo):
            self._timing.setText("")
            self._clear_sections()
            return

        timing_parts = []
        if info.interval_ms:
            timing_parts.append(f"interval ≈{info.interval_ms:.0f}ms")
        timing_parts.append(f"RX {info.count}")
        if info.parsed.tx_power is not None:
            timing_parts.append(f"TX Power {info.parsed.tx_power} dBm")
        self._timing.setText("  ·  ".join(timing_parts))

        scroll_pos = self.verticalScrollBar().value()
        self._clear_sections()
        self._build_sections(info)
        self.verticalScrollBar().setValue(scroll_pos)

    def _build_sections(self, info: AdvInfo) -> None:
        mfr_fields = [f for f in info.fields if f.ad_type == 0xFF]
        sd_fields = [f for f in info.fields if f.ad_type in (0x16, 0x20, 0x21)]

        for i, f in enumerate(mfr_fields):
            sec = self._add_section(f"mfr{i}", "Manufacturer Data", f.summary)
            for k, v in f.details:
                sec.add_kv(k, v)

        if info.fields:
            badge = " (reconstructed)" if any(f.reconstructed for f in info.fields) else ""
            sec = self._add_section("raw", "AD Structure (Raw)" + badge,
                                    f"{len(info.fields)} fields")
            for f in info.fields:
                sec.add_line(f"[0x{f.ad_type:02X}] {f.type_name}  —  "
                             f"{_hex(f.data)}\n      {f.summary}")

        if info.parsed.service_uuids:
            sec = self._add_section("services", "Services",
                                    f"{len(info.parsed.service_uuids)}")
            for uuid in info.parsed.service_uuids:
                named = resolve_name(uuid, self._aliases)
                label = f"{named[0]} ({format_uuid(uuid)})" if named \
                    else format_uuid(uuid)
                sec.add_line(label)

        for i, f in enumerate(sd_fields):
            sec = self._add_section(f"sd{i}", "Service Data", f.summary)
            for k, v in f.details:
                sec.add_kv(k, v)

    def _add_section(self, key: str, title: str, subtitle: str) -> _Section:
        sec = _Section(key, title, subtitle, self._collapsed)
        self._sections.append(sec)
        self._sections_host.addWidget(sec)
        return sec

    def _clear_sections(self) -> None:
        for sec in self._sections:
            sec.deleteLater()
        self._sections.clear()

    def clear_device(self) -> None:
        self._current_address = None
        self._title.setText("(Select a device)")
        self._timing.setText("")
        self._clear_sections()
