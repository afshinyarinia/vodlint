from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import m3u8

from .models import Finding, add_error, finalize_report, new_report, redact_location
from .network import MAX_REQUESTS, MAX_RESOURCE_BYTES, MAX_TOTAL_BYTES, HttpClient, ResourceError
from .parsers.sniff import sniff_container
from .rules import is_master, parse_manifest


@dataclass(frozen=True)
class AnalyzerConfig:
    segments_to_sample: int = 0
    http_timeout_seconds: float = 10.0
    http_retries: int = 2
    require_vod: bool = True
    fail_on: str = "warning"
    max_resource_bytes: int = MAX_RESOURCE_BYTES
    max_total_bytes: int = MAX_TOTAL_BYTES
    max_requests: int = MAX_REQUESTS

    def __post_init__(self):
        if not isinstance(self.segments_to_sample, int) or self.segments_to_sample < 0:
            raise ValueError("segments_to_sample must be a nonnegative integer")
        if self.fail_on not in ("warning", "error"):
            raise ValueError("fail_on must be warning or error")


def _playlist_info(pl: m3u8.M3U8, url: str) -> dict[str, Any]:
    master = is_master(pl)
    methods = sorted(
        {seg.key.method for seg in pl.segments if seg.key and seg.key.method != "NONE"}
    )
    return {
        "url": redact_location(url),
        "kind": "master" if master else "media",
        "is_live": None if master else not pl.is_endlist,
        "version": pl.version,
        "media_sequence": None if master else pl.media_sequence,
        "segment_count": None if master else len(pl.segments),
        "duration": None if master else math.fsum(seg.duration for seg in pl.segments),
        "target_duration": float(pl.target_duration) if pl.target_duration else None,
        "encryption_methods": methods,
        "has_init_map": any(seg.init_section for seg in pl.segments),
    }


def _variants(pl: m3u8.M3U8) -> list[dict[str, Any]]:
    variants = []
    for playlist in pl.playlists:
        info = playlist.stream_info
        resolution = getattr(info, "resolution", None)
        variants.append(
            {
                "bandwidth": getattr(info, "bandwidth", None),
                "program_id": getattr(info, "program_id", None),
                "resolution": f"{resolution[0]}x{resolution[1]}" if resolution else None,
                "codecs": getattr(info, "codecs", None),
                "uri": redact_location(playlist.uri),
            }
        )
    return variants


def _load(client, location, report, config):
    try:
        resource = client.fetch(location, max_bytes=2 * 1024 * 1024)
    except ResourceError as error:
        add_error(report, "resource.fetch", location, str(error))
        return None
    report["summary"]["manifests_checked"] += 1
    try:
        text = resource.data.decode("utf-8")
    except UnicodeDecodeError:
        report["findings"].append(
            Finding(
                "manifest.encoding",
                "error",
                "Manifest is not valid UTF-8.",
                "Encode the manifest as UTF-8 without a byte order mark.",
                resource.location,
            ).to_dict()
        )
        return None
    pl, findings = parse_manifest(text, resource.location, config.require_vod)
    report["findings"].extend(finding.to_dict() for finding in findings)
    return (pl, resource.location) if pl is not None else None


def _resolve_uri(resource, location, report, segment_index=None):
    try:
        if not resource.uri or not resource.uri.strip():
            raise ValueError
        uri = resource.absolute_uri
        parts = urlsplit(uri)
        if parts.scheme in ("http", "https"):
            if not parts.hostname:
                raise ValueError
            parts.port  # Validate port syntax/range without initiating a fetch.
        return uri
    except (ValueError, TypeError):
        report["findings"].append(
            Finding(
                "manifest.syntax",
                "error",
                "A resource URI is missing or malformed.",
                "Supply a valid relative URI or absolute HTTP(S)/file URI.",
                location,
                segment_index,
            ).to_dict()
        )
        return None


def _ranges(pl, location, report):
    ranges = []
    uris = []
    previous_uri = None
    previous_end = None
    for index, segment in enumerate(pl.segments):
        uri = _resolve_uri(segment, location, report, index)
        uris.append(uri)
        value = segment.byterange
        current = None
        if uri is None:
            current = False
        elif value is not None:
            try:
                match = re.fullmatch(r"([1-9]\d*)(?:@(\d+))?", value)
                if match is None:
                    raise ValueError
                length = int(match[1])
                if match[2] is not None:
                    start = int(match[2])
                elif uri == previous_uri and previous_end is not None:
                    start = previous_end
                else:
                    raise ValueError
                current = (start, length)
            except ValueError:
                report["findings"].append(
                    Finding(
                        "manifest.byterange",
                        "error",
                        "Invalid byte range or missing same-resource preceding offset.",
                        "Declare a positive length and an explicit offset after resource changes.",
                        location,
                        index,
                    ).to_dict()
                )
                current = False
        ranges.append(current)
        previous_uri = uri
        previous_end = current[0] + current[1] if current else None
    return ranges, uris


