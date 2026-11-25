"""Standalone interactive multi-level HTML explorer for architecture and coverage."""

from __future__ import annotations

import html
import json
from typing import Any

from codeoverlook.core.coverage import RepoCoverageReport
from codeoverlook.views.explorer_layout import build_explorer_model

_EXPLORER_CSS = """
  :root {
    --bg: #F3F8F9; --card: #FFFFFF; --border: #DCE8EB; --fg: #0B2B36;
    --text: #2F4A56; --muted: #5B7480; --primary: #0E7C86;
    --primary-strong: #0A646C; --on-primary: #FFFFFF; --soft: #ECF6F7;
    --accent: #D2EAEC; --code: #0A646C; --ok: #1E7A4D; --warn: #8A5300;
    --bad: #B42318; --g-entry: #0B2B36; --g-services: #2563A8;
    --g-engine: #8F4206; --g-foundation: #44606B; --g-tests: #2563A8;
    --edge-down: #0E7C86; --edge-up: #A8326B;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #0D1117; --card: #121C23; --border: #263943; --fg: #E8F2F4;
      --text: #B9CBD1; --muted: #8CA4AD; --primary: #56C5CE;
      --primary-strong: #7ADCE3; --on-primary: #06242A; --soft: #131F27;
      --accent: #11303A; --code: #7ADCE3; --ok: #5BD08F; --warn: #E5AC5C;
      --bad: #F2857A; --g-entry: #E8F2F4; --g-services: #7FB2F0;
      --g-engine: #F0B35A; --g-foundation: #9FB4BD; --g-tests: #7FB2F0;
      --edge-down: #56C5CE; --edge-up: #F08BB8;
    }
  }
  :root[data-theme="dark"] {
    --bg: #0D1117; --card: #121C23; --border: #263943; --fg: #E8F2F4;
    --text: #B9CBD1; --muted: #8CA4AD; --primary: #56C5CE;
    --primary-strong: #7ADCE3; --on-primary: #06242A; --soft: #131F27;
    --accent: #11303A; --code: #7ADCE3; --ok: #5BD08F; --warn: #E5AC5C;
    --bad: #F2857A; --g-entry: #E8F2F4; --g-services: #7FB2F0;
    --g-engine: #F0B35A; --g-foundation: #9FB4BD; --g-tests: #7FB2F0;
    --edge-down: #56C5CE; --edge-up: #F08BB8;
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
    max-width: 1680px; margin: 0 auto; padding: 16px 20px;
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
  .kpis {
    display: grid; grid-template-columns: repeat(5, minmax(78px, 1fr));
    gap: 8px; text-align: center;
  }
  .kpis-4 { grid-template-columns: repeat(4, 1fr); }
  .kpis-3 { grid-template-columns: repeat(3, 1fr); }
  .kpis-2 { grid-template-columns: repeat(2, 1fr); }
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
    transition: border-color 150ms ease;
  }
  .btn:hover { border-color: var(--primary); }
  .btn-sm { padding: 4px 10px; border-radius: 999px; font-size: 12px; }
  .btn-on {
    background: var(--primary) !important;
    color: var(--on-primary) !important;
    border-color: var(--primary) !important;
  }
  .levels {
    display: flex; flex-wrap: wrap; border: 1px solid var(--border);
    border-radius: 10px; overflow: hidden;
  }
  .level {
    flex: 1 1 180px; padding: 9px 12px; border: 0;
    border-right: 1px solid var(--border); background: var(--bg);
    text-align: left; cursor: pointer;
  }
  .level:last-child { border-right: 0; }
  .level:hover { background: var(--soft); }
  .level.on { background: var(--primary); }
  .level .n {
    font-size: 11px; font-weight: 700; color: var(--muted);
    letter-spacing: 0.04em;
  }
  .level .t { font-size: 13.5px; font-weight: 700; color: var(--fg); }
  .level .c { font-size: 11.5px; color: var(--muted); }
  .level.on .n, .level.on .t, .level.on .c { color: var(--on-primary); }
  .grid-arch {
    display: grid; grid-template-columns: minmax(0, 1fr) 365px;
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
  .viewport-wrap {
    position: relative; border: 1px solid var(--border);
    border-radius: 10px; background: var(--bg); overflow: hidden;
  }
  .viewport-canvas {
    width: 100%; min-height: 430px; max-height: 700px;
    overflow: hidden; cursor: grab; touch-action: none;
    position: relative;
  }
  .viewport-canvas.dragging { cursor: grabbing; }
  .viewport-canvas svg {
    display: block; transform-origin: 0 0; user-select: none;
  }
  .svg-node { cursor: pointer; }
  .svg-node:hover { stroke: var(--primary); stroke-width: 2.2; }
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
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
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
  /* Full-screen mode: covers viewport cleanly even inside an iframe */
  body.fs-active { overflow: hidden; }
  .grid-arch.fs-mode {
    position: fixed; inset: 0; z-index: 9999; background: var(--bg);
    padding: 12px; margin: 0; width: 100vw; height: 100vh;
    grid-template-columns: minmax(0, 1fr) 365px;
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
  .grid-arch.fs-mode .inspector {
    position: static; max-height: calc(100vh - 24px);
  }
  @media (max-width: 1040px) {
    .grid-arch.fs-mode { grid-template-columns: 1fr; }
    .grid-arch.fs-mode .inspector { max-height: 40vh; }
  }
"""

