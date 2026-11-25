"""Local web workbench HTML/JS renderer for inspecting local folders and GitHub repos."""

from __future__ import annotations

import json
from typing import Any

_WORKBENCH_CSS = """
  :root {
    --bg: #F3F8F9; --card: #FFFFFF; --border: #DCE8EB; --fg: #0B2B36;
    --text: #2F4A56; --muted: #5B7480; --primary: #0E7C86;
    --primary-strong: #0A646C; --on-primary: #FFFFFF; --soft: #ECF6F7;
    --accent: #D2EAEC; --ok: #1E7A4D; --warn: #8A5300; --bad: #B42318;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #0D1117; --card: #121C23; --border: #263943; --fg: #E8F2F4;
      --text: #B9CBD1; --muted: #8CA4AD; --primary: #56C5CE;
      --primary-strong: #7ADCE3; --on-primary: #06242A; --soft: #131F27;
      --accent: #11303A; --ok: #5BD08F; --warn: #E5AC5C; --bad: #F2857A;
    }
  }
  :root[data-theme="dark"] {
    --bg: #0D1117; --card: #121C23; --border: #263943; --fg: #E8F2F4;
    --text: #B9CBD1; --muted: #8CA4AD; --primary: #56C5CE;
    --primary-strong: #7ADCE3; --on-primary: #06242A; --soft: #131F27;
    --accent: #11303A; --ok: #5BD08F; --warn: #E5AC5C; --bad: #F2857A;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 18px 22px;
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.45;
  }
  body.wb-fs-active { overflow: hidden; }
  h1, strong { color: var(--fg); }
  h1 { margin: 0; font-size: 21px; font-weight: 700; }
  .topbar {
    display: flex; flex-wrap: wrap; justify-content: space-between;
    align-items: center; gap: 10px; margin-bottom: 14px;
  }
  .muted { color: var(--muted); font-size: 12px; }
  .card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 14px 16px; margin-bottom: 14px;
  }
  .source-grid {
    display: grid;
    grid-template-columns:
      minmax(250px, 2.4fr) minmax(120px, 0.9fr) minmax(130px, 0.9fr) auto;
    gap: 10px; align-items: end;
  }
  @media (max-width: 960px) { .source-grid { grid-template-columns: 1fr; } }
  label.field {
    display: flex; flex-direction: column; gap: 4px;
    font-size: 12px; color: var(--muted); font-weight: 600;
  }
  input[type="text"], input[type="number"] {
    background: var(--bg); color: var(--fg);
    border: 1px solid var(--border); border-radius: 8px;
    padding: 8px 10px; font-size: 13px; width: 100%;
  }
  input:focus { outline: none; border-color: var(--primary); }
  .checks {
    display: flex; flex-wrap: wrap; gap: 16px;
    margin-top: 10px; font-size: 13px; color: var(--text);
  }
  .checks label {
    display: inline-flex; align-items: center; gap: 6px; cursor: pointer;
  }
  button, .btn-link {
    background: var(--primary); color: var(--on-primary);
    border: 1px solid var(--primary); border-radius: 8px;
    padding: 8px 14px; font-size: 13px; font-weight: 600;
    cursor: pointer; text-decoration: none;
    display: inline-flex; align-items: center; justify-content: center;
  }
  button:hover, .btn-link:hover { filter: brightness(1.06); }
  button.secondary, .btn-link.secondary {
    background: var(--bg); border-color: var(--border);
    color: var(--fg); font-weight: 600;
  }
  button.secondary:hover, .btn-link.secondary:hover {
    border-color: var(--primary);
  }
  button.small, .btn-link.small { padding: 5px 10px; font-size: 12px; }
  button:disabled { opacity: 0.55; cursor: not-allowed; }
  .layout {
    display: grid; grid-template-columns: 280px 1fr;
    gap: 14px; align-items: start;
  }
  @media (max-width: 1080px) { .layout { grid-template-columns: 1fr; } }
  .panel-title {
    font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em;
    color: var(--muted); margin-bottom: 8px; font-weight: 700;
  }
  .cache-item {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 9px 10px; margin-bottom: 8px;
  }
  .cache-row {
    display: flex; justify-content: space-between;
    align-items: center; gap: 8px;
  }
  .status-banner {
    border-radius: 10px; padding: 10px 14px; margin-bottom: 14px;
    border: 1px solid var(--border); background: var(--card);
    display: flex; flex-wrap: wrap; justify-content: space-between;
    align-items: center; gap: 10px;
  }
  .status-banner.error {
    border-color: var(--bad); background: rgba(180, 35, 24, 0.12);
    color: var(--bad);
  }
  .status-banner.ok { border-color: var(--primary); }
  .progress-wrap {
    flex-basis: 100%; margin-top: 4px; padding-top: 8px;
    border-top: 1px solid var(--border);
  }
  .progress-head {
    display: flex; justify-content: space-between; align-items: center;
    gap: 10px; margin-bottom: 6px; font-size: 12px;
  }
  .progress-stage {
    display: inline-block; padding: 1px 7px; border-radius: 999px;
    font-size: 10.5px; font-weight: 700; letter-spacing: 0.04em;
    background: var(--accent); color: var(--fg); margin-right: 6px;
  }
  .progress-track {
    width: 100%; height: 8px; border-radius: 999px;
    background: var(--bg); border: 1px solid var(--border);
    overflow: hidden; position: relative;
  }
  .progress-fill {
    height: 100%; width: 0%; background: var(--primary);
    border-radius: 999px; transition: width 160ms ease;
  }
  @keyframes wb-indeterminate {
    0% { transform: translateX(-100%); }
    100% { transform: translateX(260%); }
  }
  .progress-fill.indeterminate {
    width: 38% !important;
    animation: wb-indeterminate 1.15s ease-in-out infinite;
  }
  .pill {
    display: inline-block; padding: 2px 8px; border-radius: 999px;
    font-size: 11px; font-weight: 700;
    background: var(--soft); border: 1px solid var(--border); color: var(--fg);
  }
  .pill.local { border-color: var(--ok); color: var(--ok); }
  .pill.online { border-color: var(--primary); color: var(--primary-strong); }
  .pill.cached { border-color: var(--warn); color: var(--warn); }
  .tabs-bar {
    display: flex; flex-wrap: wrap; justify-content: space-between;
    align-items: center; gap: 8px; margin-bottom: 12px;
  }
  .tabs { display: flex; flex-wrap: wrap; gap: 8px; }
  .tab-btn {
    background: var(--card); border: 1px solid var(--border);
    color: var(--muted); font-weight: 600;
  }
  .tab-btn.active {
    background: var(--primary); border-color: var(--primary);
    color: var(--on-primary);
  }
  .tab-pane { display: none; }
  .tab-pane.active { display: block; }
  .explorer-shell { position: relative; }
  .explorer-shell.fs-frame {
    position: fixed; inset: 0; z-index: 9999; background: var(--bg);
    padding: 0; margin: 0; width: 100vw; height: 100vh;
  }
  .fs-exit-bar {
    display: none; position: fixed; top: 10px; right: 14px; z-index: 10000;
  }
  .explorer-shell.fs-frame .fs-exit-bar { display: block; }
  iframe#explorer-frame {
    width: 100%; height: 800px; border: 1px solid var(--border);
    border-radius: 10px; background: var(--bg); display: block;
  }
  .explorer-shell.fs-frame iframe#explorer-frame {
    height: 100vh; border: 0; border-radius: 0;
  }
  pre.code-box {
    background: var(--bg); color: var(--fg);
    border: 1px solid var(--border); border-radius: 8px; padding: 12px;
    overflow: auto; max-height: 520px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12.5px; white-space: pre-wrap; word-break: break-word;
  }
  .slice-form {
    display: grid; grid-template-columns: 2fr 120px 100px auto;
    gap: 10px; align-items: end; margin-bottom: 12px;
  }
  @media (max-width: 820px) { .slice-form { grid-template-columns: 1fr; } }
  .list-card {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 8px 10px; margin-bottom: 8px; font-size: 13px;
  }
  code {
    background: var(--soft); color: var(--primary-strong);
    padding: 1px 5px; border-radius: 4px; font-size: 12px;
  }
"""


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
<style>{_WORKBENCH_CSS}</style>
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
    <div style="display:flex;align-items:center;gap:10px;">
      <div id="cache-root-label" class="muted"></div>
      <button id="wb-theme-btn" type="button" class="secondary small">Theme: system</button>
    </div>
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
    <div id="progress-wrap" class="progress-wrap" style="display:none;">
      <div class="progress-head">
        <div>
          <span id="progress-stage" class="progress-stage">RESOLVING</span>
          <span id="progress-msg" class="muted">Starting inspection...</span>
        </div>
        <div id="progress-metrics" class="muted">0% | 0.0s</div>
      </div>
      <div
        id="progress-track"
        class="progress-track"
        role="progressbar"
        aria-valuemin="0"
        aria-valuemax="100"
        aria-valuenow="0"
      >
        <div id="progress-fill" class="progress-fill indeterminate"></div>
      </div>
    </div>
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
      <div class="tabs-bar">
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
        <button type="button" id="wb-fs-btn" class="secondary small"
                onclick="toggleExplorerFullscreen()">Full Screen Explorer</button>
      </div>

      <section id="tab-explorer" class="tab-pane active">
        <div id="explorer-empty" class="card muted">
          No active inspection session yet.
        </div>
        <div id="explorer-shell" class="explorer-shell" style="display:none;">
          <div class="fs-exit-bar">
            <button type="button" class="small" onclick="toggleExplorerFullscreen(false)">
              Exit Full Screen (Esc)
            </button>
          </div>
          <iframe id="explorer-frame" allowfullscreen title="CodeOverlook Explorer"></iframe>
        </div>
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
let wbFullscreen = false;
let inspectToken = 0;
const WB_THEMES = ['system', 'light', 'dark'];
let wbTheme = 'system';

