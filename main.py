#!/usr/bin/env python3
"""
Azure DevOps Daily Task Automation
  start   — create all task templates as work items
  end     — close all tasks created today
  add     — add a task template
  list    — show task templates
  status  — show today's task status
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import requests

CONFIG_FILE = Path(__file__).parent / "config.json"
TASKS_FILE  = Path(__file__).parent / "tasks.json"
STATE_DIR   = Path(__file__).parent / "state"

# ── ANSI colors ──────────────────────────────────────────────────────────────
R  = "\033[0m"
B  = "\033[1m"
DIM= "\033[2m"
GR = "\033[32m"
YL = "\033[33m"
BL = "\033[34m"
CY = "\033[36m"
RD = "\033[31m"
MG = "\033[35m"

def ok(msg):   print(f"  {GR}✔{R}  {msg}")
def err(msg):  print(f"  {RD}✖{R}  {msg}", file=sys.stderr)
def info(msg): print(f"  {BL}→{R}  {msg}")
def warn(msg): print(f"  {YL}!{R}  {msg}")
def hdr(msg):  print(f"\n{B}{msg}{R}")

# ── Config ───────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "org": "",
    "project": "",
    "pat": "",
    "assigned_to": "",
    "area_path": "",
    "close_state": "Done",
}

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
        warn(f"Created default config at {CONFIG_FILE}")
        warn("Fill in your credentials and re-run.")
        sys.exit(1)
    cfg = json.loads(CONFIG_FILE.read_text())
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg

def validate_config(cfg: dict):
    missing = [k for k in ("org", "project", "pat") if not cfg.get(k)]
    if missing:
        err(f"Missing config keys: {', '.join(missing)}")
        info(f"Edit {CONFIG_FILE} and fill in the required values.")
        sys.exit(1)

# ── Task templates ───────────────────────────────────────────────────────────
def load_tasks() -> list:
    if not TASKS_FILE.exists():
        TASKS_FILE.write_text(json.dumps([], indent=2))
    return json.loads(TASKS_FILE.read_text())

def save_tasks(tasks: list):
    TASKS_FILE.write_text(json.dumps(tasks, indent=2))

# ── Daily state (which IDs were created today) ───────────────────────────────
def state_file() -> Path:
    STATE_DIR.mkdir(exist_ok=True)
    return STATE_DIR / f"{date.today().isoformat()}.json"

def load_state() -> list:
    f = state_file()
    return json.loads(f.read_text()) if f.exists() else []

def save_state(items: list):
    state_file().write_text(json.dumps(items, indent=2))

# ── Azure DevOps REST API ─────────────────────────────────────────────────────
def api_session(cfg: dict) -> requests.Session:
    s = requests.Session()
    s.auth = ("", cfg["pat"])
    s.headers["Content-Type"] = "application/json-patch+json"
    return s

def api_base(cfg: dict) -> str:
    org  = requests.utils.quote(cfg["org"],  safe="")
    proj = requests.utils.quote(cfg["project"], safe="")
    return f"https://dev.azure.com/{org}/{proj}"

def create_work_item(session: requests.Session, base: str, task: dict, cfg: dict) -> dict:
    ops = [
        {"op": "add", "path": "/fields/System.Title",
         "value": task["title"]},
        {"op": "add", "path": "/fields/Microsoft.VSTS.Common.Priority",
         "value": int(task.get("priority", 2))},
    ]
    if cfg.get("assigned_to"):
        ops.append({"op": "add", "path": "/fields/System.AssignedTo",
                    "value": cfg["assigned_to"]})
    if cfg.get("area_path"):
        ops.append({"op": "add", "path": "/fields/System.AreaPath",
                    "value": cfg["area_path"]})
    if task.get("tags"):
        ops.append({"op": "add", "path": "/fields/System.Tags",
                    "value": task["tags"]})

    url = f"{base}/_apis/wit/workitems/$Task?api-version=7.1"
    r = session.post(url, json=ops)
    r.raise_for_status()
    return r.json()

def close_work_item(session: requests.Session, base: str, item_id: int, close_state: str) -> dict:
    ops = [{"op": "add", "path": "/fields/System.State", "value": close_state}]
    url = f"{base}/_apis/wit/workitems/{item_id}?api-version=7.1"
    r = session.patch(url, json=ops)
    r.raise_for_status()
    return r.json()

# ── Commands ──────────────────────────────────────────────────────────────────
def cmd_start(args):
    cfg = load_config()
    validate_config(cfg)
    tasks = load_tasks()

    if not tasks:
        warn("No task templates defined. Use:  python main.py add  to create some.")
        return

    existing = [t for t in load_state() if not t.get("closed")]
    if existing:
        warn(f"{len(existing)} task(s) already open from today's run. Use 'end' to close them first.")
        return

    hdr(f"Starting day — {date.today().isoformat()}")
    session = api_session(cfg)
    base    = api_base(cfg)
    created = load_state()

    for task in tasks:
        try:
            item = create_work_item(session, base, task, cfg)
            entry = {
                "id":     item["id"],
                "title":  task["title"],
                "url":    item.get("_links", {}).get("html", {}).get("href", ""),
                "closed": False,
            }
            created.append(entry)
            save_state(created)
            ok(f"#{item['id']}  {task['title']}")
        except requests.HTTPError as e:
            err(f"{task['title']} — {e.response.status_code}: {e.response.text[:120]}")
        except Exception as e:
            err(f"{task['title']} — {e}")

    print()
    info(f"Created {len([c for c in created if not c['closed']])} task(s) in "
         f"{cfg['org']}/{cfg['project']}")


def cmd_end(args):
    cfg = load_config()
    validate_config(cfg)
    state = load_state()
    open_items = [t for t in state if not t.get("closed")]

    if not open_items:
        warn("No open tasks to close today.")
        return

    hdr(f"Ending day — {date.today().isoformat()}")
    session     = api_session(cfg)
    base        = api_base(cfg)
    close_state = cfg.get("close_state", "Done")

    for item in open_items:
        try:
            close_work_item(session, base, item["id"], close_state)
            item["closed"] = True
            save_state(state)
            ok(f"#{item['id']}  {item['title']}  →  {close_state}")
        except requests.HTTPError as e:
            err(f"#{item['id']} {item['title']} — {e.response.status_code}: {e.response.text[:120]}")
        except Exception as e:
            err(f"#{item['id']} {item['title']} — {e}")

    print()
    closed = len([t for t in state if t.get("closed")])
    info(f"Closed {closed}/{len(state)} task(s)")


def cmd_status(args):
    state = load_state()
    cfg   = load_config()
    hdr(f"Status — {date.today().isoformat()}")

    if not state:
        info("No tasks created today yet. Run:  python main.py start")
        return

    org  = cfg.get("org", "")
    proj = cfg.get("project", "")
    for t in state:
        icon  = f"{GR}●{R}" if t.get("closed") else f"{BL}●{R}"
        state_label = f"{DIM}done{R}" if t.get("closed") else f"{CY}open{R}"
        link  = f"  {DIM}{t['url']}{R}" if t.get("url") else ""
        print(f"  {icon}  #{t['id']}  {t['title']}  [{state_label}]{link}")

    open_c   = len([t for t in state if not t.get("closed")])
    closed_c = len([t for t in state if t.get("closed")])
    print(f"\n  {DIM}{closed_c} closed  /  {open_c} open  /  {len(state)} total{R}\n")


def cmd_list(args):
    tasks = load_tasks()
    hdr("Task templates")
    if not tasks:
        info("No templates yet. Add one with:  python main.py add")
        return
    priority_name = {1: "Critical", 2: "High", 3: "Medium", 4: "Low"}
    for i, t in enumerate(tasks, 1):
        p    = int(t.get("priority", 2))
        tags = f"  {DIM}[{t['tags']}]{R}" if t.get("tags") else ""
        prio = f"{YL}P{p}{R} {DIM}{priority_name.get(p,'')}{R}"
        print(f"  {DIM}{i:>2}.{R}  {t['title']}  {prio}{tags}")
    print()


def cmd_add(args):
    title    = args.title or input("  Task title: ").strip()
    if not title:
        err("Title cannot be empty."); return
    priority = args.priority
    if not priority:
        raw = input("  Priority [1=Critical 2=High 3=Medium 4=Low] (default 2): ").strip()
        priority = int(raw) if raw.isdigit() and 1 <= int(raw) <= 4 else 2
    tags = args.tags or input("  Tags (semicolon-separated, or leave blank): ").strip()

    tasks = load_tasks()
    tasks.append({"title": title, "priority": int(priority), "tags": tags})
    save_tasks(tasks)
    ok(f"Added: {title}  (P{priority})")


def cmd_remove(args):
    tasks = load_tasks()
    cmd_list(None)
    raw = input("  Remove task number: ").strip()
    if not raw.isdigit() or not (1 <= int(raw) <= len(tasks)):
        err("Invalid number."); return
    removed = tasks.pop(int(raw) - 1)
    save_tasks(tasks)
    ok(f"Removed: {removed['title']}")


def cmd_configure(args):
    cfg = load_config()
    hdr("Configure Azure DevOps credentials")
    fields = [
        ("org",          "Organization name",        cfg.get("org","")),
        ("project",      "Project name",             cfg.get("project","")),
        ("pat",          "Personal Access Token",     ""),
        ("assigned_to",  "Assign to (email/name)",   cfg.get("assigned_to","")),
        ("area_path",    "Area path (optional)",     cfg.get("area_path","")),
        ("close_state",  "Close state (Done/Closed/Resolved)", cfg.get("close_state","Done")),
    ]
    for key, label, default in fields:
        hint = f" [{default}]" if default and key != "pat" else ""
        val  = input(f"  {label}{hint}: ").strip()
        if val:
            cfg[key] = val
        elif default and key != "pat":
            cfg[key] = default
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    ok(f"Saved to {CONFIG_FILE}")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        prog="azdo-daily",
        description="Azure DevOps daily task automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python main.py configure        set up credentials interactively
  python main.py add              add a recurring task template
  python main.py list             show all task templates
  python main.py start            create today's tasks in Azure DevOps
  python main.py status           show today's task status
  python main.py end              close all of today's open tasks
        """,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("start",     help="Create today's tasks in Azure DevOps")
    sub.add_parser("end",       help="Close all open tasks created today")
    sub.add_parser("status",    help="Show today's task status")
    sub.add_parser("list",      help="List task templates")
    sub.add_parser("configure", help="Set credentials interactively")

    p_add = sub.add_parser("add", help="Add a task template")
    p_add.add_argument("title",    nargs="?", help="Task title")
    p_add.add_argument("--priority", type=int, choices=[1,2,3,4], help="1=Critical 2=High 3=Medium 4=Low")
    p_add.add_argument("--tags",   default="", help="Semicolon-separated tags")

    sub.add_parser("remove", help="Remove a task template")

    args = parser.parse_args()
    dispatch = {
        "start":     cmd_start,
        "end":       cmd_end,
        "status":    cmd_status,
        "list":      cmd_list,
        "add":       cmd_add,
        "remove":    cmd_remove,
        "configure": cmd_configure,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
