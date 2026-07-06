"""Decompose/interpret advertisement packet AD fields (pure logic).

Extracts raw AD sections from WinRT platform_data, and reconstructs from
ParsedAdv if that fails.
All interpretation fails silently without exceptions (the app never crashes).
"""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field

from ble.adv_parser import ParsedAdv
from ble.uuid_names import COMPANY_NAMES, format_uuid, resolve_name

# Bluetooth Core Spec — Common Data Types
AD_TYPE_NAMES: dict[int, str] = {
    0x01: "Flags",
    0x02: "Incomplete 16-bit Service UUIDs",
    0x03: "Complete 16-bit Service UUIDs",
    0x04: "Incomplete 32-bit Service UUIDs",
    0x05: "Complete 32-bit Service UUIDs",
    0x06: "Incomplete 128-bit Service UUIDs",
    0x07: "Complete 128-bit Service UUIDs",
    0x08: "Shortened Local Name",
    0x09: "Complete Local Name",
    0x0A: "Tx Power Level",
    0x16: "Service Data (16-bit UUID)",
    0x19: "Appearance",
    0x1A: "Advertising Interval",
    0x20: "Service Data (32-bit UUID)",
    0x21: "Service Data (128-bit UUID)",
    0xFF: "Manufacturer Specific Data",
}

_FLAG_BITS = [
    (0x01, "LE Limited Discoverable"),
    (0x02, "LE General Discoverable"),
    (0x04, "BR/EDR Not Supported"),
    (0x08, "Simultaneous LE+BR/EDR (Controller)"),
    (0x10, "Simultaneous LE+BR/EDR (Host)"),
]


@dataclass
class AdField:
    ad_type: int
    type_name: str
    data: bytes
    summary: str
    details: list[tuple[str, str]] = field(default_factory=list)
    reconstructed: bool = False


@dataclass
class AdvInfo:
    """device_found signal payload — full info for a single advertisement."""
    parsed: ParsedAdv
    fields: list[AdField]
    interval_ms: float | None
    count: int


def _hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def _ascii(data: bytes) -> str:
    return "".join(chr(b) if 32 <= b < 127 else "·" for b in data)


def _uuid128_from_le(data: bytes) -> str:
    """Convert an advertisement's 128-bit UUID (LE) to standard string form."""
    h = bytes(reversed(data)).hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _uuid_names_summary(codes: list[str]) -> str:
    parts = []
    for uuid in codes:
        named = resolve_name(uuid)
        parts.append(f"{named[0]} ({format_uuid(uuid)})" if named else format_uuid(uuid))
    return ", ".join(parts)


# ---- Per-type interpretation ----

def _interpret(ad_type: int, data: bytes) -> tuple[str, list[tuple[str, str]]]:
    """Returns (summary, details). Never raises regardless of input."""
    try:
        if ad_type == 0x01 and data:
            names = [n for bit, n in _FLAG_BITS if data[0] & bit]
            return (" + ".join(names) or f"0x{data[0]:02X}",
                    [("Value", f"0x{data[0]:02X}")])
        if ad_type in (0x08, 0x09):
            return f'"{data.decode("utf-8", errors="replace")}"', []
        if ad_type in (0x02, 0x03) and len(data) >= 2:
            codes = [f"{int.from_bytes(data[i:i+2], 'little'):04x}"
                     for i in range(0, len(data) - 1, 2)]
            return _uuid_names_summary(codes), []
        if ad_type in (0x06, 0x07) and len(data) >= 16:
            uuids = [_uuid128_from_le(data[i:i+16])
                     for i in range(0, len(data) - 15, 16)]
            return _uuid_names_summary(uuids), []
        if ad_type == 0x0A and data:
            return f"{int.from_bytes(data[:1], 'little', signed=True)} dBm", []
        if ad_type == 0xFF and len(data) >= 2:
            return _interpret_manufacturer(data)
        if ad_type == 0x16 and len(data) >= 2:
            return _interpret_service_data(data)
    except Exception:  # noqa: BLE001 — fall back to hex on interpretation failure
        pass
    return _hex(data), []


