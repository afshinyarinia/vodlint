## Project overview

This tool analyzes HTTP Live Streaming (HLS) playlists and transport stream (TS) segments for both VOD and Live content. It fetches the master/media playlists, downloads one or more segments per variant, parses MPEG-TS (or raw AAC) payloads, and reports:

- Generic playlist info: stream type (live/vod), media sequence, encryption, number of segments, total playlist duration
- Track formats: video (H.264) profile/level/resolution/aspect ratio; audio (AAC/MP3) sample rate/channels
- Timing: segment declared vs real duration, PTS ranges per track, drift
- Frames: frame types and keyframe interval; early warnings if segments don’t start with keyframes; cross-variant first-frame PTS alignment

Entry point: `hls-analyzer.py`
Core parsing: `ts_segment.py`, `parsers/*` (H.264, AAC/ADTS, ID3, MPEG audio)
Vendored playlist parser: `m3u8/*`

## How it works (high level)

1. Load playlist via `m3u8.load(url)`.
2. For each variant (or the single media playlist):
   - Choose N segments (configurable via `-s`).
   - Download each segment (optionally request byteranges).
   - Parse container in `TSSegmentParser` → dispatch to `PESReader` → specific `PayloadReader` (H.264/AAC/etc.).
   - Accumulate frames and timestamps; print summaries and warnings.
3. Compare first-frame PTS across variants to detect alignment issues.

## Immediate issues and bugs to fix

- Python 3 breakages
  - `urllib2` usage in `hls-analyzer.py` assumes `build_opener`; on Python 3 the fallback assigns `urlopen` function to `urllib2`, which has no `build_opener`.
  - `m3u8/__init__.py` exposes `getCookieProcessor()` even on Python 3 but never defines `cookieProcessor`, causing `NameError`.
  - Python 2 constructs: `print` statements without parentheses, `dict.iteritems()`, integer division using `/` in bit-level math (should be `//`).

- Networking
  - No timeouts/retries; a slow or dead server will hang.
  - No user-agent/header configuration; no proxy support.

- Output & UX
  - Only stdout printing; no machine-readable output (JSON) for CI/pipelines.
  - Mixed print styles and inconsistent formatting.

- Packaging
  - Vendored `m3u8` fork is outdated; `requirements.txt` only pins `iso8601` (unused/commented). No pin for `m3u8` or HTTP client.
  - `setup.py` lacks a `console_scripts` entry point.

## Refactor plan (phased)

### Phase 1 — Make it robust on modern Python (quick wins)

- Replace ad-hoc `urllib2` with `requests` (or `urllib.request` with proper opener). Centralize HTTP in a `network.py` module (timeouts, retries, Range support, cookies).
- Stop vendoring `m3u8`. Use the maintained PyPI package `m3u8` and remove `m3u8/` folder. If custom behavior is needed, wrap/extend instead of forking.
- Convert Python 2 code to Python 3:
  - All `print` → `print()` or, better, structured logging.
  - `iteritems()` → `items()`; `xrange` (if any) → `range`.
  - Integer arithmetic in bit parsing (`bitreader.py`): use `//` instead of `/` for offsets.
- Introduce logging (`logging`) with levels and a `--verbose/--quiet` flag; keep stdout for final summaries.
- Add `--json` flag to emit machine-readable results for CI.

### Phase 2 — Separate concerns and improve API

- Module structure
  - `cli.py`: argument parsing and command wiring.
  - `analyzer.py`: orchestration of playlist/segment analysis, pure functions returning data classes.
  - `network.py`: HTTP fetching with retries, timeouts, headers, cookies.
  - `parsers/`: keep media parsers; add interfaces and unit tests.
  - `models.py`: typed data models (dataclasses) for reports: PlaylistInfo, TrackInfo, TimingInfo, FrameStats, AlignmentReport.

- Replace print-heavy flows with returning structured results; format in CLI layer (text/JSON).
- Add graceful error handling around segment download and parse failures with clear messages.

### Phase 3 — Features and quality

