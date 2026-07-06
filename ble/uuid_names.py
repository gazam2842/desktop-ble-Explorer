"""UUID → human-readable name conversion (SIG DB + vendor DB + user aliases).

Pure logic module — no Qt dependency.
"""

import json
import sys
from pathlib import Path

BASE_SUFFIX = "-0000-1000-8000-00805f9b34fb"


def _default_alias_path() -> Path:
    """Alias file location: project root in development, next to the executable when bundled as an exe."""
    if getattr(sys, "frozen", False):  # PyInstaller bundle
        return Path(sys.executable).resolve().parent / "uuid_aliases.json"
    return Path(__file__).resolve().parent.parent / "uuid_aliases.json"


DEFAULT_ALIAS_PATH = _default_alias_path()

# Bluetooth SIG assigned numbers (16-bit code → name). Combines services/characteristics/descriptors.
# Add more as needed (YAGNI).
SIG_NAMES: dict[int, str] = {
    # ---- Services ----
    0x1800: "Generic Access",
    0x1801: "Generic Attribute",
    0x1802: "Immediate Alert",
    0x1803: "Link Loss",
    0x1804: "Tx Power",
    0x1805: "Current Time Service",
    0x180A: "Device Information",
    0x180D: "Heart Rate",
    0x180F: "Battery Service",
    0x1810: "Blood Pressure",
    0x1812: "Human Interface Device",
    0x1816: "Cycling Speed and Cadence",
    0x181A: "Environmental Sensing",
    0x181C: "User Data",
    0x181D: "Weight Scale",
    0x1826: "Fitness Machine",
    0xFE59: "Nordic Secure DFU",
    # ---- Characteristics ----
    0x2A00: "Device Name",
    0x2A01: "Appearance",
    0x2A04: "Peripheral Preferred Connection Parameters",
    0x2A05: "Service Changed",
    0x2A19: "Battery Level",
    0x2A23: "System ID",
    0x2A24: "Model Number String",
    0x2A25: "Serial Number String",
    0x2A26: "Firmware Revision String",
    0x2A27: "Hardware Revision String",
    0x2A28: "Software Revision String",
    0x2A29: "Manufacturer Name String",
    0x2A37: "Heart Rate Measurement",
    0x2A38: "Body Sensor Location",
    0x2A39: "Heart Rate Control Point",
    0x2A50: "PnP ID",
    0x2A6E: "Temperature",
    0x2A6F: "Humidity",
    0x2AA6: "Central Address Resolution",
    # ---- Descriptors ----
    0x2900: "Characteristic Extended Properties",
    0x2901: "Characteristic User Description",
    0x2902: "Client Characteristic Configuration",
    0x2903: "Server Characteristic Configuration",
    0x2904: "Characteristic Presentation Format",
}

# Well-known vendor UUIDs that aren't base UUIDs (full-form lowercase keys)
VENDOR_NAMES: dict[str, str] = {
    "6e400001-b5a3-f393-e0a9-e50e24dcca9e": "Nordic UART Service",
    "6e400002-b5a3-f393-e0a9-e50e24dcca9e": "Nordic UART RX",
    "6e400003-b5a3-f393-e0a9-e50e24dcca9e": "Nordic UART TX",
}

# Bluetooth SIG company identifier → company name (for advertisement manufacturer data)
COMPANY_NAMES: dict[int, str] = {
    0x0000: "Ericsson AB",
    0x0001: "Nokia Mobile Phones",
    0x0002: "Intel Corp.",
    0x0006: "Microsoft",
    0x000A: "Qualcomm (CSR)",
    0x000F: "Broadcom Corporation",
    0x004C: "Apple, Inc.",
    0x0059: "Nordic Semiconductor ASA",
    0x0075: "Samsung Electronics Co. Ltd.",
    0x00E0: "Google",
}


def normalize(uuid: str) -> str:
    """Normalize a 16/32-bit abbreviated form ('180F', '0x180F') to full 128-bit lowercase form."""
    u = uuid.strip().lower()
    if u.startswith("0x"):
        u = u[2:]
    if len(u) in (4, 8) and all(c in "0123456789abcdef" for c in u):
        return f"{int(u, 16):08x}{BASE_SUFFIX}"
    return u


def short_code(uuid: str) -> int | None:
    """Returns the 16/32-bit code if it's a SIG base UUID, or None if custom."""
    u = normalize(uuid)
    if len(u) == 36 and u.endswith(BASE_SUFFIX):
        return int(u[:8], 16)
    return None


def format_uuid(uuid: str) -> str:
    """Abbreviates standard UUIDs as '0x180F'; shows full UUID in uppercase for custom ones."""
    code = short_code(uuid)
    if code is not None and code <= 0xFFFF:
        return f"0x{code:04X}"
    return normalize(uuid).upper()


def resolve_name(uuid: str, aliases: dict[str, str] | None = None) -> tuple[str, str] | None:
    """Returns (name, source). Source is 'alias' | 'sig'. None if unknown.

    Keys in the aliases dict must be normalized (lowercase full-form) UUIDs.
    """
    u = normalize(uuid)
    if aliases and u in aliases:
        return aliases[u], "alias"
    code = short_code(u)
    if code is not None and code in SIG_NAMES:
        return SIG_NAMES[code], "sig"
    if u in VENDOR_NAMES:
        return VENDOR_NAMES[u], "sig"
    return None


class AliasStore:
    """Load/save uuid_aliases.json. Keys are always normalized UUIDs."""

    def __init__(self, path: Path = DEFAULT_ALIAS_PATH) -> None:
        self._path = Path(path)
        self._aliases: dict[str, str] = {}

    def load(self) -> str | None:
        """Load the file. Returns None if OK (including file not found), or a warning message on problems."""
        self._aliases = {}
        if not self._path.exists():
            return None
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return f"Could not read alias file; ignoring: {exc}"
        if not isinstance(raw, dict):
            return "Invalid alias file format; ignoring (not an object)"
        self._aliases = {normalize(k): str(v) for k, v in raw.items()}
        return None

    def get(self, uuid: str) -> str | None:
        return self._aliases.get(normalize(uuid))

    def set(self, uuid: str, name: str) -> None:
        self._aliases[normalize(uuid)] = name
        self._save()

    def remove(self, uuid: str) -> None:
        self._aliases.pop(normalize(uuid), None)
        self._save()

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._aliases, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @property
    def aliases(self) -> dict[str, str]:
        return self._aliases
