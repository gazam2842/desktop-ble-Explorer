"""Parse BLE advertisement data (pure logic). All inputs are primitive types."""

from dataclasses import dataclass


@dataclass
class ParsedAdv:
    local_name: str | None
    service_uuids: list[str]
    manufacturer: list[tuple[int, str]]      # (company_id, hex string)
    service_data: list[tuple[str, str]]      # (uuid, hex string)
    tx_power: int | None


def _hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def parse_adv(local_name, service_uuids, manufacturer_data, service_data, tx_power) -> ParsedAdv:
    return ParsedAdv(
        local_name=local_name,
        service_uuids=list(service_uuids or []),
        manufacturer=[(cid, _hex(val)) for cid, val in (manufacturer_data or {}).items()],
        service_data=[(uuid, _hex(val)) for uuid, val in (service_data or {}).items()],
        tx_power=tx_power,
    )


def format_adv(parsed: ParsedAdv) -> str:
    lines: list[str] = []
    if parsed.local_name:
        lines.append(f"Name: {parsed.local_name}")
    if parsed.tx_power is not None:
        lines.append(f"TX Power: {parsed.tx_power} dBm")
    for cid, hex_str in parsed.manufacturer:
        lines.append(f"Mfr 0x{cid:04X}: {hex_str}")
    for uuid, hex_str in parsed.service_data:
        lines.append(f"Service Data {uuid}: {hex_str}")
    if parsed.service_uuids:
        lines.append("Services: " + ", ".join(parsed.service_uuids))
    if not lines:
        return "(No advertisement data)"
    return "\n".join(lines)
