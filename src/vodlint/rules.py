from __future__ import annotations

import math
import re
from collections import Counter

import m3u8

from .models import Finding

MASTER_TAGS = {
    "#EXT-X-STREAM-INF",
    "#EXT-X-I-FRAME-STREAM-INF",
    "#EXT-X-MEDIA",
    "#EXT-X-SESSION-DATA",
    "#EXT-X-SESSION-KEY",
}
MEDIA_TAGS = {
    "#EXTINF",
    "#EXT-X-TARGETDURATION",
    "#EXT-X-MEDIA-SEQUENCE",
    "#EXT-X-ENDLIST",
    "#EXT-X-PLAYLIST-TYPE",
    "#EXT-X-BYTERANGE",
    "#EXT-X-KEY",
    "#EXT-X-MAP",
    "#EXT-X-DISCONTINUITY",
}


def is_master(pl: m3u8.M3U8) -> bool:
    return bool(pl.is_variant or pl.media or pl.iframe_playlists)


def parse_manifest(
    text: str, location: str, require_vod: bool
) -> tuple[m3u8.M3U8 | None, list[Finding]]:
    """Parse and evaluate the documented manifest rules, without any I/O."""
    findings: list[Finding] = []

    def error(rule_id, message, remediation):
        findings.append(Finding(rule_id, "error", message, remediation, location))

    lines = text.splitlines()
    if not lines or lines[0] != "#EXTM3U":
        error("manifest.header", "Missing first-line #EXTM3U header.", "Provide an HLS manifest.")
        return None, findings
    tags = Counter(line.split(":", 1)[0] for line in lines if line.startswith("#EXT"))
    master = bool(tags.keys() & MASTER_TAGS)
    if master and tags.keys() & MEDIA_TAGS:
        error(
            "manifest.mixed",
            "Master and media playlist tags are mixed.",
            "Separate master references from media segment declarations.",
        )
        return None, findings
    singletons = {
        "#EXTM3U",
        "#EXT-X-VERSION",
        "#EXT-X-TARGETDURATION",
        "#EXT-X-MEDIA-SEQUENCE",
        "#EXT-X-DISCONTINUITY-SEQUENCE",
        "#EXT-X-ENDLIST",
        "#EXT-X-PLAYLIST-TYPE",
    }
    if any(tags[tag] > 1 for tag in singletons):
        error("manifest.syntax", "A singleton tag is repeated.", "Keep one instance of each tag.")
    pending = False
    target = None
    durations = []
    version = 1
    for raw_line in lines[1:]:
        line = raw_line.strip()
        if not line or (line.startswith("#") and not line.startswith("#EXT")):
            continue
        tag, _, value = line.partition(":")
        if tag in ("#EXTINF", "#EXT-X-STREAM-INF"):
            if pending:
                error("manifest.syntax", "A declaration has no URI.", "Add its resource URI.")
            pending = True
        elif not line.startswith("#"):
            if not pending:
                error("manifest.syntax", "A URI has no declaration.", "Declare its EXTINF/stream.")
            pending = False
        if tag == "#EXTINF":
            try:
                duration = float(value.split(",", 1)[0])
                if not math.isfinite(duration) or duration <= 0:
                    raise ValueError
                durations.append(duration)
            except ValueError:
                error(
                    "manifest.segment-duration",
                    "Segment duration must be finite and positive.",
                    "Correct the EXTINF duration.",
                )
        if tag in ("#EXT-X-VERSION", "#EXT-X-TARGETDURATION"):
            try:
                if not re.fullmatch(r"[1-9]\d*", value):
                    raise ValueError
                number = int(value)
                if not math.isfinite(float(number)):
                    raise ValueError
                if tag == "#EXT-X-TARGETDURATION":
                    target = number
                else:
                    version = number
            except (ValueError, OverflowError):
                error(
                    (
                        "manifest.target-duration"
                        if tag.endswith("TARGETDURATION")
                        else "manifest.version"
                    ),
                    "Tag value must be a representable positive integer.",
                    "Correct the declared integer value.",
                )
    if pending:
        error("manifest.syntax", "A declaration has no URI.", "Add its resource URI.")
    try:
        if not math.isfinite(math.fsum(durations)):
            raise OverflowError
    except OverflowError:
        error(
            "manifest.segment-duration",
            "Total declared duration exceeds supported numeric bounds.",
            "Use finite, representable segment and playlist durations.",
        )
    if not master:
        if not durations:
            error(
                "manifest.empty", "Media playlist has no valid segments.", "Declare media segments."
            )
        if target is None or any(math.floor(duration + 0.5) > target for duration in durations):
            error(
                "manifest.target-duration",
                "Target duration is missing or less than a rounded segment duration.",
                "Set EXT-X-TARGETDURATION to cover the rounded EXTINF durations.",
            )
        if require_vod and not tags["#EXT-X-ENDLIST"]:
            error(
                "manifest.endlist",
                "VOD media playlist is unfinished.",
                "Add EXT-X-ENDLIST or use --allow-live for intentional live input.",
            )
        if tags["#EXT-X-BYTERANGE"] and version < 4:
            error("manifest.version", "Byte ranges require version >=4.", "Correct EXT-X-VERSION.")
    try:
        pl = m3u8.loads(text, uri=location)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError):
        error("manifest.syntax", "Manifest could not be parsed.", "Correct the manifest syntax.")
        return None, findings
    for key in pl.keys:
        if key and key.method != "NONE" and not key.uri:
            error(
                "manifest.syntax",
                "An encryption declaration has no key URI.",
                "Supply URI when EXT-X-KEY declares an encryption method.",
            )
    if master:
        if not (pl.playlists or pl.iframe_playlists or any(media.uri for media in pl.media)):
            error(
                "manifest.empty", "Master has no media references.", "Declare at least one stream."
            )
        for playlist in [*pl.playlists, *pl.iframe_playlists]:
            info = getattr(playlist, "stream_info", None) or getattr(
                playlist, "iframe_stream_info", None
            )
            if not playlist.uri or not info or not info.bandwidth or info.bandwidth <= 0:
                error(
                    "manifest.variant",
                    "A stream lacks a URI or positive bandwidth.",
                    "Supply URI and BANDWIDTH for each stream.",
                )
    return (None if findings else pl), findings
