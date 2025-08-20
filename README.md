# hls-health

A modern Python tool to analyze HLS playlists and segments for health, timing, and format info.

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
hls-health https://example.com/playlist.m3u8 -s 1 --json
```

## Development

- Python 3.11+
- Ruff, Black, Mypy, Pytest configured via `pyproject.toml`

Run linters and tests:

```bash
ruff check . && black --check . && mypy src && pytest -q
```

## License

MIT
