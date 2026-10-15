# buildsweep

**Find the `node_modules`, `.venv`, `target/` and other build folders in your
old projects and get the disk space back, safely.**

```bash
pipx install buildsweep
buildsweep ~/code --older-than 90d
```

Every project you have ever cloned or started leaves behind folders that its
tools can recreate in a minute: `node_modules`, Python virtualenvs, Rust and
Maven `target/`, Gradle caches, CocoaPods, Xcode `DerivedData`, `.next`,
`.terraform` and many more. On a developer laptop they easily add up to tens of
gigabytes, most of it in projects nobody has touched in months.

buildsweep finds them across every ecosystem in one pass, shows how big each one
is and how long its project has been idle, and removes the ones you choose.

```
$ buildsweep ~/code --older-than 90d
      SIZE    IDLE  TYPE        PATH
   2.1 GiB     9mo  node        ~/code/old-dashboard/node_modules
   1.4 GiB    1.3y  rust        ~/code/raytracer/target
 983.3 MiB     5mo  swift       ~/code/ios-demo/Pods
 714.1 MiB     9mo  python      ~/code/ml-notebook/.venv
 389.7 MiB    16mo  java        ~/code/kotlin-api/build
...

By type: node 6.2 GiB, rust 2.0 GiB, swift 1.1 GiB, python 0.9 GiB, java 0.4 GiB
Found 41 folders, 10.6 GiB reclaimable.
(12 more did not pass --older-than / --min-size.)
```

## Why use it

- **It only removes folders that can be rebuilt.** A folder is matched by its
  name *and* by proof from the project around it: `target/` counts only next
  to a `Cargo.toml`, `pom.xml` or `build.sbt`; `bin/` and `obj/` only next to a
  `.csproj`; a virtualenv only if it contains `pyvenv.cfg`. A folder that just
  happens to be called `build` or `target` is never touched, and neither is
  anything that is itself a git repository. Run `buildsweep --list-rules` to see
  every rule.
- **"Idle" means the project's last change, not the folder's last use.**
  buildsweep looks at the newest *source* file in each project, ignoring the
  artifacts themselves and `.git`. Running `npm install` or `git fetch` doesn't
  make an abandoned project look active.