def _interpret_manufacturer(data: bytes) -> tuple[str, list[tuple[str, str]]]:
    cid = int.from_bytes(data[:2], "little")
    payload = data[2:]
    company = COMPANY_NAMES.get(cid, f"0x{cid:04X}")
    details = [
        ("Company", f"{company} (0x{cid:04X})"),
        ("Payload", _hex(payload) or "(none)"),
        ("ASCII", _ascii(payload) or "(none)"),
    ]
    # iBeacon: Apple(0x004C) + 02 15 prefix + 23+ bytes
    if cid == 0x004C and len(payload) >= 23 and payload[:2] == b"\x02\x15":
        uuid_hex = payload[2:18].hex().upper()
        details += [
            ("UUID", f"{uuid_hex[0:8]}-{uuid_hex[8:12]}-{uuid_hex[12:16]}-"
                     f"{uuid_hex[16:20]}-{uuid_hex[20:32]}"),
            ("Major", str(int.from_bytes(payload[18:20], "big"))),
            ("Minor", str(int.from_bytes(payload[20:22], "big"))),
            ("TX Power @1m",
             f"{int.from_bytes(payload[22:23], 'big', signed=True)} dBm"),
        ]
        return f"{company} · iBeacon", details
    return f"{company} · {len(payload)} bytes", details


_EDDYSTONE_SCHEMES = ["http://www.", "https://www.", "http://", "https://"]
_EDDYSTONE_EXPANSIONS = [
    ".com/", ".org/", ".edu/", ".net/", ".info/", ".biz/", ".gov/",
    ".com", ".org", ".edu", ".net", ".info", ".biz", ".gov",
]


def _interpret_service_data(data: bytes) -> tuple[str, list[tuple[str, str]]]:
    code = int.from_bytes(data[:2], "little")
    payload = data[2:]
    named = resolve_name(f"{code:04x}")
    label = named[0] if named else f"0x{code:04X}"
    details = [("Service", f"{label} (0x{code:04X})"),
               ("Payload", _hex(payload) or "(none)")]
    if code == 0xFEAA and payload:
        eddy = _interpret_eddystone(payload)
        if eddy is not None:
            frame_name, extra = eddy
            return f"{frame_name} · {len(payload)} bytes", details + extra
    return f"{label} · {len(payload)} bytes", details


def _interpret_eddystone(frame: bytes) -> tuple[str, list[tuple[str, str]]] | None:
    """Interpret an Eddystone frame. Returns None for unknown frames or broken length."""
    try:
        kind = frame[0]
        if kind == 0x00 and len(frame) >= 18:  # UID
            tx = int.from_bytes(frame[1:2], "big", signed=True)
            return "Eddystone-UID", [
                ("TX Power @0m", f"{tx} dBm"),
                ("Namespace", _hex(frame[2:12])),
                ("Instance", _hex(frame[12:18])),
            ]
        if kind == 0x10 and len(frame) >= 4:  # URL
            tx = int.from_bytes(frame[1:2], "big", signed=True)
            scheme = _EDDYSTONE_SCHEMES[frame[2]] if frame[2] < 4 else ""
            url = scheme
            for b in frame[3:]:
                url += _EDDYSTONE_EXPANSIONS[b] if b < len(_EDDYSTONE_EXPANSIONS) \
                    else chr(b)
            return "Eddystone-URL", [("TX Power @0m", f"{tx} dBm"), ("URL", url)]
        if kind == 0x20 and len(frame) >= 14:  # TLM (unencrypted)
            vbatt = int.from_bytes(frame[2:4], "big")
            temp = int.from_bytes(frame[4:6], "big", signed=True) / 256
            return "Eddystone-TLM", [
                ("Battery", f"{vbatt} mV"),
                ("Temp", f"{temp:.1f} °C"),
                ("ADV count", str(int.from_bytes(frame[6:10], "big"))),
                ("Uptime", f"{int.from_bytes(frame[10:14], 'big') / 10:.0f} s"),
            ]
    except Exception:  # noqa: BLE001
        return None
    return None


def _make_field(ad_type: int, data: bytes, reconstructed: bool) -> AdField:
    summary, details = _interpret(ad_type, bytes(data))
    return AdField(
        ad_type=ad_type,
        type_name=AD_TYPE_NAMES.get(ad_type, f"Unknown (0x{ad_type:02X})"),
        data=bytes(data),
        summary=summary,
        details=details,
        reconstructed=reconstructed,
    )


# ---- Extraction ----

def extract_fields(platform_data, parsed: ParsedAdv) -> list[AdField]:
    """Extract raw AD fields. Falls back to reconstructing from ParsedAdv if WinRT fails."""
    fields = _winrt_fields(platform_data)
    if fields is not None:
        return fields
    return _reconstruct(parsed)


