# Completed Hours Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `azdo-daily hours` command that reports completed hours for closed tasks and user stories, grouped per story with a grand total, plus a brief hours summary in `azdo-daily status`.

**Architecture:** New `get_closed_stories()` in `azdo.py` queries closed work items via WIQL with optional date filters. `cmd_hours()` in `commands.py` fetches closed stories + their closed child tasks, displays story hours and task hours separately per story, and prints a grand total. `cmd_status()` appends a one-line hours summary. `main.py` registers the `hours` subcommand with `--since`/`--until` flags.

**Tech Stack:** Python, pytest, unittest.mock, requests

---

## File Map

| File | Change |
|------|--------|
| `azdo_daily/azdo.py` | Add `get_closed_stories()` |
| `azdo_daily/commands.py` | Add `cmd_hours()`, modify `cmd_status()` |
| `azdo_daily/main.py` | Register `hours` subcommand |
| `tests/__init__.py` | Create (empty) |
| `tests/test_azdo_hours.py` | Create: tests for `get_closed_stories` |
| `tests/test_cmd_hours.py` | Create: tests for `cmd_hours`, `cmd_status` hours line |

---

## Task 1: Test infrastructure setup

**Files:**
- Create: `tests/__init__.py`

- [ ] **Step 1: Create tests package**

```bash
mkdir -p /path/to/azdo_daily/tests
touch tests/__init__.py
```

- [ ] **Step 2: Verify pytest works**

```bash
pip install pytest
pytest --collect-only
```

Expected: `no tests ran` (zero tests collected, no errors)

- [ ] **Step 3: Commit**

```bash
git add tests/__init__.py
git commit -m "chore: Add tests package"
```

---

## Task 2: `get_closed_stories` in `azdo.py`

**Files:**
- Create: `tests/test_azdo_hours.py`
- Modify: `azdo_daily/azdo.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_azdo_hours.py`:

```python
"""Tests for get_closed_stories."""
from unittest.mock import MagicMock, patch

import pytest

from azdo_daily import azdo


def _make_sess(wiql_ids, items):
    """Return a mock Session where WIQL returns wiql_ids and workitems returns items."""
    sess = MagicMock()
    wiql_resp = MagicMock()
    wiql_resp.json.return_value = {"workItems": [{"id": i} for i in wiql_ids]}
    items_resp = MagicMock()
    items_resp.json.return_value = {"value": items}
    sess.post.return_value = wiql_resp
    sess.get.return_value = items_resp
    return sess


CFG = {
    "org": "myorg",
    "project": "myproject",
    "pat": "token",
    "assigned_to": "user@example.com",
}

CLOSED_STORY = {
    "id": 10,
    "fields": {
        "System.Id": 10,
        "System.Title": "Story A",
        "System.State": "Closed",
        "System.WorkItemType": "User Story",
        "Microsoft.VSTS.Common.ClosedDate": "2026-05-10T00:00:00Z",
        "Microsoft.VSTS.Scheduling.CompletedWork": 2.0,
    },
}


def test_get_closed_stories_returns_items():
    sess = _make_sess([10], [CLOSED_STORY])
    result = azdo.get_closed_stories(sess, CFG)
    assert len(result) == 1
    assert result[0]["id"] == 10
    assert result[0]["fields"]["Microsoft.VSTS.Scheduling.CompletedWork"] == 2.0


def test_get_closed_stories_empty_when_no_wiql_results():
    sess = _make_sess([], [])
    result = azdo.get_closed_stories(sess, CFG)
    assert result == []


def test_get_closed_stories_since_appended_to_wiql():
    sess = _make_sess([], [])
    azdo.get_closed_stories(sess, CFG, since="2026-05-01")
    wiql_body = sess.post.call_args[1]["json"]["query"]
    assert "2026-05-01" in wiql_body
    assert "ClosedDate" in wiql_body


def test_get_closed_stories_until_appended_to_wiql():
    sess = _make_sess([], [])
    azdo.get_closed_stories(sess, CFG, until="2026-05-31")
    wiql_body = sess.post.call_args[1]["json"]["query"]
    assert "2026-05-31" in wiql_body


def test_get_closed_stories_workitems_fields_include_completed_work():
    sess = _make_sess([10], [CLOSED_STORY])
    azdo.get_closed_stories(sess, CFG)
    get_url = sess.get.call_args[0][0]
    assert "CompletedWork" in get_url


def test_get_closed_stories_invalid_project_raises():
    sess = _make_sess([], [])
    bad_cfg = {**CFG, "project": "bad'project"}
    with pytest.raises(ValueError):
        azdo.get_closed_stories(sess, bad_cfg)
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_azdo_hours.py -v
```

