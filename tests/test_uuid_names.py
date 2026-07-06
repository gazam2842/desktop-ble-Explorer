import json

from ble.uuid_names import (
    COMPANY_NAMES, AliasStore, format_uuid, normalize, resolve_name, short_code,
)


# ---- normalize ----
def test_normalize_16bit_short():
    assert normalize("180F") == "0000180f-0000-1000-8000-00805f9b34fb"

def test_normalize_0x_prefix():
    assert normalize("0x180F") == "0000180f-0000-1000-8000-00805f9b34fb"

def test_normalize_full_uuid_lowercases():
    assert normalize("6E400001-B5A3-F393-E0A9-E50E24DCCA9E") == \
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e"

def test_normalize_strips_whitespace():
    assert normalize(" 180f ") == "0000180f-0000-1000-8000-00805f9b34fb"


# ---- short_code ----
def test_short_code_base_uuid():
    assert short_code("0000180f-0000-1000-8000-00805f9b34fb") == 0x180F

def test_short_code_from_short_form():
    assert short_code("2A19") == 0x2A19

def test_short_code_custom_uuid_is_none():
    assert short_code("6e400001-b5a3-f393-e0a9-e50e24dcca9e") is None


# ---- format_uuid ----
def test_format_uuid_standard_shortens():
    assert format_uuid("0000180f-0000-1000-8000-00805f9b34fb") == "0x180F"

def test_format_uuid_custom_full_uppercase():
    assert format_uuid("6e400001-b5a3-f393-e0a9-e50e24dcca9e") == \
        "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"


# ---- resolve_name (SIG) ----
def test_resolve_sig_service():
    assert resolve_name("180F") == ("Battery Service", "sig")

def test_resolve_sig_characteristic():
    assert resolve_name("00002a19-0000-1000-8000-00805f9b34fb") == \
        ("Battery Level", "sig")

def test_resolve_vendor_known():
    # Nordic UART is a vendor UUID but included in the built-in DB
    assert resolve_name("6E400001-B5A3-F393-E0A9-E50E24DCCA9E") == \
        ("Nordic UART Service", "sig")

def test_resolve_unknown_returns_none():
    assert resolve_name("12345678-1234-1234-1234-123456789abc") is None


# ---- alias priority ----
def test_alias_overrides_sig():
    aliases = {"0000180f-0000-1000-8000-00805f9b34fb": "My Battery"}
    assert resolve_name("180F", aliases) == ("My Battery", "alias")

def test_alias_key_is_normalized_lookup():
    aliases = {"6e400001-b5a3-f393-e0a9-e50e24dcca9e": "Custom UART"}
    # uppercase input is also normalized for matching
    assert resolve_name("6E400001-B5A3-F393-E0A9-E50E24DCCA9E", aliases) == \
        ("Custom UART", "alias")


# ---- company ----
def test_company_names_has_nordic():
    assert COMPANY_NAMES[0x0059] == "Nordic Semiconductor ASA"


# ---- AliasStore ----
def test_alias_store_roundtrip(tmp_path):
    path = tmp_path / "uuid_aliases.json"
    store = AliasStore(path)
    assert store.load() is None  # no file = normal (empty aliases)
    store.set("6E400001-B5A3-F393-E0A9-E50E24DCCA9E", "Custom UART")
    # saved to file immediately, and the key is normalized
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == {"6e400001-b5a3-f393-e0a9-e50e24dcca9e": "Custom UART"}
    # same result when reloaded with a new store
    store2 = AliasStore(path)
    assert store2.load() is None
    assert store2.get("6e400001-b5a3-f393-e0a9-e50e24dcca9e") == "Custom UART"
    assert resolve_name("6E400001-B5A3-F393-E0A9-E50E24DCCA9E", store2.aliases) == \
        ("Custom UART", "alias")


def test_alias_store_remove(tmp_path):
    path = tmp_path / "a.json"
    store = AliasStore(path)
    store.set("180F", "My Battery")
    store.remove("0x180F")  # different notation, same key after normalization
    assert store.get("180F") is None
    assert json.loads(path.read_text(encoding="utf-8")) == {}


def test_alias_store_corrupt_file(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json!!", encoding="utf-8")
    store = AliasStore(path)
    err = store.load()
    assert err is not None        # returns a warning message
    assert store.aliases == {}    # starts with empty aliases


def test_alias_store_non_dict_json(tmp_path):
    path = tmp_path / "list.json"
    path.write_text("[1,2,3]", encoding="utf-8")
    store = AliasStore(path)
    assert store.load() is not None
    assert store.aliases == {}
