# Changelog

## Unreleased

- Add schema-v1 `summary.segments_unsupported`, counting unsupported probes
  separately from inspected, skipped and failed samples (issue #3).
- Add downloadable manifest examples, a five-minute walkthrough and troubleshooting.
- Add a GitHub Actions integration using the published package and retained reports.
- Add issue forms, a PR template, community guidance and a private security policy.

## [0.2.0](https://github.com/afshinyarinia/vodlint/releases/tag/v0.2.0) — 2026-11-02

- Add manifest findings, actionable rule IDs, severity thresholds, and schema-v1 JSON.
- Define exit codes: 0 passed, 1 lint failure, 2 operational or usage failure.
- Validate child media playlists even when segment sampling is disabled.
- Require completed VOD media by default; add `--allow-live`.
- Correct declared durations, master playlist metadata, and resolution serialization.
- Route every fetch through one session with timeout/retry settings and resource budgets.
- Support local paths, Windows absolute paths, and exact explicit/implicit byte ranges.
- Preserve partial results and structured errors when individual resources fail.
- Fix container boundary crashes and AAC/MP3 misidentification.
- Report encrypted, initialization-dependent, and unknown sampled media explicitly.
- Implement timeout/retry environment defaults and reject invalid numeric options.
- Add offline regression tests, real HTTP fixtures, installed CLI checks, and distribution CI.

### Compatibility notes

Master playlists now expose null live/segment/duration values, with child data in
`media_playlists`. Manifest fetching includes all direct media references, including
renditions and I-frame playlists. Unknown sampled media fails the default warning
threshold; `--fail-on error` explicitly relaxes that threshold. JSON is emitted for
expected usage and resource errors. Duration is the sum of EXTINF values, not a
measurement of decoded media. The minimum requests version is now 2.32.5.
