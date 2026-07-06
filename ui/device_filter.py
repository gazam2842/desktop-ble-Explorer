"""Scan result filter match logic (pure logic, no PyQt dependency)."""


def matches(name: str, address: str, query: str, scope: str) -> bool:
    """Determine whether a device matches the filter.

    Always True if query is empty after stripping whitespace (filter inactive).
    Case-insensitive substring match. scope: "name" | "mac" | "both".
    """
    q = query.strip().lower()
    if not q:
        return True
    name_l = (name or "").lower()
    addr_l = (address or "").lower()
    if scope == "name":
        return q in name_l
    if scope == "mac":
        return q in addr_l
    # both (default)
    return q in name_l or q in addr_l
