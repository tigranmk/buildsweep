"""Self-contained HTML report.

The page has no external assets (CSS and JS are inline), so it works offline,
can be emailed or archived, and opens straight from disk. It is read-only: it
can't remove anything, but it builds the `buildsweep` command that would.

The scan results are embedded as JSON with `<`, `>` and `&` escaped, and the
page renders them with textContent only, so a folder name can never inject
markup or script.
"""

from __future__ import annotations

import datetime as _dt
import html
import json
import os
import pathlib
import time
from typing import IO, Optional, Sequence

from . import __version__
from .report import display_path
from .rules import ECOSYSTEMS
from .scanner import Artifact

_CSS = """
:root {
  --bg: #f7f7f8; --card: #ffffff; --text: #1d1d1f; --muted: #6b6b73;
  --border: #e3e3e8; --accent: #3b5bdb; --accent-bg: #e8edff;
  --old: #b35900; --old-bg: #fff1e0; --row-hover: #f2f3f7;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #141416; --card: #1e1e21; --text: #ececf1; --muted: #9a9aa3;
    --border: #2e2e33; --accent: #8ea6ff; --accent-bg: #232a45;
    --old: #ffb35c; --old-bg: #3a2a14; --row-hover: #26262a;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
main { max-width: 1100px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 26px; margin: 0 0 4px; }
h2 { font-size: 15px; margin: 0 0 10px; }
.meta { color: var(--muted); font-size: 13px; margin-bottom: 24px; word-break: break-all; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px; margin-bottom: 20px; }
.card, .panel { background: var(--card); border: 1px solid var(--border); border-radius: 10px; }
.card { padding: 14px 16px; }
.card .n { font-size: 24px; font-weight: 650; font-variant-numeric: tabular-nums; }
.card .l { color: var(--muted); font-size: 13px; }
.panel { padding: 14px 16px; margin-bottom: 20px; }
.types { display: grid; gap: 6px; }
.type { display: grid; grid-template-columns: 22px 90px 1fr 90px; gap: 8px; align-items: center;
  font-size: 13.5px; cursor: pointer; }
.type input { margin: 0; }
.type .track { height: 8px; background: var(--border); border-radius: 99px; overflow: hidden; }
.type .fill { height: 100%; background: var(--accent); border-radius: 99px; }
.type .sz { text-align: right; color: var(--muted); font-variant-numeric: tabular-nums; }
.type.off { opacity: .45; }
.toolbar { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-bottom: 12px; }
.toolbar input[type=search], .toolbar select { padding: 9px 12px; border-radius: 8px; font: inherit;
  border: 1px solid var(--border); background: var(--card); color: var(--text); }
.toolbar input[type=search] { flex: 1 1 200px; min-width: 0; }
.toolbar label { color: var(--muted); font-size: 13px; }
.cmd { display: flex; gap: 8px; align-items: stretch; margin-bottom: 20px; }
.cmd code { flex: 1; min-width: 0; background: var(--card); border: 1px solid var(--border); border-radius: 8px;
  padding: 9px 12px; font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
  overflow-x: auto; white-space: nowrap; }
.cmd button { padding: 0 14px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--card); color: var(--text); font: inherit; cursor: pointer; }
.hint { color: var(--muted); font-size: 12.5px; margin: -14px 0 20px; }
.tablewrap { background: var(--card); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
th { text-align: left; font-weight: 600; color: var(--muted); font-size: 12.5px; padding: 9px 12px;
  border-bottom: 1px solid var(--border); cursor: pointer; user-select: none; white-space: nowrap; }
th[data-dir=asc]::after { content: " \\25B4"; } th[data-dir=desc]::after { content: " \\25BE"; }
td { padding: 8px 12px; border-top: 1px solid var(--border); vertical-align: top; }
tbody tr:first-child td { border-top: 0; }
tbody tr:hover { background: var(--row-hover); }
td.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
th.num { text-align: right; }
td.path { word-break: break-all; }
td.path a { color: inherit; text-decoration: none; }
td.path a:hover { text-decoration: underline; }
td.path .restore { display: block; color: var(--muted); font-size: 12px; }
.tag { display: inline-block; font-size: 11px; font-weight: 650; letter-spacing: .03em;
  padding: 2px 7px; border-radius: 99px; text-transform: uppercase;
  color: var(--accent); background: var(--accent-bg); }
.idle.old { color: var(--old); }
.empty { text-align: center; color: var(--muted); padding: 48px 0; }
footer { color: var(--muted); font-size: 12px; margin-top: 32px; text-align: center; }
@media (max-width: 640px) {
  .type { grid-template-columns: 22px 70px 1fr 70px; }
  th.type-col, td.type-col { display: none; }
}
"""

