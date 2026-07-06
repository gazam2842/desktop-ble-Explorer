"""adv_decode tests — pure logic, no BLE/Qt required."""

from ble.adv_decode import AD_TYPE_NAMES, AdField, extract_fields
from ble.adv_parser import parse_adv


def make_parsed(**kw):
    base = dict(local_name=None, service_uuids=[], manufacturer_data={},
                service_data={}, tx_power=None)
    base.update(kw)
    return parse_adv(**base)


# ---- AD type table ----
def test_ad_type_names():
    assert AD_TYPE_NAMES[0x01] == "Flags"
    assert AD_TYPE_NAMES[0x09] == "Complete Local Name"
    assert AD_TYPE_NAMES[0xFF] == "Manufacturer Specific Data"
    assert AD_TYPE_NAMES[0x16] == "Service Data (16-bit UUID)"


# ---- Reconstruction fallback (platform_data=None) ----
def test_reconstruct_name():
    parsed = make_parsed(local_name="Device-A3")
    fields = extract_fields(None, parsed)
    name_fields = [f for f in fields if f.ad_type == 0x09]
    assert len(name_fields) == 1
    f = name_fields[0]
    assert f.reconstructed is True
    assert f.data == b"Device-A3"
    assert '"Device-A3"' in f.summary


def test_reconstruct_manufacturer():
    parsed = make_parsed(manufacturer_data={0x0059: b"\x01\x02"})
    fields = extract_fields(None, parsed)
    mfr = [f for f in fields if f.ad_type == 0xFF][0]
    assert mfr.reconstructed is True
    # Reconstructed data: company ID (2 bytes LE) + payload
    assert mfr.data == b"\x59\x00\x01\x02"
    assert "Nordic" in mfr.summary


def test_reconstruct_service_uuids_128bit():
    parsed = make_parsed(service_uuids=["6e400001-b5a3-f393-e0a9-e50e24dcca9e"])
    fields = extract_fields(None, parsed)
    f = [x for x in fields if x.ad_type == 0x07][0]
    assert "Nordic UART Service" in f.summary


def test_reconstruct_service_uuids_16bit():
    parsed = make_parsed(service_uuids=["0000180f-0000-1000-8000-00805f9b34fb"])
    fields = extract_fields(None, parsed)
    f = [x for x in fields if x.ad_type == 0x03][0]
    assert "Battery Service" in f.summary


def test_reconstruct_tx_power():
    parsed = make_parsed(tx_power=-4)
    fields = extract_fields(None, parsed)
    f = [x for x in fields if x.ad_type == 0x0A][0]
    assert "-4 dBm" in f.summary


def test_reconstruct_empty_adv():
    fields = extract_fields(None, make_parsed())
    assert fields == []


# ---- Interpreter: Flags (only appears via WinRT path, but the interpreter is shared) ----
def test_flags_interpretation():
    from ble.adv_decode import _make_field
    f = _make_field(0x01, b"\x06", reconstructed=False)
    assert "LE General Discoverable" in f.summary
    assert "BR/EDR Not Supported" in f.summary


def test_unknown_ad_type_shows_hex():
    from ble.adv_decode import _make_field
    f = _make_field(0x77, b"\xab\xcd", reconstructed=False)
    assert f.type_name.startswith("Unknown")
    assert "AB CD" in f.summary


# ---- WinRT extraction path (duck-typed fake objects) ----
class FakeSection:
    def __init__(self, data_type, data):
        self.data_type = data_type
        self.data = data


class FakeAdvertisement:
    def __init__(self, sections):
        self.data_sections = sections


class FakeArgs:
    def __init__(self, sections):
        self.advertisement = FakeAdvertisement(sections)


def test_winrt_sections_extracted():
    sections = [
        FakeSection(0x01, b"\x06"),
        FakeSection(0xFF, b"\x59\x00\xaa\xbb"),
        FakeSection(0x09, b"Device-A3"),
    ]
    parsed = make_parsed(local_name="OtherName")  # verify raw takes priority over the fallback
    fields = extract_fields((FakeArgs(sections),), parsed)
    assert [f.ad_type for f in fields] == [0x01, 0xFF, 0x09]
    assert all(f.reconstructed is False for f in fields)
    assert "Device-A3" in fields[2].summary  # uses raw data


def test_winrt_tuple_or_bare_object():
    sections = [FakeSection(0x01, b"\x06")]
    parsed = make_parsed()
    # works both when wrapped in a tuple and when passed as a bare object
    assert len(extract_fields((FakeArgs(sections),), parsed)) == 1
    assert len(extract_fields(FakeArgs(sections), parsed)) == 1


def test_winrt_broken_structure_falls_back():
    parsed = make_parsed(local_name="Fallback")
    fields = extract_fields(object(), parsed)  # no advertisement attribute
    assert len(fields) == 1
    assert fields[0].reconstructed is True


def test_winrt_empty_sections_falls_back():
    parsed = make_parsed(local_name="Fallback")
    fields = extract_fields((FakeArgs([]),), parsed)
    assert fields[0].reconstructed is True


# ---- iBeacon ----
def make_ibeacon_payload():
    uuid = bytes.fromhex("e2c56db5dffb48d2b060d0f5a71096e0")
    return b"\x02\x15" + uuid + (1).to_bytes(2, "big") + (4097).to_bytes(2, "big") + b"\xc5"


