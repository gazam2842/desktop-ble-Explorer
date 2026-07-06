"""Controller responsible for scanning and creating/removing device sessions."""

import time
from collections import deque
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal
from bleak import AdvertisementData, BLEDevice

from ble.adv_decode import AdvInfo, estimate_interval, extract_fields
from ble.adv_parser import parse_adv
from ble.scanner import Scanner
from ble.session import DeviceSession


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


class Controller(QObject):
    # address, name, rssi, ParsedAdv (object)
    device_found = pyqtSignal(str, str, int, object)
    scan_state_changed = pyqtSignal(bool)
    session_opened = pyqtSignal(str, object)  # address, DeviceSession
    session_closed = pyqtSignal(str)          # address
    log = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, session_factory=DeviceSession) -> None:
        super().__init__()
        self._scanner = Scanner(self._on_detection)
        self._sessions: dict[str, DeviceSession] = {}
        self._session_factory = session_factory
        # Cache of BLEDevice seen while scanning — skips bleak re-discovery on connect (faster connection)
        self._ble_devices: dict[str, BLEDevice] = {}
        # Advertisement timing tracking (per scan session)
        self._adv_times: dict[str, deque[float]] = {}
        self._adv_count: dict[str, int] = {}

    # ---- Scan ----
    def _on_detection(self, device: BLEDevice, adv: AdvertisementData) -> None:
        self._ble_devices[device.address] = device
        times = self._adv_times.setdefault(device.address, deque(maxlen=32))
        times.append(time.monotonic())
        self._adv_count[device.address] = self._adv_count.get(device.address, 0) + 1
        parsed = parse_adv(
            local_name=adv.local_name,
            service_uuids=adv.service_uuids,
            manufacturer_data=adv.manufacturer_data,
            service_data=adv.service_data,
            tx_power=adv.tx_power,
        )
        info = AdvInfo(
            parsed=parsed,
            fields=extract_fields(getattr(adv, "platform_data", None), parsed),
            interval_ms=estimate_interval(list(times)),
            count=self._adv_count[device.address],
        )
        name = adv.local_name or device.name or "(No Name)"
        self.device_found.emit(device.address, name, adv.rssi, info)

    async def start_scan(self) -> None:
        try:
            self._adv_times.clear()
            self._adv_count.clear()
            await self._scanner.start()
            self.scan_state_changed.emit(True)
            self.log.emit(f"[{_now()}] Scan started")
        except Exception as exc:  # noqa: BLE001 — report all BLE/OS errors to the user
            self.scan_state_changed.emit(False)
            self.error.emit(f"Failed to start scan: {exc}")

    async def stop_scan(self) -> None:
        try:
            await self._scanner.stop()
            self.scan_state_changed.emit(False)
            self.log.emit(f"[{_now()}] Scan stopped")
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Failed to stop scan: {exc}")

    # ---- Session ----
    def get_session(self, address: str) -> DeviceSession | None:
        return self._sessions.get(address)

    async def open_session(self, address: str, name: str) -> None:
        """Create session, notify the tab, then start connecting. Ignored if a duplicate (UI pre-checks via get_session)."""
        if address in self._sessions:
            return
        # Scanning and connecting compete for the adapter, slowing connection negotiation — pause scanning before connecting
        if self._scanner.is_scanning:
            await self.stop_scan()
        session = self._session_factory(
            address, name, device=self._ble_devices.get(address)
        )
        self._sessions[address] = session
        self.session_opened.emit(address, session)
        await session.connect()

    async def close_session(self, address: str) -> None:
        session = self._sessions.pop(address, None)
        if session is None:
            return
        await session.close()
        self.session_closed.emit(address)

    async def shutdown(self) -> None:
        """App shutdown: clean up all sessions + stop scanning."""
        for address in list(self._sessions):
            await self.close_session(address)
        try:
            if self._scanner.is_scanning:
                await self._scanner.stop()
        except Exception:  # noqa: BLE001 — ignore errors during shutdown
            pass
