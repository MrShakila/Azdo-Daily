# Bugs and PR Review Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `bugs`, `bug show|start|resolve` and `pr create|comments|reply` commands to Azdo-Daily, then teach flutter-mod to run the fix-all-bugs-then-PR loop with them.

**Architecture:** New `bugs.py` and `prs.py` command modules, bug API helpers in `azdo.py`, Azure Repos calls in a new `git.py`, routing in `main.py`. Every new command takes `--json` and prints one JSON document. flutter-mod gets one prompt section and no hooks.

**Tech Stack:** Python 3.9+, requests, argparse, pytest with `unittest.mock`, black and flake8 (line length 88). flutter-mod: TypeScript hooks module, `claude plugin validate`.

**Spec:** `docs/superpowers/specs/2026-11-10-bugs-pr-loop-design.md`

## Global Constraints

- Config stays per project: `.config/settings.json` under the current directory (`config.CONFIG_FILE`); no home-folder fallback.
- New config keys: `repo` and `target_branch` (default `main`).
- Do not add the new commands to `commands.py` (976 lines); use `bugs.py` and `prs.py`.
- Errors include the HTTP status code; no silent `except: pass`, use `ui.warn()` / `ui.err()`.
- Messages prefix the work item type, for example `[Bug]`.
- Bug state names come from the project's work item type states by state category, never hard-coded.
- No push, tag, GitHub release or PyPI publish; version bump to `1.8.0` with a `CHANGELOG.md` entry only.
- Work on branch `feature/bugs-pr-loop`; one small commit per task, no Co-Authored-By line.
- Run `pytest -q` and `flake8 --max-line-length=88 --extend-ignore=E203,W503 azdo_daily tests` before each commit.

## Review Focus

- A bug type with no state in the wanted category: `pick_state` raises `ValueError` listing the available state names (Task 2).
- An assignee containing a single quote: `get_my_bugs` raises `ValueError`, same as `get_my_stories` (Task 2).
- `--json` output stays pure JSON on stdout: no `ui` headers mixed in; errors go to stderr with exit code 1 (Task 3).
- PR threads with no file context (general comments) or deleted comments: `pr comments` lists them with `file: null` and does not crash (Task 4).
- `pr create` on the target branch or on a branch not on `origin`: exits 1 with a clear message and makes no API call (Task 5).
- A bug with no repro steps or attachments: `bug show` returns empty strings and an empty list, not an error (Task 2).

---

### Task 1: Config keys and gitignore

**Files:**
- Modify: `azdo_daily/config.py` (`DEFAULT_CFG`, `_ensure_gitignore`)
- Modify: `azdo_daily/commands.py:43-62` (`cmd_configure` fields)
- Test: `tests/test_config.py` (create)

**Interfaces:**
- Produces: `DEFAULT_CFG["repo"] == ""`, `DEFAULT_CFG["target_branch"] == "main"`; `_ensure_gitignore()` creates `.gitignore` containing `.config/` when `Path.cwd()/.git` exists.

- [ ] **Step 1: Write failing tests** in `tests/test_config.py`, each with `monkeypatch.chdir(tmp_path)` and `config.CONFIG_DIR`/`CONFIG_FILE` patched to `tmp_path/.config`: `test_default_cfg_has_repo_and_target_branch`; `test_gitignore_created_in_git_repo` (make `tmp_path/.git`, call `config.save_cfg({})`, assert `.gitignore` contains `.config/`); `test_gitignore_appended_when_exists` (existing `.gitignore` with `node_modules/`, assert both lines); `test_gitignore_not_created_outside_git_repo` (no `.git`, assert no `.gitignore`).
- [ ] **Step 2: Run** `pytest tests/test_config.py -v`. Expected: FAIL (keys missing; gitignore not created).
- [ ] **Step 3: Implement** the two keys in `DEFAULT_CFG`; rewrite `_ensure_gitignore() -> None` to do nothing without `.git`, create the file with `.config/\n` if missing, else append when `.config/` is absent. In `cmd_configure` add `("repo", "Azure Repos repository name")` and `("target_branch", "PR target branch (default main)")` to `fields`.
- [ ] **Step 4: Run** `pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: Add repo and target_branch config and always ignore .config/"`

