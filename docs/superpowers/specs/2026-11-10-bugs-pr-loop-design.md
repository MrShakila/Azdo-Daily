# Azure bugs and PR review loop

## Goal

QA creates Azure DevOps bugs and assigns them to the developer. Claude lists them, takes each one in turn (discuss, fix, test, commit), then opens one PR with all the fixes. When the developer comments on the PR, Claude fixes each comment, tests again and pushes, repeating until the developer is done.

## Scope

Two pieces, each in its own repo:

1. **Azdo-Daily** (this repo): new `bugs` and `pr` commands that wrap the Azure DevOps API and print JSON.
2. **flutter-mod** (`MrShakila/flutter-mod`): one new prompt section that tells Claude to run the loop using those commands. No new hooks.

Out of scope: tagging, publishing to PyPI, pushing or opening a PR without the developer saying so, anything outside Azure Repos and Azure Boards.

## Azdo-Daily changes

### Commands

All new commands take `--json` and print one JSON document to stdout. Human output stays the default.

| Command | Purpose |
|---------|---------|
| `azdo-daily bugs` | List bugs assigned to the configured user that are not closed or removed |
| `azdo-daily bug show <id>` | Title, state, severity, repro steps, comments, attachment links |
| `azdo-daily bug start <id>` | Move the bug to its in-progress state |
| `azdo-daily bug resolve <id> --comment TEXT` | Add the comment and move the bug to its resolved state |
| `azdo-daily pr create --bugs 1,2,3 --title T` | Open one PR from the current branch to `target_branch`, linking the bugs |
| `azdo-daily pr comments <pr>` | List active review threads with file, line and text |
| `azdo-daily pr reply <pr> <thread> --text T [--resolve]` | Reply to a thread and optionally resolve it |

### Modules

`commands.py` is 976 lines, so the new code does not go there.

- `azdo_daily/bugs.py`: `cmd_bugs`, `cmd_bug_show`, `cmd_bug_start`, `cmd_bug_resolve`.
- `azdo_daily/prs.py`: `cmd_pr_create`, `cmd_pr_comments`, `cmd_pr_reply`.
- `azdo_daily/azdo.py`: bug WIQL (`get_my_bugs`), bug fields and comments, and state lookup.
- `azdo_daily/git.py`: Azure Repos calls for create PR, list threads, reply, resolve thread.
- `azdo_daily/main.py`: argparse routing for the new subcommands.

### Bug queries and states

- WIQL: `WorkItemType = Bug`, assigned to the configured user, state not in (Closed, Removed).
- Azure process templates name states differently (Agile: New, Active, Resolved, Closed; Scrum: New, Approved, Committed, Done). The code reads the bug type's state list from the project's work item type API and picks the in-progress and resolved states from state categories (InProgress, Resolved/Completed), not from hard-coded names. If no state matches, the command fails with a clear error naming the available states.

### PRs

- Endpoints are under `{org}/{project}/_apis/git/repositories/{repo}`: pull requests (create, with `workItemRefs` for the bugs), threads (list, reply, set status).
- The source branch is the current git branch. `pr create` fails if the branch is not pushed or equals `target_branch`.
- `pr create` prints the PR id and URL.

### Config

- Config stays per project: `.config/settings.json` in the current directory, as today. There is no home-folder fallback.
- Two new keys: `repo` and `target_branch` (default `main`). `configure` and `reconfigure` ask for them.
- `configure` creates a `.gitignore` entry for `.config/` (and the file if it is missing) when the folder is a git repo, because the PAT lives in the project folder. Today it only edits an existing `.gitignore`.
- New commands use `require_cfg` and exit with the existing "Run: azdo-daily configure" message when a key is missing.

### Conventions kept

- Errors include the HTTP status code. No silent `except: pass`; use `ui.warn()`.
- Messages prefix the work item type, for example `[Bug]`.
- black and flake8 (line length 88) via pre-commit.

### Tests

pytest with mocked `requests`, in the style of `tests/test_cmd_hours.py`:

- `get_my_bugs` builds the right WIQL and parses results.
- State selection from categories, including the no-match error.
- `pr create` payload includes the work item refs and the right branches; refuses an unpushed branch.
- `pr comments` filters to active threads.
- `pr reply --resolve` sets the thread status.
- `configure` writes the `.gitignore` entry in a git repo with and without an existing `.gitignore`.

### Release

Bump the version to 1.8.0 in `pyproject.toml`, add a `CHANGELOG.md` entry, commit as `chore: Bump version to 1.8.0`. Tagging, the GitHub release and PyPI publishing stay with the developer.

## flutter-mod changes

One new session prompt section, `azure-bugs`, added next to `task-tracker` in `hooks/register.tsx`. Prompt text only, written without backticks (a backtick ends the template literal). The mod version is bumped (minor).

The section tells Claude:

1. Run every `azdo-daily` command from the project root, so it uses that project's `.config/settings.json`. If the file is missing, say so and ask the user to run `azdo-daily configure`.
2. When the user asks for their bugs: run `azdo-daily bugs --json`, create one vault note per bug (type bug, in the project's `bugs/` folder), and add them to Open items in `index.md`, as the task tracker rule already says.
3. Create one branch for the batch, for example `bugfix/azdo-YYYY-MM-DD`.
4. For each bug in list order: run `bug show`, discuss the cause and the fix with the user, run `bug start`, fix the root cause, run dart analyze and the relevant tests, verify with MobAI or webapp-testing as the verify loop says, make one small commit that references `AB#<id>`, run `bug resolve` with a short comment, and update the vault note. Then take the next bug.
5. When the list is done and the user says so, push the branch and run `pr create --bugs ...`. Never push or open the PR without the user's go-ahead.
6. Review loop: when the user says they commented, run `pr comments`, and for each thread fix, test, commit (one per comment or per related group), then push, reply with `pr reply --resolve`. Repeat until the user says the PR is done.
7. A comment that is unclear or disputed gets discussed with the user before any change, not guessed at.

## Success criteria

- `azdo-daily bugs --json` lists exactly the open bugs assigned to the configured user in a project with a valid config.
- A bug fix batch ends in one PR on Azure Repos that links every bug, with one commit per bug.
- A PR comment ends as a pushed commit, a reply and a resolved thread.
- `configure` never leaves the PAT unignored in a git repo.
- Existing commands and tests are unchanged and pass.

## Risks and open points

- Real Azure behavior is untested until `azdo-daily configure` is run in a project. The state-category lookup and the thread-status values are the likeliest places to differ from the docs, so the first run against a real project is the real test.
- PAT scopes needed: Work Items (read and write) and Code (read and write).
- The loop assumes the repo is on Azure Repos. A GitHub-hosted repo would need a different `pr` backend.
