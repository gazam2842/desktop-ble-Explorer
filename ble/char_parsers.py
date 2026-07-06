"""Standard characteristic values → human-readable strings (pure logic, None on failure)."""

from collections.abc import Callable

from ble.uuid_names import short_code

# Appearance upper 10 bits (category) → name. Add more as needed.
_APPEARANCE_CATEGORIES: dict[int, str] = {
    0: "Unknown",
    1: "Phone",
    2: "Computer",
    3: "Watch",
    4: "Clock",
    5: "Display",
    6: "Remote Control",
    7: "Eye-glasses",
    8: "Tag",
    9: "Keyring",
    10: "Media Player",
    11: "Barcode Scanner",
    12: "Thermometer",
    13: "Heart Rate Sensor",
    14: "Blood Pressure",
    15: "Human Interface Device",
}


def _text(data: bytes) -> str | None:
    if not data:
        return None
    return data.decode("utf-8", errors="replace")


def _battery(data: bytes) -> str | None:
    if not data:
        return None
    return f"{data[0]}%"


def _heart_rate(data: bytes) -> str | None:
    if len(data) < 2:
        return None
    if data[0] & 0x01:  # bit0: 1 = uint16 LE
        if len(data) < 3:
            return None
        bpm = int.from_bytes(data[1:3], "little")
    else:
        bpm = data[1]
    return f"{bpm} bpm"


def _appearance(data: bytes) -> str | None:
    if len(data) < 2:
        return None
    value = int.from_bytes(data[:2], "little")
    category = _APPEARANCE_CATEGORIES.get(value >> 6, f"Category {value >> 6}")
    return f"{category} ({value})"


def _pnp_id(data: bytes) -> str | None:
    if len(data) < 7:
        return None
    source = "Bluetooth SIG" if data[0] == 0x01 else "USB-IF"
    vid = int.from_bytes(data[1:3], "little")
    pid = int.from_bytes(data[3:5], "little")
    version = int.from_bytes(data[5:7], "little")
    return f"{source} VID 0x{vid:04X} PID 0x{pid:04X} v{version}"


_PARSERS: dict[int, Callable[[bytes], str | None]] = {
    0x2A00: _text,        # Device Name
    0x2A01: _appearance,  # Appearance
    0x2A19: _battery,     # Battery Level
    0x2A24: _text,        # Model Number
    0x2A25: _text,        # Serial Number
    0x2A26: _text,        # Firmware Revision
    0x2A27: _text,        # Hardware Revision
    0x2A28: _text,        # Software Revision
    0x2A29: _text,        # Manufacturer Name
    0x2A37: _heart_rate,  # Heart Rate Measurement
    0x2A50: _pnp_id,      # PnP ID
}


def has_parser(char_uuid: str) -> bool:
    code = short_code(char_uuid)
    return code is not None and code in _PARSERS


def parse_value(char_uuid: str, data: bytes) -> str | None:
    """Returns a human-readable string for known characteristics, or None for unknown/corrupt data. Never raises."""
    code = short_code(char_uuid)
    if code is None:
        return None
    parser = _PARSERS.get(code)
    if parser is None:
        return None
    try:
        return parser(bytes(data))
    except Exception:  # noqa: BLE001 — parsing must never crash on any input
        return None
