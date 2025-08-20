from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import m3u8

from .network import HttpClient
from .parsers.sniff import sniff_container


@dataclass
class AnalyzerConfig:
	segments_to_sample: int = 0
	http_timeout_seconds: float = 10.0
	http_retries: int = 2


def _playlist_info(pl: m3u8.M3U8, url: str) -> Dict[str, Any]:
	is_live = pl.is_endlist is False
	segment_count = len(pl.segments or [])
	media_sequence = getattr(pl, "media_sequence", None)
	version = getattr(pl, "version", None)
	return {
		"url": url,
		"is_live": is_live,
		"version": version,
		"media_sequence": media_sequence,
		"segment_count": segment_count,
		"duration": float(pl.target_duration * segment_count) if pl.target_duration else None,
		"target_duration": float(pl.target_duration) if pl.target_duration else None,
	}


def _variants(pl: m3u8.M3U8) -> List[Dict[str, Any]]:
	variants: List[Dict[str, Any]] = []
	for p in pl.playlists or []:
		stream_info = p.stream_info or {}
		variants.append(
			{
				"bandwidth": getattr(stream_info, "bandwidth", None),
				"program_id": getattr(stream_info, "program_id", None),
				"resolution": getattr(stream_info, "resolution", None),
				"codecs": getattr(stream_info, "codecs", None),
				"uri": p.uri,
			}
		)
	return variants


def analyze_playlist(
	playlist_location: str,
	segments_to_sample: int = 0,
	http_timeout_seconds: float = 10.0,
	http_retries: int = 2,
) -> Dict[str, Any]:
	client = HttpClient(timeout_seconds=http_timeout_seconds, retries=http_retries)
	pl = m3u8.load(playlist_location)
	result: Dict[str, Any] = {
		"playlist": _playlist_info(pl, playlist_location),
		"variants": _variants(pl),
	}

	if segments_to_sample <= 0:
		return result

	segment_probes: List[Dict[str, Any]] = []
	if pl.is_variant:
		for vidx, v in enumerate(pl.playlists or []):
			media = m3u8.load(v.absolute_uri)
			for sidx, seg in enumerate(list(media.segments)[: segments_to_sample]):
				url = seg.absolute_uri
				content = client.get_bytes(url)
				container = sniff_container(content)
				segment_probes.append(
					{
						"variant_index": vidx,
						"segment_index": sidx,
						"url": url,
						"container": container,
						"size_bytes": len(content),
					}
				)
	else:
		for sidx, seg in enumerate(list(pl.segments)[: segments_to_sample]):
			url = seg.absolute_uri
			content = client.get_bytes(url)
			container = sniff_container(content)
			segment_probes.append(
				{
					"variant_index": None,
					"segment_index": sidx,
					"url": url,
					"container": container,
					"size_bytes": len(content),
				}
			)

	result["segment_probes"] = segment_probes
	return result
