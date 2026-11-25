"""Local web workbench HTML/JS renderer for inspecting local folders and GitHub repos."""

from __future__ import annotations

import json
from typing import Any


def _safe_json_for_script(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def render_workbench_html(
    initial_target: str | None = None,
    offline_default: bool = False,
) -> str:
    """Render the self-contained offline-capable CodeOverlook Web Workbench UI.

    Args:
        initial_target: Optional local path or GitHub repo pre-filled and inspected on load.
        offline_default: Whether the `Offline mode` checkbox starts checked.

    Returns:
        Complete HTML5 document string with zero external asset or CDN dependencies.
    """
    boot_config = _safe_json_for_script(
        {
            "initial_target": initial_target or "",
            "offline_default": bool(offline_default),
        }
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>CodeOverlook Workbench</title>
<style>
  :root {{
    --bg: #0f172a;
    --surface: #1e293b;
    --surface-2: #263348;
    --border: #334155;
    --text: #f1f5f9;
    --muted: #94a3b8;
    --accent: #38bdf8;
    --accent-dark: #0284c7;
    --ok: #16a34a;
    --warn: #ca8a04;
    --err: #dc2626;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 18px 22px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 14px;
    line-height: 1.45;
  }}
  h1 {{ margin: 0; font-size: 20px; font-weight: 600; }}
  .topbar {{
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    margin-bottom: 14px;
  }}
  .muted {{ color: var(--muted); font-size: 12px; }}
  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px;
    margin-bottom: 14px;
  }}
  .source-grid {{
    display: grid;
    grid-template-columns: minmax(260px, 2.4fr) minmax(120px, 0.9fr) minmax(130px, 0.9fr) auto;
    gap: 10px;
    align-items: end;
  }}
  @media (max-width: 960px) {{
    .source-grid {{ grid-template-columns: 1fr; }}
  }}
  label.field {{
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
    color: var(--muted);
  }}
  input[type="text"], input[type="number"] {{
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 13px;
    width: 100%;
  }}
  input:focus {{
    outline: none;
    border-color: var(--accent);
  }}
  .checks {{
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    margin-top: 10px;
    font-size: 13px;
    color: var(--text);
  }}
  .checks label {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
  }}
  button, .btn-link {{
    background: var(--accent-dark);
    color: #f8fafc;
    border: 1px solid var(--accent);
    border-radius: 6px;
    padding: 8px 14px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }}
  button:hover, .btn-link:hover {{ filter: brightness(1.1); }}
  button.secondary {{
    background: var(--surface-2);
    border-color: var(--border);
    color: var(--text);
    font-weight: 500;
  }}
  button.small {{
    padding: 5px 10px;
    font-size: 12px;
  }}
  button:disabled {{
    opacity: 0.55;
    cursor: not-allowed;
  }}
  .layout {{
    display: grid;
    grid-template-columns: 290px 1fr;
    gap: 14px;
    align-items: start;
  }}
  @media (max-width: 1080px) {{
    .layout {{ grid-template-columns: 1fr; }}
  }}
  .panel-title {{
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    margin-bottom: 8px;
    font-weight: 600;
  }}
  .cache-item {{
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 7px;
    padding: 9px 10px;
    margin-bottom: 8px;
  }}
  .cache-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }}
  .status-banner {{
    border-radius: 8px;
    padding: 10px 14px;
    margin-bottom: 12px;
    border: 1px solid var(--border);
    background: var(--surface);
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
  }}
  .status-banner.error {{
    border-color: var(--err);
    background: rgba(220, 38, 38, 0.14);
    color: #fecaca;
  }}
  .status-banner.ok {{
    border-color: #1d4ed8;
  }}
  .pill {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    background: var(--surface-2);
    border: 1px solid var(--border);
  }}
  .pill.local {{ border-color: var(--ok); color: #86efac; }}
  .pill.online {{ border-color: var(--accent); color: #bae6fd; }}
  .pill.cached {{ border-color: var(--warn); color: #fde68a; }}
  .tabs {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 12px;
  }}
  .tab-btn {{
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--muted);
    font-weight: 600;
  }}
  .tab-btn.active {{
    background: var(--accent-dark);
    border-color: var(--accent);
    color: #ffffff;
  }}
  .tab-pane {{ display: none; }}
  .tab-pane.active {{ display: block; }}
  iframe#explorer-frame {{
    width: 100%;
    height: 760px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg);
  }}
  pre.code-box {{
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    overflow: auto;
    max-height: 520px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12.5px;
    white-space: pre-wrap;
    word-break: break-word;
  }}
  .slice-form {{
    display: grid;
    grid-template-columns: 2fr 120px 100px auto;
    gap: 10px;
    align-items: end;
    margin-bottom: 12px;
  }}
  @media (max-width: 820px) {{
    .slice-form {{ grid-template-columns: 1fr; }}
  }}
  .list-card {{
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 7px;
    padding: 8px 10px;
    margin-bottom: 8px;
    font-size: 13px;
  }}
  code {{
    background: rgba(15, 23, 42, 0.7);
    padding: 1px 5px;
    border-radius: 4px;
    font-size: 12px;
  }}
</style>
</head>
<body>
  <div class="topbar">
    <div>
      <h1>CodeOverlook Inspection Workbench</h1>
      <div class="muted">
        Inspect local Python repositories offline or fetch &amp; cache GitHub projects for
        offline reuse.
      </div>
    </div>
    <div id="cache-root-label" class="muted"></div>
  </div>

  <div class="card">
    <form id="inspect-form" onsubmit="event.preventDefault(); runInspect();">
      <div class="source-grid">
        <label class="field">
          Local Folder Path or GitHub URL / owner/repo
          <input
            id="target-input"
            type="text"
            placeholder="C:\\path\\to\\repo or https://github.com/owner/repo"
            required
          />
        </label>
        <label class="field">
          Git Ref (optional)
          <input id="ref-input" type="text" placeholder="main / tag / sha" />
        </label>
        <label class="field">
          Subpath (optional)
          <input id="subpath-input" type="text" placeholder="packages/core" />
        </label>
        <button id="inspect-btn" type="submit">Inspect</button>
      </div>
      <div class="checks">
        <label>
          <input id="offline-check" type="checkbox" />
          Offline mode (local folders and cached GitHub repos only)
        </label>
        <label>
          <input id="refresh-check" type="checkbox" />
          Refresh GitHub cache from upstream
        </label>
        <label>
          <input id="force-check" type="checkbox" />
          Force full AST re-index
        </label>
      </div>
    </form>
  </div>

  <div id="status-banner" class="status-banner">
    <div id="status-text" class="muted">
      Enter a local directory or GitHub repository above, or pick a cached project on the left.
    </div>
    <div id="status-actions"></div>
  </div>

  <div class="layout">
    <aside class="card">
      <div class="cache-row" style="margin-bottom:10px;">
        <div class="panel-title" style="margin:0;">Cached GitHub Repos</div>
        <button type="button" class="secondary small" onclick="loadCache()">Reload</button>
      </div>
      <div id="cache-list" class="muted">Loading offline cache...</div>
    </aside>

    <main>
      <div class="tabs">
        <button type="button" class="tab-btn active" data-tab="explorer"
                onclick="switchTab('explorer')">Explorer</button>
        <button type="button" class="tab-btn" data-tab="slicer"
                onclick="switchTab('slicer')">Context Slicer</button>
        <button type="button" class="tab-btn" data-tab="mermaid"
                onclick="switchTab('mermaid')">Mermaid</button>
        <button type="button" class="tab-btn" data-tab="risks"
                onclick="switchTab('risks')">Risks &amp; Cycles</button>
      </div>

      <section id="tab-explorer" class="tab-pane active">
        <div id="explorer-empty" class="card muted">
          No active inspection session yet.
        </div>
        <iframe id="explorer-frame" style="display:none;" title="CodeOverlook Explorer"></iframe>
      </section>

      <section id="tab-slicer" class="tab-pane">
        <div class="card">
          <form class="slice-form" onsubmit="event.preventDefault(); runSlice();">
            <label class="field">
              Symbol or Relative File Path
              <input id="slice-target" type="text" placeholder="core/store.py or FactStore" />
            </label>
            <label class="field">
              Token Budget
              <input id="slice-budget" type="number" value="2500" min="50" max="50000" />
            </label>
            <label class="field">
              Depth
              <input id="slice-depth" type="number" value="1" min="1" max="3" />
            </label>
            <button type="submit">Extract Slice</button>
          </form>
          <div style="display:flex;justify-content:space-between;align-items:center;
                      margin-bottom:8px;">
            <div id="slice-meta" class="muted">Run an inspection first, then slice a symbol.</div>
            <button type="button" class="secondary small" onclick="copyText('slice-output')">
              Copy Markdown
            </button>
          </div>
          <pre id="slice-output" class="code-box"></pre>
        </div>
      </section>

      <section id="tab-mermaid" class="tab-pane">
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;
                      gap:8px;margin-bottom:10px;">
            <div style="display:flex;gap:8px;">
              <button type="button" id="m-arch-btn" class="small"
                      onclick="setMermaidMode('arch')">Architecture</button>
              <button type="button" id="m-cov-btn" class="secondary small"
                      onclick="setMermaidMode('coverage')">Test Coverage</button>
            </div>
            <button type="button" class="secondary small" onclick="copyText('mermaid-output')">
              Copy Mermaid
            </button>
          </div>
          <pre id="mermaid-output" class="code-box">
Run an inspection to generate Mermaid diagrams.</pre>
        </div>
      </section>

      <section id="tab-risks" class="tab-pane">
        <div class="card">
          <div class="panel-title">Import Cycles</div>
          <div id="cycles-list" class="muted">No inspection data yet.</div>
          <div class="panel-title" style="margin-top:14px;">Architecture Violations</div>
          <div id="violations-list" class="muted">No inspection data yet.</div>
        </div>
      </section>
    </main>
  </div>

<script>
const BOOT = {boot_config};
let activeSession = null;
let mermaidMode = 'arch';

function esc(value) {{
  return String(value).replace(/[&<>"']/g, c => ({{
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }}[c]));
}}

