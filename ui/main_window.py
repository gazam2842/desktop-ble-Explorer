"""Tab-based main window — scanner tab + N device tabs + global log + theme toggle."""

import asyncio

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QLineEdit, QMainWindow,
    QPushButton, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from ble.uuid_names import AliasStore
from controller import Controller
from ui.adv_detail_panel import AdvDetailPanel
from ui.device_list import DeviceList
from ui.device_view import DeviceView
from ui.log_panel import LogPanel
from ui.theme import apply_theme, saved_theme
from version import __version__

# Combo label → device_filter scope value
_SCOPE_MAP = {"Both": "both", "Name": "name", "MAC": "mac"}

_SCANNER_SOURCE = "Scanner"


class MainWindow(QMainWindow):
    def __init__(self, controller: Controller, alias_store: AliasStore) -> None:
        super().__init__()
        self._controller = controller
        self._aliases = alias_store
        self._device_tabs: dict[str, DeviceView] = {}  # address → view
        self._tab_sources: dict[str, str] = {}         # address → log source name
        self.setWindowTitle(f"BLE Explorer v{__version__}")
        self.resize(1100, 760)
        self._build()
        self._wire()

    # ---- Setup ----
    def _build(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.addTab(self._build_scanner_page(), _SCANNER_SOURCE)
        # Remove close button from scanner tab
        self._tabs.tabBar().setTabButton(0, self._tabs.tabBar().ButtonPosition.RightSide, None)

        self._log_panel = LogPanel()
        self._log_panel.add_source(_SCANNER_SOURCE)

        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self._tabs)
        split.addWidget(self._log_panel)
        split.setSizes([560, 200])
        self.setCentralWidget(split)
        self.statusBar().showMessage("Ready")

    def _build_scanner_page(self) -> QWidget:
        self._scan_btn = QPushButton("Start Scan")
        self._scan_btn.setCheckable(True)
        self._theme_btn = QPushButton("Light Theme" if saved_theme() == "dark" else "Dark Theme")
        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("Search name / MAC")
        self._filter_scope = QComboBox()
        self._filter_scope.addItems(["Both", "Name", "MAC"])

        top = QHBoxLayout()
        top.addWidget(self._scan_btn)
        top.addWidget(self._filter_input, stretch=1)
        top.addWidget(self._filter_scope)
        top.addStretch()
        top.addWidget(self._theme_btn)

        self._device_list = DeviceList()
        self._adv_panel = AdvDetailPanel()
        self._adv_panel.set_aliases(self._aliases.aliases)

        body = QSplitter(Qt.Orientation.Horizontal)
        body.addWidget(self._device_list)
        body.addWidget(self._adv_panel)
        body.setSizes([550, 450])

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addLayout(top)
        layout.addWidget(body)
        return page

    def _run(self, coro) -> None:
        """Run an async method on the qasync event loop."""
        asyncio.ensure_future(coro)

    # ---- Wiring ----
    def _wire(self) -> None:
        c = self._controller
        # Scanner tab
        self._scan_btn.toggled.connect(self._on_scan_toggled)
        self._theme_btn.clicked.connect(self._on_theme_toggle)
        self._filter_input.textChanged.connect(self._on_filter_changed)
        self._filter_scope.currentTextChanged.connect(self._on_filter_changed)
        self._device_list.device_selected.connect(self._on_device_selected)
        self._device_list.connect_requested.connect(self._open_device)
        # Tab close
        self._tabs.tabCloseRequested.connect(self._on_tab_close)
        # controller → UI
        c.device_found.connect(self._on_device_found)
        c.scan_state_changed.connect(self._on_scan_state)
        c.session_opened.connect(self._on_session_opened)
        c.session_closed.connect(self._on_session_closed)
        c.log.connect(lambda t: self._log_panel.append_line(_SCANNER_SOURCE, t))
        c.error.connect(self._on_error)

    # ---- Scanner handlers ----
    def _on_scan_toggled(self, checked: bool) -> None:
        if checked:
            self._device_list.clear_devices()
            self._adv_panel.clear_device()
            self._run(self._controller.start_scan())
        else:
            self._run(self._controller.stop_scan())

    def _on_scan_state(self, scanning: bool) -> None:
        # Sync the checked state with the actual scan state (block signals to prevent re-triggering toggled)
        self._scan_btn.blockSignals(True)
        self._scan_btn.setChecked(scanning)
        self._scan_btn.blockSignals(False)
        self._scan_btn.setText("Stop Scan" if scanning else "Start Scan")

    def _on_filter_changed(self) -> None:
        scope = _SCOPE_MAP[self._filter_scope.currentText()]
        self._device_list.set_filter(self._filter_input.text(), scope)

    def _on_device_found(self, address: str, name: str, rssi: int, info: object) -> None:
        self._device_list.upsert_device(address, name, rssi, info)
        if self._device_list.selected_address() == address:
            self._adv_panel.show_device(name, address, rssi, info)

    def _on_device_selected(self, address: str) -> None:
        self._adv_panel.show_device(
            self._device_list.name_of(address),
            address,
            self._device_list.rssi_of(address),
            self._device_list.info_of(address),
        )

    # ---- Device tabs ----
    def _open_device(self, address: str) -> None:
        if address in self._device_tabs:
            self._tabs.setCurrentWidget(self._device_tabs[address])
            return
        name = self._device_list.name_of(address)
        self._run(self._controller.open_session(address, name))

    def _on_session_opened(self, address: str, session: object) -> None:
        view = DeviceView(session, self._aliases)  # type: ignore[arg-type]
        self._device_tabs[address] = view
        source = session.name if session.name != "(No Name)" else address  # type: ignore[attr-defined]
        self._tab_sources[address] = source
        self._log_panel.add_source(source)
        session.log.connect(lambda t, s=source: self._log_panel.append_line(s, t))  # type: ignore[attr-defined]
        session.error.connect(  # type: ignore[attr-defined]
            lambda t, s=source: (
                self._log_panel.append_line(s, f"[Error] {t}"),
                self.statusBar().showMessage(t),
            )
        )
        view.gatt.invalid_input.connect(
            lambda m: self.statusBar().showMessage(f"Input error: {m}")
        )
        index = self._tabs.addTab(view, source)
        self._tabs.setCurrentIndex(index)

    def _on_tab_close(self, index: int) -> None:
        if index == 0:
            return  # Do not close the scanner tab
        view = self._tabs.widget(index)
        for address, v in self._device_tabs.items():
            if v is view:
                self._run(self._controller.close_session(address))
                return

    def _on_session_closed(self, address: str) -> None:
        view = self._device_tabs.pop(address, None)
        if view is not None:
            index = self._tabs.indexOf(view)
            if index >= 0:
                self._tabs.removeTab(index)
            view.deleteLater()
        source = self._tab_sources.pop(address, None)
        if source:
            self._log_panel.remove_source(source)

    # ---- Misc ----
    def _on_theme_toggle(self) -> None:
        new = "light" if saved_theme() == "dark" else "dark"
        apply_theme(QApplication.instance(), new)  # type: ignore[arg-type]
        self._theme_btn.setText("Light Theme" if new == "dark" else "Dark Theme")

    def _on_error(self, message: str) -> None:
        self._log_panel.append_line(_SCANNER_SOURCE, f"[Error] {message}")
        self.statusBar().showMessage(message)
