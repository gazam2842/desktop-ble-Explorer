"""GATT read/write/notify operations on a connected BleakClient."""

from collections.abc import Callable

from bleak import BleakClient


async def read_char(client: BleakClient, char_uuid: str) -> bytes:
    return bytes(await client.read_gatt_char(char_uuid))


async def write_char(client: BleakClient, char_uuid: str, data: bytes, response: bool) -> None:
    await client.write_gatt_char(char_uuid, data, response=response)


async def start_notify(
    client: BleakClient,
    char_uuid: str,
    callback: Callable[[str, bytes], None],
) -> None:
    def _wrapped(_sender, data: bytearray) -> None:
        callback(char_uuid, bytes(data))

    await client.start_notify(char_uuid, _wrapped)


async def stop_notify(client: BleakClient, char_uuid: str) -> None:
    await client.stop_notify(char_uuid)