_EXPLORER_JS = r"""
const DATA = __DATA_JSON__;
const $ = id => document.getElementById(id);
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
}[c]));

let topTab = "arch";
let level = "blocks";     // "blocks" | "packages" | "modules"
let viewMode = "svg";     // "svg" | "cards"
let overlay = "arch";     // "arch" | "coverage" | "security"
let everyImport = false;
let scope = null;         // { level: "blocks"|"packages", id: string } | null
let gapFilter = "ALL";
let sortKey = "path";
let sortDown = false;
let isFullscreen = false;
let fsShowInspector = true;

let panX = 16, panY = 16, zoom = 1;
let lastLayout = { width: 920, height: 420 };
let dragState = null;
let dragMoved = false;

const BLOCK_MAP = Object.fromEntries(DATA.blocks.map(b => [b.id, b]));
const PKG_MAP = Object.fromEntries(DATA.packages.map(p => [p.id, p]));
const MOD_MAP = Object.fromEntries(DATA.modules.map(m => [m.path, m]));
const BAND_MAP = Object.fromEntries(DATA.bands.map(b => [b.id, b]));

const picked = {
  blocks: DATA.blocks.length ? DATA.blocks[0].id : null,
  packages: DATA.packages.length ? DATA.packages[0].id : null,
  modules: DATA.modules.length ? DATA.modules[0].path : null
};

const THEME_MODES = ["system", "light", "dark"];
let themeMode = "system";

function applyTheme(mode) {
  themeMode = mode;
  if (mode === "system") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", mode);
  }
  $("theme-btn").textContent = "Theme: " + mode;
}

$("theme-btn").addEventListener("click", () => {
  const next = THEME_MODES[(THEME_MODES.indexOf(themeMode) + 1) % THEME_MODES.length];
  applyTheme(next);
});

function writeHash() {
  const target = level === "modules" ? picked.modules : picked[level];
  if (target) {
    history.replaceState(null, "", `#/${level}/${encodeURIComponent(target)}`);
  }
}

function readHash() {
  const h = (location.hash || "").replace(/^#\/?/, "");
  if (!h) return;
  const idx = h.indexOf("/");
  if (idx === -1) return;
  const lvl = h.slice(0, idx);
  const id = decodeURIComponent(h.slice(idx + 1));
  if (lvl === "blocks" && BLOCK_MAP[id]) { level = "blocks"; picked.blocks = id; }
  else if (lvl === "packages" && PKG_MAP[id]) { level = "packages"; picked.packages = id; }
  else if (lvl === "modules" && MOD_MAP[id]) { level = "modules"; picked.modules = id; }
}

function renderHeader() {
  const s = DATA.summary;
  $("pill-repo").textContent = DATA.repo_name;
  $("pill-tests").textContent =
    `${s.linked_test_files}/${s.total_test_files} linked test files `
    + `(${s.total_test_functions} fns)`;
  const pills = [
    [s.blocks_count, "Blocks"],
    [s.modules_count, "Modules"],
    [s.prod_loc.toLocaleString(), "Prod LOC"],
    [`${s.overall_file_coverage_pct.toFixed(0)}%`, "File cov"],
    [s.untested_sinks, "Unt. sinks"]
  ];
  $("header-kpis").innerHTML = pills.map(([v, l]) =>
    `<div class="kpi"><div class="kpi-v">${esc(v)}</div><div class="kpi-l">${esc(l)}</div></div>`
  ).join("");
}

function setTopTab(tab) {
  topTab = tab;
  document.querySelectorAll("[data-toptab]").forEach(b => {
    b.classList.toggle("btn-on", b.dataset.toptab === tab);
  });
  $("panel-arch-root").classList.toggle("hidden", tab !== "arch");
  $("panel-gaps").classList.toggle("hidden", tab !== "gaps");
  $("panel-risks").classList.toggle("hidden", tab !== "risks");
  if (tab === "gaps") renderGapsTab();
  if (tab === "risks") renderRisksTab();
}

function renderLevels() {
  const items = [
    ["blocks", "Level 1", "Functional Blocks", `${DATA.blocks.length} blocks`],
    ["packages", "Level 2", "Packages & Bricks", `${DATA.packages.length} packages`],
    ["modules", "Level 3", "Every Module", `${DATA.modules.length} modules`]
  ];
  $("levels").innerHTML = items.map(([id, n, t, c]) => {
    const disabled = id !== "blocks" && ((id === "packages" && !DATA.packages.length)
      || (id === "modules" && !DATA.modules.length));
    return `<button class="level ${level === id ? "on" : ""}" data-level="${id}" `
      + `${disabled ? "disabled" : ""}>`
      + `<div class="n">${n}</div><div class="t">${t}</div>`
      + `<div class="c">${c}</div></button>`;
  }).join("");
  $("levels").querySelectorAll("[data-level]").forEach(btn => {
    btn.addEventListener("click", () => {
      level = btn.dataset.level;
      if (level !== "modules") scope = null;
      refreshAll();
    });
  });

  if (scope) {
    const label = scope.level === "blocks" ? `Block: ${scope.id}` : `Package: ${scope.id}`;
    $("scope-bar").classList.remove("hidden");
    $("scope-bar").innerHTML = `Filtered to <strong>${esc(label)}</strong> `
      + `<button class="btn btn-sm" id="clear-scope">Show all</button>`;
    $("clear-scope").addEventListener("click", () => {
      scope = null;
      refreshAll();
    });
  } else {
    $("scope-bar").classList.add("hidden");
  }
}

function activeNodesAndEdges() {
  if (level === "packages") {
    let nodes = DATA.packages;
    if (scope && scope.level === "blocks") {
      nodes = nodes.filter(p => p.block_id === scope.id);
    }
    const ids = new Set(nodes.map(n => n.id));
    const edges = DATA.package_edges.filter(e => ids.has(e.u) && ids.has(e.v));
    return { nodes, edges, nodeMap: PKG_MAP };
  }
  return { nodes: DATA.blocks, edges: DATA.block_edges, nodeMap: BLOCK_MAP };
}

function nodeAccent(n) {
  if (overlay === "coverage") {
    return ({
      WELL_COVERED: "var(--ok)", PARTIAL: "var(--warn)",
      LOW: "#C2410C", UNTESTED: "var(--bad)"
    })[n.coverage_status] || "var(--muted)";
  }
  if (overlay === "security") {
    if ((n.untested_sinks || 0) > 0) return "var(--bad)";
    if ((n.sensitive_sinks || 0) > 0) return "var(--warn)";
    return "var(--ok)";
  }
  const b = BAND_MAP[n.band];
  return b ? `var(--g-${b.group})` : "var(--primary)";
}

function nodeSubtitle(n) {
  if (overlay === "coverage") {
    return `${n.tested_files}/${n.prod_files} tested (${n.file_coverage_pct.toFixed(0)}%)`;
  }
  if (overlay === "security") {
    return `${n.sensitive_sinks || 0} sinks (${n.untested_sinks || 0} untested)`;
  }
  return `${n.prod_files} files | ${n.prod_loc} LOC`;
}

function layoutDiagram(nodes, edges) {
  const bandRows = DATA.bands.map(b => ({
    band: b,
    items: nodes.filter(n => n.band === b.id)
  })).filter(r => r.items.length > 0);

  if (!bandRows.length) {
    return { width: 820, height: 240, bands: [], boxes: {}, edges: [] };
  }

  const labelW = 164;
  const nodeW = 166;
  const nodeH = 54;
  const gapX = 28;
  const gapY = 26;
  const padX = 24;
  const padY = 20;

  const maxPerRow = Math.max(1, ...bandRows.map(r => r.items.length));
  const colsCap = Math.min(5, Math.max(2, maxPerRow));
  const contentW = colsCap * nodeW + (colsCap - 1) * gapX + padX * 2;
  const totalW = labelW + contentW + 34;

  let curY = 14;
  const placedBands = [];
  const boxes = {};

  bandRows.forEach(row => {
    const rowsCount = Math.ceil(row.items.length / colsCap);
    const bandH = Math.max(92, padY * 2 + rowsCount * nodeH + (rowsCount - 1) * gapY);
    placedBands.push({
      band: row.band,
      x: 10, y: curY, w: totalW - 34, h: bandH, labelW
    });

    row.items.forEach((n, idx) => {
      const rIdx = Math.floor(idx / colsCap);
      const cIdx = idx % colsCap;
      const inThisRow = Math.min(colsCap, row.items.length - rIdx * colsCap);
      const rowSpan = inThisRow * nodeW + (inThisRow - 1) * gapX;
      const startX = labelW + (contentW - rowSpan) / 2;
      boxes[n.id] = {
        x: startX + cIdx * (nodeW + gapX),
        y: curY + padY + rIdx * (nodeH + gapY),
        w: nodeW, h: nodeH
      };
    });

    curY += bandH + 14;
  });

  return { width: totalW, height: curY + 8, bands: placedBands, boxes, edges };
}

function applyTransform() {
  const svg = $("arch-svg");
  if (!svg) return;
  svg.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom})`;
  $("zoom-label").textContent = `${Math.round(zoom * 100)}%`;
}

function fitToViewport() {
  const canvas = $("viewport-canvas");
  if (!canvas || !lastLayout.width) return;
  const cw = Math.max(260, canvas.clientWidth - 20);
  const ch = Math.max(240, canvas.clientHeight - 20);
  const scale = Math.min(cw / lastLayout.width, ch / lastLayout.height, 1.35);
  zoom = Math.max(0.35, Math.min(2.5, scale));
  panX = Math.max(8, (canvas.clientWidth - lastLayout.width * zoom) / 2);
  panY = Math.max(8, (canvas.clientHeight - lastLayout.height * zoom) / 2);
  applyTransform();
}

function orthoPath(srcBox, dstBox, idx) {
  const sx = srcBox.x + srcBox.w / 2;
  const sy = srcBox.y + srcBox.h;
  const dx = dstBox.x + dstBox.w / 2;
  const dy = dstBox.y;
  const offset = ((idx % 5) - 2) * 6;

  if (Math.abs(srcBox.y - dstBox.y) < 5) {
    const loopY = srcBox.y + srcBox.h + 14 + (idx % 4) * 5;
    return `M ${sx} ${sy} L ${sx} ${loopY} L ${dx} ${loopY} L ${dx} ${sy + 2}`;
  }
  if (sy < dy) {
    const midY = (sy + dy) / 2 + offset;
    return `M ${sx} ${sy} L ${sx} ${midY} L ${dx} ${midY} L ${dx} ${dy}`;
  }
  const topY = dstBox.y - 14 - (idx % 4) * 5;
  const sideX = Math.max(srcBox.x + srcBox.w, dstBox.x + dstBox.w) + 18 + (idx % 4) * 6;
  return `M ${sx} ${srcBox.y} L ${sx} ${srcBox.y - 10} L ${sideX} ${srcBox.y - 10} `
    + `L ${sideX} ${topY} L ${dx} ${topY} L ${dx} ${dy}`;
}

function renderSvgView(fitOnRender) {
  const { nodes, edges, nodeMap } = activeNodesAndEdges();
  if (!nodes.length) {
    $("viewport-canvas").innerHTML = `<div class="muted" style="padding:20px;">No nodes.</div>`;
    return;
  }
  if (!picked[level] || !nodeMap[picked[level]]) {
    picked[level] = nodes[0].id;
  }
  const chosen = picked[level];
  const sel = nodeMap[chosen];
  const uses = new Set(sel.imports || []);
  const usedBy = new Set(sel.imported_by || []);

  const layout = layoutDiagram(nodes, edges);
  lastLayout = layout;

  const bandsSvg = layout.bands.map(b => {
    const c = `var(--g-${b.band.group})`;
    return `<g>`
      + `<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="8" `
      + `fill="${c}" fill-opacity="0.05" stroke="${c}" stroke-opacity="0.3"/>`
      + `<rect x="${b.x}" y="${b.y}" width="${b.labelW}" height="${b.h}" rx="8" `
      + `fill="${c}" fill-opacity="0.12"/>`
      + `<text x="${b.x + 12}" y="${b.y + 20}" font-size="11" font-weight="700" `
      + `fill="${c}">${esc(b.band.label)}</text>`
      + `<text x="${b.x + 12}" y="${b.y + 38}" font-size="12.5" font-weight="700" `
      + `fill="var(--fg)">${esc(b.band.title)}</text>`
      + `<text x="${b.x + 12}" y="${b.y + b.h - 10}" font-size="10" `
      + `fill="var(--muted)">${esc(b.band.desc.slice(0, 26))}</text>`
      + `</g>`;
  }).join("");

  const shownEdges = everyImport
    ? edges
    : edges.filter(e => e.u === chosen || e.v === chosen);

  const arrowsSvg = shownEdges.map((e, idx) => {
    const sb = layout.boxes[e.u];
    const db = layout.boxes[e.v];
    if (!sb || !db) return "";
    const isOut = e.u === chosen;
    const isIn = e.v === chosen;
    let stroke = "var(--muted)";
    let marker = "m-muted";
    let opacity = "0.42";
    let sw = 1.2;
    let dash = "";
    if (e.violation) {
      stroke = "var(--bad)"; marker = "m-bad"; opacity = "0.95";
      sw = 2.2; dash = 'stroke-dasharray="5 3"';
    } else if (isOut) {
      stroke = "var(--edge-down)"; marker = "m-down"; opacity = "0.95";
      sw = Math.min(3.5, 1.5 + Math.log2(1 + e.n) * 0.6);
    } else if (isIn) {
      stroke = "var(--edge-up)"; marker = "m-up"; opacity = "0.95";
      sw = Math.min(3.5, 1.5 + Math.log2(1 + e.n) * 0.6);
    }
    const d = orthoPath(sb, db, idx);
    return `<path d="${d}" fill="none" stroke="${stroke}" stroke-opacity="${opacity}" `
      + `stroke-width="${sw}" ${dash} marker-end="url(#${marker})">`
      + `<title>${esc(e.u)} -> ${esc(e.v)} (${e.n} imports)</title></path>`;
  }).join("");

  const nodesSvg = nodes.map(n => {
    const p = layout.boxes[n.id];
    const isSel = n.id === chosen;
    const isUse = uses.has(n.id);
    const isUsedBy = usedBy.has(n.id);
    const hasViolation = shownEdges.some(
      e => e.violation && ((e.u === chosen && e.v === n.id) || (e.v === chosen && e.u === n.id))
    );
    const dim = !everyImport && !isSel && !isUse && !isUsedBy;
    const accent = nodeAccent(n);
    const stroke = hasViolation ? "var(--bad)" : isSel ? "var(--primary)"
      : isUse ? "var(--edge-down)" : isUsedBy ? "var(--edge-up)" : "var(--border)";
    const sw = isSel ? 2.4 : (isUse || isUsedBy) ? 1.8 : 1.2;
    const badge = hasViolation ? "VIOLATION" : isSel ? "FOCUS"
      : isUse ? "IMPORTED" : isUsedBy ? "IMPORTS IT" : "";
    const badgeBg = hasViolation ? "var(--bad)" : isSel ? "var(--primary)"
      : isUse ? "var(--edge-down)" : "var(--edge-up)";
    const bw = badge.length * 6.2 + 12;
    const titleTxt = n.title.length > 20 ? n.title.slice(0, 18) + ".." : n.title;

    let badgeEl = "";
    if (badge) {
      badgeEl = `<rect x="${p.x + p.w - bw - 6}" y="${p.y - 8}" width="${bw}" height="15" `
        + `rx="7.5" fill="${badgeBg}"/>`
        + `<text x="${p.x + p.w - bw / 2 - 6}" y="${p.y + 3}" text-anchor="middle" `
        + `font-size="9" font-weight="700" fill="var(--on-primary)">${badge}</text>`;
    }

    return `<g opacity="${dim ? 0.52 : 1}">`
      + `<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="7" `
      + `fill="var(--card)" stroke="${stroke}" stroke-width="${sw}"/>`
      + `<rect x="${p.x}" y="${p.y}" width="5" height="${p.h}" rx="2" fill="${accent}"/>`
      + `<text x="${p.x + 14}" y="${p.y + 23}" font-size="12.5" font-weight="700" `
      + `fill="var(--fg)">${esc(titleTxt)}</text>`
      + `<text x="${p.x + 14}" y="${p.y + 41}" font-size="10.5" `
      + `fill="var(--muted)">${esc(nodeSubtitle(n))}</text>`
      + badgeEl
      + `<rect class="svg-node" data-node="${esc(n.id)}" x="${p.x}" y="${p.y}" `
      + `width="${p.w}" height="${p.h}" rx="7" fill="transparent"/>`
      + `</g>`;
  }).join("");

  const topY = layout.bands[0].y + 8;
  const botBand = layout.bands[layout.bands.length - 1];
  const botY = botBand.y + botBand.h - 8;
  const guideX = layout.width - 12;
  const guideSvg = layout.bands.length > 1
    ? `<line x1="${guideX}" y1="${topY}" x2="${guideX}" y2="${botY}" `
      + `stroke="var(--muted)" stroke-width="1.3" marker-end="url(#m-muted)"/>`
      + `<text transform="translate(${guideX - 7},${(topY + botY) / 2}) rotate(-90)" `
      + `text-anchor="middle" font-size="10" font-weight="700" fill="var(--muted)" `
      + `letter-spacing="0.5">IMPORTS FLOW DOWN</text>`
    : "";

  const marker = (id, fill) => `<marker id="${id}" viewBox="0 0 10 10" refX="9" refY="5" `
    + `markerUnits="userSpaceOnUse" markerWidth="7" markerHeight="7" orient="auto">`
    + `<path d="M1,1.5 L9,5 L1,8.5 z" fill="${fill}"/></marker>`;

  $("viewport-canvas").innerHTML =
    `<svg id="arch-svg" width="${layout.width}" height="${layout.height}" `
    + `viewBox="0 0 ${layout.width} ${layout.height}">`
    + `<defs>${marker("m-muted", "var(--muted)")}${marker("m-down", "var(--edge-down)")}`
    + `${marker("m-up", "var(--edge-up)")}${marker("m-bad", "var(--bad)")}</defs>`
    + `${bandsSvg}${guideSvg}${arrowsSvg}${nodesSvg}</svg>`;

  $("viewport-canvas").querySelectorAll("[data-node]").forEach(el => {
    el.addEventListener("click", ev => {
      if (dragMoved) return;
      ev.stopPropagation();
      picked[level] = el.dataset.node;
      refreshAll(false);
    });
  });

  $("diagram-legend").innerHTML = `
    <span><i class="swatch" style="background:var(--edge-down)"></i>Focus imports it</span>
    <span><i class="swatch" style="background:var(--edge-up)"></i>Imports the focus</span>
    <span><i class="swatch" style="background:var(--bad)"></i>Forbidden boundary violation</span>
    <span>Drag background to pan | Ctrl+wheel (or wheel in full screen) to zoom</span>`;

  if (fitOnRender) fitToViewport();
  else applyTransform();
}

function renderCardsView() {
  const { nodes, nodeMap } = activeNodesAndEdges();
  if (!nodes.length) {
    $("cards-arch").innerHTML = `<div class="muted">No items to display.</div>`;
    return;
  }
  const chosen = picked[level] || nodes[0].id;
  const sel = nodeMap[chosen] || nodes[0];
  const uses = new Set(sel.imports || []);
  const usedBy = new Set(sel.imported_by || []);

  $("cards-arch").innerHTML = DATA.bands.map(b => {
    const items = nodes.filter(n => n.band === b.id);
    if (!items.length) return "";
    const color = `var(--g-${b.group})`;
    const cardsHtml = items.map(n => {
      const isSel = n.id === chosen;
      const tag = isSel ? `<span class="tag">FOCUS</span>`
        : uses.has(n.id) ? `<span class="tag tag-down">IMPORTED</span>`
        : usedBy.has(n.id) ? `<span class="tag tag-up">IMPORTS IT</span>` : "";
      const cls = isSel ? "node-sel" : (uses.has(n.id) || usedBy.has(n.id)) ? "node-rel" : "";
      return `<button class="node-card ${cls}" data-card="${esc(n.id)}">`
        + `<div class="between" style="margin-bottom:4px;">`
        + `<strong>${esc(n.title)}</strong>${tag}</div>`
        + `<div class="muted">${esc(nodeSubtitle(n))}</div></button>`;
    }).join("");
    return `<div class="layer-box" style="border-left:4px solid ${color};">`
      + `<div class="layer-head"><div><strong style="color:${color};">${esc(b.label)}</strong> `
      + `<strong>${esc(b.title)}</strong></div><span class="muted">${esc(b.desc)}</span></div>`
      + `<div class="cards">${cardsHtml}</div></div>`;
  }).join("");

  $("cards-arch").querySelectorAll("[data-card]").forEach(btn => {
    btn.addEventListener("click", () => {
      picked[level] = btn.dataset.card;
      refreshAll(false);
    });
  });
}

function renderModulesView() {
  const q = ($("module-search").value || "").trim().toLowerCase();
  let rows = DATA.modules;
  if (scope) {
    if (scope.level === "blocks") rows = rows.filter(m => m.block_id === scope.id);
    else if (scope.level === "packages") rows = rows.filter(m => m.package_id === scope.id);
  }
  if (q) {
    rows = rows.filter(m =>
      `${m.path} ${m.block_id} ${m.docstring} ${(m.external_libs || []).join(" ")}`
        .toLowerCase().includes(q)
    );
  }

  const sorters = {
    path: (a, b) => a.path.localeCompare(b.path),
    block: (a, b) => a.block_id.localeCompare(b.block_id),
    loc: (a, b) => a.loc - b.loc,
    imports: (a, b) => a.imports.length - b.imports.length,
    used: (a, b) => a.imported_by.length - b.imported_by.length,
    sinks: (a, b) => a.sinks - b.sinks
  };
  const fn = sorters[sortKey] || sorters.path;
  rows = [...rows].sort((a, b) => (sortDown ? -1 : 1) * fn(a, b));

  if (rows.length && (!picked.modules || !rows.some(r => r.path === picked.modules))) {
    picked.modules = rows[0].path;
  }

  const th = (key, label) =>
    `<th><button data-sort="${key}">${label}`
    + `${sortKey === key ? (sortDown ? " v" : " ^") : ""}</button></th>`;

  $("modules-arch").innerHTML = `
    <div class="muted" style="margin-bottom:8px;">
      Showing ${rows.length} of ${DATA.modules.length} production modules.
    </div>
    <div class="scroll">
      <table>
        <thead><tr>
          ${th("path", "Module & Docstring")}
          ${th("block", "Block")}
          ${th("loc", "LOC")}
          ${th("imports", "Imports")}
          ${th("used", "Imported by")}
          ${th("sinks", "Sinks")}
        </tr></thead>
        <tbody>
          ${rows.map(m => {
            const cls = m.path === picked.modules ? "picked" : "";
            const covTag = m.tested
              ? `<span class="tag tag-down">TESTED</span>`
              : `<span class="tag">UNTESTED</span>`;
            return `<tr class="click ${cls}" data-mod="${esc(m.path)}">`
              + `<td><div class="mono">${esc(m.path)} ${covTag}</div>`
              + `<div class="doc-clamp">${esc(m.docstring || "No module docstring.")}</div></td>`
              + `<td>${esc(m.block_id)}</td>`
              + `<td>${m.loc}</td>`
              + `<td>${m.imports.length}</td>`
              + `<td>${m.imported_by.length}</td>`
              + `<td>${m.sinks}</td></tr>`;
          }).join("")}
        </tbody>
      </table>
    </div>`;

  $("modules-arch").querySelectorAll("[data-sort]").forEach(b => {
    b.addEventListener("click", () => {
      const k = b.dataset.sort;
      sortDown = sortKey === k ? !sortDown : k !== "path" && k !== "block";
      sortKey = k;
      renderModulesView();
    });
  });

  $("modules-arch").querySelectorAll("[data-mod]").forEach(tr => {
    tr.addEventListener("click", () => {
      picked.modules = tr.dataset.mod;
      renderModulesView();
      renderInspector();
      writeHash();
    });
  });
}

function renderArchArea(fitOnRender) {
  const isMod = level === "modules";
  $("arch-tools").classList.toggle("hidden", isMod);
  $("module-tools").classList.toggle("hidden", !isMod);
  $("diagram-wrap-block").classList.toggle("hidden", isMod || viewMode !== "svg");
  $("cards-arch").classList.toggle("hidden", isMod || viewMode !== "cards");
  $("modules-arch").classList.toggle("hidden", !isMod);

  document.querySelectorAll("[data-view]").forEach(b => {
    b.classList.toggle("btn-on", b.dataset.view === viewMode);
  });
  document.querySelectorAll("[data-overlay]").forEach(b => {
    b.classList.toggle("btn-on", b.dataset.overlay === overlay);
  });
  $("every-import-btn").classList.toggle("btn-on", everyImport);

  if (isMod) {
    $("arch-title").textContent = "Module Catalog";
    $("arch-subtitle").textContent = "Search docstrings, sort metrics, and inspect symbols.";
    renderModulesView();
  } else if (viewMode === "svg") {
    $("arch-title").textContent =
      level === "blocks" ? "Functional Block Architecture" : "Package Architecture";
    $("arch-subtitle").textContent =
      "Layered top-down by dependency flow. Click any node to focus its imports and tests.";
    renderSvgView(fitOnRender);
  } else {
    $("arch-title").textContent =
      level === "blocks" ? "Functional Blocks (Cards)" : "Packages & Bricks (Cards)";
    $("arch-subtitle").textContent = "Grouped by architectural band.";
    renderCardsView();
  }
}

function renderInspector() {
  const box = $("inspector");
  if (level === "modules") {
    const m = MOD_MAP[picked.modules];
    if (!m) {
      box.innerHTML = `<div class="muted">Select a module row to inspect details.</div>`;
      return;
    }
    const libs = (m.external_libs || []).map(l => `<span class="pill">${esc(l)}</span>`).join("");
    const syms = (m.symbols || []).map(s =>
      `<div class="subcard" style="margin-bottom:4px;">`
      + `<div class="mono">${esc(s.signature)}</div>`
      + `<div class="muted small">${esc(s.kind)} | line ${s.start_line}</div></div>`
    ).join("");
    const impChips = m.imports.length
      ? m.imports.map(
          p => `<button class="btn btn-sm" data-jump-mod="${esc(p)}">${esc(p)}</button>`
        ).join("")
      : `<span class="muted">None</span>`;
    const byChips = m.imported_by.length
      ? m.imported_by.map(
          p => `<button class="btn btn-sm" data-jump-mod="${esc(p)}">${esc(p)}</button>`
        ).join("")
      : `<span class="muted">None</span>`;
    const libsOut = libs || '<span class="muted">Stdlib / internal only</span>';
    const symsOut = syms || '<span class="muted">Module-level script</span>';

    box.innerHTML = `
      <div style="border-bottom:1px solid var(--border);padding-bottom:10px;">
        <div class="sec" style="color:var(--primary);">${esc(m.block_id)} | Module</div>
        <h3 class="mono" style="overflow-wrap:anywhere;">${esc(m.path)}</h3>
        <p class="muted" style="margin-top:6px;">${esc(m.docstring || "No module docstring.")}</p>
      </div>
      <div class="kpis kpis-4">
        <div class="kpi"><div class="kpi-v">${m.loc}</div><div class="kpi-l">LOC</div></div>
        <div class="kpi">
          <div class="kpi-v">${m.symbol_count}</div><div class="kpi-l">Symbols</div>
        </div>
        <div class="kpi">
          <div class="kpi-v">${m.imports.length}</div><div class="kpi-l">Imports</div>
        </div>
        <div class="kpi">
          <div class="kpi-v">${m.imported_by.length}</div><div class="kpi-l">Callers</div>
        </div>
      </div>
      <div>
        <div class="sec">Zoom Out</div>
        <div class="row">
          <button class="btn btn-sm" data-zoom="blocks:${esc(m.block_id)}">
            Block: ${esc(m.block_id)}
          </button>
          <button class="btn btn-sm" data-zoom="packages:${esc(m.package_id)}">Package</button>
        </div>
      </div>
      <div><div class="sec">External Libraries</div><div class="row">${libsOut}</div></div>
      <div>
        <div class="sec">Top Symbols (${(m.symbols || []).length})</div>${symsOut}
      </div>
      <div>
        <div class="sec">It Imports (${m.imports.length})</div>
        <div class="row">${impChips}</div>
      </div>
      <div>
        <div class="sec">Imported By (${m.imported_by.length})</div>
        <div class="row">${byChips}</div>
      </div>
      <div class="subcard">
        <div class="sec">AI Context Slice</div>
        <code>codeoverlook slice ${esc(m.path)} --budget 2500</code>
      </div>`;

    box.querySelectorAll("[data-jump-mod]").forEach(b => b.addEventListener("click", () => {
      picked.modules = b.dataset.jumpMod;
      renderModulesView();
      renderInspector();
      writeHash();
    }));
    box.querySelectorAll("[data-zoom]").forEach(b => b.addEventListener("click", () => {
      const [lvl, id] = b.dataset.zoom.split(":");
      level = lvl; picked[lvl] = id; scope = null;
      refreshAll(true);
    }));
    return;
  }

  const isPkg = level === "packages";
  const node = isPkg ? PKG_MAP[picked.packages] : BLOCK_MAP[picked.blocks];
  if (!node) {
    box.innerHTML = `<div class="muted">Select a node in the diagram.</div>`;
    return;
  }
  const band = BAND_MAP[node.band];
  const libs = (node.external_libs || []).map(l => `<span class="pill">${esc(l)}</span>`).join("");
  const largest = (node.largest_files || []).map(f =>
    `<button class="file-btn mono" data-open-mod="${esc(f.path)}">`
    + `<span>${esc(f.path)}</span><span>${f.loc} LOC</span></button>`
  ).join("");
  const impChips = (node.imports || []).length
    ? node.imports.map(
        id => `<button class="btn btn-sm" data-jump-node="${esc(id)}">-&gt; ${esc(id)}</button>`
      ).join("")
    : `<span class="muted">None</span>`;
  const byChips = (node.imported_by || []).length
    ? node.imported_by.map(
        id => `<button class="btn btn-sm" data-jump-node="${esc(id)}">&lt;- ${esc(id)}</button>`
      ).join("")
    : `<span class="muted">None</span>`;
  const findingsHtml = (node.findings || []).slice(0, 6).map(f =>
    `<div class="subcard" style="margin-bottom:5px;">`
    + `<strong>${esc(f.severity)} ${esc(f.rule_id)}</strong> `
    + `<span class="mono">${esc(f.file_path)}:${f.line}</span>`
    + `<div class="muted small">${esc(f.message)}</div></div>`
  ).join("");
  const gapsHtml = (node.gaps || []).slice(0, 5).map(g => {
    const tgt = g.sample_symbols && g.sample_symbols.length
      ? `${g.file_path}::${g.sample_symbols[0]}` : g.file_path;
    return `<div class="subcard" style="margin-bottom:5px;">`
      + `<button class="link mono" data-open-mod="${esc(g.file_path)}">`
      + `${esc(g.file_path)}</button>`
      + `<div class="muted small">prio ${g.priority_score} | `
      + `${g.untested_symbols} unt. syms | ${g.untested_sinks} unt. sinks</div>`
      + `<div class="small"><code>codeoverlook slice ${esc(tgt)} --budget 2500</code></div></div>`;
  }).join("");

  const zoomButtons = isPkg
    ? `<button class="btn btn-sm" data-zoom="blocks:${esc(node.block_id)}">`
      + `Level 1 · ${esc(node.block_id)}</button>`
      + `<button class="btn btn-sm" data-zoom-mods="packages:${esc(node.id)}">`
      + `Level 3 · ${node.prod_files} modules</button>`
    : (DATA.packages.length
        ? `<button class="btn btn-sm" data-zoom-pkgs="${esc(node.id)}">`
          + `Level 2 · Packages</button>`
        : "")
      + `<button class="btn btn-sm" data-zoom-mods="blocks:${esc(node.id)}">`
      + `Level 3 · ${node.prod_files} modules</button>`;
  const libsOut = libs || '<span class="muted">Stdlib / internal only</span>';

  box.innerHTML = `
    <div style="border-bottom:1px solid var(--border);padding-bottom:10px;">
      <div class="between" style="align-items:center;">
        <span class="sec" style="margin:0;color:var(--g-${band ? band.group : "entry"});">
          ${esc(band ? band.label + " · " + band.title : "Block")}
        </span>
        <span class="status-pill st-${esc(node.coverage_status)}">
          ${esc(node.coverage_status)}
        </span>
      </div>
      <h3 style="margin-top:4px;">${esc(node.title)}</h3>
      <div class="muted small" style="margin-top:4px;">
        Files: ${node.tested_files}/${node.prod_files} (${node.file_coverage_pct.toFixed(1)}%) |
        LOC: ${node.prod_loc.toLocaleString()} | Sinks: ${node.sensitive_sinks}
      </div>
    </div>
    <div><div class="sec">Navigate Levels</div><div class="row">${zoomButtons}</div></div>
    <div><div class="sec">External Libraries</div><div class="row">${libsOut}</div></div>
    ${findingsHtml
      ? `<div><div class="sec">Active Sinks &amp; Findings</div>${findingsHtml}</div>`
      : ""}
    ${gapsHtml
      ? `<div><div class="sec">Priority Targets to Test Next</div>${gapsHtml}</div>`
      : ""}
    ${largest ? `<div><div class="sec">Largest Modules</div>${largest}</div>` : ""}
    <div class="grid-2" style="border-top:1px solid var(--border);padding-top:10px;">
      <div><div class="sec">It Imports</div><div class="row">${impChips}</div></div>
      <div><div class="sec">Imported By</div><div class="row">${byChips}</div></div>
    </div>
    <div><button class="link small" id="copy-view-link">Copy link to this view</button></div>`;

  box.querySelectorAll("[data-jump-node]").forEach(b => b.addEventListener("click", () => {
    picked[level] = b.dataset.jumpNode;
    refreshAll(false);
  }));
  box.querySelectorAll("[data-zoom]").forEach(b => b.addEventListener("click", () => {
    const [lvl, id] = b.dataset.zoom.split(":");
    level = lvl; picked[lvl] = id; scope = null;
    refreshAll(true);
  }));
  box.querySelectorAll("[data-zoom-pkgs]").forEach(b => b.addEventListener("click", () => {
    scope = { level: "blocks", id: b.dataset.zoomPkgs };
    level = "packages";
    refreshAll(true);
  }));
  box.querySelectorAll("[data-zoom-mods]").forEach(b => b.addEventListener("click", () => {
    const [lvl, id] = b.dataset.zoomMods.split(":");
    scope = { level: lvl, id };
    level = "modules";
    refreshAll(false);
  }));
  box.querySelectorAll("[data-open-mod]").forEach(b => b.addEventListener("click", () => {
    if (!MOD_MAP[b.dataset.openMod]) return;
    picked.modules = b.dataset.openMod;
    level = "modules";
    refreshAll(false);
  }));
  const cp = $("copy-view-link");
  if (cp) cp.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      cp.textContent = "Link copied";
      setTimeout(() => { cp.textContent = "Copy link to this view"; }, 1500);
    } catch (_e) {}
  });
}

function renderGapsTab() {
  const filters = ["ALL", "UNTESTED", "LOW", "PARTIAL", "WELL_COVERED"];
  $("gap-filters").innerHTML = filters.map(f =>
    `<button class="btn btn-sm ${gapFilter === f ? "btn-on" : ""}" data-gf="${f}">${f}</button>`
  ).join("");
  $("gap-filters").querySelectorAll("[data-gf]").forEach(b => b.addEventListener("click", () => {
    gapFilter = b.dataset.gf;
    renderGapsTab();
  }));
  const rows = DATA.blocks.filter(b => gapFilter === "ALL" || b.coverage_status === gapFilter);
  $("gaps-tbody").innerHTML = rows.map(b => `
    <tr class="click" data-open-blk="${esc(b.id)}">
      <td><strong>${esc(b.id)}</strong></td>
      <td>
        <span class="status-pill st-${esc(b.coverage_status)}">${esc(b.coverage_status)}</span>
      </td>
      <td>${b.tested_files}/${b.prod_files} (${b.file_coverage_pct.toFixed(1)}%)</td>
      <td>${b.tested_symbols}/${b.prod_symbols} (${b.symbol_coverage_pct.toFixed(1)}%)</td>
      <td>${b.test_files_count} (${b.test_functions_count} fns)</td>
      <td>${b.untested_sinks} / ${b.sensitive_sinks}</td>
      <td>${b.priority_score.toFixed(1)}</td>
    </tr>`).join("");
  $("gaps-tbody").querySelectorAll("[data-open-blk]").forEach(
    tr => tr.addEventListener("click", () => {
      picked.blocks = tr.dataset.openBlk;
      level = "blocks";
      setTopTab("arch");
      refreshAll(true);
    })
  );
}

function renderRisksTab() {
  $("cycles-box").innerHTML = DATA.cycles.length
    ? DATA.cycles.map(
        c => `<div class="subcard mono" style="margin-bottom:6px;">`
          + `${esc(c.join(" -> "))}</div>`
      ).join("")
    : `<div class="subcard muted">No internal production import cycles detected.</div>`;
  $("violations-box").innerHTML = DATA.violations.length
    ? DATA.violations.map(v =>
        `<div class="subcard" style="margin-bottom:6px;">`
        + `<strong>${esc(v.src_block)} -&gt; ${esc(v.dst_block)}</strong> `
        + `(${v.edge_count}x ${esc(v.kind)}): ${esc(v.reason)}</div>`
      ).join("")
    : `<div class="subcard muted">No .codeoverlook.toml architecture violations detected.</div>`;
  $("findings-tbody").innerHTML = (DATA.findings || []).map(f => `
    <tr>
      <td><strong>${esc(f.severity)}</strong></td>
      <td class="mono">${esc(f.rule_id)}</td>
      <td>${esc(f.block_id)}</td>
      <td class="mono">${esc(f.file_path)}:${f.line}</td>
      <td>${esc(f.message)}</td>
    </tr>`).join("")
    || `<tr><td colspan="5" class="muted">No active AST findings or sinks.</td></tr>`;
}

function toggleFullscreen(forceState) {
  const next = typeof forceState === "boolean" ? forceState : !isFullscreen;
  isFullscreen = next;
  const grid = $("arch-grid");
  document.body.classList.toggle("fs-active", next);
  grid.classList.toggle("fs-mode", next);
  grid.classList.toggle("fs-hide-insp", next && !fsShowInspector);
  $("fs-btn").textContent = next ? "Exit full screen (Esc)" : "Full screen";
  $("fs-insp-btn").classList.toggle("hidden", !next);

  if (next && document.documentElement.requestFullscreen && !document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else if (!next && document.fullscreenElement && document.exitFullscreen) {
    document.exitFullscreen().catch(() => {});
  }
  setTimeout(() => fitToViewport(), 40);
}

function refreshAll(fitOnRender = true) {
  renderLevels();
  renderArchArea(fitOnRender);
  renderInspector();
  writeHash();
}

document.querySelectorAll("[data-toptab]").forEach(b =>
  b.addEventListener("click", () => setTopTab(b.dataset.toptab))
);
document.querySelectorAll("[data-view]").forEach(b =>
  b.addEventListener("click", () => { viewMode = b.dataset.view; refreshAll(true); })
);
document.querySelectorAll("[data-overlay]").forEach(b =>
  b.addEventListener("click", () => { overlay = b.dataset.overlay; refreshAll(false); })
);
$("every-import-btn").addEventListener("click", () => {
  everyImport = !everyImport;
  refreshAll(false);
});
$("module-search").addEventListener("input", renderModulesView);

$("zoom-in-btn").addEventListener("click", () => {
  zoom = Math.min(3.0, zoom * 1.2);
  applyTransform();
});
$("zoom-out-btn").addEventListener("click", () => {
  zoom = Math.max(0.25, zoom / 1.2);
  applyTransform();
});
$("zoom-fit-btn").addEventListener("click", fitToViewport);
$("fs-btn").addEventListener("click", () => toggleFullscreen());
$("fs-insp-btn").addEventListener("click", () => {
  fsShowInspector = !fsShowInspector;
  $("arch-grid").classList.toggle("fs-hide-insp", isFullscreen && !fsShowInspector);
  $("fs-insp-btn").textContent = fsShowInspector ? "Hide details" : "Show details";
  setTimeout(() => fitToViewport(), 30);
});

document.addEventListener("keydown", ev => {
  if (ev.key === "Escape" && isFullscreen) toggleFullscreen(false);
});
document.addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement && isFullscreen) toggleFullscreen(false);
});

const vp = $("viewport-canvas");
vp.addEventListener("mousedown", ev => {
  if (ev.button !== 0) return;
  dragState = { x: ev.clientX - panX, y: ev.clientY - panY, sx: ev.clientX, sy: ev.clientY };
  dragMoved = false;
  vp.classList.add("dragging");
});
window.addEventListener("mousemove", ev => {
  if (!dragState) return;
  if (Math.abs(ev.clientX - dragState.sx) + Math.abs(ev.clientY - dragState.sy) > 4) {
    dragMoved = true;
  }
  panX = ev.clientX - dragState.x;
  panY = ev.clientY - dragState.y;
  applyTransform();
});
window.addEventListener("mouseup", () => {
  dragState = null;
  vp.classList.remove("dragging");
  setTimeout(() => { dragMoved = false; }, 0);
});
vp.addEventListener("wheel", ev => {
  if (!isFullscreen && !ev.ctrlKey) return;
  ev.preventDefault();
  const rect = vp.getBoundingClientRect();
  const mx = ev.clientX - rect.left;
  const my = ev.clientY - rect.top;
  const factor = ev.deltaY < 0 ? 1.12 : 1 / 1.12;
  const nextZoom = Math.max(0.25, Math.min(3.2, zoom * factor));
  panX = mx - (mx - panX) * (nextZoom / zoom);
  panY = my - (my - panY) * (nextZoom / zoom);
  zoom = nextZoom;
  applyTransform();
}, { passive: false });

readHash();
renderHeader();
refreshAll(true);
"""


