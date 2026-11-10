"""Tests for the pr create, comments and reply commands."""

import argparse
import json
from unittest.mock import patch

import pytest

from azdo_daily.prs import cmd_pr_comments, cmd_pr_create, cmd_pr_reply


def _args(**kw):
    return argparse.Namespace(**{"json": True, **kw})


def _cfg(mock_cfg, target="main"):
    mock_cfg.load_cfg.return_value = {
        "org": "o",
        "project": "p",
        "pat": "t",
        "repo": "r",
        "target_branch": target,
    }


@pytest.fixture
def prs():
    with (
        patch("azdo_daily.prs.config") as cfg,
        patch("azdo_daily.prs.azdo") as azdo,
        patch("azdo_daily.prs.git_api") as api,
        patch("azdo_daily.prs.current_branch", return_value="bugfix/x") as branch,
        patch("azdo_daily.prs.branch_on_origin", return_value=True) as origin,
    ):
        _cfg(cfg)
        azdo.get_bug.side_effect = lambda s, c, i: {"id": i, "title": f"Bug {i}"}
        yield type(
            "P",
            (),
            {"cfg": cfg, "azdo": azdo, "api": api, "branch": branch, "origin": origin},
        )


def test_pr_create_refuses_target_branch(prs, capsys):
    prs.branch.return_value = "main"
    with pytest.raises(SystemExit) as exc:
        cmd_pr_create(_args(bugs="1", title="T"))
    assert exc.value.code == 1
    assert "main" in capsys.readouterr().err
    prs.api.create_pr.assert_not_called()


def test_pr_create_refuses_unpushed_branch(prs, capsys):
    prs.origin.return_value = False
    with pytest.raises(SystemExit) as exc:
        cmd_pr_create(_args(bugs="1", title="T"))
    assert exc.value.code == 1
    assert "push" in capsys.readouterr().err
    prs.api.create_pr.assert_not_called()


def test_pr_create_links_bugs_and_prints_json(prs, capsys):
    prs.api.create_pr.return_value = {"id": 12, "url": "https://x/12"}
    cmd_pr_create(_args(bugs="1,2", title="Fix bugs"))
    args = prs.api.create_pr.call_args.args
    assert args[2:5] == ("bugfix/x", "main", "Fix bugs")
    assert "#1 Bug 1" in args[5] and "#2 Bug 2" in args[5]
    assert args[6] == [1, 2]
    assert json.loads(capsys.readouterr().out) == {"id": 12, "url": "https://x/12"}


def test_pr_create_parses_bug_ids_list(prs):
    prs.api.create_pr.return_value = {"id": 1, "url": "u"}
    cmd_pr_create(_args(bugs="1, 2,3", title="T"))
    assert prs.api.create_pr.call_args.args[6] == [1, 2, 3]


def test_pr_create_non_numeric_bug_id_exits_1(prs, capsys):
    with pytest.raises(SystemExit) as exc:
        cmd_pr_create(_args(bugs="1,abc", title="T"))
    assert exc.value.code == 1
    assert "abc" in capsys.readouterr().err
    prs.api.create_pr.assert_not_called()


def test_pr_comments_json_pure(prs, capsys):
    threads = [{"id": 3, "file": None, "line": None, "comments": []}]
    prs.api.get_active_threads.return_value = threads
    cmd_pr_comments(_args(pr=12))
    assert json.loads(capsys.readouterr().out) == threads


def test_pr_reply_passes_resolve_flag(prs, capsys):
    cmd_pr_reply(_args(pr=12, thread=3, text="done", resolve=True))
    assert prs.api.reply_thread.call_args.args[2:] == (12, 3, "done", True)
    assert json.loads(capsys.readouterr().out) == {
        "pr": 12,
        "thread": 3,
        "resolved": True,
    }
