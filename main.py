#!/usr/bin/env python3
"""
Azure DevOps Daily Task Automation
────────────────────────────────────
  configure  — set credentials interactively
  start      — fetch your stories → select active → generate & create tasks
  end        — select tasks to resolve, log completion time
  status     — show today's active stories & tasks
"""

import argparse
import json
import re
import sys
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Optional

import requests

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
STATE_DIR   = BASE_DIR / "state"

# ─── Azure DevOps Work Item States ─────────────────────────────────────────────
class TaskState(Enum):
    """Standard Task states in Azure DevOps."""
    NEW = "New"
    ACTIVE = "Active"
    CLOSED = "Closed"

class StoryState(Enum):
    """Standard User Story states in Azure DevOps."""
    NEW = "New"
    ACTIVE = "Active"
    RESOLVED = "Resolved"
    CLOSED = "Closed"

# Descriptions for configure UI
TASK_STATE_DESCS = {
    TaskState.NEW: "Not started",
    TaskState.ACTIVE: "In progress",
    TaskState.CLOSED: "Cancelled",
}

STORY_STATE_DESCS = {
    StoryState.NEW: "Not started",
    StoryState.ACTIVE: "In progress",
    StoryState.RESOLVED: "Completed",
    StoryState.CLOSED: "Finished",
}

# ─── Terminal colours ─────────────────────────────────────────────────────────
R   = "\033[0m"
B   = "\033[1m"
DIM = "\033[2m"
GR  = "\033[32m"
YL  = "\033[33m"
BL  = "\033[34m"
CY  = "\033[36m"
RD  = "\033[31m"
MG  = "\033[35m"

def ok(msg):    print(f"  {GR}✔{R}  {msg}")
def err(msg):   print(f"  {RD}✖{R}  {msg}", file=sys.stderr)
def info(msg):  print(f"  {BL}→{R}  {msg}")
def warn(msg):  print(f"  {YL}!{R}  {msg}")
def hdr(msg):   print(f"\n{B}{CY}{msg}{R}")
def sep():      print(f"  {DIM}{'─'*58}{R}")
def ask(prompt, default=None):
    hint = f" [{default}]" if default is not None else ""
    val  = input(f"  {MG}?{R}  {prompt}{hint}: ").strip()
    return val if val else (str(default) if default is not None else "")

# ─── Config ───────────────────────────────────────────────────────────────────
DEFAULT_CFG = {
    "org": "", "project": "", "pat": "",
    "anthropic_api_key": "",
    "assigned_to": "",          # your email / display name for filtering stories
    "area_path": "",
    "close_state": TaskState.CLOSED.value,  # Task completion state
}

def load_cfg() -> dict:
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CFG, indent=2))
    cfg = {**DEFAULT_CFG, **json.loads(CONFIG_FILE.read_text())}
    return cfg

