# VoDLint code review and open source improvement report

Reviewed: 2026-11-01. Baseline: `f1ba90b9679fc8ce00cca94e09dbf4d89a7ec9fb`.

This is the historical 0.1.0 review. The subsequent fixes and compatibility changes
are described in CHANGELOG.md; current behavior and limitations are in README.md.

## Assessment

VoDLint has a useful focus and an understandable codebase. The `src` layout, small dependency set, separate CLI/analyzer/network modules, MIT license, contribution guide, and existing CI are good foundations.

The current implementation is an early metadata inspector and container-signature sampler. It does not yet implement the validation, timing analysis, or health verdicts that its name and README suggest. The highest-value next step is to make a small set of checks trustworthy and useful in CI, then expand format support. A rewrite is unnecessary.

## Review scope and verification

Reviewed every tracked Python source file, both test files, packaging configuration, CI, README, contribution guide, license, and historical project notes. Exercised synthetic playlists and segment bytes using local files and a loopback HTTP server. Production code was not changed.

Verification used Windows, Python 3.12.13, `m3u8` 6.0.0, `requests` 2.34.2, pytest 9.2.0, Ruff 0.17.3, and Black 26.10.1. These results do not establish behavior across every version allowed by the dependency ranges or on other operating systems.

| Check | Observed result |
| --- | --- |
| `python -m pytest -q` | 4 passed |
| `python -m ruff check --no-cache .` | Passed |
| `python -m black --check --workers 1 .` | Passed; 8 files unchanged |
| `uv build` with the review interpreter | Wheel and source distribution built |
| `python -m twine check dist/*` | Both distributions passed |
| Install built wheel in a separate environment | Succeeded; installed `vodlint --version` and `--help` worked |
| Archive contents | Expected source/package files and license present; temporary review environment excluded |
| Additional review experiments | 16 recorded observations; defects detailed below |

The existing tests cover three container-signature examples and argument parsing. They never call `analyze_playlist`, `HttpClient.get_bytes`, or `main`, which explains why the following failures coexist with a green test suite. Build and metadata checks establish that packaging works, not that stream validation is correct.

## Findings, ordered by priority

P1 means address before recommending the project as a CI validation gate. P2 means a concrete correctness or usability defect to fix in the next reliability release.

### 1. P1 — Invalid inputs can receive a successful validation exit

Locations: `src/vodlint/analyzer.py:58`, `src/vodlint/cli.py:48`, `src/vodlint/cli.py:83`.

There is no lint-rule evaluation or findings collection. A successful parser call becomes a report, and both CLI output paths return zero regardless of content problems.

Reproduced:

- A file containing only `this is not an HLS manifest` produced a normal JSON report and exit code 0.
- A media playlist declaring a 12-second segment with target duration 10 produced exit code 0 without a finding.
- A sampled segment containing plain text was reported as `container: unknown`, still with exit code 0 and no explanation of incomplete inspection.

This can let broken content pass a pipeline that trusts the executable's status. An unknown container alone should not be called corrupt: encryption and unsupported formats need separate outcomes.

Recommendation: validate the manifest envelope and required fields, evaluate explicit rules, and return a documented verdict. Define exit codes such as 0 for no findings above the selected threshold, 1 for lint failure, and 2 for invocation or operational failure. Include stable rule identifiers, severity, location, evidence, and remediation in JSON. Represent unsupported or uninspected content explicitly.

### 2. P1 — Playlist requests bypass the configured timeout and retries

Locations: `src/vodlint/analyzer.py:57`, `src/vodlint/analyzer.py:58`, `src/vodlint/analyzer.py:70`.

`HttpClient` is configured but used only for segment bytes. Root and child playlists are fetched directly through `m3u8.load` without the configuration.

Reproduced with the installed parser: requesting `http_timeout_seconds=0.1` passed `None` as the playlist downloader's timeout. A local endpoint returning HTTP 503 received exactly one request even with `http_retries=2`.

The first playlist fetch, or any child playlist fetch, can therefore outlast the user's expected timeout and lacks the promised retry behavior.