Expected: `FAILED` / `AttributeError: module 'azdo_daily.azdo' has no attribute 'get_closed_stories'`

- [ ] **Step 3: Implement `get_closed_stories` in `azdo_daily/azdo.py`**

Add after `get_my_stories` (around line 173):

```python
def get_closed_stories(
    sess: requests.Session,
    cfg: dict,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> list[dict]:
    """WIQL query: closed work items assigned to me, with optional ClosedDate filter."""
    project = cfg.get("project", "")
    if "'" in project:
        raise ValueError("Invalid project: contains forbidden character")
    assignee = cfg.get("assigned_to") or "@Me"
    if "'" in assignee:
        raise ValueError("Invalid assignee: contains forbidden character")
    if "@" not in assignee and assignee != "@Me":
        assignee_clause = f"[System.AssignedTo] contains '{assignee}'"
    else:
        assignee_clause = (
            "[System.AssignedTo] = @Me"
            if assignee == "@Me"
            else f"[System.AssignedTo] = '{assignee}'"
        )

    types = "'Epic','Feature','User Story','Story','Bug','Issue'"
    date_clauses = ""
    if since:
        date_clauses += (
            f"\n  AND  [Microsoft.VSTS.Common.ClosedDate] >= '{since}'"
        )
    if until:
        date_clauses += (
            f"\n  AND  [Microsoft.VSTS.Common.ClosedDate] <= '{until}'"
        )

    wiql = {
        "query": f"""
            SELECT [System.Id],[System.Title],[System.State],
                   [System.WorkItemType],[Microsoft.VSTS.Common.ClosedDate]
            FROM   WorkItems
            WHERE  [System.TeamProject] = '{cfg['project']}'
              AND  [System.WorkItemType] IN ({types})
              AND  {assignee_clause}
              AND  [System.State] = 'Closed'{date_clauses}
            ORDER BY [Microsoft.VSTS.Common.ClosedDate] DESC
        """
    }
    base = wit_base(cfg)
    r = sess.post(
        f"{base}/wiql?api-version=7.1",
        json=wiql,
        headers={"Content-Type": "application/json"},
    )
    r.raise_for_status()
    ids = [str(w["id"]) for w in r.json().get("workItems", [])]
    if not ids:
        return []
    r2 = sess.get(
        f"{base}/workitems?ids={','.join(ids)}"
        "&fields=System.Id,System.Title,System.State,System.WorkItemType,"
        "Microsoft.VSTS.Common.ClosedDate,"
        "Microsoft.VSTS.Scheduling.CompletedWork"
        "&api-version=7.1",
        headers={"Content-Type": "application/json"},
    )
    r2.raise_for_status()
    return r2.json().get("value", [])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_azdo_hours.py -v
```

Expected: all 6 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add azdo_daily/azdo.py tests/test_azdo_hours.py
git commit -m "feat: Add get_closed_stories to azdo.py"
```

---

## Task 3: `cmd_hours` in `commands.py`

**Files:**
- Create: `tests/test_cmd_hours.py`
- Modify: `azdo_daily/commands.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cmd_hours.py`:

```python
"""Tests for cmd_hours and cmd_status hours summary."""
import argparse
from unittest.mock import MagicMock, patch

import pytest

from azdo_daily.commands import cmd_hours


