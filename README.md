# Azure DevOps Daily Task Automation

Automate daily task creation, activation, and completion logging in Azure DevOps with AI-powered task breakdown via Claude.

## Installation

Install globally from this repository:

```bash
pip install .
```

Or install in development mode:

```bash
pip install -e .
```

Then use from anywhere:

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
| `close_state` | `Done` / `Closed` / `Resolved` (depends on your process template) |

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
   - **AI auto-breakdown** — Claude reads story and generates tasks
   - **Manual entry** — type tasks yourself
   - **Both** — AI suggests, you review/add/remove
4. If multiple stories: tasks created once, linked to all (child of #1, related to rest)
5. Tasks appear in Azure DevOps immediately

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