# Everything below runs client-side; no data leaves the page.
_JS = r"""
const data = JSON.parse(document.getElementById('data').textContent);
const $ = id => document.getElementById(id);
const DAY = 86400;

function size(n) {
  const u = ['B', 'KiB', 'MiB', 'GiB', 'TiB']; let i = 0;
  while (Math.abs(n) >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return i ? n.toFixed(1) + ' ' + u[i] : n + ' B';
}
function age(d) {
  if (d < 1) return 'today';
  if (d < 60) return Math.floor(d) + 'd';
  if (d < 730) return Math.floor(d / 30.44) + 'mo';
  return (d / 365.25).toFixed(1) + 'y';
}
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
function shellQuote(s) {
  return /^[\w@%+=:,./~-]+$/.test(s) ? s : "'" + s.replace(/'/g, "'\\''") + "'";
}

const state = { q: '', minIdle: 0, off: new Set(), sort: 'bytes', dir: 'desc' };

// Type bars double as filters.
const typeTotals = {};
for (const a of data.artifacts) typeTotals[a.ecosystem] = (typeTotals[a.ecosystem] || 0) + a.bytes;
const maxType = Math.max(1, ...Object.values(typeTotals));
for (const [eco, bytes] of Object.entries(typeTotals).sort((x, y) => y[1] - x[1])) {
  const row = el('label', 'type');
  const cb = el('input'); cb.type = 'checkbox'; cb.checked = true;
  cb.onchange = () => { cb.checked ? state.off.delete(eco) : state.off.add(eco);
                        row.classList.toggle('off', !cb.checked); render(); };
  const track = el('div', 'track'); const fill = el('div', 'fill');
  fill.style.width = Math.max(1, 100 * bytes / maxType) + '%'; track.append(fill);
  row.append(cb, el('span', '', eco), track, el('span', 'sz', size(bytes)));
  $('types').append(row);
}

$('q').oninput = e => { state.q = e.target.value.trim().toLowerCase(); render(); };
$('idle').onchange = e => { state.minIdle = +e.target.value; render(); };
for (const th of document.querySelectorAll('th[data-key]')) {
  th.onclick = () => {
    const k = th.dataset.key;
    state.dir = state.sort === k && state.dir === 'desc' ? 'asc' : 'desc';
    state.sort = k; render();
  };
}
$('copy').onclick = () => {
  navigator.clipboard.writeText($('cmd').textContent).then(
    () => { $('copy').textContent = 'Copied'; setTimeout(() => $('copy').textContent = 'Copy', 1500); });
};

function command(rows) {
  const parts = ['buildsweep', ...data.roots.map(shellQuote)];
  if (state.minIdle) parts.push('--older-than', state.minIdle + 'd');
  const on = Object.keys(typeTotals).filter(t => !state.off.has(t));
  if (state.off.size && on.length) parts.push('--only', on.join(','));
  parts.push('-i');
  return parts.join(' ');
}

function render() {
  const rows = data.artifacts.filter(a =>
    !state.off.has(a.ecosystem) && a.idle_days >= state.minIdle &&
    (!state.q || a.path.toLowerCase().includes(state.q)));
  const k = state.sort, m = state.dir === 'asc' ? 1 : -1;
  rows.sort((x, y) => (x[k] < y[k] ? -1 : x[k] > y[k] ? 1 : 0) * m || (x.path < y.path ? -1 : 1));

  const total = rows.reduce((s, a) => s + a.bytes, 0);
  $('total').textContent = size(total);
  $('count').textContent = rows.length.toLocaleString();
  $('projects').textContent = new Set(rows.map(a => a.project)).size.toLocaleString();
  $('shown').textContent = rows.length + ' of ' + data.artifacts.length;
  $('cmd').textContent = command(rows);
  $('hint').hidden = !state.q;

  for (const th of document.querySelectorAll('th[data-key]'))
    th.dataset.dir = th.dataset.key === k ? state.dir : '';

  const body = $('rows'); body.replaceChildren();
  for (const a of rows) {
    const tr = el('tr');
    tr.append(el('td', 'num', size(a.bytes)));
    tr.append(el('td', 'num idle' + (a.idle_days >= 180 ? ' old' : ''), age(a.idle_days)));
    const t = el('td', 'type-col'); t.append(el('span', 'tag', a.ecosystem)); tr.append(t);
    const p = el('td', 'path');
    const link = el('a', '', a.shown); link.href = a.href; link.title = a.path;
    p.append(link, el('span', 'restore', 'restore: ' + a.restore));
    tr.append(p);
    body.append(tr);
  }
  $('none').hidden = rows.length > 0;
}
render();
"""

