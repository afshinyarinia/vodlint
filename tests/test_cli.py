import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from vodlint.cli import build_parser, main


def write_playlist(tmp_path, text):
    path = tmp_path / "playlist.m3u8"
    path.write_text(text)
    return str(path)


def test_valid_manifest_returns_zero_and_versioned_json(tmp_path, media_text, capsys):
    assert main([write_playlist(tmp_path, media_text), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "passed"
    assert report["schema_version"] == "1"
    assert report["playlist"]["duration"] == 11.0


def test_invalid_manifest_returns_one(tmp_path, capsys):
    assert main([write_playlist(tmp_path, "not HLS"), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "failed"


def test_missing_file_returns_two_and_valid_json(tmp_path, capsys):
    assert main([str(tmp_path / "missing.m3u8"), "--json"]) == 2
    output = capsys.readouterr()
    assert json.loads(output.out)["status"] == "error"
    assert "Traceback" not in output.err


@pytest.mark.parametrize(
    "args",
    [
        ["--json"],
        ["unused", "--json", "--timeout", "nan"],
        ["unused", "--json", "--timeout", "inf"],
        ["unused", "--json", "--timeout", "0"],
        ["unused", "--json", "--segments", "-1"],
        ["unused", "--json", "--retries", "-1"],
        ["unused", "--json", "--max-resource-bytes", "0"],
        ["unused", "--json", "--unknown"],
    ],
)
def test_usage_errors_are_json_with_exit_two(args, capsys):
    assert main(args) == 2
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["status"] == "error"
    assert report["errors"][0]["code"] == "cli.usage"
    assert "Traceback" not in output.err


def test_environment_defaults_and_explicit_override(monkeypatch):
    monkeypatch.setenv("VODLINT_TIMEOUT", "30")
    monkeypatch.setenv("VODLINT_RETRIES", "5")
    args = build_parser().parse_args(["input"])
    assert args.timeout == 30
    assert args.retries == 5
    args = build_parser().parse_args(["input", "--timeout", "2", "--retries", "0"])
    assert args.timeout == 2
    assert args.retries == 0


def test_invalid_environment_setting_reports_usage_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VODLINT_TIMEOUT", "bad")
    assert main([str(tmp_path / "input"), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["errors"][0]["code"] == "cli.usage"


def test_cli_override_can_replace_invalid_environment_default(
    tmp_path, media_text, monkeypatch, capsys
):
    monkeypatch.setenv("VODLINT_TIMEOUT", "bad")
    assert main([write_playlist(tmp_path, media_text), "--timeout", "1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "passed"


def test_warning_threshold_and_allow_live(tmp_path, media_text, capsys):
    (tmp_path / "a.ts").write_bytes(b"unknown")
    path = write_playlist(tmp_path, media_text.replace("#EXT-X-ENDLIST\n", ""))
    assert main([path, "-s", "1", "--allow-live", "--json"]) == 1
    capsys.readouterr()
    assert main([path, "-s", "1", "--allow-live", "--fail-on", "error", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["inspection_complete"] is False


def test_text_output_includes_verdict_and_diagnostic(tmp_path, capsys):
    assert main([write_playlist(tmp_path, "not HLS")]) == 1
    output = capsys.readouterr().out
    assert "FAILED" in output
    assert "manifest.header" in output


@pytest.mark.parametrize(("content", "expected"), [("valid", 0), ("invalid", 1), ("missing", 2)])
def test_installed_entry_point_exit_codes_outside_checkout(tmp_path, media_text, content, expected):
    path = tmp_path / "input.m3u8"
    if content != "missing":
        path.write_text(media_text if content == "valid" else "invalid")
    executable = Path(sys.executable).parent / ("vodlint.exe" if os.name == "nt" else "vodlint")
    result = subprocess.run(
        [str(executable), str(path), "--json"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == expected, result.stderr
    assert json.loads(result.stdout)["status"] == {0: "passed", 1: "failed", 2: "error"}[expected]


def test_environment_retries_affect_real_manifest_fetch(
    http_server, monkeypatch, capsys, media_text
):
    monkeypatch.setenv("VODLINT_RETRIES", "1")
    http_server.routes["/input"] = lambda request, count: (
        (503, {}, b"retry") if count == 1 else media_text.encode()
    )
    assert main([http_server.url + "/input", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "passed"
    assert http_server.counts["/input"] == 2


def test_extreme_numbers_return_lint_failure_and_json(tmp_path, capsys):
    text = "#EXTM3U\n#EXT-X-TARGETDURATION:" + "9" * 400
    text += "\n#EXTINF:1,\na.ts\n#EXT-X-ENDLIST\n"
    assert main([write_playlist(tmp_path, text), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "failed"
