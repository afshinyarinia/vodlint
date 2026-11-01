import pytest

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
    buf = bytes.fromhex("fff15080013ffc0000")  # 9-byte ADTS frame
    assert sniff_container(buf) == "adts"


@pytest.mark.parametrize("length", [4, 187, 188, 189, 375, 376])
def test_truncated_or_invalid_ts_is_unknown(length):
    assert sniff_container(bytes([0x47]) + bytes(length - 1)) == "unknown"


@pytest.mark.parametrize("data", ["fffb9064", "fff15080", "fff13c80013ffc0000"])
def test_mp3_truncated_adts_and_reserved_frequency_are_not_adts(data):
    assert sniff_container(bytes.fromhex(data)) == "unknown"


def test_packed_audio_skips_id3_metadata():
    tag = b"ID3\x04\x00\x00\x00\x00\x00\x00"
    assert sniff_container(tag + bytes.fromhex("fff15080013ffc0000")) == "adts"


def test_incomplete_id3_is_unknown():
    assert sniff_container(b"ID3\x04\x00\x00\x7f\x7f\x7f\x7f") == "unknown"