function switchTab(tabId) {{
  document.querySelectorAll('.tab-btn').forEach(btn => {{
    btn.classList.toggle('active', btn.dataset.tab === tabId);
  }});
  document.querySelectorAll('.tab-pane').forEach(pane => {{
    pane.classList.toggle('active', pane.id === 'tab-' + tabId);
  }});
}}

function setStatus(htmlContent, kind) {{
  const banner = document.getElementById('status-banner');
  banner.className = 'status-banner' + (kind ? ' ' + kind : '');
  document.getElementById('status-text').innerHTML = htmlContent;
}}

async function loadCache() {{
  try {{
    const res = await fetch('/api/cache');
    const data = await res.json();
    document.getElementById('cache-root-label').textContent = 'Cache: ' + data.cache_dir;
    const container = document.getElementById('cache-list');
    if (!data.repositories || !data.repositories.length) {{
      container.innerHTML = '<div class="muted">No cached GitHub repositories yet.</div>';
      return;
    }}
    container.innerHTML = data.repositories.map(item => {{
      const fullName = item.owner + '/' + item.repo;
      const refVal = item.ref === 'default' ? '' : item.ref;
      const idxBadge = item.indexed
        ? '<span class="pill local">INDEXED</span>'
        : '<span class="pill">CHECKED OUT</span>';
      return `<div class="cache-item">`
        + `<div class="cache-row"><strong>${{esc(fullName)}}</strong>${{idxBadge}}</div>`
        + `<div class="muted" style="margin:3px 0 6px;">`
        + `ref: <code>${{esc(item.ref)}}</code>`
        + (item.fetched_at ? ` | ${{esc(item.fetched_at.slice(0, 19).replace('T', ' '))}}` : '')
        + `</div>`
        + `<button type="button" class="secondary small" `
        + `onclick="inspectCached('${{esc(fullName)}}', '${{esc(refVal)}}')">`
        + `Inspect Offline</button>`
        + `</div>`;
    }}).join('');
  }} catch (err) {{
    document.getElementById('cache-list').textContent = 'Failed to read cache: ' + err;
  }}
}}