def test_ibeacon_detected():
    from ble.adv_decode import _make_field
    data = (0x004C).to_bytes(2, "little") + make_ibeacon_payload()
    f = _make_field(0xFF, data, reconstructed=False)
    assert "iBeacon" in f.summary
    kv = dict(f.details)
    assert kv["UUID"] == "E2C56DB5-DFFB-48D2-B060-D0F5A71096E0"
    assert kv["Major"] == "1"
    assert kv["Minor"] == "4097"
    assert kv["TX Power @1m"] == "-59 dBm"


def test_apple_but_not_ibeacon():
    from ble.adv_decode import _make_field
    data = (0x004C).to_bytes(2, "little") + b"\x10\x05\xaa"
    f = _make_field(0xFF, data, reconstructed=False)
    assert "iBeacon" not in f.summary


def test_ibeacon_truncated_payload_no_crash():
    from ble.adv_decode import _make_field
    data = (0x004C).to_bytes(2, "little") + b"\x02\x15\xaa\xbb"
    f = _make_field(0xFF, data, reconstructed=False)
    assert isinstance(f.summary, str)  # falls back to default display without raising


# ---- Eddystone ----
def test_eddystone_url():
    from ble.adv_decode import _make_field
    # 0xFEAA + frame 0x10(URL) + tx -10 + scheme https:// + "example" + .com
    data = (0xFEAA).to_bytes(2, "little") + b"\x10\xf6\x03" + b"example" + b"\x07"
    f = _make_field(0x16, data, reconstructed=False)
    assert "Eddystone-URL" in f.summary
    kv = dict(f.details)
    assert kv["URL"] == "https://example.com"
    assert kv["TX Power @0m"] == "-10 dBm"


def test_eddystone_uid():
    from ble.adv_decode import _make_field
    data = (0xFEAA).to_bytes(2, "little") + b"\x00\xf6" + b"\x01" * 10 + b"\x02" * 6
    f = _make_field(0x16, data, reconstructed=False)
    assert "Eddystone-UID" in f.summary
    kv = dict(f.details)
    assert kv["Namespace"] == "01 01 01 01 01 01 01 01 01 01"
    assert kv["Instance"] == "02 02 02 02 02 02"


def test_eddystone_unknown_frame_hex_only():
    from ble.adv_decode import _make_field
    data = (0xFEAA).to_bytes(2, "little") + b"\x99\x01\x02"
    f = _make_field(0x16, data, reconstructed=False)
    assert isinstance(f.summary, str)


# ---- Interval estimation ----
from ble.adv_decode import estimate_interval, service_summary


def test_interval_uniform():
    times = [0.0, 0.1, 0.2, 0.3, 0.4]
    assert estimate_interval(times) == 100.0  # median 0.1s → 100ms


def test_interval_irregular_uses_median():
    import pytest
    times = [0.0, 0.1, 0.2, 1.2, 1.3]  # delta: 100,100,1000,100 → median 100
    assert estimate_interval(times) == pytest.approx(100.0)


def test_interval_insufficient_samples():
    assert estimate_interval([]) is None
    assert estimate_interval([0.0, 0.1]) is None


def test_interval_duplicate_bursts_merged():
    """WinRT delivers a single advertisement as duplicate events ~0ms apart — duplicates must not dominate the estimate.

    Measured: YMS_201 (actual 255ms), 8 of 13 deltas are ~0ms → the naive median underestimates at 37ms.
    """
    import pytest
    times = []
    for i in range(6):
        t = i * 0.255
        times += [t, t + 0.002]  # 2 duplicates per advertisement
    assert estimate_interval(times) == pytest.approx(255.0, rel=0.05)


def test_interval_missed_events_recovered():
    """Measured gap pattern (YMS_201): 760/1520/1760/2520ms = 3, 6, 7, 10 times T(≈253ms).

    Windows scan duty cycling only receives some advertisements → gaps are integer multiples of T.
    T must be estimated by recovering the common divisor (a plain median overestimates at 765ms).
    """
    import pytest
    base = 0.2533
    starts = [0.0]
    for k in (3, 6, 7, 10):
        starts.append(starts[-1] + base * k)
    times = []
    for t in starts:  # also mix in duplicate bursts
        times += [t, t + 0.001, t + 0.003]
    assert estimate_interval(times) == pytest.approx(253.3, rel=0.05)


# ---- Service summary ----
def test_service_summary_two_names():
    s = service_summary([
        "0000180f-0000-1000-8000-00805f9b34fb",
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
    ])
    assert s == "Battery Service, Nordic UART Service"


def test_service_summary_overflow_plus_n():
    s = service_summary([
        "0000180f-0000-1000-8000-00805f9b34fb",
        "0000180a-0000-1000-8000-00805f9b34fb",
        "0000180d-0000-1000-8000-00805f9b34fb",
    ])
    assert s == "Battery Service, Device Information +1"


def test_service_summary_unknown_uses_short_uuid():
    s = service_summary(["12345678-1234-1234-1234-123456789abc"])
    assert s == "12345678-1234-1234-1234-123456789ABC"


def test_service_summary_empty():
    assert service_summary([]) == ""
