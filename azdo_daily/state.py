"""Daily state management for tasks and stories."""

import json
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).parent
STATE_DIR = BASE_DIR / "state"

DEFAULT_STATE = {"stories": [], "tasks": []}


def today_file(date_str: str = None) -> Path:
    """Get path to state file for given date (default: today)."""
    STATE_DIR.mkdir(exist_ok=True)
    if date_str is None:
        date_str = date.today().isoformat()
    return STATE_DIR / f"{date_str}.json"


def load_state(date_str: str = None) -> dict:
    """Load state for given date (default: today)."""
    f = today_file(date_str)
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


def save_state(st: dict, date_str: str = None):
    """Save state for given date (default: today)."""
    today_file(date_str).write_text(json.dumps(st, indent=2))