function inspectCached(repoName, refVal) {{
  document.getElementById('target-input').value = repoName;
  document.getElementById('ref-input').value = refVal;
  document.getElementById('subpath-input').value = '';
  document.getElementById('offline-check').checked = true;
  document.getElementById('refresh-check').checked = false;
  runInspect();
}}

async function runInspect() {{
  const target = document.getElementById('target-input').value.trim();
  if (!target) return;

  const btn = document.getElementById('inspect-btn');
  btn.disabled = true;
  btn.textContent = 'Inspecting...';
  document.getElementById('status-actions').innerHTML = '';
  setStatus('Resolving target and running incremental AST scan...', '');

  try {{
    const payload = {{
      target,
      ref: document.getElementById('ref-input').value.trim() || null,
      subpath: document.getElementById('subpath-input').value.trim() || null,
      offline: document.getElementById('offline-check').checked,
      refresh: document.getElementById('refresh-check').checked,
      force: document.getElementById('force-check').checked
    }};
    const res = await fetch('/api/inspect', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify(payload)
    }});
    const data = await res.json();
    if (!res.ok) {{
      setStatus('<strong>Error:</strong> ' + esc(data.error || 'Inspection failed'), 'error');
      return;
    }}

    activeSession = data;
    const t = data.target;
    const s = data.scan;
    const cov = data.coverage_summary;
    let pillClass = 'local';
    let modeLabel = 'LOCAL (OFFLINE)';
    if (t.source_kind === 'github') {{
      pillClass = t.from_cache ? 'cached' : 'online';
      modeLabel = t.from_cache ? 'GITHUB (CACHED OFFLINE)' : 'GITHUB (ONLINE FETCH)';
    }}

    setStatus(
      `<span class="pill ${{pillClass}}">${{modeLabel}}</span> `
      + `<strong>${{esc(t.display_name)}}</strong> `
      + `<span class="muted">(${{s.elapsed_ms.toFixed(0)}} ms | `
      + `${{s.indexed_files}} indexed, ${{s.skipped_files}} unchanged, `
      + `${{s.pruned_files}} pruned | `
      + `${{cov.blocks_count}} blocks | `
      + `${{cov.linked_test_files}}/${{cov.total_test_files}} test files | `
      + `${{data.cycles.length}} cycles | ${{data.violations.length}} violations)</span>`,
      'ok'
    );

    document.getElementById('status-actions').innerHTML =
      `<a class="btn-link secondary small" href="${{esc(data.report_url)}}?download=1">`
      + `Export Standalone HTML</a>`;

    const frame = document.getElementById('explorer-frame');
    document.getElementById('explorer-empty').style.display = 'none';
    frame.style.display = 'block';
    frame.src = data.report_url;

    renderMermaid();
    renderRisks(data.cycles, data.violations);
    loadCache();
  }} catch (err) {{
    setStatus('<strong>Error:</strong> ' + esc(err), 'error');
  }} finally {{
    btn.disabled = false;
    btn.textContent = 'Inspect';
  }}
}}

