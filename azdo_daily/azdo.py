"""Azure DevOps API client."""

from typing import Optional

import requests


def session(cfg: dict) -> requests.Session:
    """Create authenticated session with PAT."""
    s = requests.Session()
    s.auth = ("", cfg["pat"])
    return s


def wit_base(cfg: dict) -> str:
    """Base URL for Work Item Tracking API."""
    o = requests.utils.quote(cfg["org"], safe="")
    p = requests.utils.quote(cfg["project"], safe="")
    return f"https://dev.azure.com/{o}/{p}/_apis/wit"


def _patch_workitem(sess: requests.Session, cfg: dict, item_id: int, ops: list):
    """Apply JSON Patch operations to work item."""
    base = wit_base(cfg)
    r = sess.patch(
        f"{base}/workitems/{item_id}?api-version=7.1",
        json=ops,
        headers={"Content-Type": "application/json-patch+json"},
    )
    r.raise_for_status()


def add_comment(sess: requests.Session, cfg: dict, item_id: int, text: str):
    """Add comment to work item."""
    base = wit_base(cfg)
    r = sess.post(
        f"{base}/workitems/{item_id}/comments?api-version=7.1-preview.3",
        json={"text": text},
        headers={"Content-Type": "application/json"},
    )
    r.raise_for_status()


def set_workitem_state(sess: requests.Session, cfg: dict, item_id: int, state: str):
    """Set work item state."""
    if not state:
        raise ValueError("State cannot be empty")
    ops = [{"op": "replace", "path": "/fields/System.State", "value": state}]
    _patch_workitem(sess, cfg, item_id, ops)


def get_workitems(sess: requests.Session, cfg: dict, ids: list[int]) -> list[dict]:
    """Fetch work item details by IDs."""
    if not ids:
        return []
    base = wit_base(cfg)
    r = sess.get(
        f"{base}/workitems?ids={','.join(map(str, ids))}"
        "&fields=System.Id,System.Title,System.State,System.WorkItemType,"
        "Microsoft.VSTS.Common.Priority,System.AreaPath,System.ChangedDate"
        "&api-version=7.1",
        headers={"Content-Type": "application/json"},
    )
    r.raise_for_status()
    return r.json().get("value", [])


def refresh_task_status(sess: requests.Session, cfg: dict, task_ids: list[int]) -> dict:
    """Fetch fresh task status from API, return map of task_id -> {id, title, state}."""
    if not task_ids:
        return {}
    items = get_workitems(sess, cfg, task_ids)
    return {
        t["id"]: {
            "id": t["id"],
            "title": t["fields"].get("System.Title", ""),
            "state": t["fields"].get("System.State", ""),
            "closed": t["fields"].get("System.State", "").lower() == "closed",
        }
        for t in items
    }


_DONE_STATES = ("Closed", "Resolved", "Removed")


def get_task_children(
    sess: requests.Session, cfg: dict, story_id: int, active_only: bool = True
) -> list[dict]:
    """Fetch child work items. active_only=True filters by state."""
    base = wit_base(cfg)
    r = sess.get(
        f"{base}/workitems/{story_id}?api-version=7.1&$expand=relations",
        headers={"Content-Type": "application/json"},
    )
    r.raise_for_status()

    item = r.json()
    child_ids = []
    for rel in item.get("relations", []):
        if rel.get("rel") == "System.LinkTypes.Hierarchy-Forward":
            url = rel.get("url", "")
            if "/workItems/" in url:
                try:
                    child_ids.append(int(url.split("/workItems/")[-1]))
                except (ValueError, IndexError):
                    pass

    if not child_ids:
        return []

    all_items = get_workitems(sess, cfg, child_ids)
    if active_only:
        all_items = [
            t
            for t in all_items
            if t.get("fields", {}).get("System.State") not in _DONE_STATES
        ]
    return all_items


