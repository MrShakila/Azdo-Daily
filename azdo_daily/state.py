"""Daily state management for tasks and stories."""

import json
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"

DEFAULT_STATE = {"stories": [], "tasks": []}


def today_file() -> Path:
    """Get path to today's state file."""
    STATE_DIR.mkdir(exist_ok=True)
    return STATE_DIR / f"{date.today().isoformat()}.json"


def load_state() -> dict:
    """Load today's state, defaulting to empty."""
    f = today_file()
    if f.exists():
        try:
            data = json.loads(f.read_text())
            if isinstance(data, list):
                return {**DEFAULT_STATE, "tasks": data}
            return {**DEFAULT_STATE, **data}
        except (json.JSONDecodeError, ValueError):
            # Malformed JSON, return empty state
            return dict(DEFAULT_STATE)
    return dict(DEFAULT_STATE)


def save_state(st: dict):
    """Save state to today's file."""
    today_file().write_text(json.dumps(st, indent=2))