### Task 2: Bug API helpers

**Files:**
- Modify: `azdo_daily/azdo.py` (add after `get_my_stories`; extract `_assignee_clause(cfg) -> str` from `get_my_stories` and reuse it)
- Test: `tests/test_azdo_bugs.py` (create)

**Interfaces:**
- Produces:
  - `get_my_bugs(sess, cfg) -> list[dict]`: WIQL `WorkItemType = 'Bug'`, assignee clause, state not in `('Closed','Removed')`, ordered by priority; returns work items with fields `System.Id, System.Title, System.State, Microsoft.VSTS.Common.Priority, Microsoft.VSTS.Common.Severity`.
  - `get_bug(sess, cfg, bug_id: int) -> dict` with keys `id, title, state, severity, repro_steps, comments (list of {author, text}), attachments (list of urls)`; reads `Microsoft.VSTS.TCM.ReproSteps`, `$expand=relations` for `AttachedFile` links, and `GET {wit}/workitems/{id}/comments?api-version=7.1-preview.3`.
  - `pick_state(sess, cfg, work_item_type: str, categories: tuple[str, ...]) -> str`: `GET {wit}/workitemtypes/{type}/states?api-version=7.1`, returns the first state whose `category` is in `categories`; raises `ValueError(f"No {categories} state for {type}; available: {names}")`.
  - Constants `IN_PROGRESS = ("InProgress",)`, `RESOLVED = ("Resolved", "Completed")`.

- [ ] **Step 1: Write failing tests** with a `MagicMock` session like `tests/test_azdo_hours.py`: `test_get_my_bugs_query_filters_bug_type_and_open_states` (assert the posted WIQL contains `'Bug'` and `NOT IN ('Closed','Removed')`); `test_get_my_bugs_rejects_quote_in_assignee` (`pytest.raises(ValueError)`); `test_get_my_bugs_empty_returns_empty_list`; `test_get_bug_missing_repro_and_attachments` (fields absent, `relations` absent, assert `repro_steps == ""` and `attachments == []`); `test_get_bug_collects_attachments_and_comments`; `test_pick_state_by_category` (states `[{"name":"Active","category":"InProgress"},...]` returns `"Active"`); `test_pick_state_no_match_lists_available` (match on the available names in the message).
- [ ] **Step 2: Run** `pytest tests/test_azdo_bugs.py -v`. Expected: FAIL (functions not defined).
- [ ] **Step 3: Implement** the functions above in `azdo.py`, following `get_my_stories` for WIQL then batch-fetch; raise `requests.HTTPError` via `raise_for_status()` as existing code does.
- [ ] **Step 4: Run** `pytest -q`. Expected: all pass (existing `get_my_stories` tests unchanged).
- [ ] **Step 5: Commit** `git commit -am "feat: Add bug queries and state lookup by category"` plus `git add tests/test_azdo_bugs.py`.

### Task 3: Bug commands and routing

**Files:**
- Create: `azdo_daily/bugs.py`
- Modify: `azdo_daily/main.py` (subparsers `bugs`, `bug` with sub-subcommands `show`, `start`, `resolve`)
- Test: `tests/test_cmd_bugs.py` (create)

**Interfaces:**
- Consumes: Task 2 functions, `config.load_cfg`, `config.require_cfg(cfg, "org", "project", "pat")`, `azdo.set_workitem_state`, `azdo.add_comment`.
- Produces: `cmd_bugs(args)`, `cmd_bug_show(args)`, `cmd_bug_start(args)`, `cmd_bug_resolve(args)` where `args` has `json: bool`, plus `id: int` and `comment: str` for the last three. `_emit(data, as_json)` prints `json.dumps(data, indent=2)` when `as_json`; otherwise human lines with `[Bug]` prefix. In `--json` mode nothing else is written to stdout; errors go to stderr via `ui.err`, then `sys.exit(1)`.
- JSON shapes: `bugs` -> `[{"id","title","state","priority","severity"}]`; `bug show` -> `get_bug` dict; `start`/`resolve` -> `{"id","state"}`.

