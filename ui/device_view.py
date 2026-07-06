"""Content of a single device tab — header (status/reconnect/disconnect) + GATT card view. 1:1 with a session."""

import asyncio

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ble.conn_params import format_conn_params
from ble.session import DeviceSession
from ble.uuid_names import AliasStore
from ui.gatt_card_view import GattCardView


class DeviceView(QWidget):
    def __init__(self, session: DeviceSession, alias_store: AliasStore) -> None:
        super().__init__()
        self._session = session

        title = QLabel(session.name)
        title.setObjectName("DeviceTitle")
        address = QLabel(session.address)
        address.setObjectName("UuidLabel")
        self._status = QLabel("Connecting…")
        self._status.setObjectName("DeviceStatus")
        self._reconnect_btn = QPushButton("Reconnect")
        self._reconnect_btn.hide()
        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setEnabled(False)

        header = QHBoxLayout()
        header.addWidget(title)
        header.addWidget(address)
        header.addWidget(self._status)
        header.addStretch()
        header.addWidget(self._reconnect_btn)
        header.addWidget(self._disconnect_btn)

        self._params_label = QLabel("")
        self._params_label.setObjectName("UuidLabel")

        self.gatt = GattCardView(alias_store)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self._params_label)
        layout.addWidget(self.gatt)

        self._wire()

    def _run(self, coro) -> None:
        asyncio.ensure_future(coro)

    def _wire(self) -> None:
        s = self._session
        # Button → session
        self._reconnect_btn.clicked.connect(self._on_reconnect)
        self._disconnect_btn.clicked.connect(lambda: self._run(s.disconnect()))
        # GATT view → session
        self.gatt.read_requested.connect(lambda u: self._run(s.read_char(u)))
        self.gatt.write_requested.connect(
            lambda u, d, p: self._run(s.write_char(u, d, p))
        )
        self.gatt.notify_toggled.connect(lambda u, en: self._run(s.set_notify(u, en)))
        # Session → view
        s.connected.connect(self._on_connected)
        s.disconnected.connect(self._on_disconnected)
        s.read_result.connect(self.gatt.display_read)
        s.notify_value.connect(self.gatt.push_notify)
        s.conn_params_changed.connect(self._on_conn_params)

    def _set_status(self, text: str, state: str) -> None:
        self._status.setText(text)
        self._status.setProperty("state", state)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _on_reconnect(self) -> None:
        self._set_status("Connecting…", "")
        self._reconnect_btn.hide()
        self._run(self._session.connect())

    def _on_connected(self, services: list) -> None:
        self._set_status("Connected", "connected")
        self._reconnect_btn.hide()
        self._disconnect_btn.setEnabled(True)
        self.gatt.populate(services)

    def _on_conn_params(self, params: object) -> None:
        self._params_label.setText(format_conn_params(params))

    def _on_disconnected(self, reason: str) -> None:
        self._set_status(f"Disconnected ({reason})", "disconnected")
        self._params_label.setText("")
        self._reconnect_btn.show()
        self._disconnect_btn.setEnabled(False)
        self.gatt.reset_notify_states()
