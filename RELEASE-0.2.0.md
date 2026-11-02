# VoDLint 0.2.0

This release introduces actionable HLS VOD manifest checks for CI, with stable rule IDs, severity thresholds, versioned JSON reports, and exit codes for passing checks, findings, and operational errors.

It corrects duration and master-playlist reporting; adds local-file and byte-range support; applies timeouts, retries, and resource budgets to all downloads; and preserves partial results when resources fail. Optional segment sampling recognizes MPEG-TS and ADTS signatures and explicitly reports unsupported or encrypted media.

Compatibility changes: VOD playlists require `EXT-X-ENDLIST` by default; use `--allow-live` when appropriate. Warnings fail by default; use `--fail-on error` to relax this. Master media statistics are null, with per-playlist data in `media_playlists`. The minimum requests version is 2.32.5.

The validator checks a documented subset of HLS and samples container signatures. It does not decode media or validate playback timing. See the README for coverage and limits.