- [ ] **Step 1: Write failing tests** patching `azdo_daily.bugs.azdo` and `azdo_daily.bugs.config` like `tests/test_cmd_hours.py`: `test_bugs_json_is_pure_json` (`json.loads(capsys.readouterr().out)` works and equals the expected list); `test_bugs_human_output_prefixes_bug_type`; `test_bug_start_sets_in_progress_state_from_category` (assert `pick_state` called with `("InProgress",)` and `set_workitem_state` with the returned name); `test_bug_resolve_adds_comment_then_sets_resolved_state`; `test_bugs_http_error_exits_1_and_prints_status_to_stderr` (HTTP 401, `SystemExit` code 1, `"401"` in stderr, stdout empty).
- [ ] **Step 2: Run** `pytest tests/test_cmd_bugs.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `bugs.py` and the argparse routing. `bug` takes a required sub-subcommand; `--json` on each; `bug resolve` takes `--comment` (required). Route through the dispatch dict in `main()` (use a nested key such as `args.bug_cmd`).
- [ ] **Step 4: Run** `pytest -q` and `azdo-daily bugs --help`. Expected: tests pass; help lists the options.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: Add bugs and bug show/start/resolve commands"`

### Task 4: Azure Repos PR API

**Files:**
- Create: `azdo_daily/git.py`
- Test: `tests/test_git_api.py` (create)

**Interfaces:**
- Produces (all use `sess` and `cfg`, base `https://dev.azure.com/{org}/{project}/_apis/git/repositories/{repo}` with url-quoting like `wit_base`; `api-version=7.1`):
  - `repo_base(cfg) -> str` (raises `ValueError` if `cfg["repo"]` is empty).
  - `create_pr(sess, cfg, source: str, target: str, title: str, description: str, bug_ids: list[int]) -> dict` returning `{"id": int, "url": str}`; posts `sourceRefName=refs/heads/<source>`, `targetRefName=refs/heads/<target>`, `workItemRefs=[{"id": str(i)}]`.
  - `get_active_threads(sess, cfg, pr_id: int) -> list[dict]` returning `{"id","file","line","comments":[{"author","text"}]}` for threads whose status is `active` and that have at least one non-deleted text comment; `file`/`line` are `None` without `threadContext`.
  - `reply_thread(sess, cfg, pr_id: int, thread_id: int, text: str, resolve: bool) -> None`: posts the comment (`parentCommentId` 1), then PATCHes thread `status` to `"fixed"` when `resolve`.

- [ ] **Step 1: Write failing tests** with a `MagicMock` session: `test_create_pr_payload_refs_and_work_items`; `test_repo_base_requires_repo`; `test_active_threads_filters_non_active`; `test_active_threads_without_file_context_has_none_file`; `test_active_threads_skips_deleted_comments`; `test_reply_thread_resolve_patches_status_fixed`; `test_reply_thread_without_resolve_does_not_patch`.
- [ ] **Step 2: Run** `pytest tests/test_git_api.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** the three functions plus `repo_base`; thread JSON fields used: `status`, `comments[].content`, `comments[].isDeleted`, `comments[].author.displayName`, `threadContext.filePath`, `threadContext.rightFileStart.line`.
- [ ] **Step 4: Run** `pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: Add Azure Repos pull request API calls"`

### Task 5: PR commands and routing

**Files:**
- Create: `azdo_daily/prs.py`
- Modify: `azdo_daily/main.py` (subparser `pr` with `create`, `comments`, `reply`)
- Test: `tests/test_cmd_prs.py` (create)

**Interfaces:**
- Consumes: Task 4 functions, `config.require_cfg(cfg, "org", "project", "pat", "repo")`.
- Produces: `cmd_pr_create(args)` (`bugs: str`, `title: str`, `json: bool`), `cmd_pr_comments(args)` (`pr: int`, `json`), `cmd_pr_reply(args)` (`pr`, `thread`, `text`, `resolve: bool`, `json`); `current_branch() -> str` (`git rev-parse --abbrev-ref HEAD`) and `branch_on_origin(branch: str) -> bool` (`git ls-remote --exit-code --heads origin <branch>`), both via `subprocess.run`, stderr suppressed.
- `pr create` target is `cfg["target_branch"] or "main"`; description lists each bug id and title from `get_bug`; JSON `{"id","url"}`.

