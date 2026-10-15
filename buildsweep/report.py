"""Output formatting: a terminal table and JSON."""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from typing import IO, Dict, List, Optional, Sequence

from .scanner import Artifact


def human_size(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024 or unit == "TiB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"  # unreachable


def human_age(days: float) -> str:
    if days < 1:
        return "today"
    if days < 60:
        return f"{int(days)}d"
    if days < 730:
        return f"{int(days / 30.44)}mo"
    return f"{days / 365.25:.1f}y"


def display_path(path: str) -> str:
    """Abbreviate the home directory to ~."""
    home = os.path.expanduser("~")
    if home and home != "~" and (path == home or path.startswith(home + os.sep)):
        return "~" + path[len(home):]
    return path


def by_ecosystem(artifacts: Sequence[Artifact]) -> Dict[str, Dict[str, int]]:
    totals: Dict[str, Dict[str, int]] = defaultdict(lambda: {"folders": 0, "bytes": 0})
    for a in artifacts:
        t = totals[a.rule.ecosystem]
        t["folders"] += 1
        t["bytes"] += a.size
    return dict(sorted(totals.items(), key=lambda kv: -kv[1]["bytes"]))


def summary(artifacts: Sequence[Artifact]) -> dict:
    return {
        "folders": len(artifacts),
        "reclaimable_bytes": sum(a.size for a in artifacts),
        "by_ecosystem": by_ecosystem(artifacts),
    }


def write_text(artifacts: Sequence[Artifact], out: IO[str], *, limit: int = 0,
               hidden_count: int = 0, numbered: bool = False,
               now: Optional[float] = None) -> None:
    now = now or time.time()
    shown = artifacts[:limit] if limit else artifacts
    if not artifacts:
        out.write("No build or dependency folders matched.\n")
    else:
        prefix_w = len(str(len(shown))) + 3 if numbered else 0
        out.write(" " * prefix_w + f"{'SIZE':>10}  {'IDLE':>6}  {'TYPE':<10}  PATH\n")
        for i, a in enumerate(shown, 1):
            prefix = f"[{i}]".rjust(prefix_w - 1) + " " if numbered else ""
            out.write(f"{prefix}{human_size(a.size):>10}  {human_age(a.age_days(now)):>6}  "
                      f"{a.rule.ecosystem:<10}  {display_path(a.path)}\n")
        if limit and len(artifacts) > limit:
            out.write(f"... and {len(artifacts) - limit} smaller folders (use --limit 0 to show all)\n")

        out.write("\n")
        parts = [f"{eco} {human_size(t['bytes'])}" for eco, t in by_ecosystem(artifacts).items()]
        out.write("By type: " + ", ".join(parts) + "\n")
        total = sum(a.size for a in artifacts)
        out.write(f"Found {len(artifacts)} folder{'s' if len(artifacts) != 1 else ''}, "
                  f"{human_size(total)} reclaimable.\n")
    if hidden_count:
        out.write(f"({hidden_count} more did not pass --older-than / --min-size.)\n")


def write_json(artifacts: Sequence[Artifact], out: IO[str], *, results=None,
               now: Optional[float] = None) -> None:
    now = now or time.time()
    status = {id(r.artifact): r for r in results or []}
    items: List[dict] = []
    for a in artifacts:
        item = {
            "path": a.path,
            "project": a.project,
            "ecosystem": a.rule.ecosystem,
            "bytes": a.size,
            "files": a.files,
            "last_active": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(a.last_active)),
            "idle_days": round(a.age_days(now), 1),
            "restore": a.rule.restore,
        }
        r = status.get(id(a))
        if r is not None:
            item["result"] = {"ok": r.ok, "message": r.message}
        items.append(item)
    json.dump({"summary": summary(artifacts), "artifacts": items}, out, indent=2)
    out.write("\n")