function esc(value) {{
  return String(value).replace(/[&<>"']/g, c => ({{
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }}[c]));
}}

document.getElementById('wb-theme-btn').addEventListener('click', () => {{
  wbTheme = WB_THEMES[(WB_THEMES.indexOf(wbTheme) + 1) % WB_THEMES.length];
  if (wbTheme === 'system') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme', wbTheme);
  document.getElementById('wb-theme-btn').textContent = 'Theme: ' + wbTheme;
}});

function toggleExplorerFullscreen(forceState) {{
  if (!activeSession) return;
  const next = typeof forceState === 'boolean' ? forceState : !wbFullscreen;
  wbFullscreen = next;
  if (next) switchTab('explorer');
  document.body.classList.toggle('wb-fs-active', next);
  document.getElementById('explorer-shell').classList.toggle('fs-frame', next);
}}

document.addEventListener('keydown', ev => {{
  if (ev.key === 'Escape' && wbFullscreen) toggleExplorerFullscreen(false);
}});

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

function updateProgressUi(stage, percent, message, elapsedMs) {{
  const wrap = document.getElementById('progress-wrap');
  const fill = document.getElementById('progress-fill');
  const track = document.getElementById('progress-track');
  const pct = Math.max(0, Math.min(100, Math.round(percent || 0)));
  wrap.style.display = 'block';
  document.getElementById('progress-stage').textContent = String(stage || 'working').toUpperCase();
  document.getElementById('progress-msg').textContent = message || 'Working...';
  const secs = ((elapsedMs || 0) / 1000).toFixed(1);
  document.getElementById('progress-metrics').textContent = `${{pct}}% | ${{secs}}s`;
  track.setAttribute('aria-valuenow', String(pct));
  if (stage === 'resolving' && pct < 15) {{
    fill.classList.add('indeterminate');
  }} else {{
    fill.classList.remove('indeterminate');
    fill.style.width = `${{pct}}%`;
  }}
}}

