# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.3] - 2026-05-06

### Fixed

- **Start command** — Now shows both New and Active tasks (previously filtered out Active tasks, causing "No new tasks" even when tasks existed)
- **Start command** — API errors per story now surface as warnings instead of being silently ignored
- **Status output** — Story state (New/Active/Resolved/etc.) now shown next to each story

## [1.4.2] - 2026-05-06

### Fixed

- **Auto-resolve guard** — Stories with no child tasks are no longer auto-resolved when running `azdo-daily end`

## [1.0.0] - 2026-04-29

### Added

- **Modular Python package** — Clean architecture with dedicated modules for API, CLI, UI, config, state management
- **Global CLI** — Install once, use anywhere: `pip install azdo-daily`
- **Interactive workflow**:
  - `azdo-daily configure` — Set credentials and preferences
  - `azdo-daily create` — Select stories, generate tasks (AI or manual)
  - `azdo-daily start` — Activate tasks
  - `azdo-daily update` — Log progress on tasks
  - `azdo-daily end` — Mark tasks complete, auto-resolve stories
  - `azdo-daily status` — Show daily progress
- **AI task breakdown** — Claude reads user stories and generates concrete development tasks
- **Azure DevOps integration**:
  - WIQL queries for story fetching
  - Task creation with parent/related links
  - State management (New → Active → Resolved/Closed)
  - Hours logging (completed + remaining)
  - Comment support
- **Project-local configuration** — `.config/settings.json` excluded from git
- **Daily state persistence** — `state/YYYY-MM-DD.json` per-day tracking
- **GitHub Actions CI/CD**:
  - Automated testing on Python 3.9-3.12
  - Code linting (flake8) + formatting (black)
  - Automatic PyPI publication on version tags

### Technical

- Python 3.9+ compatibility
- Minimal dependencies: `requests` only
- Comprehensive error handling with user-friendly messages
- Terminal UI with colors, prompts, formatted tables
- Documented public API via entry points

## Future

- [ ] Unit test suite
- [ ] Config validation on startup
- [ ] Retry logic for transient API failures
- [ ] Support for multiple Azure DevOps orgs
- [ ] Work item templates for common task patterns
- [ ] Time tracking dashboard/reports
