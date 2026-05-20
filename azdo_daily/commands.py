"""CLI command implementations."""

import sys
from datetime import datetime
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
    date_str = args.date

    ui.hdr("Fetching your user stories…")
    try:
        stories = azdo.get_my_stories(sess, cfg)
    except requests.HTTPError as e:
        ui.err(f"Azure DevOps error: {e.response.status_code}")
        sys.exit(1)

    if not stories:
        ui.warn("No active user stories found assigned to you.")
        sys.exit(0)

    ui.info(f"Found {len(stories)} {'story' if len(stories) == 1 else 'stories'}:")
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
        item_type = s["fields"].get("System.WorkItemType", "User Story")
        ui.ok(f"[{item_type}] #{s['id']}  {s['fields']['System.Title']}")

    st = state.load_state(date_str)
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
            except Exception:
                ui.err("AI task breakdown failed")
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
            ui.err(f"{task['title']} — HTTP {e.response.status_code}")
        except Exception:
            ui.err(f"{task['title']} — Failed to create")

    st["tasks"] = st.get("tasks", []) + created
    state.save_state(st)
    print()
    ui.info(f"Done. {len(created)} task(s) created and linked.")


def cmd_start(args):
    """Activate tasks (mark as In Progress)."""
    cfg = config.load_cfg()
    config.require_cfg(cfg, "org", "project", "pat")
    sess = azdo.session(cfg)

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

    # Fetch all child tasks from stories
    all_tasks = []
    task_to_story = {}
    for s in stories:
        try:
            tasks = azdo.get_task_children(sess, cfg, s["id"])
            for t in tasks:
                task_to_story[t["id"]] = s["id"]
            all_tasks.extend(tasks)
        except requests.HTTPError as e:
            ui.warn(
                f"Failed to fetch tasks for story #{s['id']}: {e.response.status_code}"
            )

    if not all_tasks:
        ui.warn("No tasks found. Run 'azdo-daily create' to generate tasks first.")
        return

    # Show all non-done tasks (New + Active)
    new_tasks = [
        {
            "id": t["id"],
            "title": f"[{t.get('fields', {}).get('System.WorkItemType', 'Task')}] "
            f"[{t.get('fields', {}).get('System.State', '')}] "
            f"{t['fields'].get('System.Title', '')}",
        }
        for t in all_tasks
    ]

    if not new_tasks:
        ui.warn(
            "All tasks already active. Use 'azdo-daily update' or 'azdo-daily end'."
        )
        return

    ui.hdr("Tasks — select to activate")
    ui.print_tasks(new_tasks)

    selected_tasks = ui.select_from_list(new_tasks, "Select tasks to start")
    if not selected_tasks:
        ui.err("No valid selection.")
        return

    # Collect unique story IDs from selected tasks
    selected_task_ids = [t["id"] for t in selected_tasks]
    story_ids = set(task_to_story[tid] for tid in selected_task_ids)

    if story_ids:
        ui.hdr("Auto-activating stories (if in New state)…")
        for story_id in story_ids:
            try:
                azdo.set_workitem_state(sess, cfg, story_id, StoryState.ACTIVE.value)
                ui.ok(f"[User Story] #{story_id} activated")
            except requests.HTTPError:
                pass

    ui.hdr("Activating tasks...")

    for task_id in selected_task_ids:
        try:
            azdo.set_workitem_state(sess, cfg, task_id, TaskState.ACTIVE.value)
            ui.ok(f"[Task] #{task_id} activated")
        except requests.HTTPError as e:
            ui.err(f"#{task_id} — HTTP {e.response.status_code}")

    # Fetch updated work items to get ChangedDate from API
    try:
        updated_items = azdo.get_workitems(sess, cfg, selected_task_ids)
        task_state_dates = {
            t["id"]: t.get("fields", {}).get("System.ChangedDate")
            for t in updated_items
        }
    except requests.HTTPError:
        task_state_dates = {}

    # Update state with start_date from API
    st = state.load_state(args.date if hasattr(args, "date") else None)
    for task in st.get("tasks", []):
        if task["id"] in selected_task_ids and "start_date" not in task:
            task["start_date"] = task_state_dates.get(task["id"])
    state.save_state(st)

    print()
    ui.info("Tasks activated.")


