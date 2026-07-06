"""DeviceSession tests — verified without BLE using fake Connection/Client."""

import asyncio

from ble.session import HISTORY_MAX, DeviceSession, choose_write_response


# ---- Fake bleak objects ----
class FakeChar:
    def __init__(self, uuid, properties):
        self.uuid = uuid
        self.description = ""
        self.properties = properties


class FakeService:
    def __init__(self, uuid, chars):
        self.uuid = uuid
        self.description = ""
        self.characteristics = chars


class FakeClient:
    """Mimics the BleakClient interface called by gatt_ops."""

    def __init__(self):
        self.notify_callbacks = {}
        self.written = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def read_gatt_char(self, uuid):
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0)  # yield control — for concurrency detection
        self.in_flight -= 1
        return bytearray(b"\x01\x02")

    async def write_gatt_char(self, uuid, data, response):
        self.written.append((uuid, bytes(data), response))

    async def start_notify(self, uuid, callback):
        self.notify_callbacks[uuid] = callback

    async def stop_notify(self, uuid):
        self.notify_callbacks.pop(uuid, None)


class FakeConnection:
    """Mimics the ble.connection.Connection interface."""

    def __init__(self, on_disconnect):
        self.on_disconnect = on_disconnect
        self.client = None
        self.fail_connect = False

    async def connect(self, address):
        if self.fail_connect:
            raise OSError("Device not found")
        self.client = FakeClient()
        return [
            FakeService("0000180f-0000-1000-8000-00805f9b34fb",
                        [FakeChar("00002a19-0000-1000-8000-00805f9b34fb",
                                  ["read", "notify"])]),
        ]

    async def disconnect(self):
        self.client = None

    @property
    def is_connected(self):
        return self.client is not None


def make_session(poll_interval=0.0):
    """poll_interval=0 → no polling task used (avoids leftover tasks in tests)."""
    holder = {}

    def factory(on_disconnect):
        holder["conn"] = FakeConnection(on_disconnect)
        return holder["conn"]

    session = DeviceSession("AA:BB:CC:DD:EE:FF", "TestDev",
                            connection_factory=factory,
                            poll_interval=poll_interval)
    return session, holder["conn"]


# ---- choose_write_response (moved from controller) ----
def test_write_response_prefers_write_with_response():
    assert choose_write_response(["read", "write"]) is True

def test_write_response_without_response_only():
    assert choose_write_response(["write-without-response"]) is False

def test_write_response_neither_defaults_false():
    assert choose_write_response(["read", "notify"]) is False


# ---- Connection ----
async def test_connect_emits_service_tree():
    session, _ = make_session()
    got = []
    session.connected.connect(got.append)
    await session.connect()
    assert len(got) == 1
    tree = got[0]
    assert tree[0]["uuid"] == "0000180f-0000-1000-8000-00805f9b34fb"
    assert tree[0]["chars"][0]["properties"] == ["read", "notify"]


async def test_connect_failure_emits_error_and_disconnected():
    session, conn = make_session()
    conn.fail_connect = True
    errors, reasons = [], []
    session.error.connect(errors.append)
    session.disconnected.connect(reasons.append)
    await session.connect()
    assert errors and "Connection failed" in errors[0]
    assert reasons == ["Connection failed"]


# ---- read / write ----
async def test_read_emits_result():
    session, _ = make_session()
    await session.connect()
    got = []
    session.read_result.connect(lambda u, d: got.append((u, bytes(d))))
    await session.read_char("2a19")
    assert got == [("2a19", b"\x01\x02")]


async def test_read_without_connection_emits_error():
    session, _ = make_session()
    errors = []
    session.error.connect(errors.append)
    await session.read_char("2a19")
    assert errors


async def test_write_uses_response_choice():
    session, conn = make_session()
    await session.connect()
    await session.write_char("2a19", b"\xff", ["write", "write-without-response"])
    assert conn.client.written == [("2a19", b"\xff", True)]


async def test_gatt_ops_serialized_per_session():
    """Concurrent reads on the same session are serialized via a Lock."""
    session, conn = make_session()
    await session.connect()
    await asyncio.gather(session.read_char("2a19"), session.read_char("2a19"))
    assert conn.client.max_in_flight == 1


