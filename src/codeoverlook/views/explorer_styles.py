"""CSS stylesheet for the standalone CodeOverlook interactive architecture explorer."""

from __future__ import annotations

EXPLORER_CSS = """
  :root {
    --bg: #F3F8F9; --card: #FFFFFF; --border: #DCE8EB; --fg: #0B2B36;
    --text: #2F4A56; --muted: #5B7480; --primary: #0E7C86;
    --primary-strong: #0A646C; --on-primary: #FFFFFF; --soft: #ECF6F7;
    --accent: #D2EAEC; --code: #0A646C; --ok: #1E7A4D; --warn: #8A5300;
    --bad: #B42318; --g-entry: #0B2B36; --g-services: #2563A8;
    --g-engine: #8F4206; --g-foundation: #44606B; --g-tests: #2563A8;
    --g-tooling: #64748B; --g-inherit: #6B4FA3;
    --edge-down: #0E7C86; --edge-up: #A8326B;
    --surface-glass: rgba(255, 255, 255, 0.92);
    --grid-dot: rgba(91, 116, 128, 0.22);
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #0D1117; --card: #121C23; --border: #263943; --fg: #E8F2F4;
      --text: #B9CBD1; --muted: #8CA4AD; --primary: #56C5CE;
      --primary-strong: #7ADCE3; --on-primary: #06242A; --soft: #131F27;
      --accent: #11303A; --code: #7ADCE3; --ok: #5BD08F; --warn: #E5AC5C;
      --bad: #F2857A; --g-entry: #E8F2F4; --g-services: #7FB2F0;
      --g-engine: #F0B35A; --g-foundation: #9FB4BD; --g-tests: #7FB2F0;
      --g-tooling: #94A3B8; --g-inherit: #B9A2E8;
      --edge-down: #56C5CE; --edge-up: #F08BB8;
      --surface-glass: rgba(18, 28, 35, 0.92);
      --grid-dot: rgba(140, 164, 173, 0.16);
    }
  }
  :root[data-theme="dark"] {
    --bg: #0D1117; --card: #121C23; --border: #263943; --fg: #E8F2F4;
    --text: #B9CBD1; --muted: #8CA4AD; --primary: #56C5CE;
    --primary-strong: #7ADCE3; --on-primary: #06242A; --soft: #131F27;
    --accent: #11303A; --code: #7ADCE3; --ok: #5BD08F; --warn: #E5AC5C;
    --bad: #F2857A; --g-entry: #E8F2F4; --g-services: #7FB2F0;
    --g-engine: #F0B35A; --g-foundation: #9FB4BD; --g-tests: #7FB2F0;
    --g-tooling: #94A3B8; --g-inherit: #B9A2E8;
    --edge-down: #56C5CE; --edge-up: #F08BB8;
    --surface-glass: rgba(18, 28, 35, 0.92);
    --grid-dot: rgba(140, 164, 173, 0.16);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    font-size: 14px; line-height: 1.45;
  }
  code, .mono {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    color: var(--code); font-size: 0.9em;
  }
  h1, h2, h3, strong { color: var(--fg); }
  h1 { margin: 4px 0; font-size: 21px; }
  h2 { margin: 0; font-size: 15px; }
  h3 { margin: 0; font-size: 15px; }
  button, input, select { font-family: inherit; color: inherit; }
  .wrap {
    max-width: 1720px; margin: 0 auto; padding: 16px 20px;
    display: flex; flex-direction: column; gap: 14px;
  }
  .card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px;
  }
  .subcard {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 9px; padding: 10px 12px;
  }
  .row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .between {
    display: flex; flex-wrap: wrap; align-items: flex-start;
    justify-content: space-between; gap: 12px;
  }
  .head {
    display: grid; grid-template-columns: minmax(0, 1fr) auto;
    gap: 16px; align-items: start;
  }
  .muted { color: var(--muted); font-size: 12.5px; }
  .small { font-size: 11.5px; }
  .hidden { display: none !important; }
  .pill {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 9px; border-radius: 999px; font-size: 11.5px;
    border: 1px solid var(--border); background: var(--soft);
    color: var(--text);
  }
  .pill-strong {
    background: var(--accent); color: var(--fg); font-weight: 600;
  }
  .pill-scale {
    background: var(--bg); color: var(--primary-strong); font-weight: 600;
  }
  .kpis {
    display: grid; grid-template-columns: repeat(5, minmax(78px, 1fr));
    gap: 8px; text-align: center;
  }
  .kpis-4 { grid-template-columns: repeat(4, 1fr); }
  .kpi {
    padding: 7px 6px; border-radius: 8px; background: var(--bg);
    border: 1px solid var(--border);
  }
  .kpi-v {
    font-size: 16px; font-weight: 700; color: var(--fg);
    font-variant-numeric: tabular-nums;
  }
  .kpi-l { font-size: 11px; color: var(--muted); }
  .tabs {
    display: flex; flex-wrap: wrap; gap: 8px; padding-top: 12px;
    border-top: 1px solid var(--border); margin-top: 12px;
  }
  .btn {
    padding: 6px 12px; border-radius: 8px; font-size: 12.5px;
    font-weight: 600; border: 1px solid var(--border);
    background: var(--bg); color: var(--fg); cursor: pointer;
    transition: border-color 150ms ease, background 150ms ease;
  }
  .btn:hover:not(:disabled) { border-color: var(--primary); }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn-sm { padding: 4px 10px; border-radius: 999px; font-size: 12px; }
  .btn-xs { padding: 3px 8px; border-radius: 999px; font-size: 11px; }
  .btn-on {
    background: var(--primary) !important;
    color: var(--on-primary) !important;
    border-color: var(--primary) !important;
  }
  .seg {
    display: inline-flex; align-items: center; gap: 2px; padding: 2px;
    border-radius: 999px; border: 1px solid var(--border); background: var(--bg);
  }
  .seg .btn-sm { border: 0; background: transparent; padding: 3px 9px; }
  .levels {
    display: flex; flex-wrap: wrap; border: 1px solid var(--border);
    border-radius: 10px; overflow: hidden;
  }
  .level {
    flex: 1 1 170px; padding: 9px 12px; border: 0;
    border-right: 1px solid var(--border); background: var(--bg);
    text-align: left; cursor: pointer;
  }
  .level:last-child { border-right: 0; }
  .level:hover:not(:disabled) { background: var(--soft); }
  .level.on { background: var(--primary); }
  .level .n {
    font-size: 11px; font-weight: 700; color: var(--muted);
    letter-spacing: 0.04em;
  }
  .level .t { font-size: 13.5px; font-weight: 700; color: var(--fg); }
  .level .c { font-size: 11.5px; color: var(--muted); }
  .level.on .n, .level.on .t, .level.on .c { color: var(--on-primary); }
  .diag-grid {
    display: grid; gap: 8px; margin-top: 8px;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  }
  .diag-card {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 9px; padding: 9px 11px; text-align: left;
    cursor: pointer; width: 100%;
  }
  .diag-card:hover { border-color: var(--primary); }
  .sev {
    display: inline-block; padding: 1px 6px; border-radius: 4px;
    font-size: 10.5px; font-weight: 700; color: #FFFFFF;
  }
  .sev-HIGH, .sev-CRITICAL { background: var(--bad); }
  .sev-MEDIUM { background: var(--warn); }
  .sev-INFO, .sev-LOW { background: var(--primary); }
  .panel-nav {
    display: flex; flex-wrap: wrap; align-items: center;
    justify-content: space-between; gap: 8px;
    padding-bottom: 10px; border-bottom: 1px solid var(--border);
    margin-bottom: 10px;
  }
  .crumbs {
    display: flex; flex-wrap: wrap; align-items: center; gap: 5px;
    font-size: 12.5px;
  }
  .crumb-btn {
    background: none; border: 0; padding: 2px 6px; border-radius: 6px;
    color: var(--primary-strong); font-weight: 600; cursor: pointer;
  }
  .crumb-btn:hover { background: var(--soft); }
  .qj-wrap { position: relative; min-width: 245px; max-width: 340px; flex: 1 1 245px; }
  .qj-input {
    width: 100%; padding: 5px 10px; border-radius: 8px;
    border: 1px solid var(--border); background: var(--bg);
    font-size: 12.5px;
  }
  .qj-input:focus { outline: 2px solid var(--primary); border-color: var(--primary); }
  .qj-dropdown {
    position: absolute; top: calc(100% + 4px); right: 0; left: 0; z-index: 60;
    background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; box-shadow: 0 12px 28px rgba(0, 0, 0, 0.16);
    max-height: 320px; overflow-y: auto; padding: 6px;
  }
  .qj-group {
    font-size: 10.5px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.04em; color: var(--muted); padding: 4px 8px 2px 8px;
  }
  .qj-item {
    display: flex; justify-content: space-between; align-items: center; gap: 8px;
    width: 100%; padding: 6px 8px; border-radius: 7px; border: 0;
    background: transparent; text-align: left; cursor: pointer; font-size: 12px;
  }
  .qj-item:hover, .qj-item.active { background: var(--soft); }
  .qj-item-sub { color: var(--muted); font-size: 11px; white-space: nowrap; }
  .grid-arch {
    display: grid; grid-template-columns: minmax(0, 1fr) 380px;
    gap: 16px; align-items: start;
  }
  .grid-2 {
    display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 12px; align-items: start;
  }
  @media (max-width: 1220px) {
    .grid-arch { grid-template-columns: 1fr; }
    .inspector { position: static !important; max-height: none !important; }
  }
  @media (max-width: 900px) {
    .head, .grid-2 { grid-template-columns: 1fr; }
    .kpis { grid-template-columns: repeat(3, 1fr); }
  }
  .inspector {
    position: sticky; top: 14px; display: flex; flex-direction: column;
    gap: 12px; max-height: calc(100vh - 28px); overflow-y: auto;
  }
  .sec {
    font-size: 11px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.04em; color: var(--muted); margin-bottom: 6px;
  }
  .scope-banner {
    display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
    gap: 8px; padding: 7px 10px; margin-bottom: 8px; border-radius: 8px;
    background: var(--soft); border: 1px solid var(--border); font-size: 12px;
  }
  .viewport-wrap {
    position: relative; border: 1px solid var(--border);
    border-radius: 10px; background: var(--bg); overflow: hidden;
  }
  .viewport-canvas {
    width: 100%; height: clamp(440px, 66vh, 860px);
    overflow: hidden; cursor: grab; touch-action: none;
    position: relative;
    background-image: radial-gradient(var(--grid-dot) 1px, transparent 1px);
    background-size: 20px 20px;
  }
  .viewport-canvas.dragging { cursor: grabbing; }
  .viewport-canvas svg {
    display: block; transform-origin: 0 0; user-select: none;
  }
  .svg-node { cursor: pointer; }
  .svg-node:hover { stroke: var(--primary); stroke-width: 2.2; }
  .svg-edge { transition: stroke-opacity 120ms ease, stroke-width 120ms ease; }
  .svg-edge:hover { stroke-opacity: 1 !important; stroke-width: 3 !important; }
  .lane-link { cursor: pointer; }
  .lane-link:hover { text-decoration: underline; fill: var(--primary); }
  .band-toggle { cursor: pointer; }
  .band-toggle:hover rect { stroke: var(--primary); }
  .vp-controls {
    position: absolute; left: 12px; bottom: 12px; z-index: 20;
    display: inline-flex; align-items: center; gap: 4px; padding: 4px 6px;
    border-radius: 999px; background: var(--surface-glass);
    border: 1px solid var(--border);
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.12);
    backdrop-filter: blur(6px);
  }
  .minimap-box {
    position: absolute; right: 12px; bottom: 12px; z-index: 20;
    width: 188px; border-radius: 10px; background: var(--surface-glass);
    border: 1px solid var(--border);
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.14);
    backdrop-filter: blur(6px); overflow: hidden;
  }
  .minimap-head {
    display: flex; align-items: center; justify-content: space-between;
    padding: 3px 8px; border-bottom: 1px solid var(--border);
    font-size: 10.5px; font-weight: 700; color: var(--muted);
  }
  .minimap-box.collapsed .minimap-body { display: none; }
  .minimap-box.collapsed { width: auto; }
  .minimap-body { padding: 4px; cursor: crosshair; }
  .minimap-body svg { display: block; width: 178px; height: 106px; }
  .hover-popover {
    position: absolute; z-index: 35; pointer-events: none;
    min-width: 220px; max-width: 300px; padding: 9px 11px;
    border-radius: 9px; background: var(--card); border: 1px solid var(--primary);
    box-shadow: 0 10px 26px rgba(0, 0, 0, 0.2); font-size: 12px;
  }
  .legend {
    display: flex; flex-wrap: wrap; gap: 8px 16px;
    font-size: 12px; color: var(--muted); padding-top: 10px;
  }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .swatch {
    width: 16px; height: 3px; border-radius: 2px; display: inline-block;
  }
  .layer-box {
    border: 1px solid var(--border); border-radius: 10px;
    padding: 11px; margin-bottom: 10px;
  }
  .layer-head {
    display: flex; flex-wrap: wrap; justify-content: space-between;
    gap: 8px; margin-bottom: 8px; font-size: 12px;
  }
  .cards {
    display: grid; gap: 8px;
    grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  }
  .node-card {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 9px 10px; cursor: pointer;
    text-align: left; width: 100%;
  }
  .node-card:hover { border-color: var(--primary); }
  .node-sel { outline: 2px solid var(--primary); outline-offset: 2px; }
  .node-rel { outline: 1.5px dashed var(--muted); outline-offset: 1px; }
  .tag {
    display: inline-block; padding: 1px 7px; border-radius: 5px;
    font-size: 10.5px; font-weight: 700; background: var(--accent);
    color: var(--fg); white-space: nowrap;
  }
  .tag-down { background: var(--edge-down); color: var(--on-primary); }
  .tag-up { background: var(--edge-up); color: var(--on-primary); }
  .tag-bad { background: var(--bad); color: #FFFFFF; }
  .status-pill {
    display: inline-block; padding: 2px 8px; border-radius: 999px;
    font-size: 11px; font-weight: 700; color: #FFFFFF;
  }
  .st-WELL_COVERED { background: var(--ok); }
  .st-PARTIAL { background: var(--warn); }
  .st-LOW { background: #C2410C; }
  .st-UNTESTED { background: var(--bad); }
  .file-btn {
    display: flex; justify-content: space-between; gap: 10px;
    width: 100%; padding: 5px 9px; border-radius: 6px;
    background: var(--bg); border: 1px solid var(--border);
    margin-bottom: 4px; font-size: 12px; cursor: pointer;
    text-align: left;
  }
  .file-btn:hover { border-color: var(--primary); }
  .link {
    background: none; border: 0; padding: 0; color: var(--primary-strong);
    cursor: pointer; font: inherit; text-decoration: underline;
    text-underline-offset: 2px; text-align: left;
  }
  .scroll {
    overflow: auto; max-height: 760px; border: 1px solid var(--border);
    border-radius: 10px;
  }
  table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
  th, td {
    padding: 8px 10px; border-bottom: 1px solid var(--border);
    text-align: left; vertical-align: top;
  }
  th {
    background: var(--bg); color: var(--muted); font-weight: 600;
    position: sticky; top: 0; z-index: 1;
  }
  th button {
    background: none; border: 0; padding: 0; font: inherit;
    font-weight: 600; color: inherit; cursor: pointer;
  }
  tr.click { cursor: pointer; }
  tr.click:hover { background: var(--soft); }
  tr.picked, tr.picked:hover {
    background: var(--accent); box-shadow: inset 3px 0 0 var(--primary);
  }
  input[type="search"] {
    padding: 6px 10px; border-radius: 8px; min-width: 240px;
    border: 1px solid var(--border); background: var(--bg);
    font-size: 12.5px;
  }
  .doc-clamp {
    color: var(--muted); display: -webkit-box;
    -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  body.fs-active { overflow: hidden; }
  .grid-arch.fs-mode {
    position: fixed; inset: 0; z-index: 9999; background: var(--bg);
    padding: 12px; margin: 0; width: 100vw; height: 100vh;
    grid-template-columns: minmax(0, 1fr) 380px;
  }
  .grid-arch.fs-mode.fs-hide-insp { grid-template-columns: minmax(0, 1fr); }
  .grid-arch.fs-mode.fs-hide-insp .inspector { display: none; }
  .grid-arch.fs-mode #arch-panel {
    height: calc(100vh - 24px); display: flex; flex-direction: column;
  }
  .grid-arch.fs-mode .viewport-wrap { flex: 1 1 auto; display: flex; }
  .grid-arch.fs-mode .viewport-canvas {
    flex: 1 1 auto; max-height: none; height: 100%;
  }
  .grid-arch.fs-mode #modules-arch {
    flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column;
  }
  .grid-arch.fs-mode #modules-arch .scroll { flex: 1 1 auto; max-height: none; }
  .grid-arch.fs-mode .inspector {
    position: static; max-height: calc(100vh - 24px);
  }
  .fs-levels { display: none; gap: 4px; }
  .grid-arch.fs-mode .fs-levels { display: inline-flex; }
  @media (max-width: 1040px) {
    .grid-arch.fs-mode { grid-template-columns: 1fr; }
    .grid-arch.fs-mode .inspector { max-height: 40vh; }
  }
"""
