# VoDLint

A small HLS VOD manifest validator with optional segment-container sampling,
designed for CI pipelines. Python 3.11+; MIT licensed.

VoDLint evaluates the checks listed below, emits actionable findings, and returns
a meaningful process status. Container sampling identifies signatures; it does
not decode media or measure playback timing.

## Installation

Install the published package from [PyPI](https://pypi.org/project/vodlint/):

```bash
python -m pip install vodlint
```

To install version 0.2.0 specifically:

```bash
python -m pip install "vodlint==0.2.0"
```

Verify the installation with `vodlint --version`. Python 3.11 or newer is required.

## Five-minute quick start

Download [valid.m3u8](https://raw.githubusercontent.com/afshinyarinia/vodlint/main/examples/valid.m3u8)
and [invalid-target-duration.m3u8](https://raw.githubusercontent.com/afshinyarinia/vodlint/main/examples/invalid-target-duration.m3u8)
(save each link with its filename), then run these commands in the download directory:

```bash
vodlint valid.m3u8
vodlint invalid-target-duration.m3u8
```

The first prints `PASSED` and exits **0**; its declared duration is 11 seconds.
The second prints `FAILED` with rule **manifest.target-duration** and exits **1**:
its 12-second segment exceeds its target duration of 10 seconds. Check the exit
status immediately after each command with `echo $?` in bash or `$LASTEXITCODE`
in PowerShell. Use `--json` for structured findings and remediation messages.

These examples validate manifests only. Their segment files are deliberately
absent. A pass here establishes that the implemented manifest checks passed;
it does not establish segment availability or playback. For actual media, use
`-s N` to fetch the first N segments per media playlist and identify supported
container signatures. Sampling does not decode media, measure timing or check
every segment; the JSON summary reports its scope and completeness.

## Install from source

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

Start with the [ready-to-copy GitHub Actions workflow](.github/workflows/example-validation.yml)
and [integration guide](docs/ci-integration.md). The workflow installs the published
0.2.0 package, validates a checked-in manifest and retains its JSON report on failure.

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
| `resources` | Ordered manifest/sample inspection inventory, including failures, skips and duplicate references (next release) |
| `findings` | rule_id, severity, message, remediation, url, segment_index |
| `errors` | code, url, message; expected operational/usage failures |
| `summary` | Scope, counts, inspection completion, and whether every declared segment was sampled |

Master `is_live`, `segment_count`, `duration`, and `media_sequence` are null.
Media duration is declared, not measured. Probe byte ranges include
`offset` and `length`; probe sizes refer to fetched range bytes.

Sample outcomes are counted separately in the summary: `segments_checked` for
inspected signatures, `segments_unsupported` for unrecognized/truncated media,
`segments_skipped` for samples deliberately not fetched/inspected, and
`segments_failed` for resource errors. These four counts sum to
`segments_requested`, the samples selected from validated media playlists.
All are zero when sampling is disabled. Encrypted and initialization-dependent
media count as skipped, even if their finding uses `segment.unsupported`.
The new count is additive within schema version 1 and does not change severity
thresholds, exit codes or completeness flags.

`summary.inspection_complete` means the requested scope finished without
manifest errors, resource failures, or unsupported/skipped samples. It does **not** mean every
segment was inspected, nor that the content plays. `all_segments_sampled`
separately identifies complete signature sampling. An invalid child prevents
both coverage flags from claiming completeness. Errors take precedence over lint failure.

Within schema version 1, consumers should tolerate new fields and rule IDs.
Removing fields or changing their types requires a new schema version.

The next release adds a schema-v1 [resource inventory](docs/resource-inventory.md)
with redacted locations, outcomes and parent/duplicate links. It lists only
manifests and selected samples; an entry does not imply its content was fetched.
The published 0.2.0 package retains its original report fields.

## Development and contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), [architecture notes](project-detail.md),
and [CHANGELOG.md](CHANGELOG.md). Bugs and feature requests belong in
[GitHub Issues](https://github.com/afshinyarinia/vodlint/issues).
See our [code of conduct](CODE_OF_CONDUCT.md) and report vulnerabilities using
the [private security reporting channel](SECURITY.md).

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Installation fails or no matching distribution | Check `python --version` (3.11+ required). Use a virtual environment and install with that interpreter's `python -m pip`. |
| `vodlint` command is not found | Activate the environment where you installed it, or run `python -m vodlint.cli --version` with that interpreter. |
| Exit 2 / resource or byte limit | Inspect `errors` in JSON. Check paths, network access and range support; increase the relevant `--max-resource-bytes`, `--max-total-bytes` or `--max-requests` only for a known workload. Manifests also have a fixed 2 MiB cap. |
| Unsupported or encrypted sample | Inspect the resource with a compatible decoder. These warnings fail the default threshold. `--fail-on error` permits warnings but leaves incomplete inspection visible. |
| Private/signed URL | Keep credentials in secrets/environment variables, quote the variable, and avoid shell tracing. Reports can still reveal private path segments; review before sharing. See the CI guide. |

When reporting a bug, use the issue form and a small sanitized reproduction.
Never include credentials, signed URL tokens, private media or keys in public issues.
