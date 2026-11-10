"""Tests for bug queries, bug details and state lookup."""

from unittest.mock import MagicMock

import pytest

from azdo_daily import azdo

CFG = {
    "org": "myorg",
    "project": "myproject",
    "pat": "token",
    "assigned_to": "user@example.com",
}


def _resp(data):
    r = MagicMock()
    r.json.return_value = data
    return r


def test_get_my_bugs_query_filters_bug_type_and_open_states():
    sess = MagicMock()
    sess.post.return_value = _resp({"workItems": [{"id": 5}]})
    sess.get.return_value = _resp({"value": [{"id": 5, "fields": {}}]})
    bugs = azdo.get_my_bugs(sess, CFG)
    query = sess.post.call_args.kwargs["json"]["query"]
    assert "'Bug'" in query
    assert "NOT IN ('Closed','Removed')" in query
    assert bugs == [{"id": 5, "fields": {}}]


def test_get_my_bugs_rejects_quote_in_assignee():
    cfg = {**CFG, "assigned_to": "o'brien@example.com"}
    with pytest.raises(ValueError):
        azdo.get_my_bugs(MagicMock(), cfg)


def test_get_my_bugs_empty_returns_empty_list():
    sess = MagicMock()
    sess.post.return_value = _resp({"workItems": []})
    assert azdo.get_my_bugs(sess, CFG) == []
    sess.get.assert_not_called()


def _bug_sess(item, comments):
    sess = MagicMock()

    def fake_get(url, **kwargs):
        if "/comments" in url:
            return _resp({"comments": comments})
        return _resp(item)

    sess.get.side_effect = fake_get
    return sess


def test_get_bug_missing_repro_and_attachments():
    item = {"id": 7, "fields": {"System.Title": "Crash", "System.State": "Active"}}
    bug = azdo.get_bug(_bug_sess(item, []), CFG, 7)
    assert bug["id"] == 7
    assert bug["title"] == "Crash"
    assert bug["repro_steps"] == ""
    assert bug["attachments"] == []
    assert bug["comments"] == []


def test_get_bug_collects_attachments_and_comments():
    item = {
        "id": 7,
        "fields": {
            "System.Title": "Crash",
            "System.State": "Active",
            "Microsoft.VSTS.Common.Severity": "2 - High",
            "Microsoft.VSTS.TCM.ReproSteps": "<div>tap save</div>",
        },
        "relations": [
            {"rel": "AttachedFile", "url": "https://x/a.png"},
            {"rel": "ArtifactLink", "url": "https://x/other"},
        ],
    }
    comments = [{"text": "seen on iOS", "createdBy": {"displayName": "QA"}}]
    bug = azdo.get_bug(_bug_sess(item, comments), CFG, 7)
    assert bug["severity"] == "2 - High"
    assert bug["repro_steps"] == "<div>tap save</div>"
    assert bug["attachments"] == ["https://x/a.png"]
    assert bug["comments"] == [{"author": "QA", "text": "seen on iOS"}]


STATES = [
    {"name": "New", "category": "Proposed"},
    {"name": "Active", "category": "InProgress"},
    {"name": "Resolved", "category": "Resolved"},
    {"name": "Closed", "category": "Completed"},
]


def test_pick_state_by_category():
    sess = MagicMock()
    sess.get.return_value = _resp({"value": STATES})
    assert azdo.pick_state(sess, CFG, "Bug", azdo.IN_PROGRESS) == "Active"
    assert azdo.pick_state(sess, CFG, "Bug", azdo.RESOLVED) == "Resolved"


def test_pick_state_no_match_lists_available():
    sess = MagicMock()
    sess.get.return_value = _resp({"value": [{"name": "New", "category": "Proposed"}]})
    with pytest.raises(ValueError, match="available: New"):
        azdo.pick_state(sess, CFG, "Bug", azdo.IN_PROGRESS)
