"""Azure Repos API: pull requests and review threads."""

import requests


def repo_base(cfg: dict) -> str:
    """Base URL of the configured repository's Git API."""
    if not cfg.get("repo"):
        raise ValueError("Missing config: repo (run: azdo-daily configure)")
    o = requests.utils.quote(cfg["org"], safe="")
    p = requests.utils.quote(cfg["project"], safe="")
    r = requests.utils.quote(cfg["repo"], safe="")
    return f"https://dev.azure.com/{o}/{p}/_apis/git/repositories/{r}"


def create_pr(
    sess: requests.Session,
    cfg: dict,
    source: str,
    target: str,
    title: str,
    description: str,
    bug_ids: list,
) -> dict:
    """Open a PR from source to target linking the bug work items."""
    body = {
        "sourceRefName": f"refs/heads/{source}",
        "targetRefName": f"refs/heads/{target}",
        "title": title,
        "description": description,
        "workItemRefs": [{"id": str(i)} for i in bug_ids],
    }
    r = sess.post(
        f"{repo_base(cfg)}/pullrequests?api-version=7.1",
        json=body,
        headers={"Content-Type": "application/json"},
    )
    r.raise_for_status()
    pr_id = r.json()["pullRequestId"]
    o = requests.utils.quote(cfg["org"], safe="")
    p = requests.utils.quote(cfg["project"], safe="")
    rp = requests.utils.quote(cfg["repo"], safe="")
    url = f"https://dev.azure.com/{o}/{p}/_git/{rp}/pullrequest/{pr_id}"
    return {"id": pr_id, "url": url}


def _text_comments(thread: dict) -> list:
    return [
        {
            "author": (c.get("author") or {}).get("displayName", ""),
            "text": c.get("content", ""),
        }
        for c in thread.get("comments", [])
        if not c.get("isDeleted") and c.get("commentType", "text") == "text"
    ]


def get_active_threads(sess: requests.Session, cfg: dict, pr_id: int) -> list:
    """Active review threads that still have at least one text comment."""
    r = sess.get(f"{repo_base(cfg)}/pullRequests/{pr_id}/threads?api-version=7.1")
    r.raise_for_status()
    out = []
    for t in r.json().get("value", []):
        if t.get("status") != "active":
            continue
        comments = _text_comments(t)
        if not comments:
            continue
        ctx = t.get("threadContext") or {}
        out.append(
            {
                "id": t["id"],
                "file": ctx.get("filePath"),
                "line": (ctx.get("rightFileStart") or {}).get("line"),
                "comments": comments,
            }
        )
    return out


def reply_thread(
    sess: requests.Session,
    cfg: dict,
    pr_id: int,
    thread_id: int,
    text: str,
    resolve: bool,
) -> None:
    """Reply to a review thread and optionally mark it fixed."""
    base = f"{repo_base(cfg)}/pullRequests/{pr_id}/threads/{thread_id}"
    r = sess.post(
        f"{base}/comments?api-version=7.1",
        json={"content": text, "parentCommentId": 1, "commentType": 1},
        headers={"Content-Type": "application/json"},
    )
    r.raise_for_status()
    if resolve:
        r2 = sess.patch(
            f"{base}?api-version=7.1",
            json={"status": "fixed"},
            headers={"Content-Type": "application/json"},
        )
        r2.raise_for_status()
