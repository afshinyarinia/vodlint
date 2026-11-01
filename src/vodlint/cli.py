from __future__ import annotations

import argparse
import json
import math
import os
import sys

from . import __version__
from .analyzer import analyze_playlist
from .models import add_error, finalize_report, new_report
from .network import MAX_REQUESTS, MAX_RESOURCE_BYTES, MAX_TOTAL_BYTES


class UsageError(ValueError):
    """An invocation error that main can render as text or JSON."""


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def nonnegative_integer(value: str) -> int:
    try:
        number = int(value)
        if number < 0:
            raise ValueError
        return number
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a nonnegative integer") from error


def positive_integer(value: str) -> int:
    number = nonnegative_integer(value)
    if number == 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def positive_timeout(value: str) -> float:
    try:
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise ValueError
        return number
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero") from error


def build_parser() -> argparse.ArgumentParser:
    parser = ArgumentParser(description="Validate HLS VOD manifests and sample segment containers")
    parser.add_argument("url", help="HTTP(S) URL or local path to an .m3u8 playlist")
    parser.add_argument(
        "-s",
        "--segments",
        type=nonnegative_integer,
        default=0,
        help="First N segments per media playlist to sample (default: manifests only)",
    )
    parser.add_argument("--json", action="store_true", help="Emit schema-v1 JSON, including errors")
    parser.add_argument(
        "--timeout",
        type=positive_timeout,
        default=os.environ.get("VODLINT_TIMEOUT", "10"),
        help="HTTP connect/read inactivity timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--retries",
        type=nonnegative_integer,
        default=os.environ.get("VODLINT_RETRIES", "2"),
        help="Additional HTTP attempts for transient failures (default: 2)",
    )
    parser.add_argument("--allow-live", action="store_true", help="Allow media without ENDLIST")
    parser.add_argument(
        "--fail-on",
        choices=("warning", "error"),
        default="warning",
        help="Minimum finding severity that fails validation (default: warning)",
    )
    parser.add_argument("--max-resource-bytes", type=positive_integer, default=MAX_RESOURCE_BYTES)
    parser.add_argument("--max-total-bytes", type=positive_integer, default=MAX_TOTAL_BYTES)
    parser.add_argument("--max-requests", type=positive_integer, default=MAX_REQUESTS)
    parser.add_argument("-v", "--version", action="version", version=f"vodlint {__version__}")
    return parser


def _text_report(report):
    print(f"{report['status'].upper()}: {report['source']}")
    playlist = report["playlist"]
    if playlist:
        print(
            f"  kind: {playlist['kind']}  live: {playlist['is_live']}  "
            f"duration: {playlist['duration']}"
        )
    summary = report["summary"]
    print(
        f"  scope: {summary['scope']}  manifests: {summary['manifests_checked']}  "
        f"segments checked: {summary['segments_checked']}/{summary['segment_count']}"
    )
    for finding in report["findings"]:
        print(f"  {finding['severity']} [{finding['rule_id']}] {finding['url']}")
        print(f"    {finding['message']} {finding['remediation']}")
    for error in report["errors"]:
        print(f"  error [{error['code']}] {error['url']}: {error['message']}")


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    try:
        args = parser.parse_args(arguments)
        report = analyze_playlist(
            playlist_location=args.url,
            segments_to_sample=args.segments,
            http_timeout_seconds=args.timeout,
            http_retries=args.retries,
            require_vod=not args.allow_live,
            fail_on=args.fail_on,
            max_resource_bytes=args.max_resource_bytes,
            max_total_bytes=args.max_total_bytes,
            max_requests=args.max_requests,
        )
    except ValueError as error:
        report = new_report("")
        add_error(report, "cli.usage", "", str(error))
        finalize_report(report)
    if "--json" in arguments:
        print(json.dumps(report, indent=2, allow_nan=False))
    else:
        _text_report(report)
    return {"passed": 0, "failed": 1, "error": 2}[report["status"]]


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