# ---- notify + history ----
async def test_notify_value_recorded_in_history():
    session, conn = make_session()
    await session.connect()
    await session.set_notify("2a19", True)
    cb = conn.client.notify_callbacks["2a19"]
    cb("2a19", b"\x37")
    cb("2a19", b"\x38")
    hist = session.history("2a19")
    assert [d for _, d in hist] == [b"\x37", b"\x38"]
    assert session.is_subscribed("2a19")


async def test_history_capped():
    session, conn = make_session()
    await session.connect()
    await session.set_notify("2a19", True)
    cb = conn.client.notify_callbacks["2a19"]
    for i in range(HISTORY_MAX + 10):
        cb("2a19", bytes([i % 256]))
    assert len(session.history("2a19")) == HISTORY_MAX


async def test_unsubscribe():
    session, conn = make_session()
    await session.connect()
    await session.set_notify("2a19", True)
    await session.set_notify("2a19", False)
    assert not session.is_subscribed("2a19")
    assert "2a19" not in conn.client.notify_callbacks


# ---- Disconnect/cleanup ----
async def test_unexpected_disconnect_clears_subscriptions():
    session, conn = make_session()
    await session.connect()
    await session.set_notify("2a19", True)
    reasons = []
    session.disconnected.connect(reasons.append)
    conn.on_disconnect()  # simulate unexpected disconnect
    assert reasons == ["Connection lost"]
    assert not session.is_subscribed("2a19")


async def test_close_swallows_errors():
    session, conn = make_session()
    await session.connect()

    async def boom():
        raise OSError("Already disconnected")

    conn.disconnect = boom
    await session.close()  # passes if the exception doesn't propagate


# ---- Connection parameters ----
from types import SimpleNamespace

from ble.conn_params import ConnParams  # noqa: F401  (for checking the signal payload type)


def attach_fake_winrt(client, interval=24, timeout=400):
    """Attach a fake WinRT device to FakeClient."""
    client.mtu_size = 247
    phy = SimpleNamespace(is_uncoded_1m_phy=False, is_uncoded_2m_phy=True,
                          is_coded_phy=False)
    state = SimpleNamespace(interval=interval, timeout=timeout)
    client._backend = SimpleNamespace(_requester=SimpleNamespace(
        get_connection_parameters=lambda: SimpleNamespace(
            connection_interval=state.interval, link_timeout=state.timeout),
        get_connection_phys=lambda: SimpleNamespace(
            transmit_info=phy, receive_info=phy),
    ))
    return state  # tests simulate parameter changes by mutating state.interval


async def test_connect_logs_timing_and_params():
    session, conn = make_session()
    logs, params = [], []
    session.log.connect(logs.append)
    session.conn_params_changed.connect(params.append)
    await session.connect()
    attach_fake_winrt(conn.client)
    # In reality WinRT already exists at connect time — reproduces the initial query path
    session._conn_params = None
    session._refresh_conn_params(initial=True)
    joined = "\n".join(logs)
    assert "Connected + service discovery done" in joined
    assert "1 services" in joined and "1 characteristics" in joined
    assert "MTU 247" in joined
    assert len(params) >= 1
    assert params[-1].interval_ms == 30.0


async def test_param_change_logged_once():
    session, conn = make_session()
    await session.connect()
    state = attach_fake_winrt(conn.client)
    session._refresh_conn_params(initial=True)
    logs, params = [], []
    session.log.connect(logs.append)
    session.conn_params_changed.connect(params.append)
    # No change → no-op
    session._refresh_conn_params()
    assert logs == [] and params == []
    # interval 24(30ms) → 204(255ms)
    state.interval = 204
    session._refresh_conn_params()
    assert any("Connection Interval changed: 30.0ms → 255.0ms" in l for l in logs)
    assert len(params) == 1
    # calling again with the same value → no additional notification
    session._refresh_conn_params()
    assert len(params) == 1


async def test_refresh_without_client_is_noop():
    session, _ = make_session()
    params = []
    session.conn_params_changed.connect(params.append)
    session._refresh_conn_params()  # before connecting
    assert params == []
