# vodlint

VOD-focused linter and health checks for HLS/m3u8 manifests and segments.

## Features

- Load master or media playlists via URL or file path
- Inspect playlist metadata: live/VOD, sequence, encryption, duration
- Optionally fetch sample segments and sniff container (TS/AAC)
- Output as human-readable text or JSON (`--json`)

## Install

```bash
pip install .
```

Editable install for development:

```bash
pip install -e .[dev]
```

## Usage

```bash
vodlint https://example.com/playlist.m3u8 -s 1 --json
```

## Programmatic use

```python
from vodlint.analyzer import analyze_playlist

report = analyze_playlist(
    "https://example.com/playlist.m3u8",
    segments_to_sample=1,
    http_timeout_seconds=10,
    http_retries=2,
)
print(report)  # dict ready to serialize to JSON
```

## Development

- Python 3.11+
- Ruff, Black, Pytest configured via `pyproject.toml`

Run linters and tests:

```bash
ruff check . && black --check . && pytest -q
```

## License

MIT