- Add support for fMP4/CMAF segments (`.m4s`). Detect container and parse minimal timing/IDR info.
- Concurrency: download N segments per variant in parallel with a bounded pool and progress output.
- Sampling strategies: analyze first, middle, and last segments; or sliding windows for live.
- Configuration file support and environment overrides for CI.
- Rich text output (optional) for better readability.

## Concrete refactor targets (by file)

- `hls-analyzer.py`
  - Extract network calls to `network.py` (requests with timeout/retries).
  - Replace prints with logger. Add `--json` output switch.
  - Stop using global state (`videoFramesInfoDict`). Pass state explicitly or encapsulate in an `Analyzer` class.
  - Fix Python 2 prints and `iteritems()` usage.

- `bitreader.py`
  - Replace `/` with `//` for integer math in `setPosition`, `skipBits`, and signed/unsigned Exp-Golomb helpers.
  - Add bounds checks and raise clear exceptions on buffer overruns.
  - Add docstrings and unit tests with crafted byte arrays.

- `ts_segment.py`
  - Replace `iteritems()` and other Python 2isms; add type hints.
  - Separate container detection from parsing; make detection reusable.
  - Consider supporting 192-byte TS packets (188 + 4-byte timestamp) if encountered.

- `parsers/*`
  - Add type hints and docstrings; ensure `getDuration()` handles empty frame lists safely.
  - `H264Reader`: guard against missing SPS before slices; avoid using `timeUs` before set.
  - `ADTSReader`: factor finite-state machine into clearer steps and add tests with real ADTS frames.

- `m3u8/*`
  - Remove vendored copy; depend on `m3u8` from PyPI. If keeping, fix `getCookieProcessor()` on Python 3 and add tests. Prefer not to maintain a fork.

## Testing and CI

- Add `pytest` with fixtures:
  - Small sample playlists (master, VOD, live, encrypted, byte-range).
  - Tiny TS/AAC segments (or golden bytes) to validate parsers and timing math.
- Add `ruff` (or `flake8`) and `black` for lint/format; enforce via pre-commit and CI.
- GitHub Actions (or similar) to run lint, type-check (mypy), and tests on 3.9–3.12.

## Developer ergonomics

- Packaging: add `console_scripts` entry point in `setup.py` (or migrate to `pyproject.toml`).
- Requirements: add `m3u8`, `requests`, `pytest`, `ruff`, `black`, `mypy` with sane pins.
- Documentation: extend `README.md` with install, examples, JSON schema, and limitations.

## Suggested JSON output schema (sketch)

```json
{
  "playlist": {
    "url": "...",
    "is_live": false,
    "version": 3,
    "media_sequence": 0,
    "encrypted": false,
    "segment_count": 181,
    "duration": 123.456
  },
  "variants": [
    {
      "bandwidth": 649879,
      "tracks": [
        {"type": "video/avc", "profile": "Main", "level": 64, "width": 640, "height": 480},
        {"type": "audio/mp4a-latm", "sample_rate": 22050, "channels": 2}
      ],
      "segments": [
        {
          "index": 0,
          "declared_duration": 9.97667,
          "tracks": [
            {"idx": 0, "first_pts": 10.0, "last_pts": 19.943333, "duration": 9.943333},
            {"idx": 1, "first_pts": 9.904222, "last_pts": 19.377961, "duration": 9.473739}
          ],
          "duration_delta": 0.502931,
          "frames": {"video": {"kf_count": 1, "kfi_sec": 0.067}}
        }
      ]
    }
  ],
  "alignment": [{"bandwidth_a": 232370, "bandwidth_b": 649879, "segment": 0, "aligned": false}]
}
```

## Implementation checklist

- [ ] Replace networking with `requests` and add timeouts/retries
- [ ] Remove vendored `m3u8/` and depend on PyPI `m3u8`
- [ ] Python 3 clean-up: prints, `iteritems`, integer math in bit ops
- [ ] Introduce logging and `--json` output
- [ ] Extract CLI → `cli.py`; core → `analyzer.py`; add dataclasses
- [ ] Add tests for `BitReader`, `H264Reader`, `ADTSReader`, `TSSegmentParser`
- [ ] Add CI and linters; type hints and mypy
- [ ] Update `README.md` with new usage and JSON docs


