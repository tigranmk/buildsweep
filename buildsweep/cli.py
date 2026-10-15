"""Command-line interface."""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from typing import List, Optional, Sequence

from . import __version__
from .actions import ACTIONS, ActionResult, apply_all
from .html_report import write_html
from .report import display_path, human_size, write_json, write_text
from .rules import ECOSYSTEMS, RULES
from .scanner import Artifact, scan

_SIZE_UNITS = {"": 1, "b": 1, "k": 1024, "m": 1024 ** 2, "g": 1024 ** 3, "t": 1024 ** 4}
_AGE_UNITS = {"h": 1 / 24, "d": 1, "w": 7, "m": 30, "y": 365}


def parse_size(text: str) -> int:
    """'500', '10k', '1.5M', '2G', '2GiB', '100MB' -> bytes (binary units)."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kmgt]?)(?:i?b)?\s*", text, re.IGNORECASE)
    if not m:
        raise argparse.ArgumentTypeError(f"invalid size: {text!r} (try 500M or 2G)")
    return int(float(m.group(1)) * _SIZE_UNITS[m.group(2).lower()])


def parse_age(text: str) -> float:
    """'12h', '30d', '2w', '6m', '1y' -> days. A bare number means days."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([hdwmy]?)\s*", text, re.IGNORECASE)
    if not m:
        raise argparse.ArgumentTypeError(f"invalid age: {text!r} (try 30d, 6m or 1y)")
    return float(m.group(1)) * _AGE_UNITS[(m.group(2) or "d").lower()]


def parse_selection(text: str, count: int) -> List[int]:
    """'1,3,5-7' or 'all' -> sorted zero-based indexes. Raises ValueError."""
    text = text.strip().lower()
    if text in ("a", "all", "*"):
        return list(range(count))
    picked = set()
    for part in filter(None, re.split(r"[,\s]+", text)):
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not m:
            raise ValueError(f"not a number or range: {part!r}")
        lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
        if lo > hi:
            lo, hi = hi, lo
        if lo < 1 or hi > count:
            raise ValueError(f"{part} is outside 1-{count}")
        picked.update(range(lo - 1, hi))
    return sorted(picked)