def cmd_update(args):
    """Log progress on tasks (keep open)."""
    cfg = config.load_cfg()
    config.require_cfg(cfg, "org", "project", "pat")
    sess = azdo.session(cfg)

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

    # Fetch all child tasks from stories
    all_tasks = []
    for s in stories:
        try:
            tasks = azdo.get_task_children(sess, cfg, s["id"])
            all_tasks.extend(tasks)
        except requests.HTTPError:
            pass

    if not all_tasks:
        ui.warn("No tasks found for your stories.")
        return

    # Format tasks for display (all non-closed tasks are available to update)
    open_tasks = []
    for t in all_tasks:
        state = t.get("fields", {}).get("System.State", "")
        start_str = ""
        if state == "Active":
            changed_date = t.get("fields", {}).get("System.ChangedDate", "")
            if changed_date:
                try:
                    dt = datetime.fromisoformat(changed_date.replace("Z", "+00:00"))
                    local_dt = dt.astimezone()
                    start_str = f" @ {local_dt.strftime('%Y-%m-%d %H:%M')}"
                except (ValueError, AttributeError):
                    pass
        title = (
            f"[{t.get('fields', {}).get('System.WorkItemType', 'Task')}] "
            f"[{state}] "
            f"{t['fields'].get('System.Title', '')}{start_str}"
        )
        open_tasks.append({"id": t["id"], "title": title})

    if not open_tasks:
        ui.warn("No open tasks for your stories.")
        return

    ui.hdr("Tasks — select to log progress")
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

    # Fetch all child tasks from stories, track task→story mapping
    all_tasks = []
    story_task_ids = {}  # story_id -> [task_ids]
    task_to_story = {}  # task_id -> story_id
    for s in stories:
        try:
            tasks = azdo.get_task_children(sess, cfg, s["id"])
            story_task_ids[s["id"]] = [t["id"] for t in tasks]
            for t in tasks:
                task_to_story[t["id"]] = s["id"]
            all_tasks.extend(tasks)
        except requests.HTTPError:
            pass

    if not all_tasks:
        ui.warn("No tasks found for your stories.")
        return

    # Format tasks for display
    open_tasks = []
    for t in all_tasks:
        state = t.get("fields", {}).get("System.State", "")
        start_str = ""
        if state == "Active":
            changed_date = t.get("fields", {}).get("System.ChangedDate", "")
            if changed_date:
                try:
                    dt = datetime.fromisoformat(changed_date.replace("Z", "+00:00"))
                    local_dt = dt.astimezone()
                    start_str = f" @ {local_dt.strftime('%Y-%m-%d %H:%M')}"
                except (ValueError, AttributeError):
                    pass
        title = (
            f"[{t.get('fields', {}).get('System.WorkItemType', 'Task')}] "
            f"[{state}] "
            f"{t['fields'].get('System.Title', '')}{start_str}"
        )
        open_tasks.append({"id": t["id"], "title": title})

    if not open_tasks:
        ui.warn("No open tasks for your stories.")
        return

    ui.hdr("Tasks — select to mark as done")
    ui.print_tasks(open_tasks)

    selected_tasks = ui.select_from_list(open_tasks, "Select tasks to complete")
    if not selected_tasks:
        ui.err("No valid selection.")
        return

    close_state = TaskState.CLOSED.value
    closed_task_ids = set()

    ui.hdr(f"Mark tasks as '{close_state}'")
    for task in selected_tasks:
        print(f"\n  {ui.B}#{task['id']}{ui.R}  {task['title']}")
        ui.sep()

        hours_raw = ui.ask("Hours spent (optional)")
        completed_hours = ui.float_or_none(hours_raw)

        note = ui.ask("Closing note (optional)")
        comment = note if note else None

        try:
            azdo.resolve_task(
                sess, cfg, task["id"], close_state, completed_hours, comment
            )
            closed_task_ids.add(task["id"])
            ui.ok(f"Marked as '{close_state}'")
        except requests.HTTPError as e:
            ui.err(f"#{task['id']} — Failed to update (HTTP {e.response.status_code})")

    print()

    # Find stories ready to resolve (all tasks closed)
    already_open = {t["id"] for t in all_tasks} - {t["id"] for t in open_tasks}
    stories_to_resolve = []
    for story_id, task_ids in story_task_ids.items():
        remaining_open = [
            tid
            for tid in task_ids
            if tid not in closed_task_ids and tid not in already_open
        ]
        if task_ids and not remaining_open:
            stories_to_resolve.append(story_id)

    # Confirm before resolving stories
    if stories_to_resolve:
        ui.hdr(f"Ready to resolve {len(stories_to_resolve)} story(ies)")
        for story_id in stories_to_resolve:
            story = next((s for s in stories if s["id"] == story_id), None)
            if story:
                title = story["fields"].get("System.Title", "")
                item_type = story["fields"].get("System.WorkItemType", "User Story")
                print(f"  [{item_type}] #{story_id}  {title}")

        confirm = ui.ask("Resolve these stories? (yes/no)", "yes").lower()
        if confirm.startswith("y"):
            for story_id in stories_to_resolve:
                try:
                    azdo.set_workitem_state(
                        sess, cfg, story_id, StoryState.RESOLVED.value
                    )
                    ui.ok(f"[User Story] #{story_id} resolved (all tasks closed)")
                except requests.HTTPError as e:
                    ui.warn(
                        f"[User Story] #{story_id} — could not resolve: "
                        f"{e.response.status_code}"
                    )
        else:
            ui.info("Story resolution skipped.")

    ui.info(f"Tasks marked as '{close_state}'.")


