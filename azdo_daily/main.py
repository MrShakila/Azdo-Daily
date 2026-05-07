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

from azdo_daily.commands import (
    cmd_clear_history,
    cmd_configure,
    cmd_create,
    cmd_end,
    cmd_help,
    cmd_nuke,
    cmd_reconfigure,
    cmd_start,
    cmd_status,
    cmd_update,
)


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

    sub.add_parser("reconfigure", help="Reconfigure credentials and settings")
    sub.add_parser("clear-history", help="Clear daily state and task history")
    sub.add_parser("nuke", help="Delete all config and state (destructive)")
    sub.add_parser("help", help="Show all available commands")

    args = ap.parse_args()
    {
        "configure": cmd_configure,
        "create": cmd_create,
        "start": cmd_start,
        "update": cmd_update,
        "end": cmd_end,
        "status": cmd_status,
        "reconfigure": cmd_reconfigure,
        "clear-history": cmd_clear_history,
        "nuke": cmd_nuke,
        "help": cmd_help,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
