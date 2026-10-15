"""Walk directory trees and collect artifact folders with size and activity.

One recursive pass does three things:
  * finds artifact folders (see rules.py) without descending into them,
    so nested node_modules are counted once, as part of their parent;
  * measures each artifact's disk usage;
  * records, for every directory, the newest modification time of the
    *source* files below it (artifacts and .git excluded). That is the
    "last active" date of the project that owns an artifact.
"""

from __future__ import annotations

import fnmatch
import os
import stat
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional, Sequence, Set, Tuple

from .rules import RULES, Rule, match

# Version-control and editor folders: never artifacts, never scanned for
# activity (a `git fetch` should not make a project look recently edited).
SKIP_DIRS = {".git", ".hg", ".svn", ".idea", ".vscode"}

# Huge system folders that hold no projects. They are skipped when reached
# from above (scanning ~), but scanned normally when given as a root. Known
# artifact locations inside them are still checked directly.
_HOME = os.path.expanduser("~")
SKIP_PATHS = {os.path.join(_HOME, "Library"), os.path.join(_HOME, ".Trash")}
KNOWN_ARTIFACTS = [os.path.join(_HOME, "Library", "Developer", "Xcode", "DerivedData")]


@dataclass
class Artifact:
    path: str
    rule: Rule
    size: int           # bytes on disk
    files: int
    last_active: float  # newest source mtime in the owning project (epoch seconds)

    @property
    def project(self) -> str:
        return os.path.dirname(self.path)

    def age_days(self, now: Optional[float] = None) -> float:
        return ((now or time.time()) - self.last_active) / 86400


@dataclass
class ScanResult:
    artifacts: List[Artifact] = field(default_factory=list)
    dirs_scanned: int = 0
    errors: List[Tuple[str, str]] = field(default_factory=list)  # (path, message)


def disk_usage(entry_stat: os.stat_result) -> int:
    """Bytes actually allocated, falling back to logical size (Windows)."""
    blocks = getattr(entry_stat, "st_blocks", None)
    return blocks * 512 if blocks is not None else entry_stat.st_size


def measure(path: str, seen_inodes: Set[Tuple[int, int]],
            errors: Optional[List[Tuple[str, str]]] = None) -> Tuple[int, int]:
    """Return (bytes, files) under `path`, never following symlinks.

    Hard-linked files (pnpm, uv and some build tools use them) are counted
    once per scan via `seen_inodes`, so totals don't promise space that
    deleting would not free.
    """
    total = files = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                entries = list(it)
        except OSError as exc:
            if errors is not None:
                errors.append((current, exc.strerror or str(exc)))
            continue
        for e in entries:
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISDIR(st.st_mode):
                stack.append(e.path)
                continue
            if st.st_nlink > 1:
                key = (st.st_dev, st.st_ino)
                if key in seen_inodes:
                    continue
                seen_inodes.add(key)
            total += disk_usage(st)
            files += 1
    return total, files


def _known_inside(skipped: str, rules: Sequence[Rule]) -> List[Tuple[str, Rule, Optional[float]]]:
    """Artifacts at well-known locations inside a skipped system folder.

    They have no project around them, so their activity is the newest mtime
    of their direct entries (Xcode touches a project's folder on each build).
    """
    hits: List[Tuple[str, Rule, Optional[float]]] = []
    for path in KNOWN_ARTIFACTS:
        if path.startswith(skipped + os.sep) and os.path.isdir(path) and not os.path.islink(path):
            rule = match(path, (), rules)
            if rule is not None:
                try:
                    with os.scandir(path) as it:
                        mtimes = [e.stat(follow_symlinks=False).st_mtime for e in it]
                except OSError:
                    mtimes = []
                hits.append((path, rule, max(mtimes, default=os.stat(path).st_mtime)))
    return hits


def _excluded(path: str, name: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(path, p) for p in patterns)


def scan(
    roots: Iterable[str],
    *,
    rules: Sequence[Rule] = RULES,
    exclude: Sequence[str] = (),
    hidden: bool = False,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> ScanResult:
    """Find artifacts under each root. `on_progress(dirs, artifacts)` is
    called periodically for a progress display."""
    result = ScanResult()
    seen_inodes: Set[Tuple[int, int]] = set()
    seen_paths: Set[str] = set()

    def walk(directory: str) -> float:
        """Scan `directory`; return newest source-file mtime beneath it."""
        result.dirs_scanned += 1
        if on_progress and result.dirs_scanned % 200 == 0:
            on_progress(result.dirs_scanned, len(result.artifacts))
        try:
            with os.scandir(directory) as it:
                entries = list(it)
        except OSError as exc:
            result.errors.append((directory, exc.strerror or str(exc)))
            return 0.0

        siblings = {e.name for e in entries}
        newest = 0.0
        found: List[Tuple[str, Rule, Optional[float]]] = []
        for e in entries:
            if _excluded(e.path, e.name, exclude):
                continue
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            if not stat.S_ISDIR(st.st_mode):
                if stat.S_ISREG(st.st_mode):
                    newest = max(newest, st.st_mtime)
                continue  # symlinks to directories are deliberately not followed
            if e.name in SKIP_DIRS:
                continue
            if e.path in SKIP_PATHS:
                found.extend(_known_inside(e.path, rules))
                continue
            rule = match(e.path, siblings, rules)
            if rule is not None:
                # A folder that is itself a repository is someone's work, not output.
                if not os.path.lexists(os.path.join(e.path, ".git")):
                    found.append((e.path, rule, None))
                continue
            if e.name.startswith(".") and not hidden:
                continue
            newest = max(newest, walk(e.path))

        # The owning project's activity is known only after its siblings are
        # walked, so artifacts are recorded last.
        for path, rule, active in found:
            size, files = measure(path, seen_inodes, result.errors)
            result.artifacts.append(Artifact(path, rule, size, files, newest if active is None else active))
        return newest

    for root in roots:
        root = os.path.abspath(os.path.expanduser(root))
        if root in seen_paths:
            continue
        seen_paths.add(root)
        if not os.path.isdir(root):
            result.errors.append((root, "not a directory"))
            continue
        walk(root)

    # Inherit activity upwards where needed: an artifact in a folder holding
    # no source files of its own (rare) reports 0; fall back to the folder's
    # own mtime so it doesn't look infinitely old.
    for a in result.artifacts:
        if a.last_active == 0.0:
            try:
                a.last_active = os.stat(a.project).st_mtime
            except OSError:
                pass
    result.artifacts.sort(key=lambda a: (-a.size, a.path))
    return result
