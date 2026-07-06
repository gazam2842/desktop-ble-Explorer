"""conn_params tests — verified with fake bleak/WinRT objects."""

from types import SimpleNamespace

from ble.conn_params import (
    ConnParams, diff_conn_params, format_conn_params, query_conn_params,
)


def make_winrt_device(interval=24, timeout=400, tx_2m=True, rx_2m=True):
    """Mimics a WinRT BluetoothLEDevice (winrt python uses snake_case)."""
    phy_info = lambda is_2m: SimpleNamespace(  # noqa: E731
        is_uncoded_1m_phy=not is_2m, is_uncoded_2m_phy=is_2m, is_coded_phy=False)
    return SimpleNamespace(
        get_connection_parameters=lambda: SimpleNamespace(
            connection_interval=interval, link_timeout=timeout),
        get_connection_phys=lambda: SimpleNamespace(
            transmit_info=phy_info(tx_2m), receive_info=phy_info(rx_2m)),
    )


def make_client(mtu=247, winrt_device="default"):
    if winrt_device == "default":
        winrt_device = make_winrt_device()
    client = SimpleNamespace(_backend=SimpleNamespace(_requester=winrt_device))
    if mtu is not None:
        client.mtu_size = mtu
    return client


# ---- query ----
def test_query_full():
    p = query_conn_params(make_client())
    assert p.mtu == 247
    assert p.tx_phy == "2M" and p.rx_phy == "2M"
    assert p.interval_ms == 24 * 1.25  # 30.0ms
    assert p.timeout_ms == 4000


def test_query_1m_phy():
    p = query_conn_params(make_client(winrt_device=make_winrt_device(tx_2m=False)))
    assert p.tx_phy == "1M" and p.rx_phy == "2M"


def test_query_no_winrt_device():
    # Duck typing fails (different structure) → MTU only, rest None
    client = SimpleNamespace(mtu_size=185, _backend=SimpleNamespace())
    p = query_conn_params(client)
    assert p.mtu == 185
    assert p.tx_phy is None and p.interval_ms is None and p.timeout_ms is None


def test_query_nothing_available():
    p = query_conn_params(object())
    assert p == ConnParams()  # all fields None


def test_query_winrt_call_raises():
    bad = SimpleNamespace(
        get_connection_parameters=lambda: (_ for _ in ()).throw(OSError("x")),
        get_connection_phys=lambda: (_ for _ in ()).throw(OSError("x")),
    )
    p = query_conn_params(make_client(mtu=None, winrt_device=bad))
    assert p == ConnParams()  # all fields None, no exception


# ---- format ----
def test_format_full():
    p = ConnParams(mtu=247, tx_phy="2M", rx_phy="2M", interval_ms=30.0, timeout_ms=4000)
    assert format_conn_params(p) == "MTU 247 · PHY 2M/2M · Interval 30.0ms · Timeout 4000ms"


def test_format_partial():
    p = ConnParams(mtu=23)
    assert format_conn_params(p) == "MTU 23"


def test_format_phy_one_side_unknown():
    p = ConnParams(tx_phy="2M")
    assert format_conn_params(p) == "PHY 2M/?"


def test_format_empty():
    assert format_conn_params(ConnParams()) == "Connection info unavailable"


# ---- diff ----
def test_diff_no_change():
    p = ConnParams(mtu=247, interval_ms=30.0)
    assert diff_conn_params(p, ConnParams(mtu=247, interval_ms=30.0)) == []


def test_diff_interval_changed():
    old = ConnParams(interval_ms=30.0)
    new = ConnParams(interval_ms=255.0)
    assert diff_conn_params(old, new) == ["Connection Interval changed: 30.0ms → 255.0ms"]


def test_diff_multiple_changes():
    old = ConnParams(mtu=23, tx_phy="1M")
    new = ConnParams(mtu=247, tx_phy="2M")
    msgs = diff_conn_params(old, new)
    assert "MTU changed: 23 → 247" in msgs
    assert "TX PHY changed: 1M → 2M" in msgs


def test_diff_from_none_field():
    msgs = diff_conn_params(ConnParams(), ConnParams(mtu=247))
    assert msgs == ["MTU changed: ? → 247"]
