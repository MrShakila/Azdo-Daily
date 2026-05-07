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
    """Add .config/ to .gitignore if git repo exists."""
    git_root = Path.cwd() / ".gitignore"
    if not git_root.exists():
        return
    content = git_root.read_text()
    if ".config/" not in content:
        git_root.write_text(content.rstrip() + "\n.config/\n")


def require_cfg(cfg: dict, *keys: str):
    """Exit if any required config keys are missing."""
    missing = [k for k in keys if not cfg.get(k)]
    if missing:
        ui.err(f"Missing config: {', '.join(missing)}")
        ui.info("Run:  azdo-daily configure")
        sys.exit(1)
