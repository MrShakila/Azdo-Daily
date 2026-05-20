# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.7.1] - 2026-05-20

### Fixed

- **Hours report includes active stories** — `azdo-daily hours` now shows active stories alongside closed stories, not just closed ones

## [1.7.0] - 2026-05-20

### Added

- **`azdo-daily hours` command** — Show completed hours for closed tasks and user stories, grouped per story with story hours and task hours displayed separately, plus a grand total. Supports `--since`/`--until` date filters (YYYY-MM-DD).
- **Hours summary in `status`** — `azdo-daily status` now appends a one-line completed hours summary (all time) at the end of output.

## [1.6.6] - 2026-05-19

### Fixed

- **Timezone conversion** — Task activation time now displays in local timezone instead of UTC

## [1.6.5] - 2026-05-19

### Changed

- **Task activation time display** — Now shows full datetime (YYYY-MM-DD HH:MM) only for Active tasks, not for New tasks

## [1.6.4] - 2026-05-19

### Added

- **Task activation time** — Display when each task was activated (last modified date) in `update` and `end` commands, format: `HH:MM` appended to task title

## [1.6.3] - 2026-05-19

### Fixed

- **Start command field error** — Fixed 400 API error by using correct Azure DevOps field name `System.ChangedDate` instead of non-existent `System.StateChangeDate`

## [1.6.2] - 2026-05-19

### Fixed

- **Task start date** — Start command now fetches actual `System.StateChangeDate` from Azure DevOps API instead of using local timestamp, ensuring accurate tracking of when tasks were activated in the system

## [1.6.0] - 2026-05-07

### Added

- **Doctor command** — `azdo-daily doctor` validates configuration and tests API connectivity
  - Checks config file exists and required fields present
  - Tests Azure DevOps and Anthropic API connectivity
  - Provides detailed error messages for troubleshooting
- **Multi-type support** — Now supports all Azure DevOps work item types (Epic, Feature, User Story, Bug, Issue)
  - Maintains parent-child hierarchy regardless of type
  - Fetches all child work items, not just Tasks
  - Supports full Azure DevOps work item structure

## [1.5.5] - 2026-05-07

### Fixed

- **Project filtering** — User stories now correctly filtered by configured project instead of fetching across all projects in org
- **Security** — Project name validation added to prevent WIQL injection (spaces allowed, quotes blocked)

## [1.5.4] - 2026-05-07

### Added

- **Nuke command** — `azdo-daily nuke` permanently deletes all config and state with confirmation (type 'nuke' to confirm)
- **Help command** — `azdo-daily help` displays all available commands with descriptions

## [1.5.3] - 2026-05-07

### Added

- **Auto gitignore** — When saving config, automatically adds `.config/` to project `.gitignore` to prevent accidental commits of API keys and PAT tokens

### Fixed

- **Security** — Error messages no longer expose HTTP response bodies or full exception details that could leak sensitive information
- **Input validation** — WIQL queries now validated to prevent injection attacks via `assigned_to` config

## [1.5.2] - 2026-05-07

### Added

- **Project-local config** — Configuration now stored in `.config/settings.json` in the current working directory instead of globally, allowing different configs for multiple projects

## [1.5.1] - 2026-05-07

### Changed

- **Logo** — Added project logo to README and PyPI package page

## [1.5.0] - 2026-05-07

### Added

- **End command** — User confirmation prompt before auto-resolving stories. Shows which stories are ready to resolve and requires explicit approval, preventing accidental resolutions.

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