function hideProgressUi() {{
  document.getElementById('progress-wrap').style.display = 'none';
}}

function applyInspectResult(data) {{
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

  document.getElementById('explorer-empty').style.display = 'none';
  document.getElementById('explorer-shell').style.display = 'block';
  document.getElementById('explorer-frame').src = data.report_url;

  renderMermaid();
  renderRisks(data.cycles, data.violations);
  loadCache();
}}

async function runInspect() {{
  const target = document.getElementById('target-input').value.trim();
  if (!target) return;

  const myToken = ++inspectToken;
  const btn = document.getElementById('inspect-btn');
  btn.disabled = true;
  btn.textContent = 'Inspecting...';
  document.getElementById('status-actions').innerHTML = '';
  setStatus('Inspecting repository...', '');
  updateProgressUi('resolving', 5, `Resolving '${{target}}'...`, 0);

  try {{
    const payload = {{
      target,
      ref: document.getElementById('ref-input').value.trim() || null,
      subpath: document.getElementById('subpath-input').value.trim() || null,
      offline: document.getElementById('offline-check').checked,
      refresh: document.getElementById('refresh-check').checked,
      force: document.getElementById('force-check').checked
    }};
    const startRes = await fetch('/api/inspect/start', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify(payload)
    }});
    const startData = await startRes.json();
    if (myToken !== inspectToken) return;
    if (!startRes.ok) {{
      hideProgressUi();
      setStatus(
        '<strong>Error:</strong> ' + esc(startData.error || 'Inspection failed'),
        'error'
      );
      return;
    }}

    while (myToken === inspectToken) {{
      const jobRes = await fetch(startData.status_url);
      const job = await jobRes.json();
      if (myToken !== inspectToken) return;
      if (!jobRes.ok) {{
        hideProgressUi();
        setStatus('<strong>Error:</strong> ' + esc(job.error || 'Job lookup failed'), 'error');
        return;
      }}

      if (job.status === 'error') {{
        hideProgressUi();
        setStatus('<strong>Error:</strong> ' + esc(job.error || 'Inspection failed'), 'error');
        return;
      }}

      updateProgressUi(job.stage, job.percent, job.message, job.elapsed_ms);

      if (job.status === 'done' && job.result) {{
        updateProgressUi('done', 100, 'Inspection complete.', job.elapsed_ms);
        applyInspectResult(job.result);
        setTimeout(() => {{
          if (myToken === inspectToken) hideProgressUi();
        }}, 600);
        return;
      }}

      await new Promise(resolve => setTimeout(resolve, 150));
    }}
  }} catch (err) {{
    if (myToken !== inspectToken) return;
    hideProgressUi();
    setStatus('<strong>Error:</strong> ' + esc(err), 'error');
  }} finally {{
    if (myToken === inspectToken) {{
      btn.disabled = false;
      btn.textContent = 'Inspect';
    }}
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
