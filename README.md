# Azure DevOps Daily Task Automation

## Setup

```bash
pip install -r requirements.txt
python main.py configure
```

You'll be prompted for:
| Field | Description |
|---|---|
| `org` | Your Azure DevOps organisation name |
| `project` | Project name |
| `pat` | Personal Access Token — needs **Work Items (Read & Write)** scope |
| `anthropic_api_key` | From console.anthropic.com — for AI task breakdown |
| `assigned_to` | Your email/display name — used to filter stories |
| `close_state` | `Done` / `Closed` / `Resolved` (depends on your process template) |

---

## Daily workflow

### Morning — `start`

```
python main.py start
```

1. Fetches all active User Stories assigned to you
2. You select one or multiple stories (e.g. `1` or `1,3` or `2-4`)
3. Choose how to create tasks:
   - **AI auto-breakdown** — Claude reads the story and generates tasks
   - **Manual entry** — type tasks yourself
   - **Both** — AI suggests, you add/remove
4. If multiple stories: tasks are created once and linked to all of them
   (child of story #1, "Related" to the rest)
5. Tasks appear in Azure DevOps immediately

### Anytime — `status`

```
python main.py status
```

Shows active stories and all tasks with open/resolved count.

### Evening — `end`

```
python main.py end
```

1. Lists all open tasks for today
2. You select which to update (e.g. `1,3` or `all`)
3. For each selected task you're asked:
   - **Fully complete?** (y/n)
   - **Hours spent today**
   - If complete → resolved with close state + hours logged
   - If not complete → stays "In Progress", logs hours + remaining estimate + comment

---

## State files

Each day's data is saved in `state/YYYY-MM-DD.json`:

```json
{
  "stories": [{"id": 42, "title": "..."}],
  "tasks": [
    {
      "id": 101, "title": "...", "url": "https://...",
      "closed": true, "completed_hours": 3.5,
      "story_ids": [42]
    }
  ]
}
```

---

## Cron (optional)

```cron
# 9 AM start reminder
0 9 * * 1-5 cd /path/to/azdo_daily && python main.py status

# Or run start automatically (non-interactive — only works if you pre-configure tasks)
```

> The `start` and `end` commands are interactive, so cron is best used for `status` reminders.
