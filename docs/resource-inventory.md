# Resource inspection inventory

The next release adds `resources` to schema version `"1"`. This is an additive
inventory of root/child manifest references and selected segment samples. It
does not change existing metadata, probes, findings, errors, counters, severity
thresholds, completeness flags or exit codes. Consumers must tolerate new fields.
The published 0.2.0 package does not include this field.

The [schema checkpoint in issue #4](https://github.com/afshinyarinia/vodlint/issues/4#issuecomment-6572534434)
was posted before implementation. Keeping failed references only in `errors`
would omit malformed and deliberately skipped resources; changing existing
metadata/probe records would break their established meaning. A separate list
preserves those contracts while exposing the attempted scope.

## Record fields

Every entry has the following fields, including explicit nulls:

| Field | Type and meaning |
| --- | --- |
| `id` | Integer, zero-based position in this report's inventory |
| `kind` | `manifest` or `segment` |
| `url` | String, redacted requested/resolved reference; a malformed reference may use `<invalid location>` |
| `effective_url` | Redacted final URL or normalized file URI after a successful fetch, otherwise null |
| `status` | Outcome from the tables below |
| `reason` | Stable detail string below, or null |
| `parent_id` | Root manifest: null; direct child: root ID; sample: its media manifest ID |
| `segment_index` | Zero-based segment ordinal in its media playlist, or null for manifests |
| `byte_range` | Resolved `{ "offset": integer, "length": integer }`, or null |
| `duplicate_of` | Prior manifest entry's ID for duplicate references, otherwise null |

Invalid byte ranges have null `byte_range`; their raw declaration is not echoed.
IDs are references within one report, not persistent identifiers across runs.

## Outcomes

| Manifest status | Reason | Meaning |
| --- | --- | --- |
| `validated` | null | Fetched, decoded, parsed and passed manifest rules at load time |
| `invalid` | `invalid_encoding` | Fetched bytes were not UTF-8 |
| `invalid` | `invalid_manifest` | Fetched text failed manifest rules or parsing |
| `invalid` | `invalid_uri` | Child URI could not be resolved; no fetch |
| `invalid` | `nested_master` | Fetched child is a master where media is required |
| `error` | `fetch_error` | Resource operation failed, including limits, transport or HTTP failures |
| `duplicate` | null | Reference shares the earlier inspection named by `duplicate_of`; no new fetch |

| Segment status | Reason | Meaning |
| --- | --- | --- |
| `inspected` | null | Fetched sample has a recognized container signature |
| `unsupported` | `unknown_container` | Fetched sample is unrecognized, unsupported or truncated |
| `skipped` | `encrypted` | Selected sample uses encryption; no fetch |
| `skipped` | `initialization_dependent` | Selected sample requires an initialization map; no fetch |
| `invalid` | `invalid_uri` | Selected sample URI cannot be resolved; no fetch |
| `invalid` | `invalid_byterange` | Selected sample range is invalid; no fetch |
| `error` | `fetch_error` | Sample resource operation failed |

URI/range checks take precedence over encryption/init skips; encryption takes
precedence over an init map. The existing `segment_probes` classify invalid
URI/range samples as `skipped`; this inventory adds the more specific outcome
without changing those probes or summary counts. A malformed root location
continues to produce an operational `error`, as it did before this addition.

`effective_url` is null for errors even if a request reached a server but failed
HTTP/range/size checks. It is present for fetched manifests that fail parsing or
encoding. A duplicate's effective URL stays null: follow `duplicate_of` to see
the shared result, including an earlier invalid/error result.

## Order and scope

The root is first. For a master, direct references follow the analyzer's existing
order: variants, then I-frame playlists, then URI-bearing renditions. Each
successfully loaded media manifest is immediately followed by its selected
samples in segment order. No timestamps or network timing affect this order.

Repeated child references each have an entry. Exact resolved URI strings share
the first inspection, even when that inspection failed. Deduplication uses the
original URI, including its query, before redaction. Different signed URLs can
therefore look identical in the report while representing separate inspections.
Redirect aliases are not additionally coalesced. Repeated segment URLs and byte
ranges are separate entries and fetches, matching existing sampling behavior.

This is an inspection inventory, not a log of individual HTTP attempts: retries
and redirects belong to one entry. It contains no unsampled segments, encryption
keys, init objects or descendants of rejected nested masters. With sampling
disabled, only manifests appear. Usage errors before analysis have `resources: []`.

`validated` describes that manifest's load-time checks; later URI/range findings
remain in `findings`. Neither it nor `inspected` asserts playback, complete media
validation or inspection of referenced content. Use the existing summary flags
and findings/errors to assess the report's coverage and verdict.

## Confidentiality

Both location fields remove URL user credentials and fragments and replace query
strings with `REDACTED`, using the same policy as existing report locations.
Malformed URLs that cannot be split use `<invalid location>`. Paths and filenames
remain visible, including local directory names and secrets embedded in path
segments. Review reports before sharing them; redaction is not anonymization.
