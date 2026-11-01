# Current architecture

These notes describe the current Python package. Earlier Python 2 scripts and
vendored parser migration notes are historical and no longer describe the tree.

VoDLint validates a documented subset of HLS manifest rules, then optionally
identifies first-N segment container signatures. It does not decode media,
calculate PTS drift, or inspect codecs and keyframes.

## Flow

1. The CLI validates options, applying explicit CLI values over environment defaults.
2. The analyzer creates one bounded local/HTTP client for the analysis.
3. The loader fetches root text; rules validate encoding, structure and metadata.
4. A media root is summarized directly. A master loads its direct variant, I-frame,
   and URI-bearing rendition manifests, deduplicating identical references.
5. All media byte-range declarations are validated, including when sampling is off.
6. Optional samples fetch exact local/HTTP ranges. Encrypted/init-dependent content
   is skipped with warnings; supported signatures produce observations.
7. Expected failures become resource errors while other children/samples continue.
8. Report finalization derives status and coverage; the CLI maps status to 0/1/2.

## Modules

| Module | Responsibility |
| --- | --- |
| src/vodlint/network.py | File/HTTP transport, effective redirect locations, limits and ranges |
| src/vodlint/rules.py | Parsing and manifest findings without network I/O |
| src/vodlint/models.py | Typed findings, redacted report data and verdict aggregation |
| src/vodlint/analyzer.py | Config, playlist traversal, metadata and probing |
| src/vodlint/cli.py | Argument/environment validation, JSON/text and exit codes |
| src/vodlint/parsers/sniff.py | TS and ADTS signatures, with safe bounds |

The public analyzer returns a JSON-compatible dictionary. Invalid configuration
raises ValueError; expected resource failures are recorded in the dictionary.
Root metadata is null when root validation fails. Master metadata keeps fields
that require a media playlist null rather than inventing an aggregate value.

## Extension boundaries

New rules should be pure and have independent valid/invalid fixtures.
Deep media analysis belongs behind a separately testable decoder interface.
Add bounded concurrency only after measuring a bottleneck and preserving
deterministic report ordering and shared budgets.

See README.md for the rule list, schema, limits and supported inspection scope.
REVIEW.md is the original review of the 0.1.0 baseline, not current defect status.


