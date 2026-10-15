"""Which folders count as regenerable build or dependency artifacts.

A folder is only ever reported when its *name* matches a rule and the
project around it proves the rule applies: a marker file next to it (for
example `Cargo.toml` beside `target/`) or a marker inside it (for example
`pyvenv.cfg` inside a virtualenv). A folder that is merely called `build` or
`target` is never touched. This is the same idea kondo and npkill use,
extended to many ecosystems.

To add an ecosystem, append a Rule to RULES and add a test in
tests/test_rules.py.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from typing import Collection, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class Rule:
    ecosystem: str             # short id used by --only / --skip
    names: Tuple[str, ...]     # folder name globs, e.g. ("node_modules",)
    # Globs matched against the folder's siblings. At least one must exist.
    markers: Tuple[str, ...] = ()
    # Names that must exist inside the folder. At least one must exist.
    inside: Tuple[str, ...] = ()
    # The folder's parent must have this exact name (e.g. Xcode's DerivedData).
    parent_name: Optional[str] = None
    restore: str = ""          # how to get it back, shown by --list-rules

    def matches_name(self, name: str) -> bool:
        return any(fnmatch.fnmatchcase(name, pat) for pat in self.names)

    def applies(self, path: str, siblings: Collection[str]) -> bool:
        """True if `path` (whose name already matched) is this rule's artifact.

        `siblings` holds the names of every entry in the parent directory.
        """
        if self.parent_name is not None:
            if os.path.basename(os.path.dirname(path)) != self.parent_name:
                return False
        if self.markers and not any(_glob_any(pat, siblings) for pat in self.markers):
            return False
        if self.inside and not any(os.path.lexists(os.path.join(path, n)) for n in self.inside):
            return False
        return True


def _glob_any(pattern: str, names: Iterable[str]) -> bool:
    if not any(c in pattern for c in "*?["):
        return pattern in names
    return any(fnmatch.fnmatchcase(n, pattern) for n in names)


GRADLE = ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts")
DOTNET = ("*.csproj", "*.fsproj", "*.vbproj", "*.sln")

RULES: List[Rule] = [
    # JavaScript / TypeScript
    Rule("node", ("node_modules",), markers=("package.json",), restore="npm/yarn/pnpm install"),
    Rule("node", (".next",), markers=("next.config.*", "package.json"), restore="next build"),
    Rule("node", (".nuxt", ".output"), markers=("nuxt.config.*",), restore="nuxt build"),
    Rule("node", (".svelte-kit",), markers=("svelte.config.*",), restore="vite build / dev"),
    Rule("node", (".parcel-cache", ".turbo"), markers=("package.json",), restore="rebuilt on next build"),
    Rule("node", (".angular",), markers=("angular.json",), restore="ng build"),
    Rule("node", ("bower_components",), markers=("bower.json",), restore="bower install"),
    # Python
    Rule("python", (".venv", "venv", "env", ".env"), inside=("pyvenv.cfg",),
         restore="python -m venv + pip install"),
    Rule("python", ("__pycache__",), restore="recreated automatically"),
    Rule("python", (".pytest_cache", ".mypy_cache", ".ruff_cache", ".hypothesis"),
         restore="recreated automatically"),
    Rule("python", (".tox",), markers=("tox.ini", "pyproject.toml", "setup.cfg"), restore="tox"),
    Rule("python", (".nox",), markers=("noxfile.py",), restore="nox"),
    # Rust
    Rule("rust", ("target",), markers=("Cargo.toml",), restore="cargo build"),
    # JVM
    Rule("java", (".gradle", "build"), markers=GRADLE, restore="gradle build"),
    Rule("java", ("target",), markers=("pom.xml",), restore="mvn package"),
    Rule("java", ("target",), markers=("build.sbt",), restore="sbt compile"),
    # .NET
    Rule("dotnet", ("bin", "obj"), markers=DOTNET, restore="dotnet build"),
    # Apple platforms
    Rule("swift", (".build",), markers=("Package.swift",), restore="swift build"),
    Rule("swift", ("Pods",), markers=("Podfile",), restore="pod install"),
    Rule("swift", ("DerivedData",), parent_name="Xcode", restore="rebuilt by Xcode"),
    # Other languages and tools
    Rule("php", ("vendor",), markers=("composer.json",), restore="composer install"),
    Rule("elixir", ("_build", "deps"), markers=("mix.exs",), restore="mix deps.get && mix compile"),
    Rule("haskell", (".stack-work",), markers=("stack.yaml",), restore="stack build"),
    Rule("haskell", ("dist-newstyle",), markers=("*.cabal", "cabal.project"), restore="cabal build"),
    Rule("dart", (".dart_tool", "build"), markers=("pubspec.yaml",), restore="flutter/dart pub get"),
    Rule("zig", ("zig-cache", ".zig-cache", "zig-out"), markers=("build.zig",), restore="zig build"),
    Rule("elm", ("elm-stuff",), markers=("elm.json",), restore="elm make"),
    Rule("terraform", (".terraform",), markers=("*.tf",), restore="terraform init"),
    Rule("cmake", ("build", "cmake-build-*", "out"), inside=("CMakeCache.txt",), restore="cmake"),
    Rule("unity", ("Library", "Temp", "Obj", "Logs"), markers=("ProjectSettings",),
         restore="reimported when Unity opens the project"),
    Rule("godot", (".godot",), markers=("project.godot",), restore="reimported by Godot"),
]

ECOSYSTEMS: List[str] = sorted({r.ecosystem for r in RULES})


def match(path: str, siblings: Collection[str], rules: Iterable[Rule] = RULES) -> Optional[Rule]:
    """Return the first rule that claims directory `path`, or None."""
    name = os.path.basename(path)
    for rule in rules:
        if rule.matches_name(name) and rule.applies(path, siblings):
            return rule
    return None
