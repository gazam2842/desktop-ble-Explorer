"""A session that manages one device's connection/GATT/notify/history."""

import asyncio
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal

from ble import gatt_ops
from ble.conn_params import diff_conn_params, format_conn_params, query_conn_params
from ble.connection import Connection

HISTORY_MAX = 500


def choose_write_response(properties: list[str]) -> bool:
    """Decide whether to use response when writing, based on characteristic properties.

    Prefers True if "write" (with response) is available; False if only
    write-without-response is available.
    """
    if "write" in properties:
        return True
    if "write-without-response" in properties:
        return False
    return False


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


class DeviceSession(QObject):
    """A session bound 1:1 to a single device tab. The UI depends only on these signals."""

    # Service tree structure: list[{uuid, description, chars: list[{uuid, description, properties}]}]
    connected = pyqtSignal(list)
    disconnected = pyqtSignal(str)              # reason
    read_result = pyqtSignal(str, bytes)        # char_uuid, data
    notify_value = pyqtSignal(str, bytes, str)  # char_uuid, data, timestamp
    log = pyqtSignal(str)
    error = pyqtSignal(str)
    conn_params_changed = pyqtSignal(object)  # ConnParams

    def __init__(
        self,
        address: str,
        name: str,
        connection_factory: Callable[[Callable[[], None]], Connection] = Connection,
        device: object | None = None,
        poll_interval: float = 2.0,
    ) -> None:
        super().__init__()
        self.address = address
        self.name = name
        # BLEDevice obtained from scanning — used to skip rediscovery on connect (falls back to address if absent)
        self.device = device
        self._connection = connection_factory(self._on_unexpected_disconnect)
        self._lock = asyncio.Lock()  # serialize GATT operations on the same device
        self._subscribed: set[str] = set()
        self._history: dict[str, deque[tuple[str, bytes]]] = {}
        # Connection parameter polling (0 disables polling — for testing)
        self._poll_interval = poll_interval
        self._poll_task: asyncio.Task | None = None
        self._conn_params = None

    @property
    def is_connected(self) -> bool:
        return self._connection.is_connected

    # ---- Connection ----
    async def connect(self) -> None:
        try:
            self.log.emit(f"[{_now()}] Connecting to {self.address}")
            t0 = time.monotonic()
            services = await self._connection.connect(self.device or self.address)
            tree = []
            for service in services:
                chars = [
                    {
                        "uuid": ch.uuid,
                        "description": ch.description,
                        "properties": list(ch.properties),
                    }
                    for ch in service.characteristics
                ]
                tree.append(
                    {"uuid": service.uuid, "description": service.description, "chars": chars}
                )
            elapsed = (time.monotonic() - t0) * 1000
            n_chars = sum(len(s["chars"]) for s in tree)
            self.connected.emit(tree)
            self.log.emit(
                f"[{_now()}] Connected + service discovery done ({elapsed:.0f}ms): "
                f"{len(tree)} services, {n_chars} characteristics"
            )
            # Initial connection parameter query + start polling
            self._conn_params = None
            self._refresh_conn_params(initial=True)
            self._start_polling()
        except Exception as exc:  # noqa: BLE001 — surface all BLE/OS errors to the user
            self.error.emit(f"Connection failed: {exc}")
            self.disconnected.emit("Connection failed")

    async def disconnect(self) -> None:
        """User-requested disconnect."""
        self._stop_polling()
        try:
            await self._stop_all_notifies()
            await self._connection.disconnect()
            self.disconnected.emit("User request")
            self.log.emit(f"[{_now()}] Disconnected")
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Disconnect failed: {exc}")

    async def close(self) -> None:
        """Cleanup for tab close/app exit. Continues through to the end even on failure."""
        self._stop_polling()
        try:
            await self._stop_all_notifies()
            await self._connection.disconnect()
        except Exception as exc:  # noqa: BLE001 — log only on cleanup failure
            self.log.emit(f"[{_now()}] Ignored error during cleanup: {exc}")

    async def _stop_all_notifies(self) -> None:
        client = self._connection.client
        if client is not None:
            for uuid in list(self._subscribed):
                try:
                    await gatt_ops.stop_notify(client, uuid)
                except Exception:  # noqa: BLE001 — e.g. already disconnected
                    pass
        self._subscribed.clear()

    def _on_unexpected_disconnect(self) -> None:
        self._stop_polling()
        self._subscribed.clear()
        self.disconnected.emit("Connection lost")
        self.log.emit(f"[{_now()}] Connection lost: {self.address}")

    # ---- GATT ----
    async def read_char(self, char_uuid: str) -> None:
        client = self._connection.client
        if client is None:
            self.error.emit("Not connected")
            return
        try:
            async with self._lock:
                data = await gatt_ops.read_char(client, char_uuid)
            self.read_result.emit(char_uuid, data)
            self.log.emit(f"[{_now()}] Read {char_uuid}: {data.hex(' ').upper()}")
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Read failed: {exc}")

    async def write_char(self, char_uuid: str, data: bytes, properties: list[str]) -> None:
        client = self._connection.client
        if client is None:
            self.error.emit("Not connected")
            return
        try:
            response = choose_write_response(properties)
            async with self._lock:
                await gatt_ops.write_char(client, char_uuid, data, response)
            self.log.emit(f"[{_now()}] Write {char_uuid}: {data.hex(' ').upper()}")
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Write failed: {exc}")

    async def set_notify(self, char_uuid: str, enable: bool) -> None:
        client = self._connection.client
        if client is None:
            if enable:
                self.error.emit("Not connected")
            return
        try:
            async with self._lock:
                if enable:
                    await gatt_ops.start_notify(client, char_uuid, self._on_notify)
                    self._subscribed.add(char_uuid)
                else:
                    await gatt_ops.stop_notify(client, char_uuid)
                    self._subscribed.discard(char_uuid)
            state = "subscribed" if enable else "unsubscribed"
            self.log.emit(f"[{_now()}] Notify {state}: {char_uuid}")
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Notify setup failed: {exc}")

    # ---- Connection parameters ----
    def _refresh_conn_params(self, initial: bool = False) -> None:
        """Query parameters → log + emit signal on change. No-op if unchanged."""
        client = self._connection.client
        if client is None:
            return
        new = query_conn_params(client)
        old = self._conn_params
        if old is None:
            self._conn_params = new
            if initial:
                self.log.emit(f"[{_now()}] {format_conn_params(new)}")
            self.conn_params_changed.emit(new)
            return
        msgs = diff_conn_params(old, new)
        if not msgs:
            return
        self._conn_params = new
        for msg in msgs:
            self.log.emit(f"[{_now()}] {msg}")
        self.conn_params_changed.emit(new)

    def _start_polling(self) -> None:
        self._stop_polling()
        if self._poll_interval <= 0:
            return
        self._poll_task = asyncio.ensure_future(self._poll_loop())

    async def _poll_loop(self) -> None:
        try:
            while self._connection.is_connected:
                await asyncio.sleep(self._poll_interval)
                self._refresh_conn_params()
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 — silently exit on polling failure
            pass

    def _stop_polling(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            self._poll_task = None

    def _on_notify(self, char_uuid: str, data: bytes) -> None:
        ts = _now()
        self._history.setdefault(char_uuid, deque(maxlen=HISTORY_MAX)).append(
            (ts, bytes(data))
        )
        self.notify_value.emit(char_uuid, data, ts)
        # Reception history is viewable in the log panel (only the latest value is shown in the characteristic row)
        self.log.emit(f"[{ts}] Notify {char_uuid}: {data.hex(' ').upper()}")

    # ---- Queries ----
    def history(self, char_uuid: str) -> list[tuple[str, bytes]]:
        return list(self._history.get(char_uuid, ()))

    def is_subscribed(self, char_uuid: str) -> bool:
        return char_uuid in self._subscribed