_IDLE_CHOICES = [(0, "any time"), (30, "30+ days"), (90, "3+ months"), (180, "6+ months"),
                 (365, "1+ year"), (730, "2+ years")]


def _page_data(artifacts: Sequence[Artifact], roots: Sequence[str], now: float) -> dict:
    base = roots[0] if len(roots) == 1 else None
    items = []
    for a in artifacts:
        try:
            href = pathlib.Path(a.path).as_uri()
        except ValueError:
            href = ""
        # With one scanned folder, paths relative to it are easier to read;
        # the full path stays in the link and tooltip.
        rel = os.path.relpath(a.path, base) if base and a.path.startswith(base + os.sep) else None
        items.append({
            "path": a.path,
            "shown": rel or display_path(a.path),
            "href": href,
            "project": a.project,
            "ecosystem": a.rule.ecosystem,
            "bytes": a.size,
            "idle_days": round(a.age_days(now), 1),
            "restore": a.rule.restore,
        })
    return {"roots": [display_path(r) for r in roots], "artifacts": items}


def _embed_json(obj: dict) -> str:
    """JSON safe to place inside a <script> element."""
    text = json.dumps(obj, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def write_html(artifacts: Sequence[Artifact], out: IO[str], *, roots: Sequence[str] = (),
               now: Optional[float] = None) -> None:
    now = now or time.time()
    generated = _dt.datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M")
    scanned = ", ".join(display_path(r) for r in roots) or "-"
    options = "".join(f'<option value="{d}">{label}</option>' for d, label in _IDLE_CHOICES)

    if not artifacts:
        content = '<div class="empty">No build or dependency folders found.</div>'
    else:
        content = f"""
<div class="cards">
  <div class="card"><div class="n" id="total"></div><div class="l">reclaimable space</div></div>
  <div class="card"><div class="n" id="count"></div><div class="l">folders</div></div>
  <div class="card"><div class="n" id="projects"></div><div class="l">projects</div></div>
</div>
<div class="panel"><h2>By type</h2><div class="types" id="types"></div></div>
<div class="toolbar">
  <input id="q" type="search" placeholder="Filter by path..." aria-label="Filter by path">
  <label for="idle">Idle for</label><select id="idle">{options}</select>
  <span class="meta" style="margin:0">Showing <span id="shown"></span></span>
</div>
<div class="cmd"><code id="cmd"></code><button id="copy" type="button">Copy</button></div>
<div class="hint" id="hint" hidden>The path filter isn't part of the command; untick rows
in the interactive list (<code>-i</code>) instead.</div>
<div class="tablewrap"><table>
  <thead><tr>
    <th class="num" data-key="bytes">Size</th>
    <th class="num" data-key="idle_days">Idle</th>
    <th class="type-col" data-key="ecosystem">Type</th>
    <th data-key="path">Folder</th>
  </tr></thead>
  <tbody id="rows"></tbody>
</table><div class="empty" id="none" hidden>Nothing matches these filters.</div></div>
<script type="application/json" id="data">{_embed_json(_page_data(artifacts, roots, now))}</script>
<script>{_JS}</script>"""

    out.write(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Build Folders Report</title>
<style>{_CSS}</style></head><body><main>
<h1>Build and dependency folders</h1>
<div class="meta">Scanned {html.escape(scanned)} &middot; generated {generated} &middot;
{len(ECOSYSTEMS)} ecosystems checked</div>
{content}
<footer>Generated by buildsweep {__version__}. This page is read-only; run the command
above to remove folders.</footer>
</main></body></html>
""")
