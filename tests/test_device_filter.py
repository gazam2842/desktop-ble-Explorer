from ui.device_filter import matches


def test_empty_query_matches_all():
    assert matches("dev", "AA:BB", "", "both") is True

def test_whitespace_query_matches_all():
    assert matches("dev", "AA:BB", "   ", "both") is True

def test_name_scope_matches_name_only():
    assert matches("HeartRate", "AA:BB:CC", "heart", "name") is True
    assert matches("HeartRate", "AA:BB:CC", "AA", "name") is False

def test_mac_scope_matches_address_only():
    assert matches("HeartRate", "AA:BB:CC", "bb", "mac") is True
    assert matches("HeartRate", "AA:BB:CC", "heart", "mac") is False

def test_both_scope_matches_either():
    assert matches("HeartRate", "AA:BB:CC", "heart", "both") is True
    assert matches("HeartRate", "AA:BB:CC", "bb", "both") is True
    assert matches("HeartRate", "AA:BB:CC", "zzz", "both") is False

def test_case_insensitive():
    assert matches("HeartRate", "aa:bb", "HEART", "name") is True

def test_none_name_safe():
    assert matches(None, "AA:BB", "aa", "both") is True
    assert matches(None, "AA:BB", "x", "name") is False
