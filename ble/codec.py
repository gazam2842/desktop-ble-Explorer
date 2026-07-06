"""Hex / String / Byte ↔ bytes conversion (pure logic)."""


class InvalidFormatError(ValueError):
    """Raised when user input cannot be interpreted in the given format."""


def encode(text: str, fmt: str) -> bytes:
    """Convert a user input string to bytes. Raises InvalidFormatError on failure."""
    if fmt == "hex":
        cleaned = text.replace(" ", "").replace(",", "")
        if cleaned == "":
            return b""
        if len(cleaned) % 2 != 0:
            raise InvalidFormatError("Hex must have an even number of digits")
        try:
            return bytes.fromhex(cleaned)
        except ValueError as exc:
            raise InvalidFormatError(f"Invalid hex input: {text!r}") from exc
    if fmt == "string":
        return text.encode("utf-8")
    if fmt == "byte":
        tokens = [t for t in text.replace(",", " ").split() if t]
        result = bytearray()
        for tok in tokens:
            try:
                value = int(tok)
            except ValueError as exc:
                raise InvalidFormatError(f"Invalid byte input: {tok!r}") from exc
            if not 0 <= value <= 255:
                raise InvalidFormatError(f"Byte value must be in range 0-255: {value}")
            result.append(value)
        return bytes(result)
    raise InvalidFormatError(f"Unknown format: {fmt!r}")


def decode(data: bytes, fmt: str) -> str:
    """Convert bytes to a display string. Avoids raising exceptions where possible since it's for display purposes."""
    if fmt == "hex":
        return " ".join(f"{b:02X}" for b in data)
    if fmt == "string":
        return data.decode("utf-8", errors="replace")
    if fmt == "byte":
        return " ".join(str(b) for b in data)
    raise InvalidFormatError(f"Unknown format: {fmt!r}")
