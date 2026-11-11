"""Bug commands: list, show, start and resolve Azure DevOps bugs."""

import json
import sys

import requests

from azdo_daily import azdo, config, ui


def _emit(data, as_json: bool, human) -> None:
    """Print data as one JSON document, or call human() for readable output."""
    if as_json:
        print(json.dumps(data, indent=2))
    else:
        human()


def _fail(msg: str) -> None:
    ui.err(msg)
    sys.exit(1)


def _session():
    cfg = config.load_cfg()
    config.require_cfg(cfg, "org", "project", "pat")
    return azdo.session(cfg), cfg


def _guard(fn):
    """Run fn, turning API and state errors into a clean exit 1."""
    try:
        return fn()
    except requests.HTTPError as e:
        _fail(f"Azure DevOps error: {e.response.status_code}")
    except ValueError as e:
        _fail(str(e))


def cmd_bugs(args):
    """List open bugs assigned to me."""
    sess, cfg = _session()
    items = _guard(lambda: azdo.get_my_bugs(sess, cfg))
    rows = [
        {
            "id": b["id"],
            "title": b["fields"].get("System.Title", ""),
            "state": b["fields"].get("System.State", ""),
            "priority": b["fields"].get("Microsoft.VSTS.Common.Priority"),
            "severity": b["fields"].get("Microsoft.VSTS.Common.Severity", ""),
        }
        for b in items
    ]

    def human():
        if not rows:
            ui.warn("No open bugs assigned to you.")
        for r in rows:
            print(f"  [Bug] [{r['state']}] #{r['id']}  {r['title']}")

    _emit(rows, args.json, human)


def cmd_bug_show(args):
    """Show one bug in full."""
    sess, cfg = _session()
    bug = _guard(lambda: azdo.get_bug(sess, cfg, args.id))

    def human():
        print(f"  [Bug] [{bug['state']}] #{bug['id']}  {bug['title']}")
        print(f"  Severity: {bug['severity']}")
        print(f"  Repro steps:\n{bug['repro_steps']}")
        for c in bug["comments"]:
            print(f"  {c['author']}: {c['text']}")
        for url in bug["attachments"]:
            print(f"  Attachment: {url}")

    _emit(bug, args.json, human)


def _move(args, categories, comment=None, task=None):
    sess, cfg = _session()

    def run():
        # Look up both states first so a failure changes nothing.
        task_state = (
            azdo.pick_state(sess, cfg, "Task", azdo.COMPLETED) if task else None
        )
        state = azdo.pick_state(sess, cfg, "Bug", categories)
        if task:
            azdo.set_workitem_state(sess, cfg, task, task_state)
        if comment:
            azdo.add_comment(sess, cfg, args.id, comment)
        azdo.set_workitem_state(sess, cfg, args.id, state)
        return state, task_state

    state, task_state = _guard(run)
    result = {"id": args.id, "state": state}
    if task:
        result.update({"task": task, "task_state": task_state})
    _emit(result, args.json, lambda: ui.ok(f"[Bug] #{args.id} → {state}"))


def cmd_bug_start(args):
    """Move a bug to its in-progress state."""
    _move(args, azdo.IN_PROGRESS)


def cmd_bug_resolve(args):
    """Comment on a bug and move it to its resolved state, closing its task."""
    _move(args, azdo.RESOLVED, args.comment, getattr(args, "task", None))


def cmd_bug_task(args):
    """Create a child Task under a bug."""
    sess, cfg = _session()
    item = _guard(lambda: azdo.create_task(sess, cfg, {"title": args.title}, [args.id]))
    _emit(
        {"id": item["id"], "bug": args.id},
        args.json,
        lambda: ui.ok(f"[Task] #{item['id']} under [Bug] #{args.id}"),
    )
