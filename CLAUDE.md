# azdo-daily — Claude Project Instructions

## Project Overview

CLI tool for Azure DevOps daily task automation with AI breakdown via Claude.
Python package, installed as `azdo-daily` CLI. Owner: Shakila (shadikari012@gmail.com).

## Architecture

```
azdo_daily/
  main.py      — CLI entry point, argparse routing
  commands.py  — All command implementations (cmd_create, cmd_start, cmd_update, cmd_end, cmd_status)
  azdo.py      — Azure DevOps API calls (WIQL, work items, state transitions)
  ai.py        — Claude AI task breakdown
  config.py    — Config load/save (project-local .config/settings.json)
  state.py     — Daily state persistence (state/YYYY-MM-DD.json)
  ui.py        — Terminal output helpers (hdr, ok, warn, err, ask, print_tasks)
```

## Commands

| Command | Function | Description |
|---------|----------|-------------|
| `azdo-daily configure` | `cmd_configure` | Set org/project/PAT/API key |
| `azdo-daily create` | `cmd_create` | Pick stories, generate + create tasks |
| `azdo-daily start` | `cmd_start` | Select tasks to activate (New + Active) |
| `azdo-daily update` | `cmd_update` | Log hours/notes on open tasks |
| `azdo-daily end` | `cmd_end` | Close tasks, auto-resolve story if all done |
| `azdo-daily status` | `cmd_status` | Show stories + open tasks with states |
| `azdo-daily nuke` | `cmd_nuke` | Delete all config and state (destructive) |

## Key Behaviors

- `get_my_stories` WIQL: returns stories NOT in (Closed, Removed), assigned to configured user
- `get_task_children`: `active_only=True` excludes Closed/Resolved/Removed tasks (default)
- Auto-resolve story in `cmd_end`: only triggers when story has tasks AND all are closed
- Stories with zero tasks are never auto-resolved
- All task/story listings show `[WorkItemType] [State] Title` format

## API Fields

Stories fetch: `System.Id, System.Title, System.State, System.WorkItemType, Microsoft.VSTS.Common.Priority, System.AreaPath`

Tasks fetch (via `get_workitems`): `System.Id, System.Title, System.State, System.WorkItemType, Microsoft.VSTS.Common.Priority, System.AreaPath, Microsoft.VSTS.Scheduling.CompletedWork, Microsoft.VSTS.Scheduling.RemainingWork`

## Dev Workflow

```bash
pip install -e ".[dev]"   # editable install with dev deps
pre-commit install         # black + flake8 hooks (line-length 88)
azdo-daily configure       # set credentials
```

## Release Process

1. Bump `version` in `pyproject.toml`
2. Add entry to `CHANGELOG.md`
3. Commit: `chore: Bump version to X.Y.Z`
4. Tag: `git tag vX.Y.Z && git push origin vX.Y.Z`
5. GitHub release: `gh release create vX.Y.Z --title "vX.Y.Z" --notes "..."`

## Conventions

- Messages always prefix work item type: `[User Story]` or `[Task]`
- Error messages include HTTP status code
- Silent `except: pass` is forbidden — always surface errors as `ui.warn()`
- `ui.ok()` = green success, `ui.warn()` = yellow warning, `ui.err()` = red error
