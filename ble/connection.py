"""BleakClient connect/disconnect + disconnect callback."""

from collections.abc import Callable

from bleak import BleakClient, BleakGATTServiceCollection, BLEDevice


class Connection:
    """Manages a single device connection. on_disconnect is called only on unexpected (non-user-initiated) disconnects."""

    def __init__(self, on_disconnect: Callable[[], None]):
        self._on_disconnect = on_disconnect
        self._client: BleakClient | None = None
        self._user_disconnecting: bool = False

    async def connect(self, target: BLEDevice | str) -> BleakGATTServiceCollection:
        """Connect. Passing the BLEDevice obtained from scanning instead of an address
        string skips bleak's pre-connection rediscovery (find_device_by_address),
        making the connection much faster."""
        client = BleakClient(target, disconnected_callback=self._handle_disconnect)
        await client.connect()
        self._client = client
        return client.services

    async def disconnect(self) -> None:
        if self._client is None:
            return
        client, self._client = self._client, None
        self._user_disconnecting = True
        try:
            await client.disconnect()
        finally:
            self._user_disconnecting = False

    def _handle_disconnect(self, _client: BleakClient) -> None:
        self._client = None
        if self._user_disconnecting:
            # Skip the callback since controller notifies directly for user-requested disconnects
            return
        self._on_disconnect()

    @property
    def client(self) -> BleakClient | None:
        return self._client

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected
