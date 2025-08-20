# Contributing to VoDLint

Thank you for your interest in contributing to VoDLint! This guide will help you get started.

## 🚀 Quick Start

1. **Fork and clone**
   ```bash
   git clone https://github.com/your-username/vodlint.git
   cd vodlint
   ```

2. **Set up development environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   pip install -e .[dev]
   ```

3. **Run tests to verify setup**
   ```bash
   pytest -v
   ```

## 🧪 Development Workflow

### Before making changes
```bash
# Create a feature branch
git checkout -b feature/your-feature-name

# Make sure everything works
ruff check . && black --check . && pytest -q
```

### While developing
```bash
# Run tests frequently
pytest

# Auto-format code
black .

# Check for lint issues
ruff check .
```

### Before committing
```bash
# Full CI check
ruff check . && black --check . && pytest -q

# Commit with a clear message
git commit -m "feat: add support for fMP4 segments"
```

## 📝 Code Style

We use automated tools to maintain code quality:

- **Ruff**: Fast linting and import sorting
- **Black**: Code formatting
- **Pytest**: Testing framework

### Formatting
```bash
# Format all code
black .

# Check formatting without changing files
black --check .
```

### Linting
```bash
# Check for issues
ruff check .

# Auto-fix issues where possible
ruff check . --fix
```

## 🧪 Testing

### Running Tests
```bash
# All tests
pytest

# Verbose output
pytest -v

# Quick run
pytest -q

# Specific test file
pytest tests/test_sniff.py
```

### Writing Tests
- Place tests in the `tests/` directory
- Name test files `test_*.py`
- Name test functions `test_*`
- Use clear, descriptive test names

Example:
```python
def test_sniff_detects_ts_container():
    """Test that TS container is correctly identified."""
    # Build 188*2 bytes with sync byte at 0 and 188
    buf = bytearray(188 * 2)
    buf[0] = 0x47
    buf[188] = 0x47
    assert sniff_container(bytes(buf)) == "ts"
```

## 📚 Documentation

### README Updates
- Update examples if you change the CLI
- Add new features to the feature list
- Update the roadmap as items are completed

### Docstrings
Use clear, concise docstrings for functions and classes:
```python
def analyze_playlist(playlist_location: str, segments_to_sample: int = 0) -> dict:
    """Analyze an HLS playlist and optionally sample segments.
    
    Args:
        playlist_location: URL or file path to the playlist
        segments_to_sample: Number of segments to download per variant
        
    Returns:
        Dictionary containing playlist info and segment probe results
    """
```

## 🐛 Bug Reports

When reporting bugs, please include:

1. **VoDLint version**: `vodlint --version`
2. **Python version**: `python --version`
3. **Operating system**
4. **Playlist URL** (if public) or minimal reproduction case
5. **Full error output**
6. **Expected behavior**

## ✨ Feature Requests

For new features:

1. **Check existing issues** to avoid duplicates
2. **Describe the use case** - what problem does this solve?
3. **Provide examples** of how the feature would be used
4. **Consider backward compatibility**

## 🎯 Areas for Contribution

### Easy/Beginner
- [ ] Add more container type detection (fMP4, WebM)
- [ ] Improve error messages
- [ ] Add more CLI examples to README
- [ ] Write additional tests

### Medium
- [ ] Add environment variable support for configuration
- [ ] Implement concurrent segment downloading
- [ ] Add rich/colored terminal output
- [ ] Add more comprehensive timing analysis

### Advanced
- [ ] Support for DASH manifests
- [ ] Advanced codec parsing (H.264 SPS/PPS, AAC ADTS)
- [ ] Encryption detection and reporting
- [ ] Performance optimizations

## 🔄 Pull Request Process

1. **Fork the repository**
2. **Create a feature branch** from `main`
3. **Make your changes** with tests
4. **Run the full test suite**
5. **Write clear commit messages**
6. **Update documentation** if needed
7. **Submit a pull request**

### PR Checklist
- [ ] Tests pass locally
- [ ] Code is formatted with Black
- [ ] No linting errors from Ruff
- [ ] Documentation updated if needed
- [ ] Clear commit messages
- [ ] PR description explains the change

### Commit Message Format
```
type: short description

Longer explanation if needed

- Use present tense: "add feature" not "added feature"
- Keep first line under 50 characters
- Reference issues: "closes #123"
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## 📞 Getting Help

- **Questions**: Open a GitHub Discussion
- **Bugs**: Create an Issue with the bug report template
- **Features**: Create an Issue with the feature request template

## 🙏 Code of Conduct

Be respectful, inclusive, and constructive. We're all here to make VoDLint better!

---

**Thank you for contributing to VoDLint!** 🎉
