"""Terminal UI helpers: colors, prompts, formatting."""

import re
import sys
from typing import Optional

# Color codes
R = "\033[0m"
B = "\033[1m"
DIM = "\033[2m"
GR = "\033[32m"
YL = "\033[33m"
BL = "\033[34m"
CY = "\033[36m"
RD = "\033[31m"
MG = "\033[35m"


def ok(msg):
    print(f"  {GR}✔{R}  {msg}")


def err(msg):
    print(f"  {RD}✖{R}  {msg}", file=sys.stderr)


def info(msg):
    print(f"  {BL}→{R}  {msg}")


def warn(msg):
    print(f"  {YL}!{R}  {msg}")


def hdr(msg):
    print(f"\n{B}{CY}{msg}{R}")


def sep():
    print(f"  {DIM}{'─'*58}{R}")


def ask(prompt, default=None):
    """Interactive input with optional default."""
    hint = f" [{default}]" if default is not None else ""
    val = input(f"  {MG}?{R}  {prompt}{hint}: ").strip()
    return val if val else (str(default) if default is not None else "")


def parse_selection(raw: str, max_n: int) -> list[int]:
    """Parse '1,3,5' or '1-3' or '2' into 0-based indices."""
    indices = set()
    for part in raw.split(","):
        part = part.strip()
        m = re.match(r"^(\d+)-(\d+)$", part)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            indices.update(range(lo - 1, hi))
        elif part.isdigit():
            indices.add(int(part) - 1)
    return sorted(i for i in indices if 0 <= i < max_n)


def select_from_list(items: list, prompt: str = "Select items") -> list:
    """Interactive selection with 'all' support. Returns selected items."""
    if not items:
        return []
    raw = ask(f"{prompt} (e.g. 1  or  1,3  or  1-3  or  all)", "all")
    if raw.strip().lower() == "all":
        return items
    indices = parse_selection(raw, len(items))
    if not indices:
        return []
    return [items[i] for i in indices]


def float_or_none(s: str) -> Optional[float]:
    """Convert string to float or None."""
    try:
        return float(s) if s else None
    except ValueError:
        return None


def print_stories(stories: list[dict]):
    """Print formatted story list with priority colors."""
    sep()
    prio_col = {1: RD, 2: YL, 3: CY, 4: DIM}
    for i, s in enumerate(stories, 1):
        fields = s.get("fields", {})
        title = fields.get("System.Title", "(no title)")
        state = fields.get("System.State", "?")
        prio = int(fields.get("Microsoft.VSTS.Common.Priority", 2))
        pc = prio_col.get(prio, "")
        print(f"  {B}{i:>2}.{R}  {title}  " f"{pc}[P{prio}]{R}  {DIM}{state}{R}")
    sep()


def print_tasks(tasks: list[dict], show_index=True):
    """Print formatted task list with details."""
    sep()
    prio_label = {1: "Critical", 2: "High", 3: "Medium", 4: "Low"}
    for i, t in enumerate(tasks, 1):
        pfx = f"{B}{i:>2}.{R}  " if show_index else "      "
        print(f"  {pfx}{t['title']}")
        if t.get("description"):
            print(f"       {DIM}{t['description'][:80]}{R}")
        detail = []
        if t.get("effort"):
            detail.append(f"{t['effort']}h")
        if t.get("priority"):
            detail.append(f"P{t['priority']} {prio_label.get(int(t['priority']), '')}")
        if t.get("tags"):
            detail.append(t["tags"])
        if detail:
            print(f"       {DIM}{' · '.join(detail)}{R}")
    sep()
