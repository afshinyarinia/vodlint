import json
from pathlib import Path

import pytest

from vodlint.cli import main


@pytest.mark.parametrize(
    ("filename", "exit_code", "status"),
    [("valid.m3u8", 0, "passed"), ("invalid-target-duration.m3u8", 1, "failed")],
)
def test_downloadable_examples_have_documented_outcomes(filename, exit_code, status, capsys):
    fixture = Path(__file__).resolve().parents[1] / "examples" / filename
    assert main([str(fixture), "--json"]) == exit_code
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == status
    assert report["summary"]["scope"] == "manifests"
    if exit_code:
        assert {f["rule_id"] for f in report["findings"]} == {"manifest.target-duration"}
    else:
        assert report["playlist"]["duration"] == 11.0