function setMermaidMode(mode) {{
  mermaidMode = mode;
  document.getElementById('m-arch-btn').classList.toggle('secondary', mode !== 'arch');
  document.getElementById('m-cov-btn').classList.toggle('secondary', mode !== 'coverage');
  renderMermaid();
}}

function renderMermaid() {{
  const box = document.getElementById('mermaid-output');
  if (!activeSession) return;
  box.textContent = mermaidMode === 'coverage'
    ? activeSession.mermaid_coverage
    : activeSession.mermaid_arch;
}}

function renderRisks(cycles, violations) {{
  const cDiv = document.getElementById('cycles-list');
  if (!cycles.length) {{
    cDiv.innerHTML = '<div class="list-card">No internal import cycles detected.</div>';
  }} else {{
    cDiv.innerHTML = cycles.map(c =>
      `<div class="list-card"><code>${{esc(c.join(' -> '))}}</code></div>`
    ).join('');
  }}

  const vDiv = document.getElementById('violations-list');
  if (!violations.length) {{
    vDiv.innerHTML = '<div class="list-card">No architecture boundary violations detected.</div>';
  }} else {{
    vDiv.innerHTML = violations.map(v =>
      `<div class="list-card"><strong>${{esc(v.src_block)}} -&gt; ${{esc(v.dst_block)}}</strong> `
      + `(${{v.edge_count}}x ${{esc(v.kind)}}): ${{esc(v.reason)}}</div>`
    ).join('');
  }}
}}

async function runSlice() {{
  if (!activeSession) {{
    document.getElementById('slice-meta').textContent = 'Inspect a repository first.';
    return;
  }}
  const target = document.getElementById('slice-target').value.trim();
  if (!target) return;
  const budget = parseInt(document.getElementById('slice-budget').value, 10) || 2500;
  const depth = parseInt(document.getElementById('slice-depth').value, 10) || 1;
  document.getElementById('slice-meta').textContent = 'Slicing...';

  try {{
    const res = await fetch('/api/slice', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        session_id: activeSession.session_id,
        target,
        budget,
        depth
      }})
    }});
    const data = await res.json();
    if (!res.ok) {{
      const errMsg = data.error || 'Slice failed';
      document.getElementById('slice-meta').textContent = 'Error: ' + errMsg;
      return;
    }}
    document.getElementById('slice-meta').textContent =
      `Target: ${{data.target}} | Estimated tokens: ${{data.estimated_tokens}}`
      + (data.truncated ? ' (truncated to budget)' : '');
    document.getElementById('slice-output').textContent = data.markdown;
  }} catch (err) {{
    document.getElementById('slice-meta').textContent = 'Error: ' + err;
  }}
}}

async function copyText(elementId) {{
  const text = document.getElementById(elementId).textContent || '';
  if (!text) return;
  try {{
    await navigator.clipboard.writeText(text);
  }} catch (_err) {{
    // Ignore clipboard API failure in restricted browser contexts.
  }}
}}

document.getElementById('offline-check').checked = Boolean(BOOT.offline_default);
loadCache();
if (BOOT.initial_target) {{
  document.getElementById('target-input').value = BOOT.initial_target;
  runInspect();
}}
</script>
</body>
</html>
"""