def _args(since=None, until=None):
    a = argparse.Namespace()
    a.since = since
    a.until = until
    return a


CLOSED_STORY = {
    "id": 10,
    "fields": {
        "System.Title": "Story A",
        "System.WorkItemType": "User Story",
        "Microsoft.VSTS.Scheduling.CompletedWork": 1.0,
    },
}

CLOSED_TASK = {
    "id": 100,
    "fields": {
        "System.Title": "Task one",
        "System.WorkItemType": "Task",
        "System.State": "Closed",
        "Microsoft.VSTS.Scheduling.CompletedWork": 3.0,
    },
}

CLOSED_TASK_NO_HOURS = {
    "id": 101,
    "fields": {
        "System.Title": "Task two",
        "System.WorkItemType": "Task",
        "System.State": "Closed",
        "Microsoft.VSTS.Scheduling.CompletedWork": None,
    },
}


@patch("azdo_daily.commands.config")
@patch("azdo_daily.commands.azdo")
def test_cmd_hours_no_closed_stories_warns(mock_azdo, mock_cfg, capsys):
    mock_cfg.load_cfg.return_value = {"org": "o", "project": "p", "pat": "t"}
    mock_cfg.require_cfg.return_value = None
    mock_azdo.session.return_value = MagicMock()
    mock_azdo.get_closed_stories.return_value = []

    cmd_hours(_args())

    out = capsys.readouterr()
    assert "No closed stories" in out.err or "No closed stories" in out.out


@patch("azdo_daily.commands.config")
@patch("azdo_daily.commands.azdo")
def test_cmd_hours_shows_story_and_task_hours(mock_azdo, mock_cfg, capsys):
    mock_cfg.load_cfg.return_value = {"org": "o", "project": "p", "pat": "t"}
    mock_cfg.require_cfg.return_value = None
    mock_azdo.session.return_value = MagicMock()
    mock_azdo.get_closed_stories.return_value = [CLOSED_STORY]
    mock_azdo.get_task_children.return_value = [CLOSED_TASK]
    mock_azdo._DONE_STATES = ("Closed", "Resolved", "Removed")

    cmd_hours(_args())

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Story hours: 1.0h" in combined
    assert "Task hours: 3.0h" in combined
    assert "Grand total" in combined


@patch("azdo_daily.commands.config")
@patch("azdo_daily.commands.azdo")
def test_cmd_hours_null_task_hours_treated_as_zero(mock_azdo, mock_cfg, capsys):
    mock_cfg.load_cfg.return_value = {"org": "o", "project": "p", "pat": "t"}
    mock_cfg.require_cfg.return_value = None
    mock_azdo.session.return_value = MagicMock()
    mock_azdo.get_closed_stories.return_value = [CLOSED_STORY]
    mock_azdo.get_task_children.return_value = [CLOSED_TASK_NO_HOURS]
    mock_azdo._DONE_STATES = ("Closed", "Resolved", "Removed")

    cmd_hours(_args())

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Task hours: 0.0h" in combined


@patch("azdo_daily.commands.config")
@patch("azdo_daily.commands.azdo")
def test_cmd_hours_grand_total_sums_all_stories(mock_azdo, mock_cfg, capsys):
    story_b = {
        "id": 11,
        "fields": {
            "System.Title": "Story B",
            "System.WorkItemType": "User Story",
            "Microsoft.VSTS.Scheduling.CompletedWork": 2.0,
        },
    }
    task_b = {
        "id": 102,
        "fields": {
            "System.Title": "Task B",
            "System.WorkItemType": "Task",
            "System.State": "Closed",
            "Microsoft.VSTS.Scheduling.CompletedWork": 5.0,
        },
    }
    mock_cfg.load_cfg.return_value = {"org": "o", "project": "p", "pat": "t"}
    mock_cfg.require_cfg.return_value = None
    mock_azdo.session.return_value = MagicMock()
    mock_azdo.get_closed_stories.return_value = [CLOSED_STORY, story_b]
    mock_azdo.get_task_children.side_effect = [[CLOSED_TASK], [task_b]]
    mock_azdo._DONE_STATES = ("Closed", "Resolved", "Removed")

    cmd_hours(_args())

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    # story total: 1.0 + 2.0 = 3.0, task total: 3.0 + 5.0 = 8.0
    assert "Story hours: 3.0h" in combined
    assert "Task hours: 8.0h" in combined