def _safe_json_for_script(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def render_atlas_html(
    repo_name: str,
    coverage: RepoCoverageReport,
    block_summary: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
    cycles: list[list[str]],
    violations: list[dict[str, Any]],
    catalog: dict[str, Any] | None = None,
) -> str:
    """Build a self-contained multi-level HTML explorer with full-screen navigation.

    Args:
        repo_name: Display name of the scanned repository.
        coverage: Output from `TestCoverageAnalyzer.analyze()`.
        block_summary: Production block summary from `FactStore.get_block_risk_summary()`.
        dependencies: Production inter-block dependency edges.
        cycles: Detected internal production import cycles.
        violations: Architectural boundary violations from `.codeoverlook.toml`.
        catalog: Optional module, external-library, and findings catalog from
            `FactStore.get_explorer_catalog()`.

    Returns:
        Standalone HTML document string requiring no external network requests.
    """
    model = build_explorer_model(
        repo_name=repo_name,
        coverage=coverage,
        block_summary=block_summary,
        dependencies=dependencies,
        cycles=cycles,
        violations=violations,
        catalog=catalog,
    )
    data_json = _safe_json_for_script(model)
    escaped_repo = html.escape(repo_name)
    js_code = _EXPLORER_JS.replace("__DATA_JSON__", data_json)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>CodeOverlook Inspector - {escaped_repo}</title>
<style>{_EXPLORER_CSS}</style>
</head>
<body>
  <div class="wrap">
    <header class="card">
      <div class="head">
        <div>
          <div class="row" style="margin-bottom:6px;">
            <span class="pill pill-strong" id="pill-repo"></span>
            <span class="pill" id="pill-tests"></span>
          </div>
          <h1>CodeOverlook Coverage &amp; Architecture Inspector</h1>
          <p class="muted" style="max-width:780px;">
            Layered dependency architecture, package drill-down, module docstrings,
            test coverage gaps, and sensitive AST sinks in one offline explorer.
          </p>
        </div>
        <div style="display:flex;flex-direction:column;gap:8px;align-items:flex-end;">
          <button id="theme-btn" class="btn btn-sm" type="button">Theme: system</button>
          <div class="kpis" id="header-kpis"></div>
        </div>
      </div>
      <div class="tabs" role="tablist">
        <button class="btn btn-on" data-toptab="arch" type="button">Architecture</button>
        <button class="btn" data-toptab="gaps" type="button">Coverage Gaps</button>
        <button class="btn" data-toptab="risks" type="button">Risks &amp; Violations</button>
      </div>
    </header>

    <section id="panel-arch-root" style="display:flex;flex-direction:column;gap:14px;">
      <div class="card" style="padding:12px 16px;display:flex;flex-direction:column;gap:8px;">
        <div class="sec" style="margin:0;">Level of Detail</div>
        <div id="levels" class="levels"></div>
        <div id="scope-bar" class="muted hidden"></div>
      </div>

      <div id="arch-grid" class="grid-arch">
        <div class="card" id="arch-panel">
          <div class="between" style="padding-bottom:10px;border-bottom:1px solid var(--border);
                                      margin-bottom:12px;">
            <div>
              <h2 id="arch-title"></h2>
              <p class="muted" id="arch-subtitle" style="margin:2px 0 0 0;"></p>
            </div>
            <div class="row" id="arch-tools">
              <button class="btn btn-sm" data-view="svg" type="button">Diagram</button>
              <button class="btn btn-sm" data-view="cards" type="button">Cards</button>
              <button class="btn btn-sm" data-overlay="arch" type="button">Architecture</button>
              <button class="btn btn-sm" data-overlay="coverage" type="button">Coverage</button>
              <button class="btn btn-sm" data-overlay="security" type="button">Security</button>
              <button class="btn btn-sm" id="every-import-btn" type="button">Every import</button>
              <button class="btn btn-sm" id="zoom-out-btn" type="button">-</button>
              <span class="muted small" id="zoom-label">100%</span>
              <button class="btn btn-sm" id="zoom-in-btn" type="button">+</button>
              <button class="btn btn-sm" id="zoom-fit-btn" type="button">Fit</button>
              <button class="btn btn-sm hidden" id="fs-insp-btn" type="button">
                Hide details
              </button>
              <button class="btn btn-sm btn-on" id="fs-btn" type="button">Full screen</button>
            </div>
            <div class="row hidden" id="module-tools">
              <input id="module-search" type="search"
                     placeholder="Search path, block, docstring, library..." />
            </div>
          </div>

          <div id="diagram-wrap-block">
            <div class="viewport-wrap">
              <div id="viewport-canvas" class="viewport-canvas"></div>
            </div>
            <div id="diagram-legend" class="legend"></div>
          </div>
          <div id="cards-arch" class="hidden"></div>
          <div id="modules-arch" class="hidden"></div>
        </div>

        <aside id="inspector" class="card inspector"></aside>
      </div>
    </section>

    <section id="panel-gaps" class="card hidden">
      <div class="between" style="margin-bottom:10px;">
        <h2>Block Coverage &amp; Test-Gap Priorities</h2>
        <div class="row" id="gap-filters"></div>
      </div>
      <div class="scroll">
        <table>
          <thead><tr>
            <th>Block</th><th>Status</th><th>Files</th><th>Symbols</th>
            <th>Tests</th><th>Untested Sinks</th><th>Priority</th>
          </tr></thead>
          <tbody id="gaps-tbody"></tbody>
        </table>
      </div>
    </section>

    <section id="panel-risks" class="hidden" style="display:flex;flex-direction:column;gap:14px;">
      <div class="grid-2">
        <div class="card">
          <h2 style="margin-bottom:8px;">Internal Import Cycles</h2>
          <div id="cycles-box"></div>
        </div>
        <div class="card">
          <h2 style="margin-bottom:8px;">Architecture Boundary Violations</h2>
          <div id="violations-box"></div>
        </div>
      </div>
      <div class="card">
        <h2 style="margin-bottom:8px;">Active Sinks &amp; Static Findings</h2>
        <div class="scroll">
          <table>
            <thead><tr>
              <th>Severity</th><th>Rule</th><th>Block</th><th>Location</th><th>Message</th>
            </tr></thead>
            <tbody id="findings-tbody"></tbody>
          </table>
        </div>
      </div>
    </section>
  </div>
<script>{js_code}</script>
</body>
</html>
"""
