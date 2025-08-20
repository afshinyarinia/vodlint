from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .analyzer import analyze_playlist


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		description="Analyze HLS playlists and sample segments for health/timing info",
	)
	parser.add_argument("url", help="URL or file path to an .m3u8 playlist")
	parser.add_argument(
		"-s",
		"--segments",
		type=int,
		default=0,
		help="Number of segments per variant to sample (0 = no segment fetch)",
	)
	parser.add_argument("--json", action="store_true", help="Emit JSON instead of text output")
	parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
	parser.add_argument(
		"--retries", type=int, default=2, help="HTTP retry attempts for transient errors"
	)
	parser.add_argument(
		"-v",
		"--version",
		action="version",
		version=f"hls-health {__version__}",
	)
	return parser


def main(argv: list[str] | None = None) -> int:
	parser = build_parser()
	args = parser.parse_args(argv)

	report = analyze_playlist(
		playlist_location=args.url,
		segments_to_sample=max(0, args.segments),
		http_timeout_seconds=max(0.1, float(args.timeout)),
		http_retries=max(0, int(args.retries)),
	)

	if args.json:
		print(json.dumps(report, indent=2, sort_keys=False))
		return 0

	# Text output
	playlist = report["playlist"]
	print(f"Playlist: {playlist['url']}")
	live = playlist["is_live"]
	version = playlist.get("version")
	target_dur = playlist.get("target_duration")
	print(f"  live: {live}  version: {version}  target_dur: {target_dur}")
	
	media_seq = playlist.get("media_sequence")
	seg_count = playlist.get("segment_count")
	duration = playlist.get("duration")
	print(f"  media_sequence: {media_seq}  segments: {seg_count}  duration: {duration}")
	variants = report.get("variants", [])
	if variants:
		print("Variants:")
		for idx, v in enumerate(variants):
			bw = v.get("bandwidth")
			uri = v.get("uri")
			print(f"  [{idx}] bandwidth={bw} uri={uri}")
	segment_probes = report.get("segment_probes", [])
	if segment_probes:
		print("Segment probes:")
		for p in segment_probes:
			variant_idx = p.get("variant_index")
			seg_idx = p.get("segment_index")
			container = p.get("container")
			size_bytes = p.get("size_bytes")
			print(
				f"  variant={variant_idx} seg_index={seg_idx} "
				f"container={container} bytes={size_bytes}"
			)
	return 0


if __name__ == "__main__":  # pragma: no cover
	sys.exit(main())
