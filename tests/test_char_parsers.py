from ble.char_parsers import has_parser, parse_value


def test_battery_level():
    assert parse_value("2A19", bytes([87])) == "87%"

def test_battery_level_empty_data():
    assert parse_value("2A19", b"") is None

def test_device_name_utf8():
    assert parse_value("2A00", "Device-A3".encode()) == "Device-A3"

def test_manufacturer_name():
    assert parse_value("2A29", b"ACME") == "ACME"

def test_text_empty_is_none():
    assert parse_value("2A29", b"") is None

def test_heart_rate_uint8():
    # flags bit0=0 → uint8 bpm
    assert parse_value("2A37", bytes([0x00, 72])) == "72 bpm"

def test_heart_rate_uint16():
    # flags bit0=1 → uint16 LE bpm
    assert parse_value("2A37", bytes([0x01, 0x2C, 0x01])) == "300 bpm"

def test_heart_rate_too_short():
    assert parse_value("2A37", bytes([0x01, 0x2C])) is None

def test_appearance():
    # 832 = Heart Rate Sensor category (13 << 6)
    assert parse_value("2A01", (832).to_bytes(2, "little")) == \
        "Heart Rate Sensor (832)"

def test_pnp_id():
    data = bytes([0x01]) + (0x0059).to_bytes(2, "little") + \
        (0x1234).to_bytes(2, "little") + (0x0100).to_bytes(2, "little")
    assert parse_value("2A50", data) == \
        "Bluetooth SIG VID 0x0059 PID 0x1234 v256"

def test_unknown_uuid_returns_none():
    assert parse_value("6e400003-b5a3-f393-e0a9-e50e24dcca9e", b"\x01") is None

def test_garbage_data_never_raises():
    # None or string for any input, without raising
    for uuid in ("2A19", "2A37", "2A01", "2A50", "2A00"):
        for data in (b"", b"\xff", b"\xff" * 2, b"\xff" * 20):
            result = parse_value(uuid, data)
            assert result is None or isinstance(result, str)

def test_has_parser():
    assert has_parser("2A19") is True
    assert has_parser("0x2A19") is True
    assert has_parser("6e400003-b5a3-f393-e0a9-e50e24dcca9e") is False
