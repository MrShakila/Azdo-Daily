# Contributing to azdo-daily

## Setup

Clone and install in development mode:

```bash
git clone https://github.com/yourusername/azdo-daily.git
cd azdo-daily
pip install -e ".[dev]"
```

## Code Style

Install pre-commit hooks (auto-formats on commit):

```bash
pip install pre-commit
pre-commit install
```

Manual formatting with black:

```bash
black azdo_daily/
```

Lint with flake8:

```bash
flake8 azdo_daily
```

Both are checked in CI before merge.

## Testing

No test suite yet. Manual testing:

```bash
azdo-daily --help
azdo-daily configure  # Configure with test credentials
azdo-daily status
```

## Publishing

1. Update `pyproject.toml` version
2. Create annotated tag:
   ```bash
   git tag -a vX.Y.Z -m "Release X.Y.Z - description"
   ```
3. Push commit + tag:
   ```bash
   git push origin main
   git push origin vX.Y.Z
   ```
4. GitHub Actions automatically:
   - Runs tests
   - Builds distribution
   - Publishes to PyPI

## GitHub Secrets

Add `PYPI_API_TOKEN` to repo settings:
1. Go to Settings → Secrets and variables → Actions
2. New repository secret
3. Name: `PYPI_API_TOKEN`
4. Value: PyPI API token from [pypi.org/manage/account/tokens/](https://pypi.org/manage/account/tokens/)

## Architecture

```
azdo_daily/
├── main.py       — CLI entry point, arg parsing
├── commands.py   — Command handlers (configure, create, start, etc.)
├── azdo.py       — Azure DevOps API client
├── config.py     — Config file management
├── state.py      — Daily state storage
├── ui.py         — Terminal UI helpers
└── ai.py         — Claude API integration
```

## Key Design Principles

- **Modular** — Each module has single responsibility
- **Config-driven** — All settings in `.config/settings.json`
- **Stateless between runs** — State persisted to `state/YYYY-MM-DD.json`
- **Error handling** — Graceful failures, continue on non-critical errors
- **No external binaries** — Pure Python + requests library

## License

MIT — see [LICENSE](LICENSE)
