# Azure DevOps Daily Task Automation

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/badge/pypi-azdo--daily-blue.svg)](https://pypi.org/project/azdo-daily/)

Python CLI for automating daily task creation, activation, and completion logging in Azure DevOps with AI-powered task breakdown via Claude.

- **AI Task Breakdown** — Claude reads user stories and generates concrete development tasks
- **Interactive Workflow** — `create` → `start` → `update` → `end` pipeline
- **Auto-linking** — Tasks linked to parent stories, related across multiple stories
- **Progress Tracking** — Log hours, remaining estimates, completion notes
- **Global CLI** — Install once, use anywhere: `azdo-daily configure`

## Installation

### From PyPI (recommended)

```bash
pip install azdo-daily
azdo-daily configure
```

### From source

Clone repository:

```bash
git clone https://github.com/MrShakila/Azdo-Daily.git
cd Azdo-Daily
pip install .
```

Or install in development mode:

```bash
pip install -e ".[dev]"
```

### Requirements

- Python 3.9+
- `requests` library (auto-installed)
- Anthropic API key (for AI task breakdown)
- Azure DevOps Personal Access Token (PAT)

Use from anywhere:

```bash
azdo-daily configure
azdo-daily status
```

## Configuration

On first run, configure your settings:

```bash
azdo-daily configure
```

Configuration stored in `.config/settings.json` (project-local, excluded from git).

Interactive prompts for:
| Field | Description |
|---|---|
| `org` | Your Azure DevOps organisation name |
| `project` | Project name |
| `pat` | Personal Access Token — needs **Work Items (Read & Write)** scope |
| `anthropic_api_key` | From console.anthropic.com — for AI task breakdown |
| `assigned_to` | Your email/display name — used to filter stories |
| `area_path` | Default area path for new tasks (optional) |

---

## Project Structure

```
azdo_daily/
├── main.py       — Entry point: argument parsing + command dispatch
├── config.py     — Configuration: load/save/validate settings
├── state.py      — Daily state: load/save work items per day
├── ui.py         — Terminal UI: colors, prompts, formatters, selection helpers
├── azdo.py       — Azure DevOps API client: work item operations
├── ai.py         — Claude AI: task breakdown from stories
└── commands.py   — Command handlers: configure, create, start, update, end, status
```

### Key Modules

**`azdo.py`** — Azure DevOps API client
- `session()` — authenticated HTTP session
- `wit_base()` — Work Item Tracking API base URL
- `get_my_stories()` — fetch assigned stories via WIQL
- `create_task()` — create new task linked to stories
- `set_workitem_state()` — change work item state
- `resolve_task()` — mark task complete with hours + comment
- `partial_task()` — log progress, keep task open
- `_patch_workitem()` — internal: apply JSON Patch operations
- `add_comment()` — internal: append work item comment

**`commands.py`** — CLI command handlers
- `cmd_configure()` — interactive setup
- `cmd_create()` — select stories → generate tasks → create in Azure DevOps
- `cmd_start()` — activate tasks (mark In Progress)
- `cmd_update()` — log progress on tasks
- `cmd_end()` — mark tasks done + auto-resolve stories
- `cmd_status()` — show today's stories and tasks

**`ui.py`** — Terminal UI helpers
- Color constants: `R`, `B`, `DIM`, `GR`, `YL`, `BL`, `CY`, `RD`, `MG`
- Output: `ok()`, `err()`, `info()`, `warn()`, `hdr()`, `sep()`
- Input: `ask()` (prompt with optional default)
- Formatters: `print_stories()`, `print_tasks()`
- Selection: `parse_selection()`, `select_from_list()` (handles "all")
- Conversion: `float_or_none()`

---

## Daily Workflow

### Setup (once)

```bash
azdo-daily configure
```

### Morning — Create tasks

```bash
azdo-daily create
```

1. Fetches all active User Stories assigned to you
2. You select stories to work on (e.g. `1` or `1,3` or `2-4`)
3. Choose task creation method:
   - **Use template** — Auto-generate standard tasks (UI, Logic, Unit Test)
   - **AI auto-breakdown** — Claude reads story and generates tasks
   - **Manual entry** — Type tasks yourself
   - **Template + AI** — Generate template tasks + AI suggestions, then review
4. If multiple stories: tasks created once, linked to all (child of #1, related to rest)
5. Task names include story title (e.g., "UI | My Story Title")
6. Tasks appear in Azure DevOps immediately with direct links

### Activate tasks

```bash
azdo-daily start
```

Marks selected new tasks as "In Progress" and auto-activates linked stories.

### Anytime — Check status

```bash
azdo-daily status
```

Shows active stories and all tasks with open/resolved counts.

### Throughout day — Log progress (optional)

```bash
azdo-daily update
```

Log hours spent and remaining estimates on open tasks (keeps them "In Progress").

### Evening — Mark complete

```bash
azdo-daily end
```

1. Lists all open tasks for today
2. You select which to complete (e.g. `1,3` or `all`)
3. For each: enter hours spent + optional closing note
4. Task marked done + hours logged
5. If all tasks for a story are done → story auto-resolved

---

## Maintenance Commands

### Reconfigure credentials

```bash
azdo-daily reconfigure
```

Update your Azure DevOps org, project, PAT, or Anthropic API key. Prompts to confirm before overwriting.

### Clear task history

```bash
azdo-daily clear-history
```

Delete all daily state files (`state/*.json`). Keeps configuration. Useful for starting fresh after month/week.

---

## State Files

Each day's data in `state/YYYY-MM-DD.json`:

```json
{
  "stories": [
    {"id": 42, "title": "Implement auth"}
  ],
  "tasks": [
    {
      "id": 101,
      "title": "Add login endpoint",
      "url": "https://...",
      "active": true,
      "closed": false,
      "completed_hours": 2.5,
      "remaining_hours": 1.0,
      "story_ids": [42]
    }
  ]
}
```

---

## Cron (optional)

Status reminder at 9 AM weekdays:

```cron
0 9 * * 1-5 azdo-daily status
```

> `start`, `update`, and `end` commands are interactive — use cron for `status` only.

---

## Troubleshooting

### "Work item X does not exist"

Task IDs in state file no longer exist in Azure DevOps. Reset today's state:

```bash
rm ~/.config/azdo_daily/state/2026-04-29.json  # or today's date
azdo-daily create
```

### "anthropic_api_key not set"

Run configure and enter Anthropic API key from [console.anthropic.com](https://console.anthropic.com):

```bash
azdo-daily configure
```

### "Personal Access Token (PAT) invalid"

Regenerate PAT in Azure DevOps → User Settings → Personal Access Tokens.
Must have **Work Items (Read & Write)** scope.

### ModuleNotFoundError after install

Reinstall in development mode:

```bash
pip install -e .
```

---

## Development

Install with dev tools:

```bash
pip install -e ".[dev]"
```

Install pre-commit hooks:

```bash
pip install pre-commit
pre-commit install
```

Format code (auto-runs on commit via pre-commit):

```bash
black azdo_daily/
```

Lint code:

```bash
flake8 azdo_daily/
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full development guide.

---

## License

MIT — see [LICENSE](LICENSE)
