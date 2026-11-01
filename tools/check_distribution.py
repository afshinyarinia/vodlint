"""Build-independent smoke checks of an installed wheel outside the checkout."""

import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main():
    output_directory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist")
    wheels = sorted(output_directory.glob("vodlint-*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Expected exactly one wheel in dist/; use a fresh output directory.")
    wheel = wheels[0].resolve()
    with tempfile.TemporaryDirectory(prefix="vodlint-wheel-") as directory:
        root = Path(directory)
        environment = root / "environment"
        venv.create(environment, with_pip=True)
        binaries = environment / ("Scripts" if os.name == "nt" else "bin")
        python = binaries / ("python.exe" if os.name == "nt" else "python")
        subprocess.run([str(python), "-m", "pip", "install", str(wheel)], cwd=root, check=True)
        executable = binaries / ("vodlint.exe" if os.name == "nt" else "vodlint")
        playlist = root / "sample.m3u8"
        segment = root / "sample.ts"
        segment.write_bytes((bytes([0x47]) + bytes(187)) * 2)
        valid = "#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nsample.ts\n#EXT-X-ENDLIST\n"
        for content, expected in ((valid, 0), ("not HLS", 1), (None, 2)):
            if content is None:
                playlist.unlink()
            else:
                playlist.write_text(content, encoding="utf-8")
            result = subprocess.run(
                [str(executable), str(playlist), "--json", "-s", "1"],
                cwd=root,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            if result.returncode != expected:
                raise SystemExit(
                    f"Unexpected exit {result.returncode}: {result.stdout} {result.stderr}"
                )
            report = json.loads(result.stdout)
            if report["status"] != {0: "passed", 1: "failed", 2: "error"}[expected]:
                raise SystemExit("Distribution status and exit code disagree.")
            if expected == 0 and report["segment_probes"][0]["container"] != "ts":
                raise SystemExit("Installed wheel did not inspect local TS bytes.")
        print("Installed wheel: valid/invalid/missing inputs returned 0/1/2 outside checkout.")


if __name__ == "__main__":
    main()