def get_my_stories(sess: requests.Session, cfg: dict) -> list[dict]:
    """WIQL query: active work items (Epic/Feature/Story/Bug/Issue) assigned to me."""
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
    wiql = {
        "query": f"""
            SELECT [System.Id],[System.Title],[System.State],
                   [System.AreaPath],[Microsoft.VSTS.Common.Priority],
                   [System.WorkItemType]
            FROM   WorkItems
            WHERE  [System.TeamProject] = '{cfg['project']}'
              AND  [System.WorkItemType] IN ({types})
              AND  {assignee_clause}
              AND  [System.State] NOT IN ('Closed','Removed')
            ORDER BY [Microsoft.VSTS.Common.Priority] ASC,
                     [System.ChangedDate]              DESC
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
    # Batch-fetch details
    r2 = sess.get(
        f"{base}/workitems?ids={','.join(ids)}"
        "&fields=System.Id,System.Title,System.State,System.WorkItemType,"
        "Microsoft.VSTS.Common.Priority,System.AreaPath"
        "&api-version=7.1",
        headers={"Content-Type": "application/json"},
    )
    r2.raise_for_status()
    return r2.json().get("value", [])


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
    if since and "'" in since:
        raise ValueError("Invalid since date: contains forbidden character")
    if until and "'" in until:
        raise ValueError("Invalid until date: contains forbidden character")
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
        date_clauses += f"\n  AND  [Microsoft.VSTS.Common.ClosedDate] >= '{since}'"
    if until:
        date_clauses += f"\n  AND  [Microsoft.VSTS.Common.ClosedDate] <= '{until}'"

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


def create_task(
    sess: requests.Session, cfg: dict, task: dict, parent_ids: list[int]
) -> dict:
    """Create Task work item linked to parent stories."""
    base = wit_base(cfg)
    ops = [
        {"op": "add", "path": "/fields/System.Title", "value": task["title"]},
        {
            "op": "add",
            "path": "/fields/Microsoft.VSTS.Common.Priority",
            "value": int(task.get("priority", 2)),
        },
    ]
    if task.get("description"):
        ops.append(
            {
                "op": "add",
                "path": "/fields/System.Description",
                "value": task["description"],
            }
        )
    if cfg.get("assigned_to"):
        ops.append(
            {
                "op": "add",
                "path": "/fields/System.AssignedTo",
                "value": cfg["assigned_to"],
            }
        )
    if cfg.get("area_path"):
        ops.append(
            {"op": "add", "path": "/fields/System.AreaPath", "value": cfg["area_path"]}
        )
    if task.get("tags"):
        ops.append({"op": "add", "path": "/fields/System.Tags", "value": task["tags"]})
    if task.get("effort"):
        ops.append(
            {
                "op": "add",
                "path": "/fields/Microsoft.VSTS.Scheduling.OriginalEstimate",
                "value": float(task["effort"]),
            }
        )

    # Parent link → first story
    org_url = f"https://dev.azure.com/{cfg['org']}"
    ops.append(
        {
            "op": "add",
            "path": "/relations/-",
            "value": {
                "rel": "System.LinkTypes.Hierarchy-Reverse",
                "url": f"{org_url}/_apis/wit/workitems/{parent_ids[0]}",
                "attributes": {"comment": "Auto-linked by azdo-daily"},
            },
        }
    )
    # Related link → additional stories
    for sid in parent_ids[1:]:
        ops.append(
            {
                "op": "add",
                "path": "/relations/-",
                "value": {
                    "rel": "System.LinkTypes.Related",
                    "url": f"{org_url}/_apis/wit/workitems/{sid}",
                    "attributes": {"comment": "Related story"},
                },
            }
        )

    r = sess.post(
        f"{base}/workitems/$Task?api-version=7.1",
        json=ops,
        headers={"Content-Type": "application/json-patch+json"},
    )
    r.raise_for_status()
    return r.json()


def resolve_task(
    sess: requests.Session,
    cfg: dict,
    task_id: int,
    close_state: str,
    completed_hours: Optional[float],
    comment: Optional[str],
):
    """Mark task resolved with state + hours + optional comment."""
    ops = [{"op": "replace", "path": "/fields/System.State", "value": close_state}]
    if completed_hours is not None:
        ops.append(
            {
                "op": "replace",
                "path": "/fields/Microsoft.VSTS.Scheduling.CompletedWork",
                "value": completed_hours,
            }
        )
    _patch_workitem(sess, cfg, task_id, ops)
    if comment:
        add_comment(sess, cfg, task_id, comment)


def partial_task(
    sess: requests.Session,
    cfg: dict,
    task_id: int,
    completed_hours: Optional[float],
    remaining_hours: Optional[float],
    comment: Optional[str],
):
    """Mark task In Progress with work-log update."""
    # Use 'replace' if field exists, 'add' if new
    ops = [{"op": "add", "path": "/fields/System.State", "value": "Active"}]
    if completed_hours is not None:
        ops.append(
            {
                "op": "add",
                "path": "/fields/Microsoft.VSTS.Scheduling.CompletedWork",
                "value": completed_hours,
            }
        )
    if remaining_hours is not None:
        ops.append(
            {
                "op": "add",
                "path": "/fields/Microsoft.VSTS.Scheduling.RemainingWork",
                "value": remaining_hours,
            }
        )
    _patch_workitem(sess, cfg, task_id, ops)
    if comment:
        add_comment(sess, cfg, task_id, comment)
