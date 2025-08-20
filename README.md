# VoDLint

**VOD-focused linter and health checks for HLS/m3u8 manifests and segments.**

VoDLint analyzes HLS playlists and probes sample segments to detect timing issues, format problems, and playlist inconsistencies. Perfect for CI/CD pipelines, content validation, and debugging streaming issues.

## ✨ Features

- 🔍 **Playlist Analysis**: Parse master/media playlists, detect live vs VOD, extract metadata
- 📊 **Segment Probing**: Download and analyze sample segments for container type (TS/AAC)
- ⚡ **Fast & Reliable**: Built-in retries, timeouts, and robust error handling
- 📋 **Multiple Formats**: Human-readable text output or structured JSON for automation
- 🐍 **Python API**: Use programmatically in your own tools and scripts
- 🔧 **CI/CD Ready**: Perfect for automated content validation pipelines

## 🚀 Quick Start

### Installation

```bash
pip install vodlint
```

For development:
```bash
git clone <your-repo>
cd vodlint
pip install -e .[dev]
```

### Basic Usage

**Analyze a playlist:**
```bash
vodlint https://example.com/playlist.m3u8
```

**Sample first segment per variant:**
```bash
vodlint https://example.com/playlist.m3u8 -s 1
```

**Get JSON output for CI:**
```bash
vodlint https://example.com/playlist.m3u8 -s 1 --json
```

## 📖 Usage Examples

### Command Line

```bash
# Basic playlist info
vodlint https://example.com/master.m3u8

# Analyze first 3 segments per variant
vodlint https://example.com/master.m3u8 --segments 3

# Local file with custom timeout
vodlint ./local-playlist.m3u8 --timeout 30 --retries 5

# JSON output for scripting
vodlint https://example.com/master.m3u8 -s 1 --json | jq '.playlist.is_live'
```

### Python API

```python
from vodlint.analyzer import analyze_playlist

# Basic analysis
report = analyze_playlist("https://example.com/master.m3u8")
print(f"Playlist type: {'Live' if report['playlist']['is_live'] else 'VOD'}")
print(f"Variants: {len(report['variants'])}")

# With segment sampling
report = analyze_playlist(
    playlist_location="https://example.com/master.m3u8",
    segments_to_sample=2,
    http_timeout_seconds=15,
    http_retries=3
)

# Check for issues
for probe in report.get('segment_probes', []):
    if probe['container'] == 'unknown':
        print(f"⚠️  Unknown container in variant {probe['variant_index']}")
```

## 📊 Output Format

### Text Output
```
Playlist: https://example.com/master.m3u8
  live: false  version: 3  target_dur: 10.0
  media_sequence: 0  segments: 180  duration: 1800.0
Variants:
  [0] bandwidth=232370 uri=low/playlist.m3u8
  [1] bandwidth=649879 uri=high/playlist.m3u8
Segment probes:
  variant=0 seg_index=0 container=ts bytes=376832
  variant=1 seg_index=0 container=ts bytes=982736
```

### JSON Output
```json
{
  "playlist": {
    "url": "https://example.com/master.m3u8",
    "is_live": false,
    "version": 3,
    "media_sequence": 0,
    "segment_count": 180,
    "duration": 1800.0,
    "target_duration": 10.0
  },
  "variants": [
    {
      "bandwidth": 232370,
      "resolution": "640x480",
      "codecs": "avc1.42001e,mp4a.40.2",
      "uri": "low/playlist.m3u8"
    }
  ],
  "segment_probes": [
    {
      "variant_index": 0,
      "segment_index": 0,
      "url": "https://example.com/low/segment000.ts",
      "container": "ts",
      "size_bytes": 376832
    }
  ]
}
```

## 🔧 Configuration

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `url` | Playlist URL or file path | Required |
| `-s, --segments` | Segments to sample per variant | `0` (no sampling) |
| `--json` | Output JSON instead of text | `false` |
| `--timeout` | HTTP timeout in seconds | `10.0` |
| `--retries` | HTTP retry attempts | `2` |

### Environment Variables

```bash
export VODLINT_TIMEOUT=30
export VODLINT_RETRIES=5
vodlint https://example.com/playlist.m3u8
```

## 🛠️ Use Cases

### CI/CD Validation
```bash
# Validate playlist in CI
vodlint $PLAYLIST_URL --json | jq -e '.playlist.segment_count > 0'
```

### Content QA
```bash
# Check all variants have valid containers
vodlint $PLAYLIST_URL -s 1 --json | \
  jq -e '.segment_probes | all(.container != "unknown")'
```

### Debugging
```bash
# Quick health check
vodlint $PLAYLIST_URL -s 3 | grep -E "(live|segments|container)"
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md).

### Development Setup

```bash
git clone <repo-url>
cd vodlint
pip install -e .[dev]

# Run tests
pytest

# Lint and format
ruff check .
black .

# Full CI check
ruff check . && black --check . && pytest -q
```

## 📋 Roadmap

- [ ] **fMP4/CMAF support** - Parse `.m4s` segments
- [ ] **Timing analysis** - Detect drift and discontinuities  
- [ ] **Encryption detection** - Report on DRM and key rotation
- [ ] **Concurrent downloads** - Parallel segment fetching
- [ ] **Rich output** - Colored terminal output
- [ ] **DASH support** - Extend beyond HLS

## 🐛 Troubleshooting

**"Connection timeout"**
```bash
vodlint $URL --timeout 30 --retries 5
```

**"Unknown container"**
- Segment may be encrypted or corrupted
- Try sampling different segments: `-s 3`

**"Import error"**
```bash
pip install -e .  # Reinstall in development mode
```

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🔗 Links

- **Issues**: [GitHub Issues](https://github.com/your-org/vodlint/issues)
- **PyPI**: [vodlint on PyPI](https://pypi.org/project/vodlint/) *(coming soon)*
- **Docs**: [Full Documentation](https://your-org.github.io/vodlint/) *(coming soon)*
