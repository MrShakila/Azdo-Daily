"""Tests for get_closed_stories."""

from unittest.mock import MagicMock

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
    assert ">= '2026-05-01'" in wiql_body


def test_get_closed_stories_until_appended_to_wiql():
    sess = _make_sess([], [])
    azdo.get_closed_stories(sess, CFG, until="2026-05-31")
    wiql_body = sess.post.call_args[1]["json"]["query"]
    assert "<= '2026-05-31'" in wiql_body


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


def test_get_closed_stories_invalid_assignee_raises():
    sess = _make_sess([], [])
    bad_cfg = {**CFG, "assigned_to": "bad'user@example.com"}
    with pytest.raises(ValueError):
        azdo.get_closed_stories(sess, bad_cfg)


def test_get_closed_stories_both_since_and_until():
    sess = _make_sess([], [])
    azdo.get_closed_stories(sess, CFG, since="2026-05-01", until="2026-05-31")
    wiql_body = sess.post.call_args[1]["json"]["query"]
    assert ">= '2026-05-01'" in wiql_body
    assert "<= '2026-05-31'" in wiql_body


def test_get_closed_stories_invalid_since_raises():
    sess = _make_sess([], [])
    with pytest.raises(ValueError):
        azdo.get_closed_stories(sess, CFG, since="2026-05-01' OR '1'='1")


def test_get_closed_stories_invalid_until_raises():
    sess = _make_sess([], [])
    with pytest.raises(ValueError):
        azdo.get_closed_stories(sess, CFG, until="2026-05-31' OR '1'='1")
