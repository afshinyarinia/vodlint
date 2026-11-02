from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from . import __version__

Severity = Literal["warning", "error"]


def redact_location(location: str) -> str:
    """Remove URL credentials, query values and fragments from diagnostics."""
    try:
        parts = urlsplit(location)
        return urlunsplit(
            (
                parts.scheme,
                parts.netloc.rsplit("@", 1)[-1],
                parts.path,
                "REDACTED" if parts.query else "",
                "",
            )
        )
    except ValueError:
        return "<invalid location>"


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: Severity
    message: str
    remediation: str
    url: str
    segment_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "url": redact_location(self.url)}


def new_report(source: str, segments: int = 0) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "tool_version": __version__,
        "source": redact_location(source),
        "status": "error",
        "playlist": None,
        "variants": [],
        "media_playlists": [],
        "segment_probes": [],
        "findings": [],
        "errors": [],
        "summary": {
            "scope": "sampled_segments" if segments else "manifests",
            "manifests_checked": 0,
            "segments_requested": 0,
        },
    }


def add_error(report: dict[str, Any], code: str, url: str, message: str):
    report["errors"].append({"code": code, "url": redact_location(url), "message": message})


def finalize_report(report: dict[str, Any], fail_on: Severity = "warning") -> dict[str, Any]:
    findings = report["findings"]
    probes = report["segment_probes"]
    segment_count = sum(p["segment_count"] for p in report["media_playlists"])
    checked = sum(p["status"] == "inspected" for p in probes)
    valid_manifests = not any(
        finding["severity"] == "error" and finding["rule_id"].startswith("manifest.")
        for finding in findings
    )
    report["summary"].update(
        {
            "segment_count": segment_count,
            "segments_checked": checked,
            "segments_unsupported": sum(p["status"] == "unsupported" for p in probes),
            "segments_failed": sum(p["status"] == "error" for p in probes),
            "segments_skipped": sum(p["status"] == "skipped" for p in probes),
            "error_count": len(report["errors"]),
            "finding_counts": {
                severity: sum(f["severity"] == severity for f in findings)
                for severity in ("warning", "error")
            },
            "inspection_complete": not report["errors"]
            and valid_manifests
            and all(p["status"] == "inspected" for p in probes),
            "all_segments_sampled": bool(segment_count)
            and checked == segment_count
            and valid_manifests
            and not report["errors"],
        }
    )
    failing = any(f["severity"] == "error" or fail_on == "warning" for f in findings)
    report["status"] = "error" if report["errors"] else "failed" if failing else "passed"
    return report
