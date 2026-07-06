import pytest
from ble.codec import encode, decode, InvalidFormatError


# ---- hex ----
def test_encode_hex_space_separated():
    assert encode("01 02 FF", "hex") == b"\x01\x02\xff"

def test_encode_hex_contiguous_and_lowercase():
    assert encode("0102ff", "hex") == b"\x01\x02\xff"

def test_encode_hex_empty_is_empty_bytes():
    assert encode("", "hex") == b""

def test_encode_hex_odd_digits_raises():
    with pytest.raises(InvalidFormatError):
        encode("0 1 2", "hex")

def test_encode_hex_non_hex_raises():
    with pytest.raises(InvalidFormatError):
        encode("zz", "hex")

def test_decode_hex_uppercase_spaced():
    assert decode(b"\x01\x02\xff", "hex") == "01 02 FF"


# ---- string ----
def test_encode_string_utf8():
    assert encode("hi", "string") == b"hi"

def test_decode_string_utf8():
    assert decode(b"hi", "string") == "hi"

def test_decode_string_invalid_utf8_is_replaced():
    # 0xff is not valid UTF-8; decode must not raise (display only)
    assert decode(b"\xff", "string") == "�"


# ---- byte ----
def test_encode_byte_space_separated():
    assert encode("1 2 255", "byte") == b"\x01\x02\xff"

def test_encode_byte_comma_separated():
    assert encode("1,2,255", "byte") == b"\x01\x02\xff"

def test_encode_byte_out_of_range_raises():
    with pytest.raises(InvalidFormatError):
        encode("256", "byte")

def test_encode_byte_non_numeric_raises():
    with pytest.raises(InvalidFormatError):
        encode("1 a 3", "byte")

def test_decode_byte_space_separated_decimal():
    assert decode(b"\x01\x02\xff", "byte") == "1 2 255"


# ---- shared ----
def test_encode_unknown_format_raises():
    with pytest.raises(InvalidFormatError):
        encode("x", "binary")
