"""Tests for cmd_hours and cmd_status hours summary."""

import argparse
from unittest.mock import MagicMock, patch

from azdo_daily.commands import cmd_hours, cmd_status


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


@patch("azdo_daily.commands.config")
@patch("azdo_daily.commands.azdo")
def test_cmd_hours_http_error_on_stories_shows_error(mock_azdo, mock_cfg, capsys):
    import requests as req

    mock_cfg.load_cfg.return_value = {"org": "o", "project": "p", "pat": "t"}
    mock_cfg.require_cfg.return_value = None
    mock_azdo.session.return_value = MagicMock()
    err_resp = MagicMock()
    err_resp.status_code = 401
    mock_azdo.get_closed_stories.side_effect = req.HTTPError(response=err_resp)

    cmd_hours(_args())

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "401" in combined
    # Should not print Grand total
    assert "Grand total" not in combined


@patch("azdo_daily.commands.config")
@patch("azdo_daily.commands.azdo")
def test_cmd_hours_http_error_on_tasks_warns_and_continues(mock_azdo, mock_cfg, capsys):
    import requests as req

    mock_cfg.load_cfg.return_value = {"org": "o", "project": "p", "pat": "t"}
    mock_cfg.require_cfg.return_value = None
    mock_azdo.session.return_value = MagicMock()
    mock_azdo.get_closed_stories.return_value = [CLOSED_STORY]
    mock_azdo._DONE_STATES = ("Closed", "Resolved", "Removed")
    err_resp = MagicMock()
    err_resp.status_code = 500
    mock_azdo.get_task_children.side_effect = req.HTTPError(response=err_resp)

    cmd_hours(_args())

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    # Should warn about failure
    assert "Failed to fetch tasks" in combined or "500" in combined
    # Should still show grand total (continues despite error)
    assert "Grand total" in combined


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


@patch("azdo_daily.commands.config")
@patch("azdo_daily.commands.azdo")
def test_cmd_status_hours_shown_when_all_tasks_done(mock_azdo, mock_cfg, capsys):
    mock_cfg.load_cfg.return_value = {"org": "o", "project": "p", "pat": "t"}
    mock_cfg.require_cfg.return_value = None
    mock_azdo.session.return_value = MagicMock()

    mock_azdo.get_my_stories.return_value = [
        {
            "id": 1,
            "fields": {
                "System.Title": "Active Story",
                "System.WorkItemType": "User Story",
                "System.State": "Active",
            },
        }
    ]
    # active_only=False: 1 closed task (total count)
    # active_only=True: no open tasks -> triggers "all tasks done" branch
    # active_only=False for story 99 in _print_hours_summary
    mock_azdo.get_task_children.side_effect = [
        [
            {
                "id": 50,
                "fields": {
                    "System.Title": "Done task",
                    "System.WorkItemType": "Task",
                    "System.State": "Closed",
                },
            }
        ],
        [],
        [],
    ]

    mock_azdo.get_closed_stories.return_value = [
        {
            "id": 99,
            "fields": {
                "System.Title": "Old Story",
                "System.WorkItemType": "User Story",
                "Microsoft.VSTS.Scheduling.CompletedWork": 2.0,
            },
        }
    ]
    mock_azdo._DONE_STATES = ("Closed", "Resolved", "Removed")

    cmd_status(argparse.Namespace(date=None))

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "All" in combined and "done" in combined
    assert "Completed hours" in combined


@patch("azdo_daily.commands.config")
@patch("azdo_daily.commands.azdo")
def test_cmd_status_hours_shown_at_end_with_open_tasks(mock_azdo, mock_cfg, capsys):
    mock_cfg.load_cfg.return_value = {"org": "o", "project": "p", "pat": "t"}
    mock_cfg.require_cfg.return_value = None
    mock_azdo.session.return_value = MagicMock()

    mock_azdo.get_my_stories.return_value = [
        {
            "id": 1,
            "fields": {
                "System.Title": "Active Story",
                "System.WorkItemType": "User Story",
                "System.State": "Active",
            },
        }
    ]
    open_task = {
        "id": 51,
        "fields": {
            "System.Title": "Open task",
            "System.WorkItemType": "Task",
            "System.State": "Active",
            "System.ChangedDate": None,
        },
    }
    # calls: active_only=False for story 1, active_only=True for story 1,
    # active_only=False for story 99 (in _print_hours_summary)
    mock_azdo.get_task_children.side_effect = [
        [open_task],
        [open_task],
        [],
    ]

    mock_azdo.get_closed_stories.return_value = [
        {
            "id": 99,
            "fields": {
                "System.Title": "Old Story",
                "System.WorkItemType": "User Story",
                "Microsoft.VSTS.Scheduling.CompletedWork": 3.0,
            },
        }
    ]
    mock_azdo._DONE_STATES = ("Closed", "Resolved", "Removed")

    cmd_status(argparse.Namespace(date=None))

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Total:" in combined
    assert "Completed hours" in combined


@patch("azdo_daily.commands.config")
@patch("azdo_daily.commands.azdo")
def test_cmd_hours_value_error_shows_config_error(mock_azdo, mock_cfg, capsys):
    mock_cfg.load_cfg.return_value = {"org": "o", "project": "p", "pat": "t"}
    mock_cfg.require_cfg.return_value = None
    mock_azdo.session.return_value = MagicMock()
    mock_azdo.get_closed_stories.side_effect = ValueError(
        "Invalid project: contains forbidden character"
    )

    cmd_hours(_args())

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Configuration error" in combined
    assert "Grand total" not in combined