def save_cfg(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

def require_cfg(cfg, *keys):
    missing = [k for k in keys if not cfg.get(k)]
    if missing:
        err(f"Missing config: {', '.join(missing)}")
        info("Run:  python main.py configure")
        sys.exit(1)

# ─── Daily state ──────────────────────────────────────────────────────────────
def today_file() -> Path:
    STATE_DIR.mkdir(exist_ok=True)
    return STATE_DIR / f"{date.today().isoformat()}.json"

DEFAULT_STATE = {"stories": [], "tasks": []}

def load_state() -> dict:
    f = today_file()
    if f.exists():
        data = json.loads(f.read_text())
        if isinstance(data, list):
            return {**DEFAULT_STATE, "tasks": data}
        return {**DEFAULT_STATE, **data}
    return dict(DEFAULT_STATE)

def save_state(st: dict):
    today_file().write_text(json.dumps(st, indent=2))

# ─── Azure DevOps helpers ─────────────────────────────────────────────────────
def session(cfg) -> requests.Session:
    s = requests.Session()
    s.auth = ("", cfg["pat"])
    return s

def wit_base(cfg) -> str:
    o = requests.utils.quote(cfg["org"],     safe="")
    p = requests.utils.quote(cfg["project"], safe="")
    return f"https://dev.azure.com/{o}/{p}/_apis/wit"

def get_my_stories(sess, cfg) -> list[dict]:
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
    r = sess.post(
        f"{wit_base(cfg)}/wiql?api-version=7.1",
        json=wiql,
        headers={"Content-Type": "application/json"},
    )
    r.raise_for_status()
    ids = [str(w["id"]) for w in r.json().get("workItems", [])]
    if not ids:
        return []
    # Batch-fetch details
    r2 = sess.get(
        f"{wit_base(cfg)}/workitems?ids={','.join(ids)}"
        "&fields=System.Id,System.Title,System.State,"
        "Microsoft.VSTS.Common.Priority,System.AreaPath"
        "&api-version=7.1",
        headers={"Content-Type": "application/json"},
    )
    r2.raise_for_status()
    return r2.json().get("value", [])

def create_task(sess, cfg, task: dict, parent_ids: list[int]) -> dict:
    """Create a Task work item linked (child) to parent_ids[0], related to rest."""
    base = wit_base(cfg)
    ops  = [
        {"op": "add", "path": "/fields/System.Title",
         "value": task["title"]},
        {"op": "add", "path": "/fields/Microsoft.VSTS.Common.Priority",
         "value": int(task.get("priority", 2))},
    ]
    if task.get("description"):
        ops.append({"op": "add", "path": "/fields/System.Description",
                    "value": task["description"]})
    if cfg.get("assigned_to"):
        ops.append({"op": "add", "path": "/fields/System.AssignedTo",
                    "value": cfg["assigned_to"]})
    if cfg.get("area_path"):
        ops.append({"op": "add", "path": "/fields/System.AreaPath",
                    "value": cfg["area_path"]})
    if task.get("tags"):
        ops.append({"op": "add", "path": "/fields/System.Tags",
                    "value": task["tags"]})
    if task.get("effort"):
        ops.append({"op": "add",
                    "path": "/fields/Microsoft.VSTS.Scheduling.OriginalEstimate",
                    "value": float(task["effort"])})

    # Parent link → first story
    org_url = f"https://dev.azure.com/{cfg['org']}"
    ops.append({
        "op": "add", "path": "/relations/-",
        "value": {
            "rel": "System.LinkTypes.Hierarchy-Reverse",
            "url": f"{org_url}/_apis/wit/workitems/{parent_ids[0]}",
            "attributes": {"comment": "Auto-linked by azdo-daily"},
        },
    })
    # Related link → additional stories
    for sid in parent_ids[1:]:
        ops.append({
            "op": "add", "path": "/relations/-",
            "value": {
                "rel": "System.LinkTypes.Related",
                "url": f"{org_url}/_apis/wit/workitems/{sid}",
                "attributes": {"comment": "Related story"},
            },
        })

    r = sess.post(
        f"{base}/workitems/$Task?api-version=7.1",
        json=ops,
        headers={"Content-Type": "application/json-patch+json"},
    )
    r.raise_for_status()
    return r.json()

def set_task_state(sess, cfg, task_id: int, state: str):
    """Set task state only."""
    if not state:
        raise ValueError("State cannot be empty")
    base = wit_base(cfg)
    ops  = [{"op": "replace", "path": "/fields/System.State", "value": state}]
    r = sess.patch(
        f"{base}/workitems/{task_id}?api-version=7.1",
        json=ops,
        headers={"Content-Type": "application/json-patch+json"},
    )
    r.raise_for_status()

def resolve_task(sess, cfg, task_id: int, close_state: str,
                 completed_hours: Optional[float], comment: Optional[str]):
    """Set task state + log completed work + optional comment."""
    base = wit_base(cfg)
    ops  = [{"op": "replace", "path": "/fields/System.State", "value": close_state}]
    if completed_hours is not None:
        ops.append({"op": "replace",
                    "path": "/fields/Microsoft.VSTS.Scheduling.CompletedWork",
                    "value": completed_hours})
    r = sess.patch(
        f"{base}/workitems/{task_id}?api-version=7.1",
        json=ops,
        headers={"Content-Type": "application/json-patch+json"},
    )
    r.raise_for_status()
    if comment:
        sess.post(
            f"{base}/workitems/{task_id}/comments?api-version=7.1-preview.3",
            json={"text": comment},
            headers={"Content-Type": "application/json"},
        )

def partial_task(sess, cfg, task_id: int,
                 completed_hours: Optional[float], remaining_hours: Optional[float],
                 comment: Optional[str]):
    """Mark task as In Progress with work-log update."""
    base = wit_base(cfg)
    ops  = [{"op": "add", "path": "/fields/System.State", "value": TaskState.ACTIVE.value}]
    if completed_hours is not None:
        ops.append({"op": "add",
                    "path": "/fields/Microsoft.VSTS.Scheduling.CompletedWork",
                    "value": completed_hours})
    if remaining_hours is not None:
        ops.append({"op": "add",
                    "path": "/fields/Microsoft.VSTS.Scheduling.RemainingWork",
                    "value": remaining_hours})
    r = sess.patch(
        f"{base}/workitems/{task_id}?api-version=7.1",
        json=ops,
        headers={"Content-Type": "application/json-patch+json"},
    )
    r.raise_for_status()
    if comment:
        sess.post(
            f"{base}/workitems/{task_id}/comments?api-version=7.1-preview.3",
            json={"text": comment},
            headers={"Content-Type": "application/json"},
        )

# ─── AI task breakdown ────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a senior agile software engineer.
Given a user story, decompose it into concrete development tasks.

Return ONLY a valid JSON array — no markdown, no explanation.
Each element:
  "title"       — short imperative phrase (e.g. "Add login endpoint")
  "description" — 1-2 sentences on what to implement or verify
  "priority"    — 1=Critical  2=High  3=Medium  4=Low
  "effort"      — estimated hours (number)
  "tags"        — semicolon-separated (e.g. "backend;api")

Cover: backend, frontend, DB, tests, docs, DevOps as appropriate.
Aim for 4–8 focused tasks."""

def ai_breakdown(story_text: str, api_key: str) -> list[dict]:
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
        json={
            "model":      "claude-sonnet-4-20250514",
            "max_tokens": 2048,
            "system":     SYSTEM_PROMPT,
            "messages":   [{"role": "user",
                            "content": f"User story:\n\n{story_text}"}],
        },
        timeout=60,
    )
    r.raise_for_status()
    raw = r.json()["content"][0]["text"].strip()
    raw = re.sub(r"^```(?:json)?", "", raw).rstrip("`").strip()
    return json.loads(raw)

# ─── Selection helpers ────────────────────────────────────────────────────────
def parse_selection(raw: str, max_n: int) -> list[int]:
    """Parse '1,3,5' or '1-3' or '2' into 0-based indices."""
    indices = set()
    for part in raw.split(","):
        part = part.strip()
        m = re.match(r"^(\d+)-(\d+)$", part)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            indices.update(range(lo - 1, hi))
        elif part.isdigit():
            indices.add(int(part) - 1)
    return sorted(i for i in indices if 0 <= i < max_n)

def print_stories(stories: list[dict]):
    sep()
    prio_col = {1: RD, 2: YL, 3: CY, 4: DIM}
    for i, s in enumerate(stories, 1):
        fields = s.get("fields", {})
        title  = fields.get("System.Title", "(no title)")
        state  = fields.get("System.State",  "?")
        prio   = int(fields.get("Microsoft.VSTS.Common.Priority", 2))
        pc     = prio_col.get(prio, "")
        print(f"  {B}{i:>2}.{R}  {title}  "
              f"{pc}[P{prio}]{R}  {DIM}{state}{R}")
    sep()

def print_tasks(tasks: list[dict], show_index=True):
    sep()
    for i, t in enumerate(tasks, 1):
        prio_label = {1:"Critical",2:"High",3:"Medium",4:"Low"}
        pfx = f"{B}{i:>2}.{R}  " if show_index else "      "
        print(f"  {pfx}{t['title']}")
        if t.get("description"):
            print(f"       {DIM}{t['description'][:80]}{R}")
        detail = []
        if t.get("effort"):
            detail.append(f"{t['effort']}h")
        if t.get("priority"):
            detail.append(f"P{t['priority']} {prio_label.get(int(t['priority']),'')}")
        if t.get("tags"):
            detail.append(t["tags"])
        if detail:
            print(f"       {DIM}{' · '.join(detail)}{R}")
    sep()

# ─── Command: configure ───────────────────────────────────────────────────────
def cmd_configure(args):
    cfg = load_cfg()
    hdr("Configure credentials")
    fields = [
        ("org",               "Azure DevOps org name"),
        ("project",           "Project name"),
        ("pat",               "Personal Access Token (PAT)"),
        ("anthropic_api_key", "Anthropic API key (for AI breakdown)"),
        ("assigned_to",       "Your email / display name (for story filter)"),
        ("area_path",         "Default area path (optional)"),
    ]
    for key, label in fields:
        current = cfg.get(key, "")
        show    = "****" if (current and key in ("pat","anthropic_api_key")) else current
        val     = ask(label, show if show else None)
        if val and val != "****":
            cfg[key] = val

    print()
    hdr("Select task completion state")
    print(f"  {B}Valid states:{R}")
    state_list = list(TaskState)
    for i, state in enumerate(state_list, 1):
        desc = TASK_STATE_DESCS.get(state, "")
        print(f"    {i}. {state.value:15} — {desc}")
    state_num = ask("Select state number", "3")
    if state_num.isdigit():
        idx = int(state_num) - 1
        if 0 <= idx < len(state_list):
            cfg["close_state"] = state_list[idx].value

    save_cfg(cfg)
    ok(f"Saved to {CONFIG_FILE}")

# ─── Command: create ──────────────────────────────────────────────────────────
def cmd_create(args):
    cfg = load_cfg()
    require_cfg(cfg, "org", "project", "pat")
    sess = session(cfg)

    # ── 1. Fetch user stories ─────────────────────────────────────────────────
    hdr("Fetching your user stories…")
    try:
        stories = get_my_stories(sess, cfg)
    except requests.HTTPError as e:
        err(f"Azure DevOps error: {e.response.status_code} {e.response.text[:200]}")
        sys.exit(1)

    if not stories:
        warn("No active user stories found assigned to you.")
        sys.exit(0)

    info(f"Found {len(stories)} user story/stories:")
    print_stories(stories)

    # ── 2. Select active stories ──────────────────────────────────────────────
    raw = ask("Select stories to work on today (e.g. 1  or  1,3  or  1-3)")
    indices = parse_selection(raw, len(stories))
    if not indices:
        err("No valid selection."); sys.exit(1)

    selected = [stories[i] for i in indices]
    selected_ids = [s["id"] for s in selected]

    hdr("Selected stories:")
    for s in selected:
        ok(f"#{s['id']}  {s['fields']['System.Title']}")

    # Save selected stories to state
    st = load_state()
    st["stories"] = [
        {"id": s["id"], "title": s["fields"]["System.Title"]}
        for s in selected
    ]

    # ── 3. Build task list ────────────────────────────────────────────────────
    hdr("Define tasks")
    if len(selected) == 1:
        story_title = selected[0]["fields"]["System.Title"]
        info(f"Story: {story_title}")
    else:
        info("Tasks will be created once and linked to all selected stories.")

    print()
    print(f"  How do you want to create tasks?")
    print(f"  {B}1.{R}  AI auto-breakdown from story description")
    print(f"  {B}2.{R}  Enter tasks manually")
    print(f"  {B}3.{R}  Both (AI suggestions → review → add/remove)")
    mode = ask("Choose", "1")

    proposed_tasks = []

    if mode in ("1", "3"):
        if not cfg.get("anthropic_api_key"):
            err("anthropic_api_key not set. Run:  python main.py configure")
            if mode == "1":
                sys.exit(1)
            warn("Falling back to manual entry.")
            mode = "2"
        else:
            # Compose story text for AI
            story_parts = []
            for s in selected:
                f = s.get("fields", {})
                story_parts.append(
                    f"Story #{s['id']}: {f.get('System.Title','')}\n"
                    f"{f.get('System.Description','(no description)')}"
                )
            story_text = "\n\n---\n\n".join(story_parts)
            info("Calling AI breakdown…")
            try:
                proposed_tasks = ai_breakdown(story_text, cfg["anthropic_api_key"])
                hdr(f"AI suggested {len(proposed_tasks)} task(s):")
                print_tasks(proposed_tasks)
            except Exception as e:
                err(f"AI error: {e}")
                if mode == "1":
                    sys.exit(1)
                proposed_tasks = []

    if mode in ("2", "3"):
        hdr("Manual task entry  (blank title to stop)")
        prio_map = {"1":1,"2":2,"3":3,"4":4}
        while True:
            title = ask("Task title")
            if not title:
                break
            prio  = ask("Priority (1=Critical 2=High 3=Medium 4=Low)", "2")
            desc  = ask("Short description (optional)")
            effort= ask("Estimated hours (optional)")
            tags  = ask("Tags semicolon-separated (optional)")
            proposed_tasks.append({
                "title":       title,
                "description": desc,
                "priority":    int(prio_map.get(prio, "2")),
                "effort":      float(effort) if effort else None,
                "tags":        tags,
            })
            ok(f"Added: {title}")

    if not proposed_tasks:
        warn("No tasks defined. Exiting."); sys.exit(0)

    # ── 4. Review & confirm ───────────────────────────────────────────────────
    if mode in ("1", "3"):
        hdr("Review tasks before creating")
        print_tasks(proposed_tasks)
        action = ask("(c)onfirm all / (e)dit list / (q)uit", "c").lower()
        if action.startswith("q"):
            sys.exit(0)
        if action.startswith("e"):
            while True:
                print(f"\n  {B}Options:{R}  (r)emove #n  (a)dd  (d)one")
                cmd_in = ask("Action").lower()
                if cmd_in.startswith("d"):
                    break
                elif cmd_in.startswith("r"):
                    num = ask("Remove task number")
                    if num.isdigit():
                        idx = int(num) - 1
                        if 0 <= idx < len(proposed_tasks):
                            removed = proposed_tasks.pop(idx)
                            warn(f"Removed: {removed['title']}")
                            print_tasks(proposed_tasks)
                elif cmd_in.startswith("a"):
                    title  = ask("Task title")
                    prio   = ask("Priority (1-4)", "2")
                    desc   = ask("Description (optional)")
                    effort = ask("Estimated hours (optional)")
                    tags   = ask("Tags (optional)")
                    proposed_tasks.append({
                        "title": title, "description": desc,
                        "priority": int(prio) if prio.isdigit() else 2,
                        "effort": float(effort) if effort else None,
                        "tags": tags,
                    })
                    ok(f"Added: {title}")

    # ── 5. Create tasks in Azure DevOps ───────────────────────────────────────
    hdr(f"Creating {len(proposed_tasks)} task(s) in Azure DevOps…")
    created = []
    for task in proposed_tasks:
        try:
            item = create_task(sess, cfg, task, selected_ids)
            entry = {
                "id":     item["id"],
                "title":  task["title"],
                "url":    item.get("_links", {}).get("html", {}).get("href", ""),
                "closed": False,
                "story_ids": selected_ids,
            }
            created.append(entry)
            linked = " + ".join(f"#{sid}" for sid in selected_ids)
            ok(f"#{item['id']}  {task['title']}  {DIM}→ linked to {linked}{R}")
        except requests.HTTPError as e:
            err(f"{task['title']} — {e.response.status_code}: {e.response.text[:120]}")
        except Exception as e:
            err(f"{task['title']} — {e}")

    st["tasks"] = st.get("tasks", []) + created
    save_state(st)
    print()
    info(f"Done. {len(created)} task(s) created and linked.")

# ─── Command: start ───────────────────────────────────────────────────────────
def cmd_start(args):
    cfg = load_cfg()
    require_cfg(cfg, "org", "project", "pat")
    sess = session(cfg)
    st   = load_state()

    tasks = st.get("tasks", [])
    new_tasks = [t for t in tasks if not t.get("active") and not t.get("closed")]
    if not new_tasks:
        warn("No new tasks to activate."); return

    hdr("New tasks — select to activate")
    print_tasks(new_tasks)

    raw = ask("Select tasks to start (e.g. 1  or  1,3  or  1-3  or  all)", "all")
    if raw.strip().lower() == "all":
        indices = list(range(len(new_tasks)))
    else:
        indices = parse_selection(raw, len(new_tasks))

    if not indices:
        err("No valid selection."); return

    selected_tasks = [new_tasks[idx] for idx in indices]
    story_ids = set()
    for task in selected_tasks:
        for sid in task.get("story_ids", []):
            story_ids.add(sid)

    if story_ids:
        hdr("Auto-activating stories (if in New state)…")
        for story_id in story_ids:
            try:
                set_task_state(sess, cfg, story_id, StoryState.ACTIVE.value)
                ok(f"Story #{story_id} activated")
            except requests.HTTPError:
                pass

    hdr("Activating tasks...")
    for idx in indices:
        task = new_tasks[idx]
        try:
            set_task_state(sess, cfg, task["id"], TaskState.ACTIVE.value)
            task["active"] = True
            save_state(st)
            ok(f"#{task['id']}  activated")
        except requests.HTTPError as e:
            err(f"#{task['id']} — {e.response.status_code}: {e.response.text[:120]}")

    print()
    info("Tasks activated.")

# ─── Command: update ──────────────────────────────────────────────────────────
def cmd_update(args):
    cfg = load_cfg()
    require_cfg(cfg, "org", "project", "pat")
    sess = session(cfg)
    st   = load_state()

    open_tasks = [t for t in st.get("tasks", []) if not t.get("closed")]
    if not open_tasks:
        warn("No open tasks for today."); return

    hdr("Open tasks — select to log progress")
    print_tasks(open_tasks)

    raw = ask("Select tasks to update (e.g. 1  or  1,3  or  1-3  or  all)", "all")
    if raw.strip().lower() == "all":
        indices = list(range(len(open_tasks)))
    else:
        indices = parse_selection(raw, len(open_tasks))

    if not indices:
        err("No valid selection."); return

    hdr("Log progress for each task (keep open)")
    for idx in indices:
        task = open_tasks[idx]
        print(f"\n  {B}#{task['id']}{R}  {task['title']}")
        sep()

        hours_raw = ask("Hours spent today (optional)")
        completed_hours = float(hours_raw) if hours_raw else None

        remaining_raw = ask("Remaining hours estimate (optional)")
        remaining_hours = float(remaining_raw) if remaining_raw else None

        comment = None
        note = ask("Progress note (optional, will be added as comment)")
        if note:
            comment = note

        try:
            partial_task(sess, cfg, task["id"],
                         completed_hours, remaining_hours, comment)
            task["remaining_hours"] = remaining_hours
            task["completed_hours"] = completed_hours
            save_state(st)
            ok(f"Updated (In Progress) — {remaining_hours or '?'}h remaining")
        except requests.HTTPError as e:
            err(f"#{task['id']} — {e.response.status_code}: {e.response.text[:120]}")

    print()
    info("Tasks kept open with progress logged.")

# ─── Command: end ─────────────────────────────────────────────────────────────
def cmd_end(args):
    cfg = load_cfg()
    require_cfg(cfg, "org", "project", "pat")
    sess = session(cfg)
    st   = load_state()

    open_tasks = [t for t in st.get("tasks", []) if not t.get("closed")]
    if not open_tasks:
        warn("No open tasks for today."); return

    hdr("Open tasks — select to mark as done")
    print_tasks(open_tasks)

    raw = ask("Select tasks to complete (e.g. 1  or  1,3  or  1-3  or  all)", "all")
    if raw.strip().lower() == "all":
        indices = list(range(len(open_tasks)))
    else:
        indices = parse_selection(raw, len(open_tasks))

    if not indices:
        err("No valid selection."); return

    close_state = cfg.get("close_state", TaskState.CLOSED.value)
    # Validate state is supported
    valid_states = [s.value for s in TaskState]
    if close_state not in valid_states:
        warn(f"State '{close_state}' not valid. Using '{TaskState.CLOSED.value}' instead.")
        close_state = TaskState.CLOSED.value
    closed_story_ids = set()

    hdr(f"Mark tasks as '{close_state}'")
    for idx in indices:
        task = open_tasks[idx]
        print(f"\n  {B}#{task['id']}{R}  {task['title']}")
        sep()

        hours_raw = ask("Hours spent today (optional)")
        completed_hours = float(hours_raw) if hours_raw else None

        note = ask("Any closing note? (optional)")
        comment = note if note else None

        try:
            resolve_task(sess, cfg, task["id"], close_state, completed_hours, comment)
            task["closed"] = True
            task["completed_hours"] = completed_hours

            story_ids = task.get("story_ids", [])
            for sid in story_ids:
                all_story_tasks = [t for t in st.get("tasks", [])
                                  if sid in t.get("story_ids", [])]
                if all(t.get("closed") for t in all_story_tasks):
                    closed_story_ids.add(sid)

            save_state(st)
            ok(f"Marked as '{close_state}'")
        except requests.HTTPError as e:
            err(f"#{task['id']} — {e.response.status_code}")
            err(f"  {e.response.text}")

    if closed_story_ids:
        hdr("Auto-resolving completed stories…")
        for story_id in closed_story_ids:
            try:
                set_task_state(sess, cfg, story_id, close_state)
                ok(f"Story #{story_id} marked as '{close_state}'")
            except requests.HTTPError as e:
                err(f"Story #{story_id} — {e.response.status_code}: {e.response.text[:120]}")

    all_tasks = st.get("tasks", [])
    closed_c  = sum(1 for t in all_tasks if t.get("closed"))
    open_c    = sum(1 for t in all_tasks if not t.get("closed"))
    print()
    info(f"Today: {closed_c} resolved  /  {open_c} still open")

# ─── Command: status ──────────────────────────────────────────────────────────
def cmd_status(args):
    st = load_state()
    hdr(f"Status — {date.today().isoformat()}")

    stories = st.get("stories", [])
    if stories:
        info("Active stories:")
        for s in stories:
            print(f"    {CY}#{s['id']}{R}  {s['title']}")
        print()

    tasks = st.get("tasks", [])
    if not tasks:
        info("No tasks created yet. Run:  python main.py create"); return

    open_t   = [t for t in tasks if not t.get("closed")]
    closed_t = [t for t in tasks if t.get("closed")]

    if open_t:
        info(f"Open ({len(open_t)}):")
        for t in open_t:
            rem = f"  {DIM}{t['remaining_hours']}h remaining{R}" if t.get("remaining_hours") else ""
            print(f"    {BL}●{R}  #{t['id']}  {t['title']}{rem}")

    if closed_t:
        info(f"Resolved ({len(closed_t)}):")
        for t in closed_t:
            hrs = f"  {DIM}{t['completed_hours']}h logged{R}" if t.get("completed_hours") else ""
            print(f"    {GR}●{R}  #{t['id']}  {t['title']}{hrs}")

    print()
    total = len(tasks)
    print(f"  {DIM}{len(closed_t)}/{total} tasks resolved today{R}\n")

# ─── Entry point ──────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        prog="azdo-daily",
        description="Azure DevOps daily task automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
workflow:
  python main.py configure   → set credentials once
  python main.py create      → pick stories, generate tasks, create in Azure DevOps
  python main.py start       → activate tasks (mark as In Progress)
  python main.py update      → log progress hours on tasks (keep open)
  python main.py end         → mark tasks as done (auto-resolves story if all tasks done)
  python main.py status      → see today's open/resolved tasks
        """,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("configure", help="Set credentials interactively")
    sub.add_parser("create",    help="Pick stories → generate tasks → create in Azure DevOps")
    sub.add_parser("start",     help="Activate tasks (mark as In Progress)")
    sub.add_parser("update",    help="Log progress on tasks (keep open)")
    sub.add_parser("end",       help="Mark tasks as done (auto-resolves story if all done)")
    sub.add_parser("status",    help="Show today's stories and tasks")

    args = ap.parse_args()
    {"configure": cmd_configure,
     "create":    cmd_create,
     "start":     cmd_start,
     "update":    cmd_update,
     "end":       cmd_end,
     "status":    cmd_status}[args.cmd](args)

if __name__ == "__main__":
    main()