def _ecosystems(text: str) -> List[str]:
    names = [n.strip().lower() for n in text.split(",") if n.strip()]
    unknown = [n for n in names if n not in ECOSYSTEMS]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown type {', '.join(unknown)}; choose from {', '.join(ECOSYSTEMS)}")
    return names


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="buildsweep",
        description="Find and remove regenerable build and dependency folders "
                    "(node_modules, .venv, target, ...) in old projects.",
        epilog="By default buildsweep only reports. Examples:\n"
               "  buildsweep ~/code\n"
               "  buildsweep ~/code --older-than 90d -i\n"
               "  buildsweep ~/code --older-than 6m --min-size 100M --action trash --yes\n"
               "  buildsweep ~/code --format html -o report.html",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("paths", nargs="*", default=["."], metavar="PATH",
                   help="folders to scan (default: current folder)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    f = p.add_argument_group("filtering")
    f.add_argument("--older-than", type=parse_age, metavar="AGE", default=0.0,
                   help="only projects with no source changes for AGE (e.g. 30d, 6m, 1y)")
    f.add_argument("--min-size", type=parse_size, metavar="SIZE", default=0,
                   help="only folders of at least SIZE (e.g. 50M)")
    f.add_argument("--only", type=_ecosystems, metavar="TYPES",
                   help="comma-separated types to include, e.g. node,python")
    f.add_argument("--skip", type=_ecosystems, metavar="TYPES", default=[],
                   help="comma-separated types to leave alone")
    f.add_argument("-x", "--exclude", action="append", default=[], metavar="GLOB",
                   help="skip folders matching GLOB (name or full path); repeatable")
    f.add_argument("--hidden", action="store_true",
                   help="also search inside hidden folders (artifacts like .venv are found either way)")

    a = p.add_argument_group("actions")
    a.add_argument("--action", choices=ACTIONS, default="report",
                   help="report (default), trash (recoverable) or delete (permanent)")
    a.add_argument("-i", "--interactive", action="store_true",
                   help="choose folders from a numbered list (implies --action trash)")
    a.add_argument("-n", "--dry-run", action="store_true", help="show what would happen, change nothing")
    a.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")

    o = p.add_argument_group("output")
    o.add_argument("--format", choices=("text", "json", "html"), default="text",
                   help="report format (default: text); html is best with -o report.html")
    o.add_argument("-o", "--output", metavar="FILE", help="write the report to FILE instead of stdout")
    o.add_argument("--limit", type=int, default=0, metavar="N", help="text: show only the N biggest")
    o.add_argument("-q", "--quiet", action="store_true", help="no progress output or warnings")
    o.add_argument("-v", "--verbose", action="store_true", help="list every folder that could not be read")
    o.add_argument("--list-rules", action="store_true", help="show every folder buildsweep recognizes and exit")
    return p


def _ask(prompt: str) -> Optional[str]:
    """Read a line from the terminal, or None if there is no terminal."""
    if not sys.stdin.isatty():
        return None
    try:
        return input(prompt)
    except EOFError:
        return None


def _confirm(prompt: str) -> bool:
    answer = _ask(f"{prompt} [y/N] ")
    return answer is not None and answer.strip().lower() in ("y", "yes")


def _list_rules(out) -> None:
    out.write(f"{'TYPE':<10}  {'FOLDER':<32}  {'ONLY WHEN':<36}  RESTORE WITH\n")
    for r in RULES:
        cond = []
        if r.markers:
            cond.append("next to " + " | ".join(r.markers))
        if r.inside:
            cond.append("contains " + " | ".join(r.inside))
        if r.parent_name:
            cond.append(f"inside {r.parent_name}/")
        out.write(f"{r.ecosystem:<10}  {', '.join(r.names):<32}  {'; '.join(cond) or 'always':<36}  {r.restore}\n")


class Progress:
    """Single-line progress on stderr, only when it is a terminal."""

    def __init__(self, enabled: bool):
        self.enabled = enabled and sys.stderr.isatty()

    def __call__(self, dirs: int, found: int) -> None:
        if self.enabled:
            sys.stderr.write(f"\r\033[KScanning: {dirs} folders, {found} artifacts found")
            sys.stderr.flush()

    def clear(self) -> None:
        if self.enabled:
            sys.stderr.write("\r\033[K")
            sys.stderr.flush()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    err = sys.stderr

    if args.list_rules:
        _list_rules(sys.stdout)
        return 0

    action = args.action
    if args.interactive:
        if args.format != "text":
            err.write(f"buildsweep: --interactive cannot be combined with --format {args.format}\n")
            return 2
        if action == "report":
            action = "trash"
    if args.format == "html" and action != "report":
        err.write("buildsweep: the HTML report is read-only; use --format text or json to remove folders\n")
        return 2

    try:
        out = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
    except OSError as exc:
        err.write(f"buildsweep: cannot write {args.output}: {exc.strerror or exc}\n")
        return 2
    try:
        return _run(args, action, out, err)
    finally:
        if args.output:
            out.close()


def _run(args: argparse.Namespace, action: str, out, err) -> int:
    rules = [r for r in RULES
             if (args.only is None or r.ecosystem in args.only) and r.ecosystem not in args.skip]

    progress = Progress(not args.quiet and (args.format == "text" or bool(args.output)))
    result = scan(args.paths, rules=rules, exclude=args.exclude, hidden=args.hidden,
                  on_progress=progress)
    progress.clear()
    if result.errors and not args.quiet:
        if args.verbose or len(result.errors) <= 3:
            for path, msg in result.errors:
                err.write(f"buildsweep: {display_path(path)}: {msg}\n")
        else:
            err.write(f"buildsweep: skipped {len(result.errors)} unreadable folders "
                      "(use -v to list them)\n")

    now = time.time()
    selected: List[Artifact] = [a for a in result.artifacts
                                if a.size >= args.min_size and a.age_days(now) >= args.older_than]
    hidden_count = len(result.artifacts) - len(selected)

    if action == "report" or not selected:
        if args.format == "json":
            write_json(selected, out, now=now)
        elif args.format == "html":
            roots = [os.path.abspath(os.path.expanduser(p)) for p in args.paths]
            write_html(selected, out, roots=roots, now=now)
            if args.output and not args.quiet:
                err.write(f"Wrote {display_path(os.path.abspath(args.output))} "
                          f"({len(selected)} folders, {human_size(sum(a.size for a in selected))}).\n")
        else:
            write_text(selected, out, limit=args.limit, hidden_count=hidden_count, now=now)
        return 0

    # --- removal -------------------------------------------------------------
    if args.format == "text":
        write_text(selected, out, limit=0 if args.interactive else args.limit,
                   hidden_count=hidden_count, numbered=args.interactive, now=now)

    if args.interactive:
        while True:
            answer = _ask("\nFolders to remove (e.g. 1,3,5-8 or 'all'; empty to cancel): ")
            if answer is None or not answer.strip():
                out.write("Nothing removed.\n")
                return 0 if answer is not None else 1
            try:
                selected = [selected[i] for i in parse_selection(answer, len(selected))]
                break
            except ValueError as exc:
                out.write(f"  {exc}\n")

    total = sum(a.size for a in selected)
    verb = "Move to Trash" if action == "trash" else "PERMANENTLY delete"
    if not args.dry_run and not args.yes:
        if not _confirm(f"\n{verb} {len(selected)} folder{'s' if len(selected) != 1 else ''} "
                        f"({human_size(total)})?"):
            err.write("Aborted; nothing was changed. (Use --yes when not running in a terminal.)\n")
            return 1

    def on_result(r: ActionResult) -> None:
        if args.format == "text" and not args.quiet:
            mark = "ok " if r.ok else "!! "
            out.write(f"  {mark}{display_path(r.artifact.path)}: {r.message}\n")

    if args.format == "text":
        out.write("\n")
    results = apply_all(selected, action, dry_run=args.dry_run, on_result=on_result)
    freed = sum(r.artifact.size for r in results if r.ok)
    failed = sum(1 for r in results if not r.ok)

    if args.format == "json":
        write_json(selected, out, results=results, now=now)
    else:
        if args.dry_run:
            line = f"Would free {human_size(freed)}"
        elif action == "trash":
            line = f"Moved {human_size(freed)} to the Trash (empty it to free the space)"
        else:
            line = f"Freed {human_size(freed)}"
        if failed:
            line += f"; {failed} folder{'s' if failed != 1 else ''} skipped or failed"
        out.write(f"\n{line}.\n")
    return 1 if failed else 0