@patch("azdo_daily.commands.config")
@patch("azdo_daily.commands.azdo")
def test_cmd_hours_story_with_no_closed_tasks_shows_zero(mock_azdo, mock_cfg, capsys):
    mock_cfg.load_cfg.return_value = {"org": "o", "project": "p", "pat": "t"}
    mock_cfg.require_cfg.return_value = None
    mock_azdo.session.return_value = MagicMock()
    mock_azdo.get_closed_stories.return_value = [CLOSED_STORY]
    mock_azdo.get_task_children.return_value = []  # no children at all
    mock_azdo._DONE_STATES = ("Closed", "Resolved", "Removed")

    cmd_hours(_args())

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "no hours logged on closed tasks" in combined
    assert "Task hours: 0.0h" in combined
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_cmd_hours.py -v
```

Expected: `FAILED` / `ImportError: cannot import name 'cmd_hours'`

- [ ] **Step 3: Implement `cmd_hours` in `azdo_daily/commands.py`**

Add `cmd_hours` function after `cmd_end` (before `cmd_status`):

```python
def cmd_hours(args):
    """Show completed hours for closed tasks and stories."""
    cfg = config.load_cfg()
    config.require_cfg(cfg, "org", "project", "pat")
    sess = azdo.session(cfg)

    since = getattr(args, "since", None)
    until = getattr(args, "until", None)

    header = "Hours Report"
    if since:
        header += f"  (since: {since})"
    if until:
        header += f"  (until: {until})"
    ui.hdr(header)

    try:
        stories = azdo.get_closed_stories(sess, cfg, since, until)
    except requests.HTTPError as e:
        ui.err(f"Azure DevOps error: {e.response.status_code}")
        return

    if not stories:
        ui.warn("No closed stories found.")
        return

    total_story_hours = 0.0
    total_task_hours = 0.0

    for story in stories:
        f = story.get("fields", {})
        story_id = story["id"]
        item_type = f.get("System.WorkItemType", "User Story")
        title = f.get("System.Title", "")
        story_hours = f.get("Microsoft.VSTS.Scheduling.CompletedWork") or 0.0
        total_story_hours += story_hours

        try:
            all_children = azdo.get_task_children(sess, cfg, story_id, active_only=False)
        except requests.HTTPError as e:
            ui.warn(f"Failed to fetch tasks for #{story_id}: {e.response.status_code}")
            all_children = []

        closed_tasks = [
            t for t in all_children
            if t.get("fields", {}).get("System.State") in azdo._DONE_STATES
        ]

        task_hours = sum(
            (t.get("fields", {}).get("Microsoft.VSTS.Scheduling.CompletedWork") or 0.0)
            for t in closed_tasks
        )
        total_task_hours += task_hours

        print(f"\n  {ui.CY}[{item_type}] #{story_id}{ui.R}  {title}")
        print(f"    Story hours: {story_hours:.1f}h  |  Task hours: {task_hours:.1f}h")

        if not closed_tasks:
            print(f"    {ui.DIM}(no hours logged on closed tasks){ui.R}")
        else:
            for t in closed_tasks:
                tf = t.get("fields", {})
                task_type = tf.get("System.WorkItemType", "Task")
                task_title = tf.get("System.Title", "")
                h = tf.get("Microsoft.VSTS.Scheduling.CompletedWork") or 0.0
                print(
                    f"    {ui.DIM}[{task_type}] #{t['id']}  {task_title}"
                    f"  — {h:.1f}h{ui.R}"
                )

    print()
    ui.sep()
    ui.info(
        f"Grand total — Story hours: {total_story_hours:.1f}h"
        f"  |  Task hours: {total_task_hours:.1f}h"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_cmd_hours.py -v
```

Expected: all 5 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add azdo_daily/commands.py tests/test_cmd_hours.py
git commit -m "feat: Add cmd_hours command"
```

---

## Task 4: Hours summary in `cmd_status`

**Files:**
- Modify: `azdo_daily/commands.py` (end of `cmd_status`)
- Modify: `tests/test_cmd_hours.py` (append new tests)

- [ ] **Step 1: Write failing test**

Append to `tests/test_cmd_hours.py`:

```python
from azdo_daily.commands import cmd_status


@patch("azdo_daily.commands.config")
@patch("azdo_daily.commands.azdo")
def test_cmd_status_appends_hours_summary(mock_azdo, mock_cfg, capsys):
    mock_cfg.load_cfg.return_value = {"org": "o", "project": "p", "pat": "t"}
    mock_cfg.require_cfg.return_value = None
    mock_azdo.session.return_value = MagicMock()

    # Active stories (for main status display)
    mock_azdo.get_my_stories.return_value = []

    # Closed stories (for hours summary)
    mock_azdo.get_closed_stories.return_value = [
        {
            "id": 10,
            "fields": {
                "System.Title": "Story A",
                "System.WorkItemType": "User Story",
                "Microsoft.VSTS.Scheduling.CompletedWork": 1.5,
            },
        }
    ]
    mock_azdo.get_task_children.return_value = [
        {
            "id": 100,
            "fields": {
                "System.Title": "Task one",
                "System.WorkItemType": "Task",
                "System.State": "Closed",
                "Microsoft.VSTS.Scheduling.CompletedWork": 4.0,
            },
        }
    ]
    mock_azdo._DONE_STATES = ("Closed", "Resolved", "Removed")

    cmd_status(argparse.Namespace(date=None))

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Completed hours" in combined
    assert "Story: 1.5h" in combined
    assert "Tasks: 4.0h" in combined


@patch("azdo_daily.commands.config")
@patch("azdo_daily.commands.azdo")
def test_cmd_status_skips_hours_when_no_closed_stories(mock_azdo, mock_cfg, capsys):
    mock_cfg.load_cfg.return_value = {"org": "o", "project": "p", "pat": "t"}
    mock_cfg.require_cfg.return_value = None
    mock_azdo.session.return_value = MagicMock()
    mock_azdo.get_my_stories.return_value = []
    mock_azdo.get_closed_stories.return_value = []

    cmd_status(argparse.Namespace(date=None))

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Completed hours" not in combined
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/test_cmd_hours.py::test_cmd_status_appends_hours_summary tests/test_cmd_hours.py::test_cmd_status_skips_hours_when_no_closed_stories -v
```

Expected: `FAILED`

- [ ] **Step 3: Modify `cmd_status` to append hours summary**

In `azdo_daily/commands.py`, at the end of `cmd_status` (after the `ui.info(f"Total: ...")` line and the `return` in the empty-open-tasks branch), add a helper `_append_hours_summary` called from two places in `cmd_status`.

Replace the final block of `cmd_status` (starting from `# Summary` comment, around line 675):

```python
    # Summary
    closed_c = sum(1 for t in display_tasks if t.get("closed"))
    open_c = sum(1 for t in display_tasks if not t.get("closed"))
    print()
    ui.info(f"Total: {closed_c} resolved  /  {open_c} still open")
    _print_hours_summary(sess, cfg)
```

And for the early-return branch where all tasks are done (around line 652):

```python
    if not open_tasks:
        done_c = total_task_count
        ui.ok(f"All {done_c} task(s) done for active stories.")
        _print_hours_summary(sess, cfg)
        return
```

Add new helper function before `cmd_status`:

```python
def _print_hours_summary(sess, cfg):
    """Fetch closed stories and print a one-line hours summary. Silent if none."""
    try:
        closed_stories = azdo.get_closed_stories(sess, cfg)
    except requests.HTTPError:
        return

    if not closed_stories:
        return

    total_story_hours = 0.0
    total_task_hours = 0.0
    for story in closed_stories:
        f = story.get("fields", {})
        total_story_hours += f.get("Microsoft.VSTS.Scheduling.CompletedWork") or 0.0
        try:
            all_children = azdo.get_task_children(sess, cfg, story["id"], active_only=False)
        except requests.HTTPError:
            continue
        for t in all_children:
            if t.get("fields", {}).get("System.State") in azdo._DONE_STATES:
                total_task_hours += (
                    t.get("fields", {}).get("Microsoft.VSTS.Scheduling.CompletedWork") or 0.0
                )

    ui.info(
        f"Completed hours (all time):  Story: {total_story_hours:.1f}h"
        f"  |  Tasks: {total_task_hours:.1f}h"
    )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_cmd_hours.py -v
```

Expected: all 7 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add azdo_daily/commands.py tests/test_cmd_hours.py
git commit -m "feat: Append completed hours summary to status command"
```

---

## Task 5: Register `hours` in `main.py`

**Files:**
- Modify: `azdo_daily/main.py`

- [ ] **Step 1: Add date validator and `hours` subcommand**

In `azdo_daily/main.py`, add import at top:

```python
import argparse
from datetime import datetime

from azdo_daily.commands import (
    cmd_clear_history,
    cmd_configure,
    cmd_create,
    cmd_doctor,
    cmd_end,
    cmd_help,
    cmd_hours,
    cmd_nuke,
    cmd_reconfigure,
    cmd_start,
    cmd_status,
    cmd_update,
)
```

Add helper before `main()`:

```python
def _valid_date(s):
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        raise argparse.ArgumentTypeError(f"Date must be YYYY-MM-DD, got: {s}")
```

Add subcommand registration inside `main()`, after `status_p`:

```python
    hours_p = sub.add_parser("hours", help="Show completed hours for closed tasks and stories")
    hours_p.add_argument("--since", type=_valid_date, metavar="YYYY-MM-DD",
                         help="Filter by closed date >= YYYY-MM-DD")
    hours_p.add_argument("--until", type=_valid_date, metavar="YYYY-MM-DD",
                         help="Filter by closed date <= YYYY-MM-DD")
```

Add to the dispatch dict:

```python
        "hours": cmd_hours,
```

Also add to the docstring at top of file and `cmd_help` list in `commands.py`:

In `cmd_help` in `commands.py`, add to the `commands` list:

```python
        ("hours", "Show completed hours for closed tasks and stories (--since/--until)"),
```

- [ ] **Step 2: Verify CLI registers correctly**

```bash
azdo-daily hours --help
```

Expected output:
```
usage: azdo-daily hours [-h] [--since YYYY-MM-DD] [--until YYYY-MM-DD]

options:
  -h, --help           show this help message and exit
  --since YYYY-MM-DD   Filter by closed date >= YYYY-MM-DD
  --until YYYY-MM-DD   Filter by closed date <= YYYY-MM-DD
```

- [ ] **Step 3: Test invalid date rejected**

```bash
azdo-daily hours --since 2026/05/01
```

Expected: `error: argument --since: Date must be YYYY-MM-DD, got: 2026/05/01`

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add azdo_daily/main.py azdo_daily/commands.py
git commit -m "feat: Register hours subcommand in CLI"
```

---

## Self-Review Notes

- **Spec coverage:** `get_closed_stories` with `since`/`until` ✓ — `cmd_hours` per-story + grand total ✓ — story hours + task hours separate ✓ — stories with no closed tasks show `0.0h` + message ✓ — `cmd_status` one-line summary ✓ — `--since`/`--until` argparse with validator ✓
- **Placeholders:** None.
- **Type consistency:** `get_closed_stories` returns `list[dict]` matching `get_my_stories` shape. `_print_hours_summary` takes same `(sess, cfg)` signature used throughout. `azdo._DONE_STATES` referenced directly (existing tuple in `azdo.py`). `get_task_children` signature unchanged.
