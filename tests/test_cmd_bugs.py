"""Tests for the bugs and bug show/start/resolve commands."""

import argparse
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from azdo_daily.bugs import cmd_bug_resolve, cmd_bug_start, cmd_bug_task, cmd_bugs

ITEM = {
    "id": 5,
    "fields": {
        "System.Title": "Crash on save",
        "System.State": "Active",
        "Microsoft.VSTS.Common.Priority": 1,
        "Microsoft.VSTS.Common.Severity": "2 - High",
    },
}


def _args(**kw):
    return argparse.Namespace(**{"json": False, **kw})


def _azdo(mock_azdo):
    mock_azdo.IN_PROGRESS = ("InProgress",)
    mock_azdo.RESOLVED = ("Resolved", "Completed")
    mock_azdo.COMPLETED = ("Completed",)
    return mock_azdo


@patch("azdo_daily.bugs.config")
@patch("azdo_daily.bugs.azdo")
def test_bugs_json_is_pure_json(mock_azdo, mock_cfg, capsys):
    _azdo(mock_azdo).get_my_bugs.return_value = [ITEM]
    cmd_bugs(_args(json=True))
    out = capsys.readouterr().out
    assert json.loads(out) == [
        {
            "id": 5,
            "title": "Crash on save",
            "state": "Active",
            "priority": 1,
            "severity": "2 - High",
        }
    ]


@patch("azdo_daily.bugs.config")
@patch("azdo_daily.bugs.azdo")
def test_bugs_human_output_prefixes_bug_type(mock_azdo, mock_cfg, capsys):
    _azdo(mock_azdo).get_my_bugs.return_value = [ITEM]
    cmd_bugs(_args())
    assert "[Bug] [Active] #5" in capsys.readouterr().out


@patch("azdo_daily.bugs.config")
@patch("azdo_daily.bugs.azdo")
def test_bug_start_sets_in_progress_state_from_category(mock_azdo, mock_cfg, capsys):
    _azdo(mock_azdo).pick_state.return_value = "Active"
    cmd_bug_start(_args(id=5, json=True))
    assert mock_azdo.pick_state.call_args.args[2:] == ("Bug", ("InProgress",))
    assert mock_azdo.set_workitem_state.call_args.args[2:] == (5, "Active")
    assert json.loads(capsys.readouterr().out) == {"id": 5, "state": "Active"}


@patch("azdo_daily.bugs.config")
@patch("azdo_daily.bugs.azdo")
def test_bug_resolve_adds_comment_then_sets_resolved_state(mock_azdo, mock_cfg, capsys):
    calls = []
    _azdo(mock_azdo).pick_state.return_value = "Resolved"
    mock_azdo.add_comment.side_effect = lambda *a: calls.append("comment")
    mock_azdo.set_workitem_state.side_effect = lambda *a: calls.append("state")
    cmd_bug_resolve(_args(id=5, comment="fixed null check", task=None, json=True))
    assert calls == ["comment", "state"]
    assert mock_azdo.add_comment.call_args.args[2:] == (5, "fixed null check")
    assert mock_azdo.pick_state.call_args.args[3] == ("Resolved", "Completed")
    assert json.loads(capsys.readouterr().out) == {"id": 5, "state": "Resolved"}


@patch("azdo_daily.bugs.config")
@patch("azdo_daily.bugs.azdo")
def test_bugs_http_error_exits_1_and_prints_status_to_stderr(
    mock_azdo, mock_cfg, capsys
):
    resp = MagicMock(status_code=401)
    _azdo(mock_azdo).get_my_bugs.side_effect = requests.HTTPError(response=resp)
    with pytest.raises(SystemExit) as exc:
        cmd_bugs(_args(json=True))
    captured = capsys.readouterr()
    assert exc.value.code == 1
    assert "401" in captured.err
    assert captured.out == ""


@patch("azdo_daily.bugs.config")
@patch("azdo_daily.bugs.azdo")
def test_bug_task_creates_child_task_under_bug(mock_azdo, mock_cfg, capsys):
    _azdo(mock_azdo).create_task.return_value = {"id": 77}
    cmd_bug_task(_args(id=5, title="Fix crash on save", json=True))
    call = mock_azdo.create_task.call_args.args
    assert call[2] == {"title": "Fix crash on save"}
    assert call[3] == [5]
    assert json.loads(capsys.readouterr().out) == {"id": 77, "bug": 5}


@patch("azdo_daily.bugs.config")
@patch("azdo_daily.bugs.azdo")
def test_bug_resolve_with_task_closes_task_then_resolves_bug(
    mock_azdo, mock_cfg, capsys
):
    calls = []
    states = {"Task": "Closed", "Bug": "Resolved"}
    _azdo(mock_azdo).pick_state.side_effect = lambda s, c, t, cats: states[t]
    mock_azdo.set_workitem_state.side_effect = lambda s, c, i, st: calls.append((i, st))
    cmd_bug_resolve(_args(id=5, comment="fixed", task=77, json=True))
    assert calls == [(77, "Closed"), (5, "Resolved")]
    assert mock_azdo.pick_state.call_args_list[0].args[2:] == ("Task", ("Completed",))
    assert json.loads(capsys.readouterr().out) == {
        "id": 5,
        "state": "Resolved",
        "task": 77,
        "task_state": "Closed",
    }


@patch("azdo_daily.bugs.config")
@patch("azdo_daily.bugs.azdo")
def test_bug_resolve_without_task_leaves_task_alone(mock_azdo, mock_cfg, capsys):
    _azdo(mock_azdo).pick_state.return_value = "Resolved"
    cmd_bug_resolve(_args(id=5, comment="fixed", task=None, json=True))
    assert mock_azdo.pick_state.call_count == 1
    assert json.loads(capsys.readouterr().out) == {"id": 5, "state": "Resolved"}
