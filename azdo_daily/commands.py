"""CLI command implementations."""

import sys
from enum import Enum

import requests

from azdo_daily import ai, azdo, config, state, ui


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


TASK_STATE_DESCS = {
    TaskState.NEW: "Not started",
    TaskState.ACTIVE: "In progress",
    TaskState.CLOSED: "Completed",
}

STORY_STATE_DESCS = {
    StoryState.NEW: "Not started",
    StoryState.ACTIVE: "In progress",
    StoryState.RESOLVED: "Completed",
    StoryState.CLOSED: "Finished",
}


def cmd_configure(args):
    """Interactive configuration."""
    cfg = config.load_cfg()
    ui.hdr("Configure credentials")
    fields = [
        ("org", "Azure DevOps org name"),
        ("project", "Project name"),
        ("pat", "Personal Access Token (PAT)"),
        ("anthropic_api_key", "Anthropic API key (for AI breakdown)"),
        ("assigned_to", "Your email / display name (for story filter)"),
        ("area_path", "Default area path (optional)"),
    ]
    for key, label in fields:
        current = cfg.get(key, "")
        show = "****" if (current and key in ("pat", "anthropic_api_key")) else current
        val = ui.ask(label, show if show else None)
        if val and val != "****":
            cfg[key] = val

    config.save_cfg(cfg)
    ui.ok(f"Saved to {config.CONFIG_FILE}")


