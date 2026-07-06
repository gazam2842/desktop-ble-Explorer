"""Query/display connection parameters (WinRT duck-typing — failed fields are None, never raises).

PHY/Interval/Timeout are obtained not from bleak's public API but from the
Windows WinRT BluetoothLEDevice (Win10 19041+). If bleak's internal
structure changes, only the query fails and the app is unaffected.
"""

from dataclasses import dataclass


@dataclass
class ConnParams:
    mtu: int | None = None
    tx_phy: str | None = None        # "1M" | "2M" | "Coded"
    rx_phy: str | None = None
    interval_ms: float | None = None  # WinRT ConnectionInterval × 1.25
    timeout_ms: int | None = None     # WinRT LinkTimeout × 10


def _phy_name(info) -> str | None:
    if info is None:
        return None
    if getattr(info, "is_uncoded_2m_phy", False):
        return "2M"
    if getattr(info, "is_uncoded_1m_phy", False):
        return "1M"
    if getattr(info, "is_coded_phy", False):
        return "Coded"
    return None


def _find_winrt_device(client):
    """Search for the WinRT BluetoothLEDevice inside the bleak client (duck-typed)."""
    candidates = []
    backend = getattr(client, "_backend", None)
    if backend is not None:
        candidates.append(getattr(backend, "_requester", None))  # bleak 3.x
        if hasattr(backend, "__dict__"):
            candidates.extend(vars(backend).values())
    if hasattr(client, "__dict__"):
        candidates.extend(vars(client).values())
    for obj in candidates:
        if obj is not None and hasattr(obj, "get_connection_parameters"):
            return obj
    return None


def query_conn_params(client) -> ConnParams:
    """Query current connection parameters. Never raises regardless of input."""
    p = ConnParams()
    try:
        p.mtu = int(client.mtu_size)
    except Exception:  # noqa: BLE001
        pass
    try:
        dev = _find_winrt_device(client)
    except Exception:  # noqa: BLE001
        dev = None
    if dev is None:
        return p
    try:
        phys = dev.get_connection_phys()
        p.tx_phy = _phy_name(getattr(phys, "transmit_info", None))
        p.rx_phy = _phy_name(getattr(phys, "receive_info", None))
    except Exception:  # noqa: BLE001
        pass
    try:
        cp = dev.get_connection_parameters()
        p.interval_ms = float(cp.connection_interval) * 1.25
        p.timeout_ms = int(cp.link_timeout) * 10
    except Exception:  # noqa: BLE001
        pass
    return p


def _fmt(field: str, value) -> str:
    if value is None:
        return "?"
    if field == "interval_ms":
        return f"{value:.1f}ms"
    if field == "timeout_ms":
        return f"{value}ms"
    return str(value)


def format_conn_params(p: ConnParams) -> str:
    """For the header info line — omits None fields, shows a placeholder message if all are missing."""
    parts = []
    if p.mtu is not None:
        parts.append(f"MTU {p.mtu}")
    if p.tx_phy is not None or p.rx_phy is not None:
        parts.append(f"PHY {p.tx_phy or '?'}/{p.rx_phy or '?'}")
    if p.interval_ms is not None:
        parts.append(f"Interval {p.interval_ms:.1f}ms")
    if p.timeout_ms is not None:
        parts.append(f"Timeout {p.timeout_ms}ms")
    return " · ".join(parts) if parts else "Connection info unavailable"


_DIFF_FIELDS = [
    ("mtu", "MTU"),
    ("tx_phy", "TX PHY"),
    ("rx_phy", "RX PHY"),
    ("interval_ms", "Connection Interval"),
    ("timeout_ms", "Link Timeout"),
]


def diff_conn_params(old: ConnParams, new: ConnParams) -> list[str]:
    """Log messages per changed field. Returns an empty list if unchanged."""
    msgs = []
    for field, label in _DIFF_FIELDS:
        o, n = getattr(old, field), getattr(new, field)
        if o != n:
            msgs.append(f"{label} changed: {_fmt(field, o)} → {_fmt(field, n)}")
    return msgs
