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
    sess.post(
        f"{base}/workitems/{item_id}/comments?api-version=7.1-preview.3",
        json={"text": text},
        headers={"Content-Type": "application/json"},
    )


def set_workitem_state(sess: requests.Session, cfg: dict, item_id: int, state: str):
    """Set work item state."""
    if not state:
        raise ValueError("State cannot be empty")
    ops = [{"op": "replace", "path": "/fields/System.State", "value": state}]
    _patch_workitem(sess, cfg, item_id, ops)


def get_my_stories(sess: requests.Session, cfg: dict) -> list[dict]:
    """WIQL query: active User Stories assigned to me."""
    assignee = cfg.get("assigned_to") or "@Me"
    if "@" not in assignee and assignee != "@Me":
        assignee_clause = f"[System.AssignedTo] contains '{assignee}'"
    else:
        assignee_clause = (
            "[System.AssignedTo] = @Me"
            if assignee == "@Me"
            else f"[System.AssignedTo] = '{assignee}'"
        )

    wiql = {
        "query": f"""
            SELECT [System.Id],[System.Title],[System.State],
                   [System.AreaPath],[Microsoft.VSTS.Common.Priority]
            FROM   WorkItems
            WHERE  [System.WorkItemType] IN ('User Story','Story')
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
        "&fields=System.Id,System.Title,System.State,"
        "Microsoft.VSTS.Common.Priority,System.AreaPath"
        "&api-version=7.1",
        headers={"Content-Type": "application/json"},
    )
    r2.raise_for_status()
    return r2.json().get("value", [])


def create_task(sess: requests.Session, cfg: dict, task: dict, parent_ids: list[int]) -> dict:
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
        ops.append(
            {"op": "add", "path": "/fields/System.Tags", "value": task["tags"]}
        )
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
    from ui import warn

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