def cmd_create(args):
    """Pick stories → generate tasks → create in Azure DevOps."""
    cfg = config.load_cfg()
    config.require_cfg(cfg, "org", "project", "pat")
    sess = azdo.session(cfg)

    ui.hdr("Fetching your user stories…")
    try:
        stories = azdo.get_my_stories(sess, cfg)
    except requests.HTTPError as e:
        ui.err(f"Azure DevOps error: {e.response.status_code} {e.response.text[:200]}")
        sys.exit(1)

    if not stories:
        ui.warn("No active user stories found assigned to you.")
        sys.exit(0)

    ui.info(f"Found {len(stories)} user story/stories:")
    ui.print_stories(stories)

    raw = ui.ask("Select stories to work on today (e.g. 1  or  1,3  or  1-3)")
    indices = ui.parse_selection(raw, len(stories))
    if not indices:
        ui.err("No valid selection.")
        sys.exit(1)

    selected = [stories[i] for i in indices]
    selected_ids = [s["id"] for s in selected]

    ui.hdr("Selected stories:")
    for s in selected:
        ui.ok(f"#{s['id']}  {s['fields']['System.Title']}")

    st = state.load_state()
    st["stories"] = [
        {"id": s["id"], "title": s["fields"]["System.Title"]} for s in selected
    ]

    # Build task list
    ui.hdr("Define tasks")
    if len(selected) == 1:
        story_title = selected[0]["fields"]["System.Title"]
        ui.info(f"Story: {story_title}")
    else:
        ui.info("Tasks will be created once and linked to all selected stories.")

    print()
    print("  How do you want to create tasks?")
    print(f"  {ui.B}1.{ui.R}  Use template (UI, Logic, Unit Test)")
    print(f"  {ui.B}2.{ui.R}  AI auto-breakdown from story description")
    print(f"  {ui.B}3.{ui.R}  Enter tasks manually")
    print(f"  {ui.B}4.{ui.R}  Template + AI suggestions → review")
    mode = ui.ask("Choose", "1")

    proposed_tasks = []
    templates = cfg.get("task_templates", [])
    if mode in ("1", "4"):
        story_title = selected[0]["fields"]["System.Title"]
        for t in templates:
            task = dict(t)
            task["title"] = f"{t['title']} | {story_title}"
            proposed_tasks.append(task)

    if mode in ("2", "4"):
        if not cfg.get("anthropic_api_key"):
            ui.err("anthropic_api_key not set. Run:  azdo-daily configure")
            if mode == "2":
                sys.exit(1)
            ui.warn("Falling back to manual entry.")
            mode = "3"
        else:
            story_parts = []
            for s in selected:
                f = s.get("fields", {})
                story_parts.append(
                    f"Story #{s['id']}: {f.get('System.Title','')}\n"
                    f"{f.get('System.Description','(no description)')}"
                )
            story_text = "\n\n---\n\n".join(story_parts)
            ui.info("Calling AI breakdown…")
            try:
                ai_tasks = ai.ai_breakdown(story_text, cfg["anthropic_api_key"])
                if mode == "4":
                    proposed_tasks.extend(ai_tasks)
                    ui.hdr(f"Template + AI: {len(proposed_tasks)} task(s):")
                else:
                    proposed_tasks = ai_tasks
                    ui.hdr(f"AI suggested {len(proposed_tasks)} task(s):")
                ui.print_tasks(proposed_tasks)
            except Exception as e:
                ui.err(f"AI error: {e}")
                if mode == "2":
                    sys.exit(1)
                if mode == "4":
                    ui.warn("Keeping template tasks only.")
                else:
                    proposed_tasks = []

    if mode in ("3", "4"):
        ui.hdr("Manual task entry  (blank title to stop)")
        prio_map = {"1": 1, "2": 2, "3": 3, "4": 4}
        while True:
            title = ui.ask("Task title")
            if not title:
                break
            prio = ui.ask("Priority (1=Critical 2=High 3=Medium 4=Low)", "2")
            desc = ui.ask("Short description (optional)")
            effort = ui.ask("Estimated hours (optional)")
            tags = ui.ask("Tags semicolon-separated (optional)")
            proposed_tasks.append(
                {
                    "title": title,
                    "description": desc,
                    "priority": int(prio_map.get(prio, "2")),
                    "effort": ui.float_or_none(effort),
                    "tags": tags,
                }
            )
            ui.ok(f"Added: {title}")

    if not proposed_tasks:
        ui.warn("No tasks defined. Exiting.")
        sys.exit(0)

    # Review & confirm
    if mode in ("2", "4"):
        ui.hdr("Review tasks before creating")
        ui.print_tasks(proposed_tasks)
        action = ui.ask("(c)onfirm all / (e)dit list / (q)uit", "c").lower()
        if action.startswith("q"):
            sys.exit(0)
        if action.startswith("e"):
            while True:
                print(f"\n  {ui.B}Options:{ui.R}  (r)emove #n  (a)dd  (d)one")
                cmd_in = ui.ask("Action").lower()
                if cmd_in.startswith("d"):
                    break
                elif cmd_in.startswith("r"):
                    num = ui.ask("Remove task number")
                    if num.isdigit():
                        idx = int(num) - 1
                        if 0 <= idx < len(proposed_tasks):
                            removed = proposed_tasks.pop(idx)
                            ui.warn(f"Removed: {removed['title']}")
                            ui.print_tasks(proposed_tasks)
                elif cmd_in.startswith("a"):
                    title = ui.ask("Task title")
                    prio = ui.ask("Priority (1-4)", "2")
                    desc = ui.ask("Description (optional)")
                    effort = ui.ask("Estimated hours (optional)")
                    tags = ui.ask("Tags (optional)")
                    proposed_tasks.append(
                        {
                            "title": title,
                            "description": desc,
                            "priority": int(prio) if prio.isdigit() else 2,
                            "effort": ui.float_or_none(effort),
                            "tags": tags,
                        }
                    )
                    ui.ok(f"Added: {title}")

    # Create tasks in Azure DevOps
    ui.hdr(f"Creating {len(proposed_tasks)} task(s) in Azure DevOps…")
    created = []
    story_titles = [s["fields"]["System.Title"] for s in selected]
    for task in proposed_tasks:
        try:
            item = azdo.create_task(sess, cfg, task, selected_ids)
            task_url = item.get("_links", {}).get("html", {}).get("href", "")
            entry = {
                "id": item["id"],
                "title": task["title"],
                "url": task_url,
                "closed": False,
                "story_ids": selected_ids,
            }
            created.append(entry)
            linked = " + ".join(f"#{sid}" for sid in selected_ids)
            story_str = (
                " | ".join(story_titles) if len(story_titles) > 1 else story_titles[0]
            )
            print(f"{ui.B}#{item['id']}{ui.R}  {task['title']}")
            print(f"  {ui.DIM}Story: {story_str}{ui.R}")
            if task_url:
                print(f"  {ui.DIM}{task_url}{ui.R}")
            print(f"  {ui.DIM}→ linked to {linked}{ui.R}")
        except requests.HTTPError as e:
            ui.err(
                f"{task['title']} — {e.response.status_code}: {e.response.text[:120]}"
            )
        except Exception as e:
            ui.err(f"{task['title']} — {e}")

    st["tasks"] = st.get("tasks", []) + created
    state.save_state(st)
    print()
    ui.info(f"Done. {len(created)} task(s) created and linked.")


