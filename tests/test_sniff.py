from vodlint.parsers.sniff import sniff_container


def test_sniff_unknown_for_empty():
    assert sniff_container(b"") == "unknown"


def test_sniff_ts_signature():
    # Build 188*2 bytes with sync byte at 0 and 188
    buf = bytearray(188 * 2)
    buf[0] = 0x47
    buf[188] = 0x47
    assert sniff_container(bytes(buf)) == "ts"


def test_sniff_adts_signature():
    buf = bytes([0xFF, 0xF1, 0x50, 0x80])  # sync 0xFFF and typical ADTS header
    assert sniff_container(buf) == "adts"