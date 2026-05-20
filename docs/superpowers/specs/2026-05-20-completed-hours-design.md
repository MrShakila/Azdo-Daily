# Completed Hours Report — Design Spec

**Date:** 2026-05-20  
**Feature:** `azdo-daily hours` command + `status` integration

---

## Overview

Surface total completed hours for closed tasks and user stories, grouped per story with a grand total. New dedicated `hours` command with optional date range flags; brief summary appended to `status`.

---

## Data Layer (`azdo.py`)

### `get_closed_stories(sess, cfg, since=None, until=None) -> list[dict]`

WIQL query:
- Types: same as `get_my_stories` (`Epic`, `Feature`, `User Story`, `Story`, `Bug`, `Issue`)
- `WHERE State = 'Closed'` AND assigned to configured user
- Optional: `AND [Microsoft.VSTS.Common.ClosedDate] >= 'YYYY-MM-DD'`
- Optional: `AND [Microsoft.VSTS.Common.ClosedDate] <= 'YYYY-MM-DD'`

Fields fetched via batch `get_workitems`:
- `System.Id`, `System.Title`, `System.State`, `System.WorkItemType`
- `Microsoft.VSTS.Common.ClosedDate`
- `Microsoft.VSTS.Scheduling.CompletedWork` (story's own hours — may be 0 or null)

### Task hours rollup (inline in `cmd_hours`)

For each closed story, call `get_task_children(active_only=False)`, filter tasks to state in `_DONE_STATES`. Sum `Microsoft.VSTS.Scheduling.CompletedWork` across closed tasks. `CompletedWork` is already fetched by `get_workitems` per existing field list.

---

## Command Layer (`commands.py`)

### `cmd_hours(args)`

Args:
- `--since YYYY-MM-DD` (optional)
- `--until YYYY-MM-DD` (optional)

Flow:
1. Load config, require `org`, `project`, `pat`
2. Call `azdo.get_closed_stories(sess, cfg, since, until)`
3. If none found: `ui.warn("No closed stories found.")` and return
4. For each story, fetch closed child tasks, sum `CompletedWork`
5. Display per story + grand total (see Output Format)

### `cmd_status` change

After existing task list output, call `get_closed_stories` (no date filter), sum all closed task `CompletedWork` and story `CompletedWork`. Append one summary line:

```
Completed hours (all time): Story: 2.0h  |  Tasks: 7.5h
```

Skips silently if no closed stories found (no extra API call if none).

---

## Output Format (`hours` command)

```
──────────────────────────────────────
Hours Report  (since: 2026-05-01)
──────────────────────────────────────

[User Story] #123  Story Title
  Story hours: 0.0h  |  Task hours: 3.0h
  [Task] #456  Task one  — 3.0h

[User Story] #124  Other Story
  Story hours: 2.0h  |  Task hours: 4.5h
  [Task] #457  Task A  — 2.0h
  [Task] #458  Task B  — 2.5h

──────────────────────────────────────
Grand total — Story hours: 2.0h  |  Task hours: 7.5h
```

- Stories with no closed tasks: show `Task hours: 0.0h` and `(no hours logged on closed tasks)`
- Tasks with null/0 `CompletedWork`: shown as `— 0.0h`
- Date range shown in header only when `--since` or `--until` supplied

---

## CLI Registration (`main.py`)

```
hours       Show completed hours for closed tasks and stories
  --since   Filter by closed date >= YYYY-MM-DD (optional)
  --until   Filter by closed date <= YYYY-MM-DD (optional)
```

---

## Error Handling

- `HTTPError` on `get_closed_stories`: `ui.err(f"Azure DevOps error: {status_code}")` + return
- `HTTPError` on per-story task fetch: `ui.warn(f"Failed to fetch tasks for #{story_id}")`, continue with remaining stories
- Invalid `--since`/`--until` format: argparse type validator raises `ArgumentTypeError` with message `"Date must be YYYY-MM-DD"`

---

## What Is Not In Scope

- Open (non-closed) task hours
- Editing or patching hours from this command
- Export to CSV/JSON
