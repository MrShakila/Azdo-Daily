#!/usr/bin/env python3
"""
Azure DevOps Daily Task Automation
────────────────────────────────────
  configure  — set credentials interactively
  create     — pick stories → generate tasks → create in Azure DevOps
  start      — activate tasks (mark as In Progress)
  update     — log progress on tasks (keep open)
  end        — mark tasks as done (auto-resolves story if all done)
  status     — show today's active stories & tasks
"""

import argparse
from datetime import datetime

from azdo_daily.bugs import cmd_bug_resolve, cmd_bug_show, cmd_bug_start, cmd_bugs
from azdo_daily.prs import cmd_pr_comments, cmd_pr_create, cmd_pr_reply
from azdo_daily.commands import (
    cmd_clear_history,
    cmd_configure,
    cmd_create,
    cmd_doctor,
    cmd_end,
    cmd_help,
    cmd_hours,
    cmd_nuke,
    cmd_reconfigure,
    cmd_start,
    cmd_status,
    cmd_update,
)


def _valid_date(s):
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        raise argparse.ArgumentTypeError(f"Date must be YYYY-MM-DD, got: {s}")


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
  python main.py end         → mark tasks as done (auto-resolves story if all done)
  python main.py status      → see today's open/resolved tasks
        """,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("configure", help="Set credentials interactively")
    create_p = sub.add_parser(
        "create",
        help="Pick stories → generate tasks → create in Azure DevOps",
    )
    create_p.add_argument("--date", help="Date for tasks (YYYY-MM-DD, default today)")

    start_p = sub.add_parser("start", help="Activate tasks (mark as In Progress)")
    start_p.add_argument("--date", help="Date for tasks (YYYY-MM-DD, default today)")

    update_p = sub.add_parser("update", help="Log progress on tasks (keep open)")
    update_p.add_argument("--date", help="Date for tasks (YYYY-MM-DD, default today)")

    end_p = sub.add_parser(
        "end", help="Mark tasks as done (auto-resolves story if all done)"
    )
    end_p.add_argument("--date", help="Date for tasks (YYYY-MM-DD, default today)")

    status_p = sub.add_parser("status", help="Show today's stories and tasks")
    status_p.add_argument("--date", help="Date for tasks (YYYY-MM-DD, default today)")

    hours_p = sub.add_parser(
        "hours", help="Show completed hours for closed tasks and stories"
    )
    hours_p.add_argument(
        "--since",
        type=_valid_date,
        metavar="YYYY-MM-DD",
        help="Filter by closed date >= YYYY-MM-DD",
    )
    hours_p.add_argument(
        "--until",
        type=_valid_date,
        metavar="YYYY-MM-DD",
        help="Filter by closed date <= YYYY-MM-DD",
    )

    bugs_p = sub.add_parser("bugs", help="List open bugs assigned to you")
    bugs_p.add_argument("--json", action="store_true", help="Print JSON")

    bug_p = sub.add_parser("bug", help="Show, start or resolve one bug")
    bug_sub = bug_p.add_subparsers(dest="bug_cmd", required=True)
    for name, hlp in (
        ("show", "Show a bug with repro steps and comments"),
        ("start", "Move a bug to its in-progress state"),
        ("resolve", "Comment on a bug and move it to its resolved state"),
    ):
        bp = bug_sub.add_parser(name, help=hlp)
        bp.add_argument("id", type=int, help="Bug work item id")
        bp.add_argument("--json", action="store_true", help="Print JSON")
        if name == "resolve":
            bp.add_argument("--comment", required=True, help="Resolution comment")

    pr_p = sub.add_parser("pr", help="Create a PR, list comments, reply to threads")
    pr_sub = pr_p.add_subparsers(dest="pr_cmd", required=True)
    pc = pr_sub.add_parser("create", help="Open one PR linking the bugs")
    pc.add_argument("--bugs", required=True, help="Bug ids, e.g. 1,2,3")
    pc.add_argument("--title", required=True, help="PR title")
    pm = pr_sub.add_parser("comments", help="List active review threads")
    pm.add_argument("pr", type=int, help="PR id")
    pp = pr_sub.add_parser("reply", help="Reply to a thread")
    pp.add_argument("pr", type=int, help="PR id")
    pp.add_argument("thread", type=int, help="Thread id")
    pp.add_argument("--text", required=True, help="Reply text")
    pp.add_argument("--resolve", action="store_true", help="Mark thread fixed")
    for p_ in (pc, pm, pp):
        p_.add_argument("--json", action="store_true", help="Print JSON")

    sub.add_parser("reconfigure", help="Reconfigure credentials and settings")
    sub.add_parser("clear-history", help="Clear daily state and task history")
    sub.add_parser("doctor", help="Check configuration and API connectivity")
    sub.add_parser("nuke", help="Delete all config and state (destructive)")
    sub.add_parser("help", help="Show all available commands")

    args = ap.parse_args()
    if args.cmd == "pr":
        {"create": cmd_pr_create, "comments": cmd_pr_comments, "reply": cmd_pr_reply}[
            args.pr_cmd
        ](args)
        return
    if args.cmd == "bug":
        {"show": cmd_bug_show, "start": cmd_bug_start, "resolve": cmd_bug_resolve}[
            args.bug_cmd
        ](args)
        return
    {
        "configure": cmd_configure,
        "create": cmd_create,
        "start": cmd_start,
        "update": cmd_update,
        "end": cmd_end,
        "status": cmd_status,
        "hours": cmd_hours,
        "bugs": cmd_bugs,
        "reconfigure": cmd_reconfigure,
        "clear-history": cmd_clear_history,
        "doctor": cmd_doctor,
        "nuke": cmd_nuke,
        "help": cmd_help,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
