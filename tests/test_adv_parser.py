from ble.adv_parser import parse_adv, format_adv, ParsedAdv


def test_parse_basic_fields():
    parsed = parse_adv(
        local_name="MyDevice",
        service_uuids=["0000180d-0000-1000-8000-00805f9b34fb"],
        manufacturer_data={0x0059: b"\x01\x02"},
        service_data={"0000180f-0000-1000-8000-00805f9b34fb": b"\x64"},
        tx_power=-12,
    )
    assert parsed.local_name == "MyDevice"
    assert parsed.service_uuids == ["0000180d-0000-1000-8000-00805f9b34fb"]
    assert parsed.manufacturer == [(0x0059, "01 02")]
    assert parsed.service_data == [("0000180f-0000-1000-8000-00805f9b34fb", "64")]
    assert parsed.tx_power == -12


def test_parse_handles_missing_fields():
    parsed = parse_adv(
        local_name=None,
        service_uuids=[],
        manufacturer_data={},
        service_data={},
        tx_power=None,
    )
    assert parsed == ParsedAdv(
        local_name=None,
        service_uuids=[],
        manufacturer=[],
        service_data=[],
        tx_power=None,
    )


def test_format_includes_present_fields_only():
    parsed = ParsedAdv(
        local_name="Dev",
        service_uuids=["abcd"],
        manufacturer=[(0x0059, "01 02")],
        service_data=[],
        tx_power=-12,
    )
    text = format_adv(parsed)
    assert "Name: Dev" in text
    assert "TX Power: -12 dBm" in text
    assert "Mfr 0x0059: 01 02" in text
    assert "Services: abcd" in text
    # service_data is empty, so that line should not appear
    assert "Service Data" not in text


def test_format_empty_returns_placeholder():
    parsed = parse_adv(None, [], {}, {}, None)
    assert format_adv(parsed) == "(No advertisement data)"
