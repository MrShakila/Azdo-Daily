"""Tests for the Azure Repos pull request API calls."""

from unittest.mock import MagicMock

import pytest

from azdo_daily import git

CFG = {"org": "myorg", "project": "my project", "pat": "t", "repo": "myrepo"}


def _resp(data):
    r = MagicMock()
    r.json.return_value = data
    return r


def test_repo_base_requires_repo():
    with pytest.raises(ValueError):
        git.repo_base({**CFG, "repo": ""})


def test_repo_base_quotes_project():
    assert git.repo_base(CFG) == (
        "https://dev.azure.com/myorg/my%20project/_apis/git/repositories/myrepo"
    )


def test_create_pr_payload_refs_and_work_items():
    sess = MagicMock()
    sess.post.return_value = _resp({"pullRequestId": 12})
    pr = git.create_pr(sess, CFG, "bugfix/x", "main", "Fix bugs", "desc", [1, 2])
    body = sess.post.call_args.kwargs["json"]
    assert body["sourceRefName"] == "refs/heads/bugfix/x"
    assert body["targetRefName"] == "refs/heads/main"
    assert body["title"] == "Fix bugs"
    assert body["description"] == "desc"
    assert body["workItemRefs"] == [{"id": "1"}, {"id": "2"}]
    assert pr["id"] == 12
    assert pr["url"].endswith("/_git/myrepo/pullrequest/12")


def _thread(tid, status="active", comments=None, context=None):
    t = {"id": tid, "status": status, "comments": comments or []}
    if context:
        t["threadContext"] = context
    return t


def _comment(text, deleted=False, kind="text", author="Rev"):
    return {
        "content": text,
        "isDeleted": deleted,
        "commentType": kind,
        "author": {"displayName": author},
    }


def _threads(sess, threads):
    sess.get.return_value = _resp({"value": threads})
    return git.get_active_threads(sess, CFG, 12)


def test_active_threads_filters_non_active():
    out = _threads(
        MagicMock(),
        [
            _thread(1, "fixed", [_comment("done")]),
            _thread(2, "active", [_comment("fix this")]),
        ],
    )
    assert [t["id"] for t in out] == [2]


def test_active_threads_without_file_context_has_none_file():
    out = _threads(MagicMock(), [_thread(3, comments=[_comment("general")])])
    assert out[0]["file"] is None
    assert out[0]["line"] is None
    assert out[0]["comments"] == [{"author": "Rev", "text": "general"}]


def test_active_threads_reads_file_and_line():
    ctx = {"filePath": "/lib/a.dart", "rightFileStart": {"line": 10}}
    out = _threads(MagicMock(), [_thread(4, comments=[_comment("x")], context=ctx)])
    assert out[0]["file"] == "/lib/a.dart"
    assert out[0]["line"] == 10


def test_active_threads_skips_deleted_and_system_comments():
    out = _threads(
        MagicMock(),
        [
            _thread(5, comments=[_comment("gone", deleted=True)]),
            _thread(6, comments=[_comment("sys", kind="system")]),
            _thread(7, comments=[_comment("keep"), _comment("old", deleted=True)]),
        ],
    )
    assert [t["id"] for t in out] == [7]
    assert out[0]["comments"] == [{"author": "Rev", "text": "keep"}]


def test_reply_thread_resolve_patches_status_fixed():
    sess = MagicMock()
    git.reply_thread(sess, CFG, 12, 7, "done", True)
    post = sess.post.call_args
    assert post.args[0].endswith("/pullRequests/12/threads/7/comments?api-version=7.1")
    assert post.kwargs["json"] == {
        "content": "done",
        "parentCommentId": 1,
        "commentType": 1,
    }
    patch = sess.patch.call_args
    assert patch.args[0].endswith("/pullRequests/12/threads/7?api-version=7.1")
    assert patch.kwargs["json"] == {"status": "fixed"}


def test_reply_thread_without_resolve_does_not_patch():
    sess = MagicMock()
    git.reply_thread(sess, CFG, 12, 7, "question?", False)
    sess.patch.assert_not_called()
