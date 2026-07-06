"""Controller tests — session creation/duplication/removal. Uses a fake session factory."""

from controller import Controller


class FakeSession:
    def __init__(self, address, name, device=None):
        self.address = address
        self.name = name
        self.device = device
        self.connect_calls = 0
        self.closed = False

    async def connect(self):
        self.connect_calls += 1

    async def close(self):
        self.closed = True


def make_controller():
    return Controller(session_factory=FakeSession)


async def test_open_session_creates_and_emits():
    c = make_controller()
    opened = []
    c.session_opened.connect(lambda addr, s: opened.append((addr, s)))
    await c.open_session("AA:BB", "Dev1")
    assert len(opened) == 1
    addr, session = opened[0]
    assert addr == "AA:BB"
    assert session.connect_calls == 1
    assert c.get_session("AA:BB") is session


async def test_open_session_duplicate_ignored():
    c = make_controller()
    opened = []
    c.session_opened.connect(lambda addr, s: opened.append(addr))
    await c.open_session("AA:BB", "Dev1")
    first = c.get_session("AA:BB")
    await c.open_session("AA:BB", "Dev1")  # duplicate — ignored
    assert opened == ["AA:BB"]
    assert c.get_session("AA:BB") is first
    assert first.connect_calls == 1


async def test_close_session_closes_and_emits():
    c = make_controller()
    closed = []
    c.session_closed.connect(closed.append)
    await c.open_session("AA:BB", "Dev1")
    session = c.get_session("AA:BB")
    await c.close_session("AA:BB")
    assert session.closed is True
    assert closed == ["AA:BB"]
    assert c.get_session("AA:BB") is None


async def test_close_unknown_session_is_noop():
    c = make_controller()
    closed = []
    c.session_closed.connect(closed.append)
    await c.close_session("ZZ:ZZ")
    assert closed == []


async def test_open_session_passes_cached_ble_device():
    """BLEDevice seen during scan is passed to the session, skipping bleak re-discovery."""
    c = make_controller()
    fake_device = object()
    c._ble_devices["AA:BB"] = fake_device  # simulate scan detection cache
    await c.open_session("AA:BB", "Dev1")
    assert c.get_session("AA:BB").device is fake_device


async def test_open_session_without_scan_uses_none_device():
    c = make_controller()
    await c.open_session("AA:BB", "Dev1")
    assert c.get_session("AA:BB").device is None


async def test_shutdown_closes_all_sessions():
    c = make_controller()
    await c.open_session("AA:BB", "Dev1")
    await c.open_session("CC:DD", "Dev2")
    s1, s2 = c.get_session("AA:BB"), c.get_session("CC:DD")
    await c.shutdown()
    assert s1.closed and s2.closed
    assert c.get_session("AA:BB") is None
    assert c.get_session("CC:DD") is None
