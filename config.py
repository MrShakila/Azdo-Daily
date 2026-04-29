"""Configuration management for Azure DevOps Daily."""

import json
import sys
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"

DEFAULT_CFG = {
    "org": "",
    "project": "",
    "pat": "",
    "anthropic_api_key": "",
    "assigned_to": "",
    "area_path": "",
    "close_state": "Closed",
}


def load_cfg() -> dict:
    """Load config from file or create with defaults."""
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CFG, indent=2))
    cfg = {**DEFAULT_CFG, **json.loads(CONFIG_FILE.read_text())}
    return cfg


def save_cfg(cfg: dict):
    """Save config to file."""
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def require_cfg(cfg: dict, *keys: str):
    """Exit if any required config keys are missing."""
    from ui import err, info

    missing = [k for k in keys if not cfg.get(k)]
    if missing:
        err(f"Missing config: {', '.join(missing)}")
        info("Run:  python main.py configure")
        sys.exit(1)
