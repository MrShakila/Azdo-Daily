"""Configuration management for Azure DevOps Daily."""

import json
import sys
from pathlib import Path

from azdo_daily import ui

CONFIG_DIR = Path.cwd() / ".config"
CONFIG_FILE = CONFIG_DIR / "settings.json"

DEFAULT_CFG = {
    "org": "",
    "project": "",
    "pat": "",
    "anthropic_api_key": "",
    "assigned_to": "",
    "area_path": "",
    "repo": "",
    "target_branch": "main",
    "task_templates": [
        {"title": "UI", "priority": 2, "effort": None},
        {"title": "Logic", "priority": 2, "effort": None},
        {"title": "Unit Test", "priority": 3, "effort": None},
    ],
}


def load_cfg() -> dict:
    """Load config from file or create with defaults."""
    CONFIG_DIR.mkdir(exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CFG, indent=2))
    cfg = {**DEFAULT_CFG, **json.loads(CONFIG_FILE.read_text())}
    return cfg


def save_cfg(cfg: dict):
    """Save config to file and ensure .config/ is in .gitignore."""
    CONFIG_DIR.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    _ensure_gitignore()


def _ensure_gitignore():
    """Make sure .config/ is ignored when the current folder is a git repo."""
    cwd = Path.cwd()
    if not (cwd / ".git").exists():
        return
    ignore = cwd / ".gitignore"
    content = ignore.read_text() if ignore.exists() else ""
    if ".config/" not in content:
        ignore.write_text((content.rstrip() + "\n" if content else "") + ".config/\n")


def require_cfg(cfg: dict, *keys: str):
    """Exit if any required config keys are missing."""
    missing = [k for k in keys if not cfg.get(k)]
    if missing:
        ui.err(f"Missing config: {', '.join(missing)}")
        ui.info("Run:  azdo-daily configure")
        sys.exit(1)