def cmd_hours(args):
    """Show completed hours for closed tasks and stories."""
    cfg = config.load_cfg()
    config.require_cfg(cfg, "org", "project", "pat")
    sess = azdo.session(cfg)

    since = getattr(args, "since", None)
    until = getattr(args, "until", None)

    header = "Hours Report"
    if since:
        header += f"  (since: {since})"
    if until:
        header += f"  (until: {until})"
    ui.hdr(header)

    try:
        active_stories = azdo.get_my_stories(sess, cfg)
    except requests.HTTPError as e:
        ui.err(f"Azure DevOps error: {e.response.status_code}")
        return

    try:
        closed_stories = azdo.get_closed_stories(sess, cfg, since, until)
    except ValueError as e:
        ui.err(f"Configuration error: {e}")
        return
    except requests.HTTPError as e:
        ui.err(f"Azure DevOps error: {e.response.status_code}")
        return

    seen_ids = set()
    stories = []
    for s in active_stories + closed_stories:
        if s["id"] not in seen_ids:
            seen_ids.add(s["id"])
            stories.append(s)

    if not stories:
        ui.warn("No stories found.")
        return

    total_story_hours = 0.0
    total_task_hours = 0.0

    for story in stories:
        f = story.get("fields", {})
        story_id = story["id"]
        item_type = f.get("System.WorkItemType", "User Story")
        title = f.get("System.Title", "")
        story_hours = f.get("Microsoft.VSTS.Scheduling.CompletedWork") or 0.0
        total_story_hours += story_hours

        try:
            all_children = azdo.get_task_children(
                sess, cfg, story_id, active_only=False
            )
        except requests.HTTPError as e:
            ui.warn(f"Failed to fetch tasks for #{story_id}: {e.response.status_code}")
            all_children = []

        closed_tasks = [
            t
            for t in all_children
            if t.get("fields", {}).get("System.State") in azdo._DONE_STATES
        ]

        task_hours = sum(
            (t.get("fields", {}).get("Microsoft.VSTS.Scheduling.CompletedWork") or 0.0)
            for t in closed_tasks
        )
        total_task_hours += task_hours

        print(f"\n  {ui.CY}[{item_type}] #{story_id}{ui.R}  {title}")
        print(f"    Story hours: {story_hours:.1f}h  |  Task hours: {task_hours:.1f}h")

        if not closed_tasks:
            print(f"    {ui.DIM}(no hours logged on closed tasks){ui.R}")
        else:
            for t in closed_tasks:
                tf = t.get("fields", {})
                task_type = tf.get("System.WorkItemType", "Task")
                task_title = tf.get("System.Title", "")
                h = tf.get("Microsoft.VSTS.Scheduling.CompletedWork") or 0.0
                print(
                    f"    {ui.DIM}[{task_type}] #{t['id']}  {task_title}"
                    f"  — {h:.1f}h{ui.R}"
                )

    print()
    ui.sep()
    ui.info(
        f"Grand total — Story hours: {total_story_hours:.1f}h"
        f"  |  Task hours: {total_task_hours:.1f}h"
    )


