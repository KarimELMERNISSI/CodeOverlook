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
    --g-tooling: #64748B; --g-inherit: #6B4FA3;
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
      --g-tooling: #94A3B8; --g-inherit: #B9A2E8;
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
    --g-tooling: #94A3B8; --g-inherit: #B9A2E8;
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
    flex: 1 1 170px; padding: 9px 12px; border: 0;
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
  .crumbs {
    display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
    font-size: 12.5px;
  }
  .crumb-btn {
    background: none; border: 0; padding: 2px 6px; border-radius: 6px;
    color: var(--primary-strong); font-weight: 600; cursor: pointer;
  }
  .crumb-btn:hover { background: var(--soft); }
  .grid-arch {
    display: grid; grid-template-columns: minmax(0, 1fr) 375px;
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
    width: 100%; min-height: 450px; max-height: 740px;
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
    grid-template-columns: repeat(auto-fit, minmax(195px, 1fr));
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
    grid-template-columns: minmax(0, 1fr) 375px;
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
let level = "blocks";     // "blocks" | "packages" | "modules" | "functions"
let viewMode = "svg";     // "svg" | "cards"
let overlay = "arch";     // "arch" | "weaknesses" | "coverage" | "security"
let everyImport = false;
let activeFeatureId = null;
let scope = null;         // { level: "blocks"|"packages", id: string } | null
let fnScope = null;       // { kind: "block"|"package"|"module", id: string, title: string }
let diagOpen = true;
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
const FEAT_MAP = Object.fromEntries((DATA.features || []).map(f => [f.id, f]));

const picked = {
  blocks: DATA.blocks.length ? DATA.blocks[0].id : null,
  packages: DATA.packages.length ? DATA.packages[0].id : null,
  modules: DATA.modules.length ? DATA.modules[0].path : null,
  functions: null
};

const THEME_MODES = ["system", "light", "dark"];
let themeMode = "system";

function applyTheme(mode) {
  themeMode = mode;
  if (mode === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", mode);
  $("theme-btn").textContent = "Theme: " + mode;
}

$("theme-btn").addEventListener("click", () => {
  applyTheme(THEME_MODES[(THEME_MODES.indexOf(themeMode) + 1) % THEME_MODES.length]);
});

function writeHash() {
  const target = level === "functions" && fnScope
    ? `${fnScope.kind}:${fnScope.id}`
    : (level === "modules" ? picked.modules : picked[level]);
  if (target) history.replaceState(null, "", `#/${level}/${encodeURIComponent(target)}`);
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

function renderDiagnosis() {
  const items = DATA.diagnosis || [];
  const card = $("diag-card");
  if (!items.length) {
    card.classList.add("hidden");
    return;
  }
  card.classList.remove("hidden");
  $("diag-title").textContent = `Architect's Diagnosis (${items.length} key findings)`;
  $("diag-toggle").textContent = diagOpen ? "Hide" : "Show";
  $("diag-body").classList.toggle("hidden", !diagOpen);
  $("diag-body").innerHTML = items.map(d => `
    <button class="diag-card" type="button"
            data-jlevel="${esc(d.jump_level)}" data-jid="${esc(d.jump_id)}">
      <div class="row" style="margin-bottom:4px;">
        <span class="sev sev-${esc(d.severity)}">${esc(d.severity)}</span>
        <span class="muted small">${esc(d.kind)}</span>
      </div>
      <div><strong>${esc(d.title)}</strong></div>
      <div class="muted small" style="margin-top:2px;">${esc(d.detail)}</div>
    </button>
  `).join("");
  $("diag-body").querySelectorAll("[data-jid]").forEach(btn => {
    btn.addEventListener("click", () => {
      const jl = btn.dataset.jlevel;
      const jid = btn.dataset.jid;
      if (jl === "modules" && MOD_MAP[jid]) {
        level = "modules"; picked.modules = jid; scope = null;
      } else if (BLOCK_MAP[jid]) {
        level = "blocks"; picked.blocks = jid; scope = null;
      }
      refreshAll(true);
    });
  });
}

$("diag-toggle").addEventListener("click", () => {
  diagOpen = !diagOpen;
  renderDiagnosis();
});

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

function renderLevelsAndFeatures() {
  const fnDesc = fnScope ? `${fnScope.title}` : "Double-click any node";
  const items = [
    ["blocks", "Level 1", "Functional Blocks", `${DATA.blocks.length} blocks`],
    ["packages", "Level 2", "Packages & Bricks", `${DATA.packages.length} packages`],
    ["modules", "Level 3", "Every Module", `${DATA.modules.length} modules`],
    ["functions", "Level 4", "Functions & Classes", fnDesc]
  ];
  $("levels").innerHTML = items.map(([id, n, t, c]) => {
    const disabled = (id === "packages" && !DATA.packages.length)
      || (id === "modules" && !DATA.modules.length)
      || (id === "functions" && !fnScope);
    return `<button class="level ${level === id ? "on" : ""}" data-level="${id}" `
      + `${disabled ? "disabled" : ""}>`
      + `<div class="n">${n}</div><div class="t">${t}</div>`
      + `<div class="c">${esc(c)}</div></button>`;
  }).join("");
  $("levels").querySelectorAll("[data-level]").forEach(btn => {
    btn.addEventListener("click", () => {
      level = btn.dataset.level;
      if (level === "blocks") scope = null;
      refreshAll(true);
    });
  });

  // Feature highlight bar (only relevant for blocks & packages).
  const feats = DATA.features || [];
  const featRow = $("feature-row");
  if (!feats.length || level === "modules" || level === "functions") {
    featRow.classList.add("hidden");
  } else {
    featRow.classList.remove("hidden");
    const chips = [
      `<button type="button" class="btn btn-sm ${!activeFeatureId ? "btn-on" : ""}" `
      + `data-feat="">All</button>`,
      ...feats.map(f =>
        `<button type="button" class="btn btn-sm ${activeFeatureId === f.id ? "btn-on" : ""}" `
        + `data-feat="${esc(f.id)}">${esc(f.label)}</button>`
      )
    ].join("");
    $("feature-chips").innerHTML = chips;
    const af = activeFeatureId ? FEAT_MAP[activeFeatureId] : null;
    $("feature-desc").textContent = af ? af.summary : "";
    $("feature-chips").querySelectorAll("[data-feat]").forEach(btn => {
      btn.addEventListener("click", () => {
        activeFeatureId = btn.dataset.feat || null;
        if (activeFeatureId && FEAT_MAP[activeFeatureId]) {
          const firstBlk = FEAT_MAP[activeFeatureId].blocks[0];
          if (level === "blocks" && firstBlk) picked.blocks = firstBlk;
        }
        refreshAll(false);
      });
    });
  }

  renderBreadcrumbs();
}

function renderBreadcrumbs() {
  const crumbs = [`<button type="button" class="crumb-btn" data-bc="blocks">Architecture</button>`];
  if (level === "packages" && scope && scope.level === "blocks") {
    crumbs.push(`<span class="muted">&gt;</span>`);
    crumbs.push(
      `<button type="button" class="crumb-btn" data-bc="packages">${esc(scope.id)}</button>`
    );
  } else if (level === "modules" && scope) {
    crumbs.push(`<span class="muted">&gt;</span>`);
    crumbs.push(`<span class="muted">${esc(scope.id)}</span>`);
    crumbs.push(`<span class="muted">&gt;</span>`);
    crumbs.push(`<strong>Modules</strong>`);
  } else if (level === "functions" && fnScope) {
    if (fnScope.kind === "package" && PKG_MAP[fnScope.id]) {
      const blk = PKG_MAP[fnScope.id].block_id;
      crumbs.push(`<span class="muted">&gt;</span>`);
      crumbs.push(
        `<button type="button" class="crumb-btn" data-bc-blk="${esc(blk)}">${esc(blk)}</button>`
      );
    } else if (fnScope.kind === "module" && MOD_MAP[fnScope.id]) {
      const m = MOD_MAP[fnScope.id];
      crumbs.push(`<span class="muted">&gt;</span>`);
      crumbs.push(
        `<button type="button" class="crumb-btn" data-bc-blk="${esc(m.block_id)}">`
        + `${esc(m.block_id)}</button>`
      );
      crumbs.push(`<span class="muted">&gt;</span>`);
      crumbs.push(
        `<button type="button" class="crumb-btn" data-bc-pkg="${esc(m.package_id)}">`
        + `${esc(m.package)}</button>`
      );
    }
    crumbs.push(`<span class="muted">&gt;</span>`);
    crumbs.push(`<strong>${esc(fnScope.title)} (Functions)</strong>`);
  }

  if (scope && level !== "functions") {
    crumbs.push(
      `<button type="button" class="btn btn-sm" id="clear-scope-btn">Show all</button>`
    );
  }
  $("breadcrumbs").innerHTML = crumbs.join("");
  $("breadcrumbs").querySelectorAll("[data-bc]").forEach(b => b.addEventListener("click", () => {
    level = b.dataset.bc;
    if (level === "blocks") scope = null;
    refreshAll(true);
  }));
  $("breadcrumbs").querySelectorAll("[data-bc-blk]").forEach(
    b => b.addEventListener("click", () => {
      const bid = b.dataset.bcBlk;
      if (BLOCK_MAP[bid] && BLOCK_MAP[bid].packages.length > 1) {
        scope = { level: "blocks", id: bid };
        level = "packages";
      } else {
        scope = null;
        level = "blocks";
        picked.blocks = bid;
      }
      refreshAll(true);
    })
  );
  $("breadcrumbs").querySelectorAll("[data-bc-pkg]").forEach(
    b => b.addEventListener("click", () => {
      const pid = b.dataset.bcPkg;
      scope = { level: "packages", id: pid };
      level = "modules";
      refreshAll(false);
    })
  );
  const clr = $("clear-scope-btn");
  if (clr) clr.addEventListener("click", () => {
    scope = null;
    refreshAll(true);
  });
}

function stepUpOneLevel() {
  if (level === "functions" && fnScope) {
    if (fnScope.kind === "module" && MOD_MAP[fnScope.id]) {
      level = "modules";
      picked.modules = fnScope.id;
    } else if (fnScope.kind === "package") {
      level = "packages";
      picked.packages = fnScope.id;
    } else {
      level = "blocks";
      picked.blocks = fnScope.id;
    }
    refreshAll(true);
    return;
  }
  if (level === "modules") {
    if (scope && scope.level === "packages") {
      level = "packages";
      picked.packages = scope.id;
      scope = PKG_MAP[scope.id] ? { level: "blocks", id: PKG_MAP[scope.id].block_id } : null;
    } else {
      level = "blocks";
      if (scope && scope.level === "blocks") picked.blocks = scope.id;
      scope = null;
    }
    refreshAll(true);
    return;
  }
  if (level === "packages") {
    if (scope && scope.level === "blocks") picked.blocks = scope.id;
    level = "blocks";
    scope = null;
    refreshAll(true);
  }
}

function openFunctionsView(kind, id) {
  let title = id;
  if (kind === "package" && PKG_MAP[id]) title = PKG_MAP[id].title;
  fnScope = { kind, id, title };
  level = "functions";
  picked.functions = null;
  refreshAll(true);
}

function handleDoubleClickNode(nodeId) {
  if (level === "blocks" && BLOCK_MAP[nodeId]) {
    const blk = BLOCK_MAP[nodeId];
    if (blk.packages && blk.packages.length > 1) {
      scope = { level: "blocks", id: nodeId };
      level = "packages";
      picked.packages = blk.packages[0];
      refreshAll(true);
    } else {
      openFunctionsView("block", nodeId);
    }
    return;
  }
  if (level === "packages" && PKG_MAP[nodeId]) {
    openFunctionsView("package", nodeId);
  }
}

function resolveFunctionGraph(fScope) {
  const sg = DATA.symbol_graph || { by_module: {}, by_block: {} };
  if (!fScope) return { symbols: [], edges: [] };
  if (fScope.kind === "block") {
    return sg.by_block[fScope.id] || { symbols: [], edges: [] };
  }
  if (fScope.kind === "module") {
    return sg.by_module[fScope.id] || { symbols: [], edges: [] };
  }
  const pkg = PKG_MAP[fScope.id];
  if (!pkg) return { symbols: [], edges: [] };
  let allSyms = [];
  let allEdges = [];
  (pkg.member_modules || []).forEach(fp => {
    const sub = sg.by_module[fp];
    if (sub) {
      allSyms = allSyms.concat(sub.symbols || []);
      allEdges = allEdges.concat(sub.edges || []);
    }
  });
  allSyms.sort((a, b) => (b.degree - a.degree) || (b.sinks - a.sinks));
  const kept = allSyms.slice(0, 36);
  const keepIds = new Set(kept.map(s => s.id));
  kept.sort((a, b) => a.file_path.localeCompare(b.file_path) || (a.line - b.line));
  return {
    symbols: kept,
    edges: allEdges.filter(e => keepIds.has(e.u) && keepIds.has(e.v))
  };
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
  if (overlay === "weaknesses") {
    const tags = n.weakness_tags || [];
    if (tags.includes("CYCLE") || tags.includes("BACK-EDGE")) return "var(--bad)";
    if (tags.includes("HIGH BLAST RADIUS") || tags.includes("GOD MODULE")) return "var(--warn)";
    return "var(--ok)";
  }
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
  if (n.zone === "tooling") return "var(--g-tooling)";
  const b = BAND_MAP[n.band];
  return b ? `var(--g-${b.group})` : "var(--primary)";
}

function nodeSubtitle(n) {
  if (overlay === "weaknesses") {
    const inst = n.instability !== undefined ? `I=${n.instability.toFixed(2)}` : "";
    const br = n.blast_radius !== undefined ? ` | blast ${n.blast_radius}` : "";
    return inst ? `${inst}${br}` : `${n.prod_files} files | ${n.prod_loc} LOC`;
  }
  if (overlay === "coverage") {
    return `${n.tested_files}/${n.prod_files} tested (${n.file_coverage_pct.toFixed(0)}%)`;
  }
  if (overlay === "security") {
    return `${n.sensitive_sinks || 0} sinks (${n.untested_sinks || 0} untested)`;
  }
  return `${n.prod_files} files | ${n.prod_loc.toLocaleString()} LOC`;
}

function layoutDiagram(nodes, edges) {
  const bandRows = DATA.bands.map(b => ({
    band: b,
    items: nodes.filter(n => n.band === b.id && n.zone !== "tooling")
  })).filter(r => r.items.length > 0);

  const toolingItems = nodes.filter(n => n.zone === "tooling");
  if (toolingItems.length) {
    bandRows.push({
      band: {
        id: "TOOLING",
        label: "TOOLING",
        group: "tooling",
        title: "Tooling & Scripts",
        desc: "Isolated non-production scripts & scratch"
      },
      items: toolingItems
    });
  }

  if (!bandRows.length) {
    return { width: 820, height: 240, bands: [], boxes: {}, edges: [] };
  }

  const labelW = 196;
  const nodeW = 178;
  const nodeH = 60;
  const gapX = 26;
  const gapY = 26;
  const padX = 22;
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
    const bandH = Math.max(96, padY * 2 + rowsCount * nodeH + (rowsCount - 1) * gapY);
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
  zoom = Math.max(0.32, Math.min(2.5, scale));
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

function markerDefs() {
  const marker = (id, fill) => `<marker id="${id}" viewBox="0 0 10 10" refX="9" refY="5" `
    + `markerUnits="userSpaceOnUse" markerWidth="7" markerHeight="7" orient="auto">`
    + `<path d="M1,1.5 L9,5 L1,8.5 z" fill="${fill}"/></marker>`;
  return `<defs>${marker("m-muted", "var(--muted)")}${marker("m-down", "var(--edge-down)")}`
    + `${marker("m-up", "var(--edge-up)")}${marker("m-bad", "var(--bad)")}`
    + `${marker("m-inh", "var(--g-inherit)")}</defs>`;
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
  const feat = activeFeatureId ? FEAT_MAP[activeFeatureId] : null;
  const featSet = feat
    ? new Set(level === "packages" ? feat.packages : feat.blocks)
    : null;

  const layout = layoutDiagram(nodes, edges);
  lastLayout = layout;

  const bandsSvg = layout.bands.map(b => {
    const c = `var(--g-${b.band.group})`;
    const titleStr = b.band.title.length > 26
      ? b.band.title.slice(0, 24) + ".." : b.band.title;
    return `<g>`
      + `<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="8" `
      + `fill="${c}" fill-opacity="0.05" stroke="${c}" stroke-opacity="0.3"/>`
      + `<rect x="${b.x}" y="${b.y}" width="${b.labelW}" height="${b.h}" rx="8" `
      + `fill="${c}" fill-opacity="0.12"/>`
      + `<text x="${b.x + 12}" y="${b.y + 20}" font-size="10.5" font-weight="700" `
      + `fill="${c}">${esc(b.band.label)}</text>`
      + `<text x="${b.x + 12}" y="${b.y + 38}" font-size="12" font-weight="700" `
      + `fill="var(--fg)">${esc(titleStr)}</text>`
      + `<text x="${b.x + 12}" y="${b.y + b.h - 10}" font-size="10" `
      + `fill="var(--muted)">${esc(b.band.desc.slice(0, 28))}</text>`
      + `</g>`;
  }).join("");

  const shownEdges = everyImport
    ? edges
    : edges.filter(e => e.u === chosen || e.v === chosen
      || (featSet && featSet.has(e.u) && featSet.has(e.v)));

  const arrowsSvg = shownEdges.map((e, idx) => {
    const sb = layout.boxes[e.u];
    const db = layout.boxes[e.v];
    if (!sb || !db) return "";
    const isOut = e.u === chosen;
    const isIn = e.v === chosen;
    const dir = e.direction || "";
    let stroke = "var(--muted)";
    let marker = "m-muted";
    let opacity = "0.42";
    let sw = 1.2;
    let dash = "";
    if (e.violation || dir === "violation") {
      stroke = "var(--bad)"; marker = "m-bad"; opacity = "0.95";
      sw = 2.3; dash = 'stroke-dasharray="5 3"';
    } else if (dir === "up" || dir === "cycle") {
      stroke = dir === "cycle" ? "var(--bad)" : "var(--edge-up)";
      marker = dir === "cycle" ? "m-bad" : "m-up";
      opacity = (isOut || isIn) ? "0.95" : "0.75";
      sw = 1.8; dash = 'stroke-dasharray="4 3"';
    } else if (isOut) {
      stroke = "var(--edge-down)"; marker = "m-down"; opacity = "0.95";
      sw = Math.min(3.4, 1.5 + Math.log2(1 + e.n) * 0.6);
    } else if (isIn) {
      stroke = "var(--edge-up)"; marker = "m-up"; opacity = "0.95";
      sw = Math.min(3.4, 1.5 + Math.log2(1 + e.n) * 0.6);
    }
    const d = orthoPath(sb, db, idx);
    return `<path d="${d}" fill="none" stroke="${stroke}" stroke-opacity="${opacity}" `
      + `stroke-width="${sw}" ${dash} marker-end="url(#${marker})">`
      + `<title>${esc(e.u)} -> ${esc(e.v)} (${e.n} imports${dir ? ", " + dir : ""})</title>`
      + `</path>`;
  }).join("");

  const nodesSvg = nodes.map(n => {
    const p = layout.boxes[n.id];
    const isSel = n.id === chosen;
    const isUse = uses.has(n.id);
    const isUsedBy = usedBy.has(n.id);
    const inFeat = !featSet || featSet.has(n.id);
    const hasViolation = shownEdges.some(
      e => e.violation && ((e.u === chosen && e.v === n.id) || (e.v === chosen && e.u === n.id))
    );
    const dim = featSet ? !inFeat : (!everyImport && !isSel && !isUse && !isUsedBy);
    const accent = nodeAccent(n);
    const wTags = n.weakness_tags || [];
    const hasWeak = overlay === "weaknesses" && wTags.length > 0;
    const stroke = hasViolation ? "var(--bad)" : isSel ? "var(--primary)"
      : isUse ? "var(--edge-down)" : isUsedBy ? "var(--edge-up)"
      : hasWeak ? "var(--warn)" : "var(--border)";
    const sw = isSel ? 2.4 : (isUse || isUsedBy) ? 1.8 : 1.2;

    let badge = hasViolation ? "VIOLATION" : isSel ? "FOCUS"
      : isUse ? "IMPORTED" : isUsedBy ? "IMPORTS IT" : "";
    let badgeBg = hasViolation ? "var(--bad)" : isSel ? "var(--primary)"
      : isUse ? "var(--edge-down)" : "var(--edge-up)";
    if (!badge && overlay === "weaknesses" && wTags.length) {
      badge = wTags[0];
      badgeBg = wTags[0] === "CYCLE" || wTags[0] === "BACK-EDGE" ? "var(--bad)" : "var(--warn)";
    }
    const bw = badge.length * 6.0 + 12;
    const titleTxt = n.title.length > 20 ? n.title.slice(0, 18) + ".." : n.title;
    const covW = Math.max(0, Math.min(p.w - 10, ((n.file_coverage_pct || 0) / 100) * (p.w - 10)));
    const covFill = (n.file_coverage_pct || 0) >= 70 ? "var(--ok)"
      : (n.file_coverage_pct || 0) >= 35 ? "var(--warn)" : "var(--bad)";

    let badgeEl = "";
    if (badge) {
      badgeEl = `<rect x="${p.x + p.w - bw - 6}" y="${p.y - 8}" width="${bw}" height="15" `
        + `rx="7.5" fill="${badgeBg}"/>`
        + `<text x="${p.x + p.w - bw / 2 - 6}" y="${p.y + 3}" text-anchor="middle" `
        + `font-size="8.5" font-weight="700" fill="var(--on-primary)">${esc(badge)}</text>`;
    }

    return `<g opacity="${dim ? 0.36 : 1}">`
      + `<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="7" `
      + `fill="var(--card)" stroke="${stroke}" stroke-width="${sw}"/>`
      + `<rect x="${p.x}" y="${p.y}" width="5" height="${p.h}" rx="2" fill="${accent}"/>`
      + `<text x="${p.x + 14}" y="${p.y + 23}" font-size="12.5" font-weight="700" `
      + `fill="var(--fg)">${esc(titleTxt)}</text>`
      + `<text x="${p.x + 14}" y="${p.y + 40}" font-size="10.5" `
      + `fill="var(--muted)">${esc(nodeSubtitle(n))}</text>`
      + `<rect x="${p.x + 7}" y="${p.y + p.h - 6}" width="${p.w - 12}" height="3" `
      + `rx="1.5" fill="var(--border)"/>`
      + `<rect x="${p.x + 7}" y="${p.y + p.h - 6}" width="${covW.toFixed(1)}" height="3" `
      + `rx="1.5" fill="${covFill}"/>`
      + badgeEl
      + `<rect class="svg-node" data-node="${esc(n.id)}" x="${p.x}" y="${p.y}" `
      + `width="${p.w}" height="${p.h}" rx="7" fill="transparent">`
      + `<title>${esc(n.role_summary || n.title)} (Double-click to open internals)</title>`
      + `</rect></g>`;
  }).join("");

  const prodBands = layout.bands.filter(b => b.band.id !== "TOOLING");
  const guideX = layout.width - 12;
  let guideSvg = "";
  if (prodBands.length > 1) {
    const topY = prodBands[0].y + 8;
    const botY = prodBands[prodBands.length - 1].y + prodBands[prodBands.length - 1].h - 8;
    guideSvg = `<line x1="${guideX}" y1="${topY}" x2="${guideX}" y2="${botY}" `
      + `stroke="var(--muted)" stroke-width="1.3" marker-end="url(#m-muted)"/>`
      + `<text transform="translate(${guideX - 7},${(topY + botY) / 2}) rotate(-90)" `
      + `text-anchor="middle" font-size="10" font-weight="700" fill="var(--muted)" `
      + `letter-spacing="0.5">IMPORTS FLOW DOWN</text>`;
  }

  $("viewport-canvas").innerHTML =
    `<svg id="arch-svg" width="${layout.width}" height="${layout.height}" `
    + `viewBox="0 0 ${layout.width} ${layout.height}">`
    + `${markerDefs()}${bandsSvg}${guideSvg}${arrowsSvg}${nodesSvg}</svg>`;

  $("viewport-canvas").querySelectorAll("[data-node]").forEach(el => {
    el.addEventListener("click", ev => {
      if (dragMoved) return;
      ev.stopPropagation();
      picked[level] = el.dataset.node;
      refreshAll(false);
    });
    el.addEventListener("dblclick", ev => {
      ev.stopPropagation();
      handleDoubleClickNode(el.dataset.node);
    });
  });

  $("diagram-legend").innerHTML = `
    <span><i class="swatch" style="background:var(--edge-down)"></i>Focus imports it</span>
    <span>
      <i class="swatch" style="background:var(--edge-up)"></i>Imports the focus / back-edge
    </span>
    <span><i class="swatch" style="background:var(--bad)"></i>Cycle or forbidden violation</span>
    <span>Bottom bar = file coverage | Double-click node for internals</span>`;

  if (fitOnRender) fitToViewport();
  else applyTransform();
}

function renderFunctionsSvg(fitOnRender) {
  const graph = resolveFunctionGraph(fnScope);
  const syms = graph.symbols || [];
  const edges = graph.edges || [];
  if (!syms.length) {
    $("viewport-canvas").innerHTML =
      `<div class="muted" style="padding:24px;">`
      + `No class or function symbols found in this scope.</div>`;
    return;
  }

  const symMap = Object.fromEntries(syms.map(s => [s.id, s]));
  if (!picked.functions || !symMap[picked.functions]) {
    picked.functions = syms[0].id;
  }
  const chosen = picked.functions;

  const laneKey = fnScope.kind === "module"
    ? (s => s.qualname.includes(".") ? s.qualname.split(".")[0] : "Module Functions")
    : (s => s.file_path);

  const laneMap = new Map();
  syms.forEach(s => {
    const lk = laneKey(s);
    if (!laneMap.has(lk)) laneMap.set(lk, []);
    laneMap.get(lk).push(s);
  });

  const labelW = 190;
  const nodeW = 186;
  const nodeH = 52;
  const gapX = 24;
  const gapY = 22;
  const padX = 20;
  const padY = 16;
  const maxCols = 4;

  const lanes = [...laneMap.entries()];
  const maxItems = Math.max(1, ...lanes.map(([, arr]) => arr.length));
  const colsCap = Math.min(maxCols, Math.max(2, maxItems));
  const contentW = colsCap * nodeW + (colsCap - 1) * gapX + padX * 2;
  const totalW = labelW + contentW + 24;

  let curY = 14;
  const placedLanes = [];
  const boxes = {};
  lanes.forEach(([title, arr]) => {
    const rowsCount = Math.ceil(arr.length / colsCap);
    const laneH = Math.max(82, padY * 2 + rowsCount * nodeH + (rowsCount - 1) * gapY);
    placedLanes.push({ title, count: arr.length, x: 10, y: curY, w: totalW - 20, h: laneH });
    arr.forEach((s, idx) => {
      const rIdx = Math.floor(idx / colsCap);
      const cIdx = idx % colsCap;
      boxes[s.id] = {
        x: labelW + padX + cIdx * (nodeW + gapX),
        y: curY + padY + rIdx * (nodeH + gapY),
        w: nodeW, h: nodeH
      };
    });
    curY += laneH + 12;
  });

  lastLayout = { width: totalW, height: curY + 8 };

  const lanesSvg = placedLanes.map(l => {
    const shortTitle = l.title.length > 24 ? "..." + l.title.slice(-22) : l.title;
    return `<g>`
      + `<rect x="${l.x}" y="${l.y}" width="${l.w}" height="${l.h}" rx="8" `
      + `fill="var(--primary)" fill-opacity="0.04" stroke="var(--border)"/>`
      + `<rect x="${l.x}" y="${l.y}" width="${labelW - 14}" height="${l.h}" rx="8" `
      + `fill="var(--primary)" fill-opacity="0.09"/>`
      + `<text x="${l.x + 12}" y="${l.y + 24}" font-size="11.5" font-weight="700" `
      + `fill="var(--fg)">${esc(shortTitle)}</text>`
      + `<text x="${l.x + 12}" y="${l.y + 42}" font-size="10.5" `
      + `fill="var(--muted)">${l.count} symbols</text></g>`;
  }).join("");

  const outSet = new Set(edges.filter(e => e.u === chosen).map(e => e.v));
  const inSet = new Set(edges.filter(e => e.v === chosen).map(e => e.u));
  const shownEdges = everyImport ? edges : edges.filter(e => e.u === chosen || e.v === chosen);

  const arrowsSvg = shownEdges.map((e, idx) => {
    const sb = boxes[e.u];
    const db = boxes[e.v];
    if (!sb || !db) return "";
    const isInh = e.kind === "INHERITS";
    const isOut = e.u === chosen;
    const isIn = e.v === chosen;
    const stroke = isInh ? "var(--g-inherit)"
      : isOut ? "var(--edge-down)" : isIn ? "var(--edge-up)" : "var(--muted)";
    const marker = isInh ? "m-inh" : isOut ? "m-down" : isIn ? "m-up" : "m-muted";
    const dash = isInh ? 'stroke-dasharray="4 3"' : "";
    const sw = (isOut || isIn) ? 2.0 : 1.2;
    const opacity = (isOut || isIn) ? 0.95 : 0.45;
    return `<path d="${orthoPath(sb, db, idx)}" fill="none" stroke="${stroke}" `
      + `stroke-opacity="${opacity}" stroke-width="${sw}" ${dash} marker-end="url(#${marker})">`
      + `<title>${esc(e.u)} ${e.kind} ${esc(e.v)}</title></path>`;
  }).join("");

  const nodesSvg = syms.map(s => {
    const p = boxes[s.id];
    const isSel = s.id === chosen;
    const isOut = outSet.has(s.id);
    const isIn = inSet.has(s.id);
    const dim = !everyImport && !isSel && !isOut && !isIn;
    const accent = s.sinks > 0 ? "var(--bad)"
      : s.kind === "class" ? "var(--g-inherit)"
      : s.tested ? "var(--ok)" : "var(--primary)";
    const stroke = isSel ? "var(--primary)" : isOut ? "var(--edge-down)"
      : isIn ? "var(--edge-up)" : "var(--border)";
    const kindLbl = s.kind === "class" ? "CLASS" : s.kind === "method" ? "METHOD" : "FN";
    const nameTxt = s.name.length > 20 ? s.name.slice(0, 18) + ".." : s.name;
    const metaTxt = `${kindLbl} · L${s.line}`
      + (s.tested ? " · TESTED" : "") + (s.sinks > 0 ? ` · ${s.sinks} SINK` : "");

    return `<g opacity="${dim ? 0.42 : 1}">`
      + `<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="7" `
      + `fill="var(--card)" stroke="${stroke}" stroke-width="${isSel ? 2.4 : 1.3}"/>`
      + `<rect x="${p.x}" y="${p.y}" width="4.5" height="${p.h}" rx="2" fill="${accent}"/>`
      + `<text x="${p.x + 12}" y="${p.y + 21}" font-size="12" font-weight="700" `
      + `fill="var(--fg)">${esc(nameTxt)}</text>`
      + `<text x="${p.x + 12}" y="${p.y + 39}" font-size="10" `
      + `fill="var(--muted)">${esc(metaTxt)}</text>`
      + `<rect class="svg-node" data-fn="${esc(s.id)}" x="${p.x}" y="${p.y}" `
      + `width="${p.w}" height="${p.h}" rx="7" fill="transparent">`
      + `<title>${esc(s.signature)}</title></rect></g>`;
  }).join("");

  $("viewport-canvas").innerHTML =
    `<svg id="arch-svg" width="${lastLayout.width}" height="${lastLayout.height}" `
    + `viewBox="0 0 ${lastLayout.width} ${lastLayout.height}">`
    + `${markerDefs()}${lanesSvg}${arrowsSvg}${nodesSvg}</svg>`;

  $("viewport-canvas").querySelectorAll("[data-fn]").forEach(el => {
    el.addEventListener("click", ev => {
      if (dragMoved) return;
      ev.stopPropagation();
      picked.functions = el.dataset.fn;
      renderFunctionsSvg(false);
      renderInspector();
    });
  });

  $("diagram-legend").innerHTML = `
    <span><i class="swatch" style="background:var(--edge-down)"></i>Calls</span>
    <span><i class="swatch" style="background:var(--edge-up)"></i>Called by</span>
    <span><i class="swatch" style="background:var(--g-inherit)"></i>Inherits</span>
    <span>Showing ${syms.length} symbols &amp; ${edges.length} internal edges</span>`;

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
  const feat = activeFeatureId ? FEAT_MAP[activeFeatureId] : null;
  const featSet = feat
    ? new Set(level === "packages" ? feat.packages : feat.blocks) : null;

  const allBands = [...DATA.bands];
  if (nodes.some(n => n.zone === "tooling")) {
    allBands.push({
      id: "TOOLING", label: "TOOLING", group: "tooling",
      title: "Tooling & Scripts", desc: "Isolated non-production scripts & scratch"
    });
  }

  $("cards-arch").innerHTML = allBands.map(b => {
    const items = nodes.filter(n =>
      b.id === "TOOLING" ? n.zone === "tooling" : (n.band === b.id && n.zone !== "tooling")
    );
    if (!items.length) return "";
    const color = `var(--g-${b.group})`;
    const cardsHtml = items.map(n => {
      const isSel = n.id === chosen;
      const tag = isSel ? `<span class="tag">FOCUS</span>`
        : uses.has(n.id) ? `<span class="tag tag-down">IMPORTED</span>`
        : usedBy.has(n.id) ? `<span class="tag tag-up">IMPORTS IT</span>` : "";
      const cls = isSel ? "node-sel" : (uses.has(n.id) || usedBy.has(n.id)) ? "node-rel" : "";
      const dimStyle = featSet && !featSet.has(n.id) ? 'style="opacity:0.35;"' : "";
      return `<button class="node-card ${cls}" data-card="${esc(n.id)}" ${dimStyle}>`
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
    btn.addEventListener("dblclick", () => handleDoubleClickNode(btn.dataset.card));
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
      Showing ${rows.length} of ${DATA.modules.length} modules. Double-click a row for functions.
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
    tr.addEventListener("dblclick", () => openFunctionsView("module", tr.dataset.mod));
  });
}

function renderArchArea(fitOnRender) {
  const isMod = level === "modules";
  const isFn = level === "functions";
  $("arch-tools").classList.toggle("hidden", isMod);
  $("module-tools").classList.toggle("hidden", !isMod);
  $("view-toggle-group").classList.toggle("hidden", isFn);
  $("overlay-toggle-group").classList.toggle("hidden", isFn);
  $("diagram-wrap-block").classList.toggle("hidden", isMod || (!isFn && viewMode !== "svg"));
  $("cards-arch").classList.toggle("hidden", isMod || isFn || viewMode !== "cards");
  $("modules-arch").classList.toggle("hidden", !isMod);

  document.querySelectorAll("[data-view]").forEach(b => {
    b.classList.toggle("btn-on", b.dataset.view === viewMode);
  });
  document.querySelectorAll("[data-overlay]").forEach(b => {
    b.classList.toggle("btn-on", b.dataset.overlay === overlay);
  });
  $("every-import-btn").classList.toggle("btn-on", everyImport);

  if (isFn) {
    $("arch-title").textContent = `Functions & Classes: ${fnScope ? fnScope.title : ""}`;
    $("arch-subtitle").textContent =
      "Internal CALLS & INHERITS graph. Click a symbol to inspect or slice.";
    renderFunctionsSvg(fitOnRender);
  } else if (isMod) {
    $("arch-title").textContent = "Module Catalog";
    $("arch-subtitle").textContent =
      "Search docstrings, sort metrics, or double-click any module for its call diagram.";
    renderModulesView();
  } else if (viewMode === "svg") {
    $("arch-title").textContent =
      level === "blocks" ? "Functional Block Architecture" : "Package Architecture";
    $("arch-subtitle").textContent =
      "Layered by Tarjan SCC & dependency rank. Double-click any box to drill down.";
    renderSvgView(fitOnRender);
  } else {
    $("arch-title").textContent =
      level === "blocks" ? "Functional Blocks (Cards)" : "Packages & Bricks (Cards)";
    $("arch-subtitle").textContent = "Grouped by inferred architectural plane.";
    renderCardsView();
  }
}

function renderInspector() {
  const box = $("inspector");
  if (level === "functions") {
    const graph = resolveFunctionGraph(fnScope);
    const symMap = Object.fromEntries((graph.symbols || []).map(s => [s.id, s]));
    const sym = symMap[picked.functions];
    if (!sym) {
      box.innerHTML = `<div class="muted">Select a function or class node.</div>`;
      return;
    }
    const callees = (graph.edges || []).filter(e => e.u === sym.id);
    const callers = (graph.edges || []).filter(e => e.v === sym.id);
    const jumpBtns = (list, key) => list.length
      ? list.map(e => {
          const targetId = e[key];
          const label = symMap[targetId] ? symMap[targetId].name : targetId;
          return `<button class="btn btn-sm" data-jfn="${esc(targetId)}">`
            + `${esc(label)}</button>`;
        }).join("")
      : `<span class="muted">None inside scope</span>`;

    box.innerHTML = `
      <div style="border-bottom:1px solid var(--border);padding-bottom:10px;">
        <div class="sec" style="color:var(--primary);">${esc(sym.kind)} · ${esc(sym.block_id)}</div>
        <h3 class="mono" style="overflow-wrap:anywhere;">${esc(sym.qualname)}</h3>
        <div class="mono small" style="margin-top:6px;">${esc(sym.signature)}</div>
        <div class="muted small" style="margin-top:4px;">
          ${esc(sym.file_path)}:${sym.line}-${sym.end_line}
        </div>
      </div>
      <div class="kpis kpis-4">
        <div class="kpi"><div class="kpi-v">${sym.degree}</div><div class="kpi-l">Degree</div></div>
        <div class="kpi">
          <div class="kpi-v">${callees.length}</div><div class="kpi-l">Calls</div>
        </div>
        <div class="kpi">
          <div class="kpi-v">${callers.length}</div><div class="kpi-l">Callers</div>
        </div>
        <div class="kpi">
          <div class="kpi-v">${sym.tested ? "YES" : "NO"}</div><div class="kpi-l">Tested</div>
        </div>
      </div>
      <div>
        <button class="btn btn-sm" id="back-up-btn">Back up one level (Backspace)</button>
      </div>
      <div>
        <div class="sec">Calls (${callees.length})</div>
        <div class="row">${jumpBtns(callees, "v")}</div>
      </div>
      <div>
        <div class="sec">Called By (${callers.length})</div>
        <div class="row">${jumpBtns(callers, "u")}</div>
      </div>
      <div class="subcard">
        <div class="sec">AI Context Slice</div>
        <code>codeoverlook slice ${esc(sym.id)} --budget 2500</code>
      </div>`;

    box.querySelectorAll("[data-jfn]").forEach(b => b.addEventListener("click", () => {
      picked.functions = b.dataset.jfn;
      renderFunctionsSvg(false);
      renderInspector();
    }));
    $("back-up-btn").addEventListener("click", stepUpOneLevel);
    return;
  }

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
        <div class="sec">Navigate</div>
        <div class="row">
          <button class="btn btn-sm btn-on" id="open-mod-fns">Functions Diagram</button>
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

    $("open-mod-fns").addEventListener("click", () => openFunctionsView("module", m.path));
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

  const fnBtnLabel = isPkg ? "Functions Diagram" : "Functions Diagram";
  const zoomButtons = isPkg
    ? `<button class="btn btn-sm btn-on" id="open-node-fns">${fnBtnLabel}</button>`
      + `<button class="btn btn-sm" data-zoom="blocks:${esc(node.block_id)}">`
      + `Level 1 · ${esc(node.block_id)}</button>`
      + `<button class="btn btn-sm" data-zoom-mods="packages:${esc(node.id)}">`
      + `Level 3 · ${node.prod_files} modules</button>`
    : `<button class="btn btn-sm btn-on" id="open-node-fns">${fnBtnLabel}</button>`
      + (DATA.packages.length
          ? `<button class="btn btn-sm" data-zoom-pkgs="${esc(node.id)}">`
            + `Level 2 · Packages</button>`
          : "")
      + `<button class="btn btn-sm" data-zoom-mods="blocks:${esc(node.id)}">`
      + `Level 3 · ${node.prod_files} modules</button>`;
  const libsOut = libs || '<span class="muted">Stdlib / internal only</span>';
  const weakPills = (node.weakness_tags || []).map(
    w => `<span class="tag tag-bad">${esc(w)}</span>`
  ).join(" ");

  const eyebrowTxt = node.zone === "tooling"
    ? "Tooling & Scripts"
    : (band ? band.label + " · " + band.title : "Block");
  const roleDescHtml = node.role_summary
    ? `<p class="muted small" style="margin-top:4px;">${esc(node.role_summary)}</p>`
    : "";
  const instStr = node.instability !== undefined ? node.instability.toFixed(2) : "-";

  box.innerHTML = `
    <div style="border-bottom:1px solid var(--border);padding-bottom:10px;">
      <div class="between" style="align-items:center;">
        <span class="sec" style="margin:0;color:var(--g-${band ? band.group : "entry"});">
          ${esc(eyebrowTxt)}
        </span>
        <span class="status-pill st-${esc(node.coverage_status)}">
          ${esc(node.coverage_status)}
        </span>
      </div>
      <h3 style="margin-top:4px;">${esc(node.title)}</h3>
      ${roleDescHtml}
      ${weakPills ? `<div class="row" style="margin-top:6px;">${weakPills}</div>` : ""}
    </div>
    <div class="kpis kpis-4">
      <div class="kpi">
        <div class="kpi-v">${node.prod_files}</div><div class="kpi-l">Files</div>
      </div>
      <div class="kpi">
        <div class="kpi-v">${node.file_coverage_pct.toFixed(0)}%</div>
        <div class="kpi-l">Covered</div>
      </div>
      <div class="kpi">
        <div class="kpi-v">${node.sensitive_sinks}</div><div class="kpi-l">Sinks</div>
      </div>
      <div class="kpi">
        <div class="kpi-v">${instStr}</div><div class="kpi-l">Instab.</div>
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

  $("open-node-fns").addEventListener("click", () =>
    openFunctionsView(isPkg ? "package" : "block", node.id)
  );
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
  renderLevelsAndFeatures();
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
  if (ev.key === "Escape" && isFullscreen) {
    toggleFullscreen(false);
    return;
  }
  if (ev.key === "Backspace" && !["INPUT", "TEXTAREA"].includes(ev.target.tagName)) {
    ev.preventDefault();
    stepUpOneLevel();
  }
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
renderDiagnosis();
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
        catalog: Optional module, external-library, findings, and symbol graph catalog.

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
            Project-specific semantic layers, vertical feature slices, structural weaknesses,
            and interactive function call graphs in one offline explorer.
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
      <div id="diag-card" class="card" style="padding:12px 16px;">
        <div class="between" style="align-items:center;">
          <h2 id="diag-title">Architect's Diagnosis</h2>
          <button id="diag-toggle" class="btn btn-sm" type="button">Hide</button>
        </div>
        <div id="diag-body" class="diag-grid"></div>
      </div>

      <div class="card" style="padding:12px 16px;display:flex;flex-direction:column;gap:10px;">
        <div class="sec" style="margin:0;">Level of Detail</div>
        <div id="levels" class="levels"></div>
        <div id="feature-row" class="row">
          <span class="sec" style="margin:0;">Highlight a feature:</span>
          <div id="feature-chips" class="row"></div>
          <span id="feature-desc" class="muted small"></span>
        </div>
        <div class="between" style="align-items:center;">
          <div id="breadcrumbs" class="crumbs"></div>
          <span class="muted small">
            Click to inspect · Double-click to open internals · Backspace to zoom out
          </span>
        </div>
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
              <div id="view-toggle-group" class="row" style="gap:4px;">
                <button class="btn btn-sm" data-view="svg" type="button">Diagram</button>
                <button class="btn btn-sm" data-view="cards" type="button">Cards</button>
              </div>
              <div id="overlay-toggle-group" class="row" style="gap:4px;">
                <button class="btn btn-sm" data-overlay="arch" type="button">Architecture</button>
                <button class="btn btn-sm" data-overlay="weaknesses" type="button">
                  Weaknesses
                </button>
                <button class="btn btn-sm" data-overlay="coverage" type="button">Coverage</button>
                <button class="btn btn-sm" data-overlay="security" type="button">Security</button>
              </div>
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