- **Safe by default.** Without `--action`, buildsweep only reports. Removal asks
  for confirmation, `--dry-run` previews it, and the default `trash` action is
  recoverable (on macOS, Finder's **Put Back** works). Right before removing
  each folder, buildsweep checks again that it still exists, is not a symlink,
  and still matches its rule.
- **Every ecosystem in one tool.** Node, Python, Rust, Java/Kotlin (Gradle,
  Maven, sbt), .NET, Swift/iOS, PHP, Elixir, Haskell, Dart/Flutter, Zig, Elm,
  Terraform, CMake, Unity and Godot.
- **Honest numbers.** Sizes are real disk usage. Hard-linked files (pnpm, uv)
  are counted once, so the total doesn't promise space that removal won't free.
- **A report you can browse and share.** `--format html` writes a single
  offline page with totals per type, filters, sortable columns and the exact
  `buildsweep` command for what you've filtered.
- **No dependencies.** Pure Python 3.9+ standard library. Runs on macOS, Linux
  and Windows.

## Install

You need Python 3.9 or newer (`python3 --version`). Installing with
[pipx](https://pipx.pypa.io/) is recommended. It keeps the tool in its own
environment and puts the `buildsweep` command on your PATH:

```bash
pipx install buildsweep            # or: pip install buildsweep
buildsweep --help
```

To try it without installing anything: `pipx run buildsweep ~/code` or
`uvx buildsweep ~/code`.

If you don't have pipx yet, install it with `brew install pipx` (macOS) or
`python3 -m pip install --user pipx`, then run `pipx ensurepath` and open a new
terminal.

**Optional: Trash support on Linux and Windows.** On macOS, moving to the
Trash works out of the box. On Linux and Windows, install the extra:

```bash
pipx install 'buildsweep[trash]'
```

**From source:**

```bash
git clone https://github.com/tigranmk/buildsweep.git
cd buildsweep
python3 -m buildsweep ~/code    # run in place, no install
pipx install .                # or install the command from this checkout
```

## Usage

```bash
buildsweep [PATH ...] [options]
```

With no path, buildsweep scans the current folder.

### Common recipes

| Goal | Command |
| --- | --- |
| See what's there (changes nothing) | `buildsweep ~/code` |
| Only projects idle for 3+ months | `buildsweep ~/code --older-than 90d` |
| Pick folders from a numbered list, then trash them | `buildsweep ~/code --older-than 90d -i` |
| Preview a cleanup | `buildsweep ~/code --older-than 6m --action trash --dry-run` |
| Trash everything idle for 6+ months, no prompt | `buildsweep ~/code --older-than 6m --action trash --yes` |
| Only big folders | `buildsweep ~/code --min-size 500M` |
| Only Node and Python | `buildsweep ~/code --only node,python` |
| Everything except Rust | `buildsweep ~/code --skip rust` |
| Leave one project alone | `buildsweep ~/code -x '*/keep-this-project'` |
| Clean Xcode's DerivedData too | `buildsweep ~ --only swift` |
| Browsable report to open in a browser | `buildsweep ~ --format html -o report.html && open report.html` |
| Feed results to another tool | `buildsweep ~/code --format json \| jq '.summary'` |
| Monthly cleanup from cron | `buildsweep ~/code --older-than 6m --action trash --yes -q` |

### Interactive mode

`-i` shows a numbered list and asks which folders to remove. Answer with
numbers and ranges (`1,3,5-8`), `all`, or press Enter to cancel. You are then
asked to confirm. Interactive mode trashes by default; add `--action delete`
to delete permanently.

```
$ buildsweep ~/code --older-than 90d -i
          SIZE    IDLE  TYPE        PATH
[1]    2.1 GiB     9mo  node        ~/code/old-dashboard/node_modules
[2]    1.4 GiB    1.3y  rust        ~/code/raytracer/target
[3]  983.3 MiB     5mo  swift       ~/code/ios-demo/Pods

Folders to remove (e.g. 1,3,5-8 or 'all'; empty to cancel): 1-2

Move to Trash 2 folders (3.5 GiB)? [y/N] y

  ok ~/code/old-dashboard/node_modules: moved to Trash (Finder)
  ok ~/code/raytracer/target: moved to Trash (Finder)

Moved 3.5 GiB to the Trash (empty it to free the space).
```

### Actions (`--action`)

| Action | What happens | Reversible? |
| --- | --- | --- |
| `report` *(default)* | nothing | n/a |
| `trash` | moved to the Trash/Recycle Bin | yes: on macOS, Finder's **Put Back** restores it |
| `delete` | permanently removed | **no**, but you can rebuild it (see `--list-rules`) |

Removal prompts `[y/N]`. Add `--yes` to skip the prompt (for scripts) or
`--dry-run` to see exactly what would happen. When stdin isn't a terminal and
`--yes` isn't given, buildsweep refuses and changes nothing.

Space from trashed folders is freed when you empty the Trash. Use
`--action delete` if you want it back immediately.

**How `trash` works on macOS.** buildsweep asks Finder to trash the folders in
batches, so **Put Back** works exactly as if you had deleted them in Finder.
The first time, macOS may ask whether your terminal may control Finder: click
**OK**. If you decline, or Finder isn't available (for example over SSH),
buildsweep falls back to the optional Send2Trash package, then to moving folders
into `~/.Trash`. To change your answer later, go to System Settings → Privacy
& Security → Automation. Set `BUILDSWEEP_NO_FINDER=1` to skip Finder entirely.

### All options

```
filtering:
  --older-than AGE      only projects with no source changes for AGE (e.g. 30d, 6m, 1y)
  --min-size SIZE       only folders of at least SIZE (e.g. 50M)
  --only TYPES          comma-separated types to include, e.g. node,python
  --skip TYPES          comma-separated types to leave alone
  -x, --exclude GLOB    skip folders matching GLOB (name or full path); repeatable
  --hidden              also search inside hidden folders (artifacts like .venv are found either way)

actions:
  --action {report,trash,delete}
  -i, --interactive     choose folders from a numbered list (implies --action trash)
  -n, --dry-run         show what would happen, change nothing
  -y, --yes             do not ask for confirmation

output:
  --format {text,json,html}
  -o, --output FILE     write the report to FILE instead of stdout
  --limit N             text: show only the N biggest
  -q, --quiet           no progress output or warnings
  -v, --verbose         list every folder that could not be read
  --list-rules          show every folder buildsweep recognizes and exit
```

Ages accept `h`, `d`, `w`, `m` (30 days) and `y` (365 days); a bare number
means days. Sizes accept binary units: `500`, `10k`, `1.5M`, `2G`, `2GiB`.

Types for `--only` and `--skip`: `cmake`, `dart`, `dotnet`, `elixir`, `elm`,
`godot`, `haskell`, `java`, `node`, `php`, `python`, `rust`, `swift`,
`terraform`, `unity`, `zig`.

**Exit status:** `0` on success, `1` if removal was aborted or any folder was
skipped or failed, `2` for usage errors.

### HTML report

```bash
buildsweep ~ --format html -o report.html && open report.html
```

`--format html` writes one self-contained page: no external files, works
offline, and can be emailed or archived. It shows:

- reclaimable space, folder and project counts, updating as you filter;
- a bar per type, whose checkbox shows or hides that type;
- a path filter and an "idle for" filter (30 days to 2+ years);
- a table sortable by size, idle time, type or path, with each folder linked
  and the command that restores it;
- a copyable `buildsweep ... -i` command matching your type and idle filters,
  so you can go from the report straight to an interactive cleanup.

The page is read-only and can't remove anything. Light and dark themes follow
your system setting. Folder names are embedded as escaped data and displayed
as plain text, so a strangely named folder can't inject anything into the
page. Because the report lists your local paths, think before sharing it.

### JSON output

`--format json` prints a summary and one entry per folder: path, project,
type, bytes, file count, last activity date, idle days and the command that
restores it. After a removal, each entry also has a `result`.

```json
{
  "summary": {"folders": 41, "reclaimable_bytes": 11381852160, "by_ecosystem": {"node": {"folders": 22, "bytes": 6657199308}}},
  "artifacts": [
    {"path": "/Users/me/code/old-dashboard/node_modules", "ecosystem": "node", "bytes": 2254857830,
     "idle_days": 271.4, "restore": "npm/yarn/pnpm install"}
  ]
}
```

### Behaviour worth knowing

- **It doesn't look inside artifacts.** A `node_modules` with thousands of
  nested `node_modules` is one entry, and the scan stays fast.
- **Hidden folders are skipped** (except artifacts like `.venv`, `.next` or
  `.gradle`, which are always found). Use `--hidden` to search inside folders
  like `~/.config`.
- **On macOS, `~/Library` and `~/.Trash` are skipped** when you scan your home
  folder, because they hold no projects and take long to walk. Xcode's
  `~/Library/Developer/Xcode/DerivedData` is still checked. Pass a path inside
  `~/Library` explicitly to scan it.
- **Symlinks are never followed**, so a link can't lead buildsweep outside the
  folders you asked it to scan.
- **Generic `dist/` and `build/` folders are not removed** unless a build tool
  proves they are output (Gradle, Flutter, CMake). Some projects commit them.
- **Version control folders (`.git`, `.hg`, `.svn`) are never touched.**

## Python API

```python
from buildsweep import scan

result = scan(["~/code"], exclude=["*/keep-me"])
for a in result.artifacts:          # biggest first
    print(a.rule.ecosystem, a.size, round(a.age_days()), a.path)
```

## Adding an ecosystem

Rules live in [`buildsweep/rules.py`](https://github.com/tigranmk/buildsweep/blob/main/buildsweep/rules.py). Each rule names the
folder, the marker files that must sit next to it (or inside it), and how to
restore it:

```python
Rule("rust", ("target",), markers=("Cargo.toml",), restore="cargo build"),
```

Add a test in `tests/test_rules.py` for the match and for a look-alike folder
that must *not* match, then open a pull request.

## Development

```bash
python3 -m unittest discover -s tests -v
```

The tests need nothing beyond the standard library and run on macOS, Linux and
Windows in CI.

```
buildsweep/
  rules.py     which folders are artifacts, per ecosystem
  scanner.py   one-pass walk: finds artifacts, sizes them, dates their projects
  actions.py   trash and delete, with re-checks right before removal
  report.py    terminal table and JSON
  html_report.py  self-contained HTML report
  cli.py       command-line interface
tests/         unittest suite with throwaway project trees
```

## Related projects and credits

buildsweep builds on ideas from these projects. No code was copied from them
unless noted.

- [**kondo**](https://github.com/tbillington/kondo) (MIT): cleans project
  artifacts across ecosystems by detecting project types from marker files.
  buildsweep's "marker next to the folder" rules follow the same idea.
- [**npkill**](https://github.com/voidcosmos/npkill) (MIT): finds and removes
  `node_modules` interactively, showing size and last modification. buildsweep
  extends that workflow to every ecosystem.
- [**twinsweep**](https://github.com/tigranmk/twinsweep) (MIT, same author):
  finds duplicate files. buildsweep shares its safety conventions and its Finder
  trash code. The two tools complement each other: twinsweep finds identical
  copies of *your* files; buildsweep removes *generated* folders.
- [**Send2Trash**](https://github.com/arsenetar/send2trash) (BSD-3-Clause):
  optional dependency used for the Trash on Linux and Windows.

See [THIRD_PARTY_NOTICES.md](https://github.com/tigranmk/buildsweep/blob/main/THIRD_PARTY_NOTICES.md) for license details.

## License

MIT. See [LICENSE](https://github.com/tigranmk/buildsweep/blob/main/LICENSE).