def _print_hours_summary(sess, cfg):
    """Fetch closed stories and print a one-line hours summary. Silent if none."""
    try:
        closed_stories = azdo.get_closed_stories(sess, cfg)
    except requests.HTTPError:
        return

    if not closed_stories:
        return

    total_story_hours = 0.0
    total_task_hours = 0.0
    for story in closed_stories:
        f = story.get("fields", {})
        total_story_hours += f.get("Microsoft.VSTS.Scheduling.CompletedWork") or 0.0
        try:
            all_children = azdo.get_task_children(
                sess, cfg, story["id"], active_only=False
            )
        except requests.HTTPError:
            continue
        for t in all_children:
            if t.get("fields", {}).get("System.State") in azdo._DONE_STATES:
                total_task_hours += (
                    t.get("fields", {}).get("Microsoft.VSTS.Scheduling.CompletedWork")
                    or 0.0
                )

    ui.info(
        f"Completed hours (all time):  Story: {total_story_hours:.1f}h"
        f"  |  Tasks: {total_task_hours:.1f}h"
    )


def cmd_status(args):
    """Show today's stories and tasks from Azure DevOps API."""
    from datetime import date

    cfg = config.load_cfg()
    config.require_cfg(cfg, "org", "project", "pat")
    sess = azdo.session(cfg)
    date_str = args.date or date.today().isoformat()

    ui.hdr(f"Status — {date_str}")

    # Fetch stories from API
    ui.info("Fetching stories from Azure DevOps…")
    try:
        stories = azdo.get_my_stories(sess, cfg)
    except requests.HTTPError as e:
        ui.err(f"Azure DevOps error: {e.response.status_code}")
        return

    if not stories:
        ui.warn("No active user stories assigned to you.")
        _print_hours_summary(sess, cfg)
        return

    ui.info(f"Your stories ({len(stories)}):")
    for s in stories:
        item_type = s["fields"].get("System.WorkItemType", "User Story")
        state = s["fields"].get("System.State", "")
        title = s["fields"]["System.Title"]
        print(f"    {ui.CY}#{s['id']}{ui.R}  [{item_type}]  [{state}]  {title}")
    print()

    # Fetch all child tasks from stories (include done to show totals)
    open_tasks = []
    total_task_count = 0
    for s in stories:
        try:
            all_children = azdo.get_task_children(sess, cfg, s["id"], active_only=False)
            total_task_count += len(all_children)
            open_children = azdo.get_task_children(sess, cfg, s["id"], active_only=True)
            open_tasks.extend(open_children)
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

    if total_task_count == 0:
        ui.info("No tasks found for your stories.")
        return

    if not open_tasks:
        done_c = total_task_count
        ui.ok(f"All {done_c} task(s) done for active stories.")
        _print_hours_summary(sess, cfg)
        return

    all_tasks = open_tasks

    # Format tasks for display with type
    display_tasks = []
    for t in all_tasks:
        state_val = t.get("fields", {}).get("System.State", "")
        task_type = t.get("fields", {}).get("System.WorkItemType", "Task")
        title = t["fields"].get("System.Title", "")
        display_tasks.append(
            {
                "id": t["id"],
                "title": f"[{task_type}] [{state_val}] {title}",
                "closed": state_val.lower() == "closed",
            }
        )

    ui.print_tasks(display_tasks)

    # Summary
    closed_c = sum(1 for t in display_tasks if t.get("closed"))
    open_c = sum(1 for t in display_tasks if not t.get("closed"))
    print()
    ui.info(f"Total: {closed_c} resolved  /  {open_c} still open")
    _print_hours_summary(sess, cfg)


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