def _winrt_fields(platform_data) -> list[AdField] | None:
    """Extract data_sections from bleak Windows backend's platform_data (duck-typed)."""
    try:
        args = platform_data[0] if isinstance(platform_data, (tuple, list)) \
            else platform_data
        sections = args.advertisement.data_sections
        fields = [
            _make_field(int(s.data_type), bytes(s.data), reconstructed=False)
            for s in sections
        ]
        return fields or None
    except Exception:  # noqa: BLE001 — fall back to reconstruction if structure differs
        return None


def _reconstruct(parsed: ParsedAdv) -> list[AdField]:
    """Reassemble AD structure from parsed fields (some info like Flags is unavailable)."""
    fields: list[AdField] = []
    if parsed.local_name:
        fields.append(_make_field(0x09, parsed.local_name.encode(), True))
    for cid, hex_str in parsed.manufacturer:
        payload = bytes.fromhex(hex_str.replace(" ", ""))
        fields.append(_make_field(0xFF, cid.to_bytes(2, "little") + payload, True))
    uuid16, uuid128 = [], []
    for uuid in parsed.service_uuids:
        code = format_uuid(uuid)
        if code.startswith("0x"):
            uuid16.append(int(code, 16).to_bytes(2, "little"))
        else:
            uuid128.append(bytes.fromhex(code.replace("-", ""))[::-1])
    if uuid16:
        fields.append(_make_field(0x03, b"".join(uuid16), True))
    if uuid128:
        fields.append(_make_field(0x07, b"".join(uuid128), True))
    for uuid, hex_str in parsed.service_data:
        code = format_uuid(uuid)
        if code.startswith("0x"):
            payload = bytes.fromhex(hex_str.replace(" ", ""))
            fields.append(_make_field(
                0x16, int(code, 16).to_bytes(2, "little") + payload, True))
    if parsed.tx_power is not None:
        fields.append(_make_field(
            0x0A, parsed.tx_power.to_bytes(1, "little", signed=True), True))
    return fields


# ---- Timing/summary ----

_DUP_MERGE_S = 0.010   # Threshold for merging duplicate receptions of the same adv event (half the BLE minimum interval of 20ms)
_MAX_MISSED = 12       # Assumed maximum number of consecutive missed multiples
_RATIO_TOL = 0.25      # Tolerance for gap/T deviating from an integer (advDelay jitter)


def estimate_interval(times: Sequence[float]) -> float | None:
    """Estimate the advertising interval (ms) from detection timestamps (seconds).

    Corrects for two characteristics of Windows WinRT reception:
    1. A single advertisement arrives as a burst of duplicate events ~0ms apart
       → merge events within 10ms
    2. Due to the scan duty cycle only some advertisements are received, so the
       gap becomes an integer multiple of the actual interval T
       → recover the largest T that makes all gaps integer multiples

    Still just an estimate — the UI should mark it with '≈'. Returns None if
    fewer than 3 valid samples.
    """
    if len(times) < 3:
        return None
    # 1) Merge duplicate bursts (use only the first reception time of each burst)
    clustered = [times[0]]
    for t in times[1:]:
        if t - clustered[-1] > _DUP_MERGE_S:
            clustered.append(t)
    if len(clustered) < 3:
        return None
    gaps = [t2 - t1 for t1, t2 in zip(clustered, clustered[1:])]
    # 2) Correct for misses: even the minimum gap may be k×T — find the largest T that makes all gaps integer multiples
    base = min(gaps)
    for k in range(1, _MAX_MISSED + 1):
        candidate = base / k
        if candidate < 0.020:  # stop if below the BLE minimum advertising interval
            break
        if all(abs(g / candidate - round(g / candidate)) <= _RATIO_TOL for g in gaps):
            per_event = [g / round(g / candidate) for g in gaps]
            return statistics.median(per_event) * 1000
    # Correction failed (e.g. irregular advertising) — fall back to median of merged gaps
    return statistics.median(gaps) * 1000


def service_summary(service_uuids: Sequence[str], max_names: int = 2) -> str:
    """For the device list's 'Services' column — up to max_names names plus a '+N' for the remainder."""
    if not service_uuids:
        return ""
    names = []
    for uuid in service_uuids:
        named = resolve_name(uuid)
        names.append(named[0] if named else format_uuid(uuid))
    shown = names[:max_names]
    extra = len(names) - len(shown)
    return ", ".join(shown) + (f" +{extra}" if extra > 0 else "")
