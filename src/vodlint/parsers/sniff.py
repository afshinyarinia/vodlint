from __future__ import annotations

from typing import Literal

Container = Literal["ts", "adts", "unknown"]


def sniff_container(data: bytes) -> Container:
    """Identify signatures, without claiming that the media decodes correctly."""
    # Check only complete packets; never index a packet that is not present.
    packets = min(len(data) // 188, 3)
    if packets >= 2 and all(data[index * 188] == 0x47 for index in range(packets)):
        return "ts"

    # Packed audio can have a leading ID3v2 tag with a synchsafe size.
    if data.startswith(b"ID3"):
        if len(data) < 10 or any(value & 0x80 for value in data[6:10]):
            return "unknown"
        size = sum(value << shift for value, shift in zip(data[6:10], (21, 14, 7, 0)))
        footer = 10 if data[3] == 4 and data[5] & 0x10 else 0
        data = data[10 + size + footer :]

    # ADTS has a 12-bit sync, layer zero, and a valid sampling-frequency index.
    if len(data) >= 7 and data[0] == 0xFF and data[1] & 0xF6 == 0xF0:
        frequency_index = (data[2] >> 2) & 0x0F
        frame_length = ((data[3] & 0x03) << 11) | (data[4] << 3) | (data[5] >> 5)
        header_length = 7 if data[1] & 1 else 9
        if frequency_index <= 12 and header_length <= frame_length <= len(data):
            return "adts"
    return "unknown"