- [ ] **Step 1: Write failing tests** patching `azdo_daily.prs.git_api`, `azdo_daily.prs.config`, `azdo_daily.prs.current_branch` and `azdo_daily.prs.branch_on_origin`: `test_pr_create_refuses_target_branch` (exit 1, `create_pr` not called); `test_pr_create_refuses_unpushed_branch` (exit 1, `create_pr` not called, message mentions push); `test_pr_create_links_bugs_and_prints_json`; `test_pr_create_parses_bug_ids_list` (`"1, 2,3"` -> `[1,2,3]`; non-numeric exits 1); `test_pr_comments_json_pure`; `test_pr_reply_passes_resolve_flag`.
- [ ] **Step 2: Run** `pytest tests/test_cmd_prs.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `prs.py` and the `pr` routing; same `_emit`/stderr/exit-code convention as `bugs.py` (import `_emit` from `bugs.py` rather than duplicating).
- [ ] **Step 4: Run** `pytest -q` and `azdo-daily pr --help`. Expected: tests pass; help lists `create`, `comments`, `reply`.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: Add pr create, comments and reply commands"`

### Task 6: Docs and version

**Files:**
- Modify: `pyproject.toml` (`version = "1.8.0"`), `CHANGELOG.md` (1.8.0 entry), `CLAUDE.md` (commands table rows, architecture lines for `bugs.py`, `prs.py`, `git.py`), `README.md` (commands section, one short block on the new commands and the two config keys)

- [ ] **Step 1: Make the four edits**, keeping the existing formats.
- [ ] **Step 2: Run** `pytest -q` and `black --check --line-length 88 azdo_daily tests`. Expected: pass.
- [ ] **Step 3: Commit** `git commit -am "chore: Bump version to 1.8.0"` (split docs and bump into two commits if the docs diff is large).

### Task 7: flutter-mod prompt section

**Files (repo `~/.claude/dev-mods/flutter-skills`):**
- Modify: `hooks/register.tsx` (new constant `AZURE_BUGS` before `const TRACKER`; add `{ id: 'azure-bugs', text: AZURE_BUGS, scope: 'session' }` after the `task-tracker` entry), `.claude-plugin/plugin.json` (version `0.10.0`)

**Interfaces:**
- Consumes: the Azdo-Daily command names and JSON shapes from Tasks 3 and 5.

- [ ] **Step 1: Write `AZURE_BUGS`** with no backtick and no `${` inside the template literal, covering spec items 1 to 7 (run from the project root; missing `.config/settings.json` means ask the user to run azdo-daily configure; create vault notes through the task tracker rule; one branch bugfix/azdo-YYYY-MM-DD; per bug `bug show`, discuss, `bug start`, fix, analyze and tests, MobAI or webapp-testing, one commit referencing AB#id, `bug resolve`; skip bugs already Resolved or Done; push and `pr create` only on the user's go-ahead; review loop with `pr comments`, fix, test, commit, push, `pr reply --resolve`; discuss unclear comments first).
- [ ] **Step 2: Run** `claude plugin validate .` in the mod repo. Expected: validation passed (a parse error means a stray backtick).
- [ ] **Step 3: Verify headlessly** with `claude -p --plugin-dir <mod>` from a temp folder: ask where a PR comment fix ends up and which command lists active threads. Expected: the answer names `azdo-daily pr comments`, a commit and `pr reply --resolve`.
- [ ] **Step 4: Commit** the prompt and the version bump as two commits (`feat: Add Azure bugs and PR review loop prompt`, `Bump to 0.10.0`), sync the session copy with rsync as before.

## Manual check after Task 7

In a real project: `azdo-daily configure` (include repo and target branch), `azdo-daily doctor`, `azdo-daily bugs --json`, then one bug through `start`, a throwaway branch and `pr create`. This is the only test against real Azure; the state-category lookup and the thread status `fixed` are the likeliest to need a tweak.
