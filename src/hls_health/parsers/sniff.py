from __future__ import annotations

from typing import Literal

Container = Literal["ts", "adts", "unknown"]


def sniff_container(data: bytes) -> Container:
	if not data or len(data) < 4:
		return "unknown"
	# MPEG-TS packets usually start with 0x47 and repeat every 188 bytes
	if (
		data[0] == 0x47
		and (len(data) >= 188 and data[188] == 0x47 or len(data) >= 376 and data[376] == 0x47)
	):
		return "ts"
	# ADTS AAC sync word: 12 bits '1111 1111 1111' -> 0xFFF
	if (data[0] == 0xFF) and (data[1] & 0xF0 == 0xF0):
		return "adts"
	return "unknown"