def _probe_media(client, pl, location, variant_index, report, config):
    info = _playlist_info(pl, location)
    info["variant_index"] = variant_index
    report["media_playlists"].append(info)
    ranges, uris = _ranges(pl, location, report)
    count = min(config.segments_to_sample, len(pl.segments))
    report["summary"]["segments_requested"] += count
    for index, segment in enumerate(pl.segments[:count]):
        url = uris[index] or location
        byte_range = ranges[index]
        probe = {
            "variant_index": variant_index,
            "segment_index": index,
            "url": redact_location(url),
            "container": "unknown",
            "size_bytes": 0,
            "byte_range": (
                {"offset": byte_range[0], "length": byte_range[1]} if byte_range else None
            ),
            "status": "skipped",
        }
        report["segment_probes"].append(probe)
        if byte_range is False:
            continue
        encrypted = segment.key and segment.key.method != "NONE"
        if encrypted or segment.init_section:
            rule_id = "segment.encrypted" if encrypted else "segment.unsupported"
            report["findings"].append(
                Finding(
                    rule_id,
                    "warning",
                    "Encrypted or initialization-dependent media was not inspected.",
                    "Use a decoder that supports this media to complete payload validation.",
                    url,
                    index,
                ).to_dict()
            )
            continue
        try:
            content = client.fetch(url, byte_range=byte_range).data
        except ResourceError as error:
            probe["status"] = "error"
            add_error(report, "resource.fetch", url, str(error))
            continue
        probe["container"] = sniff_container(content)
        probe["size_bytes"] = len(content)
        probe["status"] = "inspected" if probe["container"] != "unknown" else "unsupported"
        if probe["status"] == "unsupported":
            report["findings"].append(
                Finding(
                    "segment.unsupported",
                    "warning",
                    "Segment container is unsupported, truncated, or unrecognized.",
                    "Verify the resource and inspect it with a compatible media decoder.",
                    url,
                    index,
                ).to_dict()
            )


def analyze_playlist(
    playlist_location: str,
    segments_to_sample: int = 0,
    http_timeout_seconds: float = 10.0,
    http_retries: int = 2,
    *,
    require_vod: bool = True,
    fail_on: str = "warning",
    max_resource_bytes: int = MAX_RESOURCE_BYTES,
    max_total_bytes: int = MAX_TOTAL_BYTES,
    max_requests: int = MAX_REQUESTS,
) -> dict[str, Any]:
    """Validate manifests and optionally identify the first N segment containers.

    Returns schema-v1 JSON-compatible data, including partial results on expected
    resource failures. Invalid API configuration raises ValueError.
    """
    config = AnalyzerConfig(
        segments_to_sample,
        http_timeout_seconds,
        http_retries,
        require_vod,
        fail_on,
        max_resource_bytes,
        max_total_bytes,
        max_requests,
    )
    report = new_report(playlist_location, segments_to_sample)
    with HttpClient(
        timeout_seconds=http_timeout_seconds,
        retries=http_retries,
        max_resource_bytes=max_resource_bytes,
        max_total_bytes=max_total_bytes,
        max_requests=max_requests,
    ) as client:
        loaded = _load(client, playlist_location, report, config)
        if loaded:
            pl, location = loaded
            report["playlist"] = _playlist_info(pl, location)
            report["variants"] = _variants(pl)
            if not is_master(pl):
                _probe_media(client, pl, location, None, report, config)
            else:
                references = list(enumerate(pl.playlists))
                references.extend((None, p) for p in pl.iframe_playlists)
                references.extend((None, p) for p in pl.media if p.uri)
                seen = set()
                for index, reference in references:
                    uri = _resolve_uri(reference, location, report)
                    if uri is None:
                        continue
                    if uri in seen:
                        continue
                    seen.add(uri)
                    child = _load(client, uri, report, config)
                    if child:
                        media, child_location = child
                        if is_master(media):
                            report["findings"].append(
                                Finding(
                                    "manifest.nested-master",
                                    "error",
                                    "A master references another master instead of media.",
                                    "Reference a media playlist directly.",
                                    child_location,
                                ).to_dict()
                            )
                        else:
                            _probe_media(client, media, child_location, index, report, config)
    return finalize_report(report, config.fail_on)
