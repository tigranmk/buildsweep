"""Removing artifact folders: move to the Trash, or delete permanently.

Every removal is re-checked right before it happens: the folder must still
exist, still be a real directory (not a symlink), and its rule must still
apply. A scan can be minutes old by the time the user confirms.

The macOS Trash path talks to Finder (so "Put Back" works), the same
approach twinsweep uses; elsewhere it uses the optional Send2Trash package
(BSD-3-Clause).
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

from .scanner import Artifact

ACTIONS = ("report", "trash", "delete")
NO_FINDER_ENV = "BUILDSWEEP_NO_FINDER"
FINDER_BATCH = 50


@dataclass
class ActionResult:
    artifact: Artifact
    ok: bool
    message: str


class ActionError(Exception):
    pass


def precheck(a: Artifact) -> Optional[str]:
    """Return a reason to skip `a`, or None if it is still safe to remove."""
    try:
        st = os.lstat(a.path)
    except OSError:
        return "no longer exists"
    if not stat.S_ISDIR(st.st_mode):
        return "no longer a directory"
    try:
        siblings = set(os.listdir(a.project))
    except OSError as exc:
        return f"cannot read project folder: {exc.strerror or exc}"
    if not a.rule.applies(a.path, siblings):
        return "project markers changed since the scan"
    return None


def _make_writable_and_retry(func, path, exc):
    # Read-only files (common in Go module caches and git objects) block
    # rmtree. Removing an entry needs write access to its *parent* folder,
    # and on Windows the entry itself must be writable: fix both, retry once.
    rwx = stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC
    try:
        os.chmod(os.path.dirname(path), rwx)
        if not os.path.islink(path):
            os.chmod(path, rwx)
        func(path)
    except OSError:
        raise exc


def delete(path: str) -> str:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_make_writable_and_retry)
    else:  # pragma: no cover - Python < 3.12
        shutil.rmtree(path, onerror=lambda f, p, info: _make_writable_and_retry(f, p, info[1]))
    return "deleted"


# --- Trash -------------------------------------------------------------------

# Paths arrive as argv items, never interpolated into the script, so no folder
# name can alter the AppleScript.
_FINDER_SCRIPT = """
on run argv
    set targets to {}
    repeat with p in argv
        set end of targets to (POSIX file (contents of p)) as alias
    end repeat
    tell application "Finder" to delete targets
end run
"""


def finder_available() -> bool:
    return (sys.platform == "darwin" and not os.environ.get(NO_FINDER_ENV)
            and shutil.which("osascript") is not None)


def finder_trash(paths: Sequence[str]) -> Optional[str]:
    """Ask Finder to trash `paths`. Returns an error message or None.

    Callers must check which paths are actually gone: Finder can fail part
    way through a batch.
    """
    try:
        proc = subprocess.run(["osascript", "-e", _FINDER_SCRIPT, "--", *paths],
                              capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)
    if proc.returncode != 0:
        msg = proc.stderr.strip() or f"osascript exited with {proc.returncode}"
        if "-1743" in msg:  # errAEEventNotPermitted
            return ("macOS blocked control of Finder; allow it in System Settings > "
                    "Privacy & Security > Automation")
        return msg
    return None


def _unique_path(path: str) -> str:
    if not os.path.lexists(path):
        return path
    n = 1
    while os.path.lexists(f"{path} ({n})"):
        n += 1
    return f"{path} ({n})"


def trash_one(path: str) -> str:
    """Trash a single folder without Finder."""
    try:
        from send2trash import send2trash  # optional, BSD-3-Clause
    except ImportError:
        send2trash = None
    if send2trash is not None:
        send2trash(path)
        return "moved to trash"
    if sys.platform == "darwin":
        dest = _unique_path(os.path.join(os.path.expanduser("~/.Trash"), os.path.basename(path)))
        shutil.move(path, dest)
        return f"moved to {dest}"
    raise ActionError("trash needs the optional 'send2trash' package on this OS "
                      "(pip install send2trash), or use --action delete")


# --- driver ------------------------------------------------------------------

def apply_all(
    artifacts: Sequence[Artifact],
    action: str,
    *,
    dry_run: bool = False,
    on_result: Optional[Callable[[ActionResult], None]] = None,
) -> List[ActionResult]:
    """Apply `action` to every artifact and return one result each."""
    if action not in ("trash", "delete"):
        raise ValueError(f"not a removal action: {action}")
    results: List[ActionResult] = []

    def emit(r: ActionResult) -> None:
        results.append(r)
        if on_result:
            on_result(r)

    ready: List[Artifact] = []
    for a in artifacts:
        reason = precheck(a)
        if reason:
            emit(ActionResult(a, False, f"skipped: {reason}"))
        elif dry_run:
            emit(ActionResult(a, True, f"would {action}"))
        else:
            ready.append(a)

    if action == "trash" and finder_available():
        ready = _trash_via_finder(ready, emit)

    for a in ready:
        try:
            msg = delete(a.path) if action == "delete" else trash_one(a.path)
            emit(ActionResult(a, True, msg))
        except (OSError, ActionError, shutil.Error) as exc:
            emit(ActionResult(a, False, f"failed: {exc}"))
    return results


def _trash_via_finder(ready: List[Artifact], emit) -> List[Artifact]:
    """Trash in batches through Finder; return the artifacts still left to
    handle (all of them if Finder refuses outright)."""
    leftover: List[Artifact] = []
    for i in range(0, len(ready), FINDER_BATCH):
        batch = ready[i:i + FINDER_BATCH]
        err = finder_trash([a.path for a in batch])
        trashed_any = False
        for a in batch:
            if os.path.lexists(a.path):
                leftover.append(a)
            else:
                trashed_any = True
                emit(ActionResult(a, True, "moved to Trash (Finder)"))
        if err and i == 0 and not trashed_any:
            # Finder refused outright (no permission, no GUI session): stop asking.
            sys.stderr.write(f"buildsweep: Finder unavailable ({err}); using fallback\n")
            return leftover + list(ready[len(batch):])
    return leftover
