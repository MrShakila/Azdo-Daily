"""Pull request commands: create, list review comments and reply."""

import subprocess

from azdo_daily import azdo, config, ui
from azdo_daily import git as git_api
from azdo_daily.bugs import _emit, _fail, _guard


def current_branch() -> str:
    """Name of the checked-out git branch."""
    out = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def branch_on_origin(branch: str) -> bool:
    """True when the branch exists on the origin remote."""
    out = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--heads", "origin", branch],
        capture_output=True,
        text=True,
    )
    return out.returncode == 0


def _session():
    cfg = config.load_cfg()
    config.require_cfg(cfg, "org", "project", "pat", "repo")
    return azdo.session(cfg), cfg


def _parse_ids(raw: str) -> list:
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if not part.isdigit():
            _fail(f"Bug id must be a number, got: {part or '(empty)'}")
        ids.append(int(part))
    return ids


def cmd_pr_create(args):
    """Open one PR for the current branch, linking the bugs."""
    sess, cfg = _session()
    ids = _parse_ids(args.bugs)
    target = cfg.get("target_branch") or "main"
    branch = current_branch()
    if branch == target:
        _fail(f"Current branch is the target branch ({target}); use a fix branch.")
    if not branch_on_origin(branch):
        _fail(f"Branch {branch} is not on origin; push it first.")

    def run():
        lines = [f"- #{i} {azdo.get_bug(sess, cfg, i)['title']}" for i in ids]
        description = "Fixes:\n" + "\n".join(lines)
        return git_api.create_pr(
            sess, cfg, branch, target, args.title, description, ids
        )

    pr = _guard(run)
    _emit(pr, args.json, lambda: ui.ok(f"PR #{pr['id']}: {pr['url']}"))


def cmd_pr_comments(args):
    """List active review threads on a PR."""
    sess, cfg = _session()
    threads = _guard(lambda: git_api.get_active_threads(sess, cfg, args.pr))

    def human():
        if not threads:
            ui.warn("No active review threads.")
        for t in threads:
            where = f"{t['file']}:{t['line']}" if t["file"] else "general"
            print(f"  Thread {t['id']} ({where})")
            for c in t["comments"]:
                print(f"    {c['author']}: {c['text']}")

    _emit(threads, args.json, human)


def cmd_pr_reply(args):
    """Reply to a review thread, optionally resolving it."""
    sess, cfg = _session()
    _guard(
        lambda: git_api.reply_thread(
            sess, cfg, args.pr, args.thread, args.text, args.resolve
        )
    )
    _emit(
        {"pr": args.pr, "thread": args.thread, "resolved": args.resolve},
        args.json,
        lambda: ui.ok(f"Replied on thread {args.thread}"),
    )
