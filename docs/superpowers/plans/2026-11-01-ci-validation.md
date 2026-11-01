# CI validation implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement these tasks in the existing checkout. Steps use checkbox syntax for tracking.

**Goal:** Correct the nine findings in REVIEW.md and establish a tested, documented CI validation contract.

**Architecture:** Retain the existing Python package and public dictionary API. Separate bounded file/HTTP transport, pure manifest rules, report construction, orchestration, and CLI formatting. Validate manifests independently of optional media sampling; preserve partial results on operational failures.

**Tech stack:** Python >=3.11, requests, m3u8, pytest, Ruff, Black, Hatchling.

**Spec:** REVIEW.md, findings 1–9, as requested by the user. The broader future media-analysis roadmap remains future work.

## Global constraints

- Work in the existing checkout; preserve the original review as a historical baseline.
- Exit status 0 = passed, 1 = findings at/above threshold, 2 = usage/operational error.
- JSON schema version 1; stable rule IDs; default failure threshold warning.
- VOD checks default on; --allow-live disables only the requirement for ENDLIST.
- Always inspect root and directly referenced media manifests; optional first-N segment sampling.
- Unsupported/encrypted sampled media is explicit, never silently treated as valid.
- HTTP and local files share resource budgets; HTTP requests share a session and timeout/retry settings.
- Existing CLI/API options remain available. Numeric settings reject invalid values.

## Review focus

- Malformed or missing inputs must return the appropriate exit code and valid JSON.
- Redirected master and child playlists must resolve resources against their effective locations.
- Implicit byte offsets must refer to the preceding segment of the same resource.
- One failed child/segment must preserve and continue other inspections.
- Configuration, dependency floors, installed distributions, and Windows paths must behave consistently.

## Tasks

### 1. Safe format identification

Files: src/vodlint/parsers/sniff.py; tests/test_sniff.py.

- [x] Add boundary lengths, MP3 false positives, complete/truncated ADTS frames and ID3-prefix fixtures.
- [x] Run tests to observe the current boundary and misclassification failures.
- [x] Guard packet indices and validate ADTS header/frame length.
- [x] Run format tests and existing suite.

### 2. Resource transport

Files: src/vodlint/network.py; tests/conftest.py; tests/test_network.py.

- [x] Add real local-HTTP tests for retries, timeouts, redirects, byte ranges, malformed/ignored ranges and limits; add local file/path tests.
- [x] Observe failures against the current implementation.
- [x] Introduce fetched-resource results and a context-managed shared HttpClient, with bounded reads and local-file routing.
- [x] Verify retries change observed HTTP attempts; byte ranges return exact bytes; resource limits reject oversize input.

### 3. Findings, media metadata and orchestration

Files: src/vodlint/models.py; src/vodlint/rules.py; src/vodlint/analyzer.py; tests/test_analyzer.py.

- [x] Add failing tests for non-HLS text, invalid target duration, duration sum 11.0, master live status null, nested local paths, child failures, invalid ranges, and unsupported/encrypted samples.
- [x] Add schema/versioned report helpers, pure rule evaluation, typed configuration and input validation.
- [x] Load all referenced manifests through transport; validate media metadata; sample exact segment ranges through one loop; preserve partial failures.
- [x] Verify findings and operational errors produce distinct statuses and coverage summaries.

### 4. CLI contract

Files: src/vodlint/cli.py; tests/test_cli.py; tests/test_cli_smoke.py.

- [x] Add failing real CLI and main() tests for codes 0/1/2, JSON errors, thresholds, environment defaults, explicit overrides, and invalid options.
- [x] Implement numeric validation, environment configuration and threshold options; render report verdict and findings.
- [x] Run the complete suite and confirm the actual installed executable behavior.

### 5. Distribution, CI and truthful documentation

Files: README.md; CONTRIBUTING.md; project-detail.md; pyproject.toml; .github/workflows/ci.yml; CHANGELOG.md.

- [x] Replace placeholders and unsupported feature claims; document rules, limits, sample coverage, schema, configuration precedence and exit codes.
- [x] Run behavioral tests on Windows/Linux and supported Python versions in CI, including minimum runtime dependencies.
- [x] Build wheel/source distribution, check metadata, install wheel outside the checkout and run behavioral fixtures.
- [x] Run full pytest, Ruff and Black checks; review the complete diff against all nine report findings.

No commits, publishing, or merges are required by this task.

## Execution record

All five tasks completed in the existing checkout. Regression tests were run against failing behavior before fixes. Final evidence and scope are recorded in VALIDATION.md. A fresh reviewer found seven important follow-up defects; all were reproduced and fixed, followed by the full suite. Optional inventory/count enhancements are documented as future work. No commits or publishing were performed.