def cmd_doctor(args):
    """Check configuration health and connectivity."""
    ui.hdr("Configuration Doctor")

    # Check config file exists
    if not config.CONFIG_FILE.exists():
        ui.err("❌ Config file not found: " + str(config.CONFIG_FILE))
        ui.info("Run: azdo-daily configure")
        return

    ui.ok("✓ Config file exists")

    # Load and check required fields
    cfg = config.load_cfg()
    required = ["org", "project", "pat", "assigned_to"]
    missing = [k for k in required if not cfg.get(k)]

    if missing:
        ui.err(f"❌ Missing required config: {', '.join(missing)}")
        return

    ui.ok("✓ All required fields present")

    # Test Azure DevOps API connectivity
    ui.info("Testing Azure DevOps API...")
    try:
        sess = azdo.session(cfg)
        stories = azdo.get_my_stories(sess, cfg)
        ui.ok(f"✓ Azure DevOps API OK ({len(stories)} story/ies)")
    except requests.HTTPError as e:
        ui.err(f"❌ Azure DevOps API error: HTTP {e.response.status_code}")
        if e.response.status_code == 401:
            ui.err("  Invalid PAT or credentials")
        elif e.response.status_code == 404:
            ui.err("  Project or org not found")
        return
    except Exception as e:
        ui.err(f"❌ Azure DevOps API failed: {type(e).__name__}")
        return

    # Test Anthropic API key if set
    if cfg.get("anthropic_api_key"):
        ui.info("Testing Anthropic API...")
        try:
            import requests as req

            r = req.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": cfg["anthropic_api_key"],
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-opus-4-1",
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "hi"}],
                },
                timeout=10,
            )
            r.raise_for_status()
            ui.ok("✓ Anthropic API OK")
        except requests.HTTPError as e:
            ui.err(f"❌ Anthropic API error: HTTP {e.response.status_code}")
            if e.response.status_code == 401:
                ui.err("  Invalid API key")
            return
        except Exception as e:
            ui.err(f"❌ Anthropic API failed: {type(e).__name__}")
            return
    else:
        ui.warn("⊘ Anthropic API key not set (AI breakdown disabled)")

    print()
    ui.ok("All checks passed ✓")


def cmd_help(args):
    """Show all available commands."""
    ui.hdr("Available commands")
    commands = [
        ("configure", "Set org/project/PAT/API key"),
        ("create", "Pick stories → generate tasks → create in Azure DevOps"),
        ("start", "Activate tasks (mark as In Progress)"),
        ("update", "Log progress hours/notes on tasks (keep open)"),
        ("end", "Mark tasks done → auto-resolve story if all done"),
        ("status", "Show today's stories and open tasks"),
        ("hours", "Show completed hours for closed stories/tasks (--since/--until)"),
        ("reconfigure", "Update credentials and settings"),
        ("clear-history", "Clear all daily state files"),
        ("doctor", "Check config health and API connectivity"),
        ("nuke", "Delete all config and state (destructive)"),
        ("help", "Show this help message"),
    ]
    for cmd, desc in commands:
        print(f"  {ui.B}{cmd:<16}{ui.R} {desc}")


def cmd_nuke(args):
    """Delete all config and state files (destructive)."""
    ui.hdr("⚠️  NUKE — Remove all config and state")
    ui.err("This will DELETE:")
    ui.err("  • .config/settings.json (credentials, API keys)")
    ui.err("  • state/ (all daily task history)")
    print()
    ui.warn("This cannot be undone.")
    print()

    confirm = ui.ask("Type 'nuke' to confirm", "")
    if confirm.lower() != "nuke":
        ui.warn("Cancelled.")
        return

    try:
        config_file = config.CONFIG_FILE
        state_dir = state.STATE_DIR

        deleted = []
        if config_file.exists():
            config_file.unlink()
            deleted.append(".config/settings.json")

        if state_dir.exists():
            import shutil

            shutil.rmtree(state_dir)
            deleted.append("state/")

        if deleted:
            ui.ok("Deleted: " + ", ".join(deleted))
        else:
            ui.info("Nothing to delete.")
    except Exception as e:
        ui.err(f"Failed to nuke: {e}")
