"""Scan result table widget. Manages rows keyed by address, holds AdvInfo."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

from ble.adv_decode import AdvInfo
from ble.adv_parser import format_adv
from ui.device_filter import matches

_COLS = ["Name", "Address", "RSSI", "Interval"]


class DeviceList(QTableWidget):
    device_selected = pyqtSignal(str)   # address
    connect_requested = pyqtSignal(str)  # address (double-click)

    def __init__(self) -> None:
        super().__init__(0, len(_COLS))
        self.setHorizontalHeaderLabels(_COLS)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.horizontalHeader().setStretchLastSection(True)
        self.setColumnWidth(0, 170)
        self.setColumnWidth(1, 140)
        self.setColumnWidth(2, 55)
        self._rows: dict[str, int] = {}      # address -> row index
        self._infos: dict[str, AdvInfo] = {}  # address -> latest advertisement info
        self._rssi: dict[str, int] = {}
        self._query: str = ""
        self._scope: str = "both"
        self.itemSelectionChanged.connect(self._emit_selected)
        self.itemDoubleClicked.connect(self._emit_connect)

    def upsert_device(self, address: str, name: str, rssi: int, info: object) -> None:
        self._infos[address] = info  # type: ignore[assignment]
        self._rssi[address] = rssi
        interval = self._interval_text(info)
        if address in self._rows:
            row = self._rows[address]
            self.item(row, 0).setText(name)
            self.item(row, 2).setText(str(rssi))
            self.item(row, 3).setText(interval)
        else:
            row = self.rowCount()
            self.insertRow(row)
            self._rows[address] = row
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, address)
            self.setItem(row, 0, name_item)
            self.setItem(row, 1, QTableWidgetItem(address))
            self.setItem(row, 2, QTableWidgetItem(str(rssi)))
            self.setItem(row, 3, QTableWidgetItem(interval))
        summary = format_adv(info.parsed) if isinstance(info, AdvInfo) else ""
        for col in range(len(_COLS)):
            self.item(row, col).setToolTip(summary)
        # Apply the current filter to this row immediately (live update)
        self.setRowHidden(row, not matches(name, address, self._query, self._scope))

    @staticmethod
    def _interval_text(info: object) -> str:
        if isinstance(info, AdvInfo) and info.interval_ms:
            return f"≈{info.interval_ms:.0f}ms"
        return ""

    def set_filter(self, query: str, scope: str) -> None:
        self._query = query
        self._scope = scope
        for address, row in self._rows.items():
            name = self.item(row, 0).text()
            self.setRowHidden(row, not matches(name, address, query, scope))

    def clear_devices(self) -> None:
        self.setRowCount(0)
        self._rows.clear()
        self._infos.clear()
        self._rssi.clear()

    # ---- Lookup ----
    def info_of(self, address: str) -> AdvInfo | None:
        return self._infos.get(address)

    def rssi_of(self, address: str) -> int:
        return self._rssi.get(address, 0)

    def name_of(self, address: str) -> str:
        row = self._rows.get(address)
        return self.item(row, 0).text() if row is not None else address

    def selected_address(self) -> str | None:
        items = self.selectedItems()
        if not items:
            return None
        return self.item(items[0].row(), 0).data(Qt.ItemDataRole.UserRole)

    def _emit_selected(self) -> None:
        address = self.selected_address()
        if address:
            self.device_selected.emit(address)

    def _emit_connect(self, item: QTableWidgetItem) -> None:
        address = self.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        if address:
            self.connect_requested.emit(address)
