# Use VoDLint in GitHub Actions

Copy [the example workflow](../.github/workflows/example-validation.yml) into your
repository's `.github/workflows/` directory and include the example manifests,
or change the manifest selection to your checked-in playlist. It installs
`vodlint==0.2.0` from PyPI, uses read-only repository permissions and a five-minute
job timeout, and uploads `vodlint-report.json` even when validation fails.

The default run validates `examples/valid.m3u8` and succeeds. To demonstrate failure
handling, open **Actions → Example validation → Run workflow**, select `invalid`,
and run it. The validation step and workflow should fail with exit 1; the report
upload should succeed. Download the `vodlint-report` artifact to inspect
`status: failed` and rule `manifest.target-duration`. This deliberate failure is
a demonstration, not a passing test or a broken main CI job.

For your own manifest, replace the selection block with:

```bash
vodlint path/to/master.m3u8 --json > vodlint-report.json
```

Keep the upload step's `if: always()` condition. Without it, a failing command
would skip the report upload. Exit 1 means lint findings; exit 2 means an
invocation or resource error. Neither is silently permitted by this workflow.

## Private playlists

Prefer checked-in, sanitized reproductions for public CI. If your real playlist
URL contains credentials or signatures, store it in a GitHub Actions secret
called `PLAYLIST_URL`, expose it as an environment variable on the validation
step, and use `vodlint "$PLAYLIST_URL" --json > vodlint-report.json`. Never embed
the secret directly in shell source, print it, or enable shell tracing. Secrets
are normally unavailable to pull requests from forks; keep the checked-in example
for those runs and run private validation only on trusted events.

Reports redact URL credentials, query strings and fragments, but path segments,
resource names and operational details may still identify private content.
Review reports before sharing them and use a private repository for confidential
artifacts. GitHub's masking is not a guarantee that a report is safe to publish.

## What the workflow establishes

These fixtures exercise manifest rules only. Segment files are intentionally not
included. Adding `-s N` checks availability and container signatures for the first
N segments per media playlist; it requires actual segment resources and still
does not decode media or establish playback correctness. The report's scope and
coverage fields describe what was inspected.
