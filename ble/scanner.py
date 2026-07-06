"""Thin wrapper around BleakScanner."""

from collections.abc import Callable

from bleak import AdvertisementData, BLEDevice, BleakScanner


class Scanner:
    """Detection-callback-based scanner. Controlled via start/stop."""

    def __init__(self, on_detection: Callable[[BLEDevice, AdvertisementData], None]):
        self._on_detection = on_detection
        self._scanner: BleakScanner | None = None

    async def start(self) -> None:
        if self._scanner is not None:
            return
        self._scanner = BleakScanner(detection_callback=self._on_detection)
        await self._scanner.start()

    async def stop(self) -> None:
        if self._scanner is None:
            return
        await self._scanner.stop()
        self._scanner = None

    @property
    def is_scanning(self) -> bool:
        return self._scanner is not None