def cmd_start(args):
    """Activate tasks (mark as In Progress)."""
    cfg = config.load_cfg()
    config.require_cfg(cfg, "org", "project", "pat")
    sess = azdo.session(cfg)
    st = state.load_state()

    tasks = st.get("tasks", [])
    if not tasks:
        ui.warn("No tasks for today.")
        return

    # Fetch fresh status from API
    task_ids = [t["id"] for t in tasks]
    api_status = azdo.refresh_task_status(sess, cfg, task_ids)

    # Filter for non-closed, non-active tasks
    new_tasks = [
        t
        for t in tasks
        if api_status.get(t["id"], {}).get("closed") is False
        and api_status.get(t["id"], {}).get("state", "").lower() != "active"
    ]

    if not new_tasks:
        ui.warn("No new tasks to activate.")
        return

    ui.hdr("New tasks — select to activate")
    ui.print_tasks(new_tasks)

    selected_tasks = ui.select_from_list(new_tasks, "Select tasks to start")
    if not selected_tasks:
        ui.err("No valid selection.")
        return

    story_ids = set()
    for task in selected_tasks:
        for sid in task.get("story_ids", []):
            story_ids.add(sid)

    if story_ids:
        ui.hdr("Auto-activating stories (if in New state)…")
        for story_id in story_ids:
            try:
                azdo.set_workitem_state(sess, cfg, story_id, StoryState.ACTIVE.value)
                ui.ok(f"Story #{story_id} activated")
            except requests.HTTPError:
                pass

    ui.hdr("Activating tasks...")
    for task in selected_tasks:
        try:
            azdo.set_workitem_state(sess, cfg, task["id"], TaskState.ACTIVE.value)
            task["active"] = True
            state.save_state(st)
            ui.ok(f"#{task['id']}  activated")
        except requests.HTTPError as e:
            ui.err(f"#{task['id']} — {e.response.status_code}: {e.response.text[:120]}")

    print()
    ui.info("Tasks activated.")


def cmd_update(args):
    """Log progress on tasks (keep open)."""
    cfg = config.load_cfg()
    config.require_cfg(cfg, "org", "project", "pat")
    sess = azdo.session(cfg)
    st = state.load_state()

    tasks = st.get("tasks", [])
    if not tasks:
        ui.warn("No tasks for today.")
        return

    # Fetch fresh status from API
    task_ids = [t["id"] for t in tasks]
    api_status = azdo.refresh_task_status(sess, cfg, task_ids)

    # Filter for non-closed tasks
    open_tasks = [
        t for t in tasks if api_status.get(t["id"], {}).get("closed") is False
    ]

    if not open_tasks:
        ui.warn("No open tasks for today.")
        return

    ui.hdr("Open tasks — select to log progress")
    ui.print_tasks(open_tasks)

    selected_tasks = ui.select_from_list(open_tasks, "Select tasks to update")
    if not selected_tasks:
        ui.err("No valid selection.")
        return

    ui.hdr("Log progress for each task (keep open)")
    for task in selected_tasks:
        print(f"\n  {ui.B}#{task['id']}{ui.R}  {task['title']}")
        ui.sep()

        hours_raw = ui.ask("Hours spent today (optional)")
        completed_hours = ui.float_or_none(hours_raw)

        remaining_raw = ui.ask("Remaining hours estimate (optional)")
        remaining_hours = ui.float_or_none(remaining_raw)

        note = ui.ask("Progress note (optional, will be added as comment)")
        comment = note if note else None

        try:
            azdo.partial_task(
                sess, cfg, task["id"], completed_hours, remaining_hours, comment
            )
            task["remaining_hours"] = remaining_hours
            task["completed_hours"] = completed_hours
            state.save_state(st)
            ui.ok(f"Updated (In Progress) — {remaining_hours or '?'}h remaining")
        except requests.HTTPError as e:
            ui.err(f"#{task['id']} — {e.response.status_code}: {e.response.text[:120]}")

    print()
    ui.info("Tasks kept open with progress logged.")


