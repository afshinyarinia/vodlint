# CI validation changes and evidence

This records pre-release verification on Windows on 2026-11-01. Version 0.2.0
was subsequently [released on 2026-11-02](https://github.com/afshinyarinia/vodlint/releases/tag/v0.2.0)
and [published to PyPI](https://pypi.org/project/vodlint/0.2.0/).

## Results

| Environment/check | Result |
| --- | --- |
| Python 3.11.15, m3u8 4.0.0, requests 2.32.5 | 100 tests passed |
| Python 3.12.13, m3u8 6.0.0, requests 2.34.2 | 100 tests passed |
| Python 3.14.7, m3u8 6.0.0, requests 2.34.2 | 100 tests passed |
| Coverage on Python 3.12, including branches | 92.04%; required threshold 85% |
| Ruff | Passed |
| Black | Passed; 15 files unchanged |
| git diff whitespace check | Passed |
| Wheel and source distribution | Built; Twine metadata checks passed |
| Installed wheel in a fresh environment, outside checkout | Valid/invalid/missing inputs returned 0/1/2; local TS sample inspected |
| Distribution inspection | Runtime code/version matched; no virtualenv or git contents bundled |
| README offline command | Passed; declared duration 11.0 seconds, explicit manifest-only scope |

CI now configures Windows and Linux across Python 3.11–3.14, a minimum-dependency
job, distribution checks on both systems, a coverage floor, and job timeouts.
Hosted results are recorded in [GitHub Actions](https://github.com/afshinyarinia/vodlint/actions).
The first hosted run exposed an installed-entry-point test assumption on global
Windows Python installations: console scripts live in the installation's Scripts
directory rather than beside python.exe. The test now uses sysconfig's scripts
path, supporting both global installations and virtual environments.

## Original findings addressed

REVIEW.md remains the historical baseline. The implementation and regression tests
address all nine findings:

| Finding | Result and regression coverage |
| --- | --- |
| 1. Invalid content succeeds | Manifest findings and stable verdict; malformed text, invalid durations, warnings and real process exit codes tested |
| 2. Playlist HTTP settings bypassed | One transport/session for root, child and segment fetches; real timeout/retry and cookie tests |
| 3. Sniffer crashes/mislabels | Safe TS bounds, complete ADTS header checks, MP3 rejection, ID3 handling |
| 4. Wrong duration | Sum declared EXTINF values; 11.0-second fixture and numeric overflow tests |
| 5. Master misclassification | Null intrinsic media fields, distinct child metadata, child fetching without sampling |
| 6. Local paths fail | Relative paths, Windows absolute paths, file URIs, nested directories and spaces tested |
| 7. Byte ranges ignored | Explicit and implicit offsets, exact response validation, local/HTTP ranges and bounded bodies tested |
| 8. Errors break JSON/partial results | Expected resource and usage errors use schema-v1 JSON; valid children/samples continue after failures |
| 9. Documentation mismatch | Environment precedence implemented; resolution normalized; README, links, architecture and changelog updated |

## Independent review

A fresh read-only reviewer examined the implementation, tests, documentation,
workflow and distribution checker. Seven additional important issues were
reproduced, covered by failing regression tests, and fixed:

- Redirect/retry bodies bypassing resource limits.
- Malformed or blank resource references aborting analysis or passing validation.
- Empty byte-range declarations becoming full-resource reads.
- Coverage falsely claiming completeness after a malformed child.
- Extreme numeric values breaking metadata/JSON construction.
- Masters with no inspectable references passing validation.
- Unrequested partial HTTP responses being accepted as full resources.

Follow-up transport tests also cover cumulative intermediate-body budgets,
redirect loops, cookie preservation and cross-host credential stripping.

Two optional review suggestions remain future report enhancements: a dedicated
resource inspection inventory and an explicit unsupported-sample summary count.
Current errors/findings retain affected locations, and every probe retains its
inspection status, including unsupported results.

## Scope and interpretation

The default threshold fails warnings as well as errors. Unknown, encrypted and
initialization-dependent sampled payloads therefore do not silently pass CI.
`--fail-on error` is an explicit relaxation and retains incomplete-inspection flags.

The implemented manifest rules are a documented subset, not complete HLS protocol
conformance. Sampling identifies supported container signatures; it does not
decode media, measure PTS drift, check codecs/keyframes, or establish playback
correctness. With sampling disabled, segment resources are not fetched. Coverage
flags describe the requested inspection scope and never establish playback health.

The HTTP timeout is for connect/read inactivity, not a total-run deadline. Use a
CI job timeout as well as resource budgets. The initial implementation was verified
before committing. Subsequent commits and hosted CI results are recorded in Git
history and GitHub Actions. The 0.2.0 publication completed after this original
verification; its published files remain unchanged.
