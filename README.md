# VoDLint

A small HLS VOD manifest validator with optional segment-container sampling,
designed for CI pipelines. Python 3.11+; MIT licensed.

VoDLint evaluates the checks listed below, emits actionable findings, and returns
a meaningful process status. Container sampling identifies signatures; it does
not decode media or measure playback timing.

## Install from source

This describes the source version (0.2.0, unreleased):

```bash
git clone https://github.com/afshinyarinia/vodlint.git
cd vodlint
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
python -m pip install .
```

## Run in CI

```bash
# Validate a local master and all its direct media manifests:
vodlint path/to/master.m3u8 --json > report.json

# Also fetch and identify the first three segments per media playlist:
vodlint https://media.example.com/master.m3u8 -s 3 --json > report.json

# Offline, manifest-only example included in this checkout:
vodlint tests/fixtures/vod.m3u8 --json
```

Use the executable's exit status directly:

| Code | Meaning |
| --- | --- |
| 0 | No findings at or above the selected failure threshold |
| 1 | One or more lint findings reach the failure threshold |
| 2 | Usage or resource failure; inspection could not finish as requested |

The default failure threshold is **warning**. An unknown, encrypted, or
initialization-dependent sampled segment produces a warning and exit 1.
`--fail-on error` explicitly permits warnings; those warnings and incomplete
inspection remain visible in the report. Operational failures always return 2.

A master has no live/VOD status of its own. Each media playlist has its own
metadata in `media_playlists`. Media must contain `EXT-X-ENDLIST` by default;
use `--allow-live` for an intentional live/event snapshot.

## Checks and limits

| Rule ID | What it checks |
| --- | --- |
| `manifest.header` | First-line EXTM3U header |
| `manifest.encoding` | UTF-8 manifest encoding |
| `manifest.syntax` | Parser failures, duplicate singleton tags, URI/declaration pairing |
| `manifest.mixed` | Mixed master/media tags |
| `manifest.empty` | Missing media segments or master references |
| `manifest.target-duration` | Positive integer target covering rounded declared segment durations |
| `manifest.segment-duration` | Finite, positive EXTINF durations |
| `manifest.endlist` | Completed media playlists in default VOD mode |
| `manifest.version` | Positive version and byte-range compatibility |
| `manifest.variant` | Stream URI and positive bandwidth |
| `manifest.byterange` | Positive range length and correct implicit-offset predecessor |
| `manifest.nested-master` | Media references that incorrectly resolve to another master |
| `segment.unsupported` | Unrecognized/truncated or initialization-dependent sampled media |
| `segment.encrypted` | Sampled encrypted media that cannot be inspected |

Manifest findings have error severity; segment inspection limitations have
warning severity. These are a documented subset of HLS checks, not complete
protocol conformance validation. The relevant baseline syntax and duration/range
semantics are described in [RFC 8216](https://www.rfc-editor.org/rfc/rfc8216.html).

Declared duration sums EXTINF values. Master statistics are not fabricated from
one child. Direct variant, I-frame, and URI-bearing rendition manifests are
loaded and duplicate references are inspected once.

Without `-s`, **only manifests are fetched**; referenced segment availability and
payloads are not checked. With `-s N`, only the first N segments per unique media
playlist are sampled. MPEG-TS and ADTS AAC signatures are recognized; packed AAC
may have leading ID3 metadata. Encrypted and initialization-dependent samples
are skipped explicitly. Keys and init segments are not fetched. fMP4 decoding,
codec verification, PTS drift, keyframe alignment, full-stream validation, and
continuous live monitoring are not implemented.

HTTP responses and local reads are bounded. Defaults:

- Maximum manifest: 2 MiB, also subject to the resource limit.
- Maximum resource: 16 MiB.
- Total bytes read: 64 MiB, including redirect and retry response bodies.
- Resource fetches: 1,000, excluding transport retries and redirects.
- HTTP timeout: 10 seconds for connect/read inactivity; this is not a total-run deadline.
- Retries: two additional attempts for connection failures and HTTP 502/503/504.
- Each resource has bounded redirects; HTTP range responses must match the requested bytes.

Budget failures are operational errors, not passing inspections. A read may consume
one bounded chunk beyond a byte limit before rejection. URL credentials, queries,
and fragments are redacted from normal reports; URLs with secrets in path segments
should be kept private.

## Configuration

| Option | Default |
| --- | --- |
| `-s, --segments N` | 0, manifests only |
| `--json` | Text output |
| `--timeout SECONDS` | `VODLINT_TIMEOUT`, otherwise 10 |
| `--retries N` | `VODLINT_RETRIES`, otherwise 2 |
| `--allow-live` | Off |
| `--fail-on warning\|error` | warning |
| `--max-resource-bytes N` | 16777216 |
| `--max-total-bytes N` | 67108864 |
| `--max-requests N` | 1000 |
| `--version` | Show tool version |

Explicit CLI options override environment defaults. Invalid numeric settings
return usage error 2, including in JSON mode. Negative values are rejected.

## Python API

```python
from vodlint.analyzer import analyze_playlist

report = analyze_playlist(
    "path/to/master.m3u8",
    segments_to_sample=2,
    http_timeout_seconds=15,
    http_retries=1,
)
print(report["status"])  # passed, failed, or error
for finding in report["findings"]:
    print(finding["rule_id"], finding["message"], finding["remediation"])
```

Expected resource failures return structured errors with partial results.
Invalid API configuration raises `ValueError`.

## Report contract

JSON has `schema_version: "1"` and `tool_version`. Top-level fields are:

| Field | Meaning |
| --- | --- |
| `source` | Redacted input location |
| `status` | passed, failed, or error |
| `playlist` | Root metadata, or null if it could not be validated |
| `variants` | Master stream metadata; resolution is a string such as 640x480 |
| `media_playlists` | Validated media metadata with declared durations and variant indices |
| `segment_probes` | Sample results: inspected, unsupported, skipped, or error |
| `findings` | rule_id, severity, message, remediation, url, segment_index |
| `errors` | code, url, message; expected operational/usage failures |
| `summary` | Scope, counts, inspection completion, and whether every declared segment was sampled |

Master `is_live`, `segment_count`, `duration`, and `media_sequence` are null.
Media duration is declared, not measured. Probe byte ranges include
`offset` and `length`; probe sizes refer to fetched range bytes.

`summary.inspection_complete` means the requested scope finished without
manifest errors, resource failures, or unsupported/skipped samples. It does **not** mean every
segment was inspected, nor that the content plays. `all_segments_sampled`
separately identifies complete signature sampling. An invalid child prevents
both coverage flags from claiming completeness. Errors take precedence over lint failure.

Within schema version 1, consumers should tolerate new fields and rule IDs.
Removing fields or changing their types requires a new schema version.

## Development and contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), [architecture notes](project-detail.md),
and [CHANGELOG.md](CHANGELOG.md). Bugs and feature requests belong in
[GitHub Issues](https://github.com/afshinyarinia/vodlint/issues).