def cmd_end(args):
    """Mark tasks as done (auto-resolves story if all done)."""
    cfg = config.load_cfg()
    config.require_cfg(cfg, "org", "project", "pat")
    sess = azdo.session(cfg)
    st = state.load_state()

    tasks = st.get("tasks", [])
    if not tasks:
        ui.warn("No tasks for today.")
        return

    # Fetch fresh status from API
    task_ids = [t["id"] for t in tasks]
    api_status = azdo.refresh_task_status(sess, cfg, task_ids)

    # Filter for non-closed tasks
    open_tasks = [
        t for t in tasks if api_status.get(t["id"], {}).get("closed") is False
    ]

    if not open_tasks:
        ui.warn("No open tasks for today.")
        return

    ui.hdr("Open tasks — select to mark as done")
    ui.print_tasks(open_tasks)

    selected_tasks = ui.select_from_list(open_tasks, "Select tasks to complete")
    if not selected_tasks:
        ui.err("No valid selection.")
        return

    close_state = TaskState.CLOSED.value
    closed_story_ids = set()

    ui.hdr(f"Mark tasks as '{close_state}'")
    for task in selected_tasks:
        print(f"\n  {ui.B}#{task['id']}{ui.R}  {task['title']}")
        ui.sep()

        hours_raw = ui.ask("Hours spent today (optional)")
        completed_hours = ui.float_or_none(hours_raw)

        note = ui.ask("Any closing note? (optional)")
        comment = note if note else None

        try:
            azdo.resolve_task(
                sess, cfg, task["id"], close_state, completed_hours, comment
            )
            task["closed"] = True
            task["completed_hours"] = completed_hours

            story_ids = task.get("story_ids", [])
            for sid in story_ids:
                all_story_tasks = [
                    t for t in st.get("tasks", []) if sid in t.get("story_ids", [])
                ]
                if all(t.get("closed") for t in all_story_tasks):
                    closed_story_ids.add(sid)

            state.save_state(st)
            ui.ok(f"Marked as '{close_state}'")
        except requests.HTTPError as e:
            ui.err(f"#{task['id']} — {e.response.status_code}")
            ui.err(f"  {e.response.text}")

    if closed_story_ids:
        ui.hdr("Auto-resolving completed stories…")
        for story_id in closed_story_ids:
            try:
                azdo.set_workitem_state(sess, cfg, story_id, close_state)
                ui.ok(f"Story #{story_id} marked as '{close_state}'")
            except requests.HTTPError as e:
                msg = f"Story #{story_id} — {e.response.status_code}: "
                msg += e.response.text[:120]
                ui.err(msg)

    all_tasks = st.get("tasks", [])
    closed_c = sum(1 for t in all_tasks if t.get("closed"))
    open_c = sum(1 for t in all_tasks if not t.get("closed"))
    print()
    ui.info(f"Today: {closed_c} resolved  /  {open_c} still open")


def cmd_status(args):
    """Show today's stories and tasks from Azure DevOps API."""
    from datetime import date

    cfg = config.load_cfg()
    config.require_cfg(cfg, "org", "project", "pat")
    sess = azdo.session(cfg)

    ui.hdr(f"Status — {date.today().isoformat()}")

    # Fetch stories from API
    ui.info("Fetching stories from Azure DevOps…")
    try:
        stories = azdo.get_my_stories(sess, cfg)
    except requests.HTTPError as e:
        ui.err(f"Azure DevOps error: {e.response.status_code}")
        return

    if not stories:
        ui.warn("No active user stories assigned to you.")
        return

    ui.info(f"Active stories ({len(stories)}):")
    for s in stories:
        print(f"    {ui.CY}#{s['id']}{ui.R}  {s['fields']['System.Title']}")
    print()

    # Fetch all child tasks from stories
    all_tasks = []
    for s in stories:
        try:
            tasks = azdo.get_task_children(sess, cfg, s["id"])
            all_tasks.extend(tasks)
        except requests.HTTPError as e:
            error_detail = ""
            try:
                resp_json = e.response.json()
                error_detail = resp_json.get("message", "")
            except Exception:
                error_detail = e.response.text[:200]
            ui.warn(
                f"Failed to fetch tasks for story #{s['id']}: "
                f"{e.response.status_code} {error_detail}"
            )

    if not all_tasks:
        ui.info("No tasks found for active stories.")
        return

    # Format tasks for display with type
    display_tasks = []
    for t in all_tasks:
        state_val = t.get("fields", {}).get("System.State", "")
        task_type = t.get("fields", {}).get("System.WorkItemType", "Task")
        title = t["fields"].get("System.Title", "")
        display_tasks.append(
            {
                "id": t["id"],
                "title": f"[{task_type}] {title}",
                "closed": state_val.lower() == "closed",
            }
        )

    ui.print_tasks(display_tasks)

    # Summary
    closed_c = sum(1 for t in display_tasks if t.get("closed"))
    open_c = sum(1 for t in display_tasks if not t.get("closed"))
    print()
    ui.info(f"Total: {closed_c} resolved  /  {open_c} still open")


def cmd_clear_history(args):
    """Clear daily state and task history."""
    ui.hdr("Clear history")
    ui.warn("This will delete all daily state files (state/*.json)")

    confirm = ui.ask("Type 'yes' to confirm", "")
    if confirm.lower() != "yes":
        ui.warn("Cancelled.")
        return

    try:
        state_dir = state.STATE_DIR
        if state_dir.exists():
            import shutil

            shutil.rmtree(state_dir)
        ui.ok("History cleared")
    except Exception as e:
        ui.err(f"Failed to clear history: {e}")


def cmd_reconfigure(args):
    """Reconfigure credentials and settings."""
    ui.hdr("Reconfigure azdo-daily")

    confirm = ui.ask("Overwrite existing config? (yes/no)", "no")
    if confirm.lower() != "yes":
        ui.warn("Cancelled.")
        return

    cmd_configure(args)