Recommendation: route every remote fetch through one transport, then parse fetched text with the correct effective base URI, including after redirects. Reuse the same session throughout an analysis and close it at the end. Test configuration propagation for both root and child playlists.

### 3. P2 — Container detection crashes at packet boundaries and mislabels MP3

Locations: `src/vodlint/parsers/sniff.py:13`, `src/vodlint/parsers/sniff.py:17`.

The length checks permit out-of-bounds access: index 188 requires at least 189 bytes, and index 376 requires at least 377 bytes. A 188-byte buffer beginning with `0x47` raised `IndexError`. A 376-byte buffer beginning with `0x47` and lacking the second sync byte also raised `IndexError`.

The ADTS check accepts any `0xFFF` prefix. The MPEG-1 Layer III header `FF FB 90 64` was labeled `adts`.

Recommendation: guard each accessed index, use clear packet-stride checks, and validate enough header fields to distinguish supported formats. Treat truncated or insufficient data as an explicit unknown/incomplete result. Add boundary and false-positive cases; the current four-byte ADTS fixture is only a signature example, not a valid complete frame.

### 4. P2 — Total duration is calculated from the target rather than segment durations

Location: `src/vodlint/analyzer.py:30`.

The implementation multiplies target duration by segment count. With target duration 10 and segment durations 9.9 and 1.1, it reported 20 seconds instead of 11 seconds.

