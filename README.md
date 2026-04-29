# Azure DevOps Daily Task Automation

Creates your recurring tasks in Azure DevOps every morning and closes them at end of day — one command each way.

## Setup

```bash
pip install -r requirements.txt
python main.py configure        # enter your org, project, PAT interactively
```

Or edit `config.json` directly:

```json
{
  "org": "your-org",
  "project": "YourProject",
  "pat": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "assigned_to": "you@example.com",
  "area_path": "",
  "close_state": "Done"
}
```

**Creating a PAT** — Azure DevOps → User Settings → Personal Access Tokens → New Token
→ Scope: **Work Items (Read & Write)**

---

## Daily workflow

```bash
# Morning — creates all task templates as work items
python main.py start

# Check progress anytime
python main.py status

# Evening — closes all open tasks created today
python main.py end
```

---

## Managing task templates

```bash
python main.py add                        # interactive prompt
python main.py add "Review PRs" --priority 2 --tags "daily;review"
python main.py list                       # show all templates
python main.py remove                     # remove by number
```

Priority levels: 1 = Critical, 2 = High, 3 = Medium, 4 = Low

---

## Scheduling (optional)

**Linux / macOS — cron:**
```
# Start day at 9:00 AM
0 9 * * 1-5 cd /path/to/azdo_daily && python main.py start

# End day at 6:00 PM
0 18 * * 1-5 cd /path/to/azdo_daily && python main.py end
```

**Windows — Task Scheduler:**
Create two tasks pointing to `python main.py start` and `python main.py end`.

---

## File layout

```
azdo_daily/
├── main.py           — CLI entry point
├── config.json       — credentials & defaults
├── tasks.json        — recurring task templates
├── requirements.txt
└── state/
    └── 2026-04-29.json   — IDs created each day (auto-generated)
```

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python main.py configure       # enter org, project, PAT interactively
python main.py add             # add your recurring tasks
python main.py start           # morning — creates all tasks
python main.py end             # evening — closes them all