Recommendation: sum declared segment durations and name that field clearly. Keep measured media duration separate when actual timing analysis exists. The distinction between `EXTINF` duration and target duration, as well as byte-range behavior referenced below, is defined in [RFC 8216](https://www.rfc-editor.org/rfc/rfc8216.html).

### 5. P2 — Master playlists are given misleading live status and media statistics

Locations: `src/vodlint/analyzer.py:19`, `src/vodlint/analyzer.py:60`, `src/vodlint/analyzer.py:70`.

The root playlist is always treated like a media playlist. A master referencing a completed VOD media playlist was reported as `is_live: true`, with zero segments and null duration. Loading child playlists for sampling does not add their media metadata to the report.

This also breaks the README's suggested master-playlist CI check based on `.playlist.segment_count > 0`.

Recommendation: distinguish master and media playlist models. A master should have no asserted live status of its own; expose the status, declared duration, segment count, and inspection state for each loaded media playlist. Report child data as uninspected when it has not been fetched. Avoid an undocumented aggregate live/VOD verdict.

### 6. P2 — Local-file support breaks when sampling, and Windows absolute paths fail earlier

Locations: `src/vodlint/analyzer.py:58`, `src/vodlint/analyzer.py:70`, `src/vodlint/analyzer.py:73`, `src/vodlint/analyzer.py:87`.

A relative local media playlist could be loaded, but sampling its adjacent segment raised `requests.exceptions.MissingSchema`: a filesystem path was passed to `requests.get`. Passing an absolute Windows playlist path raised `URLError: unknown url type: c` in `m3u8.load`.

Recommendation: resolve local paths separately from HTTP URLs, normalize them with `pathlib`, and load local playlists and segment bytes through a file transport. Apply this consistently to child playlists. Test relative paths, absolute paths, spaces, and nested directories on Windows and Linux.

### 7. P2 — Byte-range playlists probe entire objects instead of the declared segments

Locations: `src/vodlint/analyzer.py:71`, `src/vodlint/analyzer.py:85`, `src/vodlint/network.py:29`.

The analyzer ignores `seg.byterange`. A playlist containing two 376-byte ranges in the same 752-byte object triggered two full downloads. Both requests omitted `Range`, and each probe reported 752 bytes.

Results therefore describe the containing object rather than the referenced segment, and large single-object presentations can be downloaded repeatedly.

Recommendation: resolve explicit and implicit byte offsets, fetch the declared range, and verify the returned range/length. Handle a server ignoring range requests explicitly. Record range information in each probe. Bound response sizes; the current `resp.content` path also buffers unrestricted bodies in memory. The size-risk observation comes from source inspection, not a large-download stress test.

### 8. P2 — Operational errors abort the run and break the JSON interface

Location: `src/vodlint/cli.py:41`; fetch loops in `src/vodlint/analyzer.py:69` and `src/vodlint/analyzer.py:85`.

There is no exception boundary around analysis. A missing file in `--json` mode raised `FileNotFoundError` instead of returning a JSON error. Network and parse exceptions follow the same unhandled path. A failed segment or variant interrupts analysis before the accumulated result is returned.

Recommendation: catch expected file/network/parser errors at suitable boundaries, preserve successful probes, and represent failed inspections with their locations and causes. Emit a valid error envelope in JSON mode and an operational-failure exit code. Keep detailed tracebacks for an explicit debug mode.

### 9. P2 — Documentation advertises behavior and contracts that do not exist

Locations: `README.md:5`, `README.md:94`, `README.md:120`, `README.md:149`, `pyproject.toml:40`, and `project-detail.md`.

- Timing-issue and playlist-inconsistency detection are advertised, but no corresponding checks exist.
- `VODLINT_TIMEOUT` and `VODLINT_RETRIES` are documented but never read. Setting them to 30 and 5 still yielded defaults 10 and 2.
- JSON documents resolution as `"640x480"`; actual output is `[640, 480]` with the installed parser.
- Example master-playlist output combines root variant entries with media-level statistics that the implementation does not populate.
- Repository and documentation links still contain `your-org`, and clone commands contain placeholders. The configured Git remote identifies `afshinyarinia/vodlint`.
- `project-detail.md` describes removed files and Python 2 problems rather than the current architecture. It is also included in the source distribution.

Recommendation: make examples reproducible fixtures and generate their output from the executable. Either implement environment configuration with documented precedence or remove it from the current feature documentation. Mark historical notes as historical or replace them with a current architecture document. Verify release availability separately before advertising a working PyPI install; no published-release audit was performed here.

## How to make this a much stronger open source project

### Establish a specific promise

Position the next release around a concrete job: **catch actionable HLS VOD packaging problems before publication, with results developers can trust in CI**. Prioritize correctness, useful diagnostics, and predictable execution. Broader DASH support, terminal decoration, and a custom full media parser can wait until the HLS validation contract is dependable.

Keep the existing lightweight install. Consider an optional media-probing backend later for measured timing and codec details, rather than immediately maintaining a large binary parser. Clearly label declared metadata versus measured facts and sampled coverage versus complete inspection.

### Introduce a small, explicit validation architecture

Evolve the current modules incrementally:

| Component | Responsibility |
| --- | --- |
| Loader/transport | Local and HTTP loading, URL resolution, redirects, ranges, bounded reads, retries and deadlines |
| Models | Typed report, playlist kind, media metadata, probe outcome, finding, and configuration |
| Analyzer | Traverse playlists, choose samples, collect observations and partial failures |
| Rules | Evaluate observations without network calls; return consistent diagnostics |
| CLI/formatters | Validate options, select thresholds, emit text/JSON, choose exit status |

Dataclasses and small functions are enough at this size. Consolidate the duplicated segment-probing loops. Use or remove the currently unused `AnalyzerConfig`. Avoid a plugin framework until real extension needs emerge.

For each rule, require an identifier, rationale, applicable playlist/container types, severity, fixture demonstrating failure, fixture demonstrating success, and a remediation message. Early rules should cover malformed/empty manifests, required media tags, target-duration violations, unexpected unfinished VOD media, unavailable resources, and explicit unsupported inspection states. Report encryption and initialization metadata before attempting to interpret encrypted or initialization-dependent bytes.

### Make the machine interface a product feature

Add a report schema version and document compatibility. Include tool version, inspected resources, findings, errors, and a summary of coverage. Keep collection order deterministic even if downloads later become concurrent. Reject invalid numeric options with a clear usage error instead of silently clamping negative values.

Useful future controls include failure severity, a total request/byte budget, sampling strategy, and a total analysis deadline. Always show what was actually inspected. A clean sample is not proof that every segment is healthy. Redact credentials and signed-URL tokens from routine diagnostics.

### Build tests around user-visible outcomes

| Test area | Important cases |
| --- | --- |
| Manifest analysis | Completed VOD, live/event, master with multiple children, malformed input, mixed segment durations |
| Segment probing | Tiny/truncated input, TS boundary lengths, AAC versus MP3, encrypted content, unsupported containers |
| Filesystem | Relative/absolute paths, nested masters, spaces, missing files, Windows path handling |
| HTTP | Redirect base URI, timeout propagation, retries, 404/503, range offsets, ignored ranges, bounded bodies |
| CLI contract | Real entry point, exit codes, valid JSON on errors, partial failures, option precedence |
| Distribution | Build source/wheel, install wheel in a clean environment, run CLI outside an editable checkout |

Use tiny synthetic fixtures and a local HTTP server so tests remain deterministic and offline. Add a few redistributable real-media fixtures with provenance if deeper parsing requires them. Track branch coverage to reveal gaps, while requiring behavioral assertions rather than chasing a percentage.

CI should cover Windows as well as Linux and the oldest/newest Python versions the project explicitly supports. Separate quality checks, behavioral tests, and distribution checks. Use a reproducible contributor dependency set while retaining sensible compatibility ranges for library consumers; test the dependency floor as well as the normal development set.

### Complete the contributor and release experience

The repository already has a license and contribution guide. The remaining repository-level gaps are issue forms, a pull-request template, a dedicated conduct policy, vulnerability-reporting instructions, maintainer/support information, and a changelog. These files give contributors a clear route from a problem to a reviewable contribution; GitHub supports them as [community health files](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file). Account-level inherited defaults and repository settings were not inspected.

Create small starter issues with fixtures and acceptance criteria: duration math, sniffer boundaries, environment documentation, and local-path handling are good candidates. Document who reviews contributions, how compatibility changes are decided, and what support users should expect. Preserve historical copyright attribution when updating branding.

Add tagged releases, release notes describing user-visible behavior, wheel-install CI, automated dependency update checks, and a documented publishing process. Use [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) for release authentication through short-lived credentials when publishing is configured. No release was published during this review.

## Recommended order of work

| Milestone | Scope | Acceptance criterion |
| --- | --- | --- |
| Reliability patch | Findings 2–9, regression fixtures, truthful README | Reproduced defects are covered and corrected; JSON failures and local paths behave predictably |
| First dependable lint release | Finding 1, typed outcomes, rule IDs, severity policy, schema and exit codes | Known-invalid fixtures fail CI; valid fixtures pass; unsupported inspection is explicit |
| Open source release readiness | Real links, tested installation, support/contribution policies, changelog, release workflow | A new contributor can install, reproduce an issue, add a rule, and run all required checks from the docs |
| Deeper HLS inspection | fMP4/init segments, rendition coverage, encryption metadata, measured timing, wider sampling | Each advertised capability has documented limits and representative fixtures |
| Performance and integrations | Measured bottlenecks, bounded concurrency, optional CI annotations/report formats | Faster runs retain deterministic results, resource limits, and the established contract |

The best first contribution is a compact reliability PR with regression cases for the existing failures. The most important subsequent product work is a real findings-and-exit-code contract. Together, these would improve user trust more than adding several new formats to the present implementation.

## Reproduction notes

Local review tooling remains in ignored paths: `.venv/review_probes.py`, `.venv/review_results.jsonl`, and `.venv/review/`. Build outputs are in ignored `dist/`. The probes are review experiments, not additions to the project's test suite.

Run the boundary reproduction after installing the project:

```python
from vodlint.parsers.sniff import sniff_container

sniff_container(bytes([0x47]) + bytes(187))  # currently raises IndexError
```

For the duration reproduction, save this as `sample.m3u8` and run `vodlint sample.m3u8 --json` without segment sampling:

```m3u8
#EXTM3U
#EXT-X-TARGETDURATION:10
#EXTINF:9.9,
a.ts
#EXTINF:1.1,
b.ts
#EXT-X-ENDLIST
```

The current report says 20.0 seconds; the declared segment durations sum to 11.0 seconds. Replacing the file content with plain non-HLS text reproduces the false-success issue.
