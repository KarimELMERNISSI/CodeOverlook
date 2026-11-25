"""Modular JavaScript client for the standalone CodeOverlook HTML explorer."""

from __future__ import annotations

JS_CORE = r"""
const DATA = __DATA_JSON__;
const $ = id => document.getElementById(id);
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
}[c]));

let topTab = "arch";
let level = "blocks";     // "blocks" | "packages" | "modules" | "functions"
let viewMode = "svg";     // "svg" | "cards"
let modViewUser = null;   // null (auto) | "svg" | "table"
let overlay = "arch";     // "arch" | "weaknesses" | "coverage" | "security"
let densityMode = "auto"; // "auto" | "compact" | "balanced" | "detailed"
let edgeScope = "focus";  // "focus" | "hop2" | "risks" | "all"
let hideTooling = false;
let fnConnectedOnly = false;
let minimapOpen = true;
let minimapUserSet = false;
let nodeCap = 48;         // 48 | 96 | 99999
const collapsedBands = new Set();
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
let lastLayout = { width: 920, height: 420, boxes: {}, bands: [] };
let dragState = null;
let dragMoved = false;
let mmDragging = false;

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

function currentModView() {
  if (modViewUser) return modViewUser;
  return (scope || DATA.modules.length <= 50) ? "svg" : "table";
}

function buildQuickJumpIndex() {
  const items = [];
  DATA.blocks.forEach(b => items.push({
    kind: "Block", id: b.id, label: b.title,
    sub: `${b.prod_files} files | ${b.prod_loc} LOC`
  }));
  DATA.packages.forEach(p => items.push({
    kind: "Package", id: p.id, label: p.title,
    sub: `${p.block_id} | ${p.prod_files} files`
  }));
  DATA.modules.forEach(m => items.push({
    kind: "Module", id: m.path, label: m.path,
    sub: `${m.block_id} | ${m.loc} LOC`
  }));
  const seenSyms = new Set();
  const sg = DATA.symbol_graph || { by_module: {}, by_block: {} };
  const addSyms = obj => Object.values(obj || {}).forEach(g => (g.symbols || []).forEach(s => {
    if (seenSyms.has(s.id)) return;
    seenSyms.add(s.id);
    items.push({
      kind: "Symbol", id: s.id, file_path: s.file_path, label: s.qualname || s.name,
      sub: `${s.file_path}:${s.line}`
    });
  }));
  addSyms(sg.by_block);
  addSyms(sg.by_module);
  return items;
}

const QJ_INDEX = buildQuickJumpIndex();
let qjMatches = [];
let qjCursor = 0;

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
  else if (lvl === "functions") {
    const sep = id.indexOf(":");
    if (sep !== -1) {
      const kind = id.slice(0, sep);
      const targetId = id.slice(sep + 1);
      if (
        (kind === "block" && BLOCK_MAP[targetId])
        || (kind === "package" && PKG_MAP[targetId])
        || (kind === "module" && MOD_MAP[targetId])
      ) {
        const title = kind === "package" ? PKG_MAP[targetId].title : targetId;
        fnScope = { kind, id: targetId, title };
        level = "functions";
      }
    }
  }
}

function toggleBandCollapse(bandKey) {
  if (collapsedBands.has(bandKey)) collapsedBands.delete(bandKey);
  else collapsedBands.add(bandKey);
  refreshAll(false);
}

function renderHeader() {
  const s = DATA.summary;
  const prof = DATA.profile || {};
  $("pill-repo").textContent = DATA.repo_name;
  const scalePill = $("pill-scale");
  if (scalePill) {
    if (prof.size_label) {
      scalePill.textContent = prof.size_label;
      scalePill.classList.remove("hidden");
    } else {
      scalePill.classList.add("hidden");
    }
  }
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
      centerOnNode(jid);
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

  const shortNames = {
    blocks: "L1 Blocks", packages: "L2 Packages",
    modules: "L3 Modules", functions: "L4 Functions"
  };
  $("fs-levels").innerHTML = items.map(([id]) => {
    const disabled = (id === "packages" && !DATA.packages.length)
      || (id === "modules" && !DATA.modules.length)
      || (id === "functions" && !fnScope);
    return `<button type="button" class="btn btn-xs ${level === id ? "btn-on" : ""}" `
      + `data-level="${id}" ${disabled ? "disabled" : ""}>${shortNames[id]}</button>`;
  }).join("");

  document.querySelectorAll("[data-level]").forEach(btn => {
    btn.addEventListener("click", () => {
      level = btn.dataset.level;
      if (level === "blocks") scope = null;
      refreshAll(true);
    });
  });

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
      `<button type="button" class="btn btn-xs" id="clear-scope-btn">Show all</button>`
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
      refreshAll(true);
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
  } else if (level === "modules" && MOD_MAP[nodeId]) {
    openFunctionsView("module", nodeId);
  }
}

function jumpToQuickResult(item) {
  if (!item) return;
  $("quick-jump-dropdown").classList.add("hidden");
  $("quick-jump-input").value = "";
  if (item.kind === "Block") {
    scope = null; level = "blocks"; picked.blocks = item.id;
    refreshAll(true);
    centerOnNode(item.id);
  } else if (item.kind === "Package") {
    const pkg = PKG_MAP[item.id];
    scope = pkg ? { level: "blocks", id: pkg.block_id } : null;
    level = "packages"; picked.packages = item.id;
    refreshAll(true);
    centerOnNode(item.id);
  } else if (item.kind === "Module") {
    const m = MOD_MAP[item.id];
    scope = m ? { level: "blocks", id: m.block_id } : null;
    level = "modules"; picked.modules = item.id; modViewUser = "svg";
    refreshAll(true);
    centerOnNode(item.id);
  } else if (item.kind === "Symbol" && item.file_path) {
    fnScope = { kind: "module", id: item.file_path, title: item.file_path };
    level = "functions"; picked.functions = item.id;
    refreshAll(true);
    centerOnNode(item.id);
  }
}

function renderQuickJumpDropdown(query) {
  const dd = $("quick-jump-dropdown");
  const q = (query || "").trim().toLowerCase();
  if (!q) {
    dd.classList.add("hidden");
    qjMatches = [];
    return;
  }
  qjMatches = QJ_INDEX.filter(it =>
    it.label.toLowerCase().includes(q) || it.sub.toLowerCase().includes(q)
  ).slice(0, 12);
  if (qjCursor >= qjMatches.length) qjCursor = 0;
  if (!qjMatches.length) {
    dd.innerHTML = `<div class="muted small" style="padding:8px;">No matching items.</div>`;
    dd.classList.remove("hidden");
    return;
  }
  const byKind = new Map();
  qjMatches.forEach((it, idx) => {
    if (!byKind.has(it.kind)) byKind.set(it.kind, []);
    byKind.get(it.kind).push({ ...it, idx });
  });
  let htmlOut = "";
  byKind.forEach((arr, kind) => {
    htmlOut += `<div class="qj-group">${esc(kind)}s</div>`;
    arr.forEach(it => {
      htmlOut += `<button type="button" class="qj-item ${it.idx === qjCursor ? "active" : ""}" `
        + `data-qj-idx="${it.idx}">`
        + `<span class="mono">${esc(it.label)}</span>`
        + `<span class="qj-item-sub">${esc(it.sub)}</span></button>`;
    });
  });
  dd.innerHTML = htmlOut;
  dd.classList.remove("hidden");
  dd.querySelectorAll("[data-qj-idx]").forEach(btn => {
    btn.addEventListener("mousedown", ev => {
      ev.preventDefault();
      jumpToQuickResult(qjMatches[Number(btn.dataset.qjIdx)]);
    });
  });
}
"""

JS_LAYOUT = r"""
function orderNodesInBands(bandRows, edges) {
  const ordered = bandRows.map(r => ({
    band: r.band,
    items: [...r.items].sort((a, b) => (b.prod_loc - a.prod_loc) || a.id.localeCompare(b.id))
  }));
  const bandIdxOf = {};
  ordered.forEach((r, bi) => r.items.forEach(n => { bandIdxOf[n.id] = bi; }));

  const posMap = () => {
    const pos = {};
    ordered.forEach(r => r.items.forEach((n, idx) => { pos[n.id] = idx; }));
    return pos;
  };
  const neighborsOf = {};
  ordered.forEach(r => r.items.forEach(n => { neighborsOf[n.id] = []; }));
  edges.forEach(e => {
    if (neighborsOf[e.u] && bandIdxOf[e.v] !== undefined && e.u !== e.v) {
      neighborsOf[e.u].push(e.v);
    }
    if (neighborsOf[e.v] && bandIdxOf[e.u] !== undefined && e.u !== e.v) {
      neighborsOf[e.v].push(e.u);
    }
  });

  const sweep = dir => {
    const start = dir > 0 ? 1 : ordered.length - 2;
    const end = dir > 0 ? ordered.length : -1;
    for (let bi = start; bi !== end; bi += dir) {
      const pos = posMap();
      const targetBand = bi - dir;
      const rank = new Map();
      ordered[bi].items.forEach((n, idx) => {
        const adj = neighborsOf[n.id].filter(pid => bandIdxOf[pid] === targetBand);
        if (adj.length) {
          const avg = adj.reduce((acc, pid) => acc + (pos[pid] ?? idx), 0) / adj.length;
          rank.set(n.id, avg);
        } else {
          rank.set(n.id, idx + 0.01);
        }
      });
      ordered[bi].items.sort(
        (a, b) => (rank.get(a.id) - rank.get(b.id)) || a.id.localeCompare(b.id)
      );
    }
  };
  if (ordered.length > 1) { sweep(1); sweep(-1); }
  return ordered;
}

function computeEdgePaths(edges, boxes, layoutWidth) {
  const outGroups = {};
  const inGroups = {};
  edges.forEach((e, idx) => {
    if (!boxes[e.u] || !boxes[e.v]) return;
    (outGroups[e.u] ||= []).push({ idx, peer: boxes[e.v] });
    (inGroups[e.v] ||= []).push({ idx, peer: boxes[e.u] });
  });
  Object.values(outGroups).forEach(arr =>
    arr.sort((a, b) => (a.peer.x + a.peer.w / 2) - (b.peer.x + b.peer.w / 2))
  );
  Object.values(inGroups).forEach(arr =>
    arr.sort((a, b) => (a.peer.x + a.peer.w / 2) - (b.peer.x + b.peer.w / 2))
  );

  const outPort = {};
  const inPort = {};
  Object.entries(outGroups).forEach(([id, arr]) => {
    const b = boxes[id];
    arr.forEach((item, i) => {
      const frac = arr.length === 1 ? 0.5 : 0.18 + (0.64 * i) / (arr.length - 1);
      outPort[item.idx] = b.x + b.w * frac;
    });
  });
  Object.entries(inGroups).forEach(([id, arr]) => {
    const b = boxes[id];
    arr.forEach((item, i) => {
      const frac = arr.length === 1 ? 0.5 : 0.18 + (0.64 * i) / (arr.length - 1);
      inPort[item.idx] = b.x + b.w * frac;
    });
  });

  let upLane = 0;
  let latLane = 0;
  return edges.map((e, idx) => {
    const sb = boxes[e.u];
    const db = boxes[e.v];
    if (!sb || !db) return null;
    const sx = outPort[idx] ?? (sb.x + sb.w / 2);
    const dx = inPort[idx] ?? (db.x + db.w / 2);
    const sy = sb.y + sb.h;
    const dy = db.y;

    if (Math.abs(sb.y - db.y) < 6) {
      const laneOff = (latLane++ % 5) * 6;
      const dropY = sb.y + sb.h + 16 + laneOff;
      const d = `M ${sx.toFixed(1)} ${sy} C ${sx.toFixed(1)} ${dropY}, `
        + `${dx.toFixed(1)} ${dropY}, ${dx.toFixed(1)} ${sy + 3}`;
      return { d, midX: (sx + dx) / 2, midY: dropY - 2 };
    }
    if (sy < dy - 4) {
      const span = dy - sy;
      const c1y = sy + span * 0.42;
      const c2y = dy - span * 0.42;
      const d = `M ${sx.toFixed(1)} ${sy} C ${sx.toFixed(1)} ${c1y.toFixed(1)}, `
        + `${dx.toFixed(1)} ${c2y.toFixed(1)}, ${dx.toFixed(1)} ${dy}`;
      return { d, midX: (sx + dx) / 2, midY: (sy + dy) / 2 };
    }
    const lane = upLane++ % 14;
    const marginX = Math.max(sb.x + sb.w, db.x + db.w) + 22 + lane * 10;
    const clampedX = Math.min(layoutWidth - 28, marginX);
    const outY = sb.y + sb.h * 0.36;
    const inY = db.y + db.h * 0.36;
    const rx = sb.x + sb.w;
    const rdx = db.x + db.w;
    const d = `M ${rx} ${outY.toFixed(1)} L ${clampedX} ${outY.toFixed(1)} `
      + `L ${clampedX} ${inY.toFixed(1)} L ${rdx + 2} ${inY.toFixed(1)}`;
    return { d, midX: clampedX, midY: (outY + inY) / 2 };
  });
}

function resolveDensity(itemCount) {
  if (densityMode !== "auto") return densityMode;
  if (itemCount <= 10) return "detailed";
  if (itemCount <= 28) return "balanced";
  return "compact";
}

function getDensitySpec(density, maxRowItems) {
  const base = density === "detailed"
    ? { labelW: 236, nodeW: 236, nodeH: 88, gapX: 30, gapY: 32, maxCols: 4 }
    : density === "compact"
      ? { labelW: 204, nodeW: 168, nodeH: 52, gapX: 16, gapY: 16, maxCols: 9 }
      : { labelW: 224, nodeW: 210, nodeH: 76, gapX: 26, gapY: 28, maxCols: 6 };
  const canvas = $("viewport-canvas");
  const canvasWidth = (canvas && canvas.clientWidth) ? canvas.clientWidth : 960;
  const availCols = Math.floor((canvasWidth - base.labelW - 100) / (base.nodeW + base.gapX));
  const colsCap = Math.max(
    2,
    Math.min(base.maxCols, Math.max(2, availCols), Math.max(2, maxRowItems))
  );
  return { ...base, density, colsCap };
}

function layoutDiagram(nodes, edges, density) {
  let bandRows = DATA.bands.map(b => ({
    band: b,
    items: nodes.filter(n => n.band === b.id && n.zone !== "tooling")
  })).filter(r => r.items.length > 0);

  bandRows = orderNodesInBands(bandRows, edges);

  const toolingItems = hideTooling ? [] : nodes.filter(n => n.zone === "tooling");
  if (toolingItems.length) {
    bandRows.push({
      band: {
        id: "TOOLING", label: "TOOLING", group: "tooling",
        title: "Tooling & Scripts", desc: "Isolated non-production scripts & scratch",
        blocks_count: toolingItems.length,
        prod_files: toolingItems.reduce((a, b) => a + (b.prod_files || 0), 0),
        prod_loc: toolingItems.reduce((a, b) => a + (b.prod_loc || 0), 0),
        avg_coverage_pct: 0
      },
      items: toolingItems
    });
  }

  if (!bandRows.length) {
    return { width: 860, height: 240, bands: [], boxes: {}, edges: [], density: "balanced" };
  }

  const bandRankOf = {};
  bandRows.forEach((r, idx) => r.items.forEach(n => { bandRankOf[n.id] = idx; }));
  const upCount = edges.filter(
    e => e.direction === "up"
      || (bandRankOf[e.u] !== undefined && bandRankOf[e.v] !== undefined
        && bandRankOf[e.u] > bandRankOf[e.v])
  ).length;
  const rightGutter = Math.max(96, 48 + Math.min(14, upCount) * 10);

  const maxPerRow = Math.max(1, ...bandRows.map(r => r.items.length));
  const spec = getDensitySpec(density || resolveDensity(nodes.length), maxPerRow);
  const { labelW, nodeW, nodeH, gapX, gapY, colsCap } = spec;
  const padX = 22;
  const padY = density === "compact" ? 14 : 20;

  const contentW = colsCap * nodeW + (colsCap - 1) * gapX + padX * 2;
  const totalW = labelW + contentW + rightGutter;

  let curY = 14;
  const placedBands = [];
  const boxes = {};

  bandRows.forEach(row => {
    const bKey = `${level}:${row.band.id}`;
    const isCollapsed = collapsedBands.has(bKey);
    if (isCollapsed) {
      const bandH = 44;
      placedBands.push({
        band: row.band,
        bandKey: bKey,
        collapsed: true,
        itemCount: row.items.length,
        x: 10, y: curY, w: totalW - rightGutter + 8, h: bandH, labelW
      });
      curY += bandH + 10;
      return;
    }

    const rowsCount = Math.ceil(row.items.length / colsCap);
    const bandH = Math.max(
      density === "compact" ? 84 : 114,
      padY * 2 + rowsCount * nodeH + (rowsCount - 1) * gapY
    );
    placedBands.push({
      band: row.band,
      bandKey: bKey,
      collapsed: false,
      itemCount: row.items.length,
      x: 10, y: curY, w: totalW - rightGutter + 8, h: bandH, labelW
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

    curY += bandH + (density === "compact" ? 12 : 16);
  });

  return {
    width: totalW, height: curY + 8, bands: placedBands,
    boxes, edges, density: spec.density
  };
}

function applyTransform() {
  const svg = $("arch-svg");
  if (!svg) return;
  svg.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom})`;
  $("zoom-label").textContent = `${Math.round(zoom * 100)}%`;
  updateMinimapViewport();
}

function fitToViewport() {
  const canvas = $("viewport-canvas");
  if (!canvas || !lastLayout.width) return;
  const cw = Math.max(260, canvas.clientWidth - 28);
  const ch = Math.max(240, canvas.clientHeight - 28);
  const scale = Math.min(cw / lastLayout.width, ch / lastLayout.height, 1.35);
  zoom = Math.max(0.28, Math.min(2.5, scale));
  panX = Math.max(10, (canvas.clientWidth - lastLayout.width * zoom) / 2);
  panY = Math.max(10, (canvas.clientHeight - lastLayout.height * zoom) / 2);
  applyTransform();
}

function centerOnNode(nodeId) {
  const canvas = $("viewport-canvas");
  const box = (lastLayout.boxes || {})[nodeId];
  if (!canvas || !box) return;
  if (zoom < 0.85) zoom = 0.95;
  const cx = box.x + box.w / 2;
  const cy = box.y + box.h / 2;
  panX = canvas.clientWidth / 2 - cx * zoom;
  panY = canvas.clientHeight / 2 - cy * zoom;
  applyTransform();
}

function renderMinimap(chosenId, visibleCount) {
  const mmBox = $("minimap-box");
  const mmSvg = $("minimap-svg");
  if (!mmBox || !mmSvg) return;
  if (!minimapUserSet && typeof visibleCount === "number") {
    minimapOpen = visibleCount > 6;
  }
  mmBox.classList.toggle("collapsed", !minimapOpen);
  $("minimap-toggle").textContent = minimapOpen ? "-" : "+";
  if (!minimapOpen || !lastLayout.width) return;

  mmSvg.setAttribute("viewBox", `0 0 ${lastLayout.width} ${lastLayout.height}`);
  const bandsRects = (lastLayout.bands || []).map(b =>
    `<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="8" `
    + `fill="var(--soft)" stroke="var(--border)" stroke-width="3"/>`
  ).join("");
  const nodeRects = Object.entries(lastLayout.boxes || {}).map(([id, b]) => {
    const isSel = id === chosenId;
    return `<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="6" `
      + `fill="${isSel ? "var(--primary)" : "var(--muted)"}" `
      + `fill-opacity="${isSel ? "0.9" : "0.35"}"/>`;
  }).join("");
  mmSvg.innerHTML = `${bandsRects}${nodeRects}`
    + `<rect id="minimap-vp" x="0" y="0" width="100" height="80" fill="var(--primary)" `
    + `fill-opacity="0.12" stroke="var(--primary)" stroke-width="6" rx="4"/>`;
  updateMinimapViewport();
}

function updateMinimapViewport() {
  const vpRect = $("minimap-vp");
  const canvas = $("viewport-canvas");
  if (!vpRect || !canvas || !lastLayout.width) return;
  const vx = -panX / zoom;
  const vy = -panY / zoom;
  const vw = canvas.clientWidth / zoom;
  const vh = canvas.clientHeight / zoom;
  vpRect.setAttribute("x", Math.max(0, vx).toFixed(1));
  vpRect.setAttribute("y", Math.max(0, vy).toFixed(1));
  vpRect.setAttribute("width", Math.max(24, Math.min(lastLayout.width, vw)).toFixed(1));
  vpRect.setAttribute("height", Math.max(24, Math.min(lastLayout.height, vh)).toFixed(1));
}

function showHoverPopover(ev, htmlContent) {
  const pop = $("hover-popover");
  const wrap = $("viewport-canvas").parentElement;
  if (!pop || !wrap || dragState) return;
  pop.innerHTML = htmlContent;
  pop.classList.remove("hidden");
  const rect = wrap.getBoundingClientRect();
  const pw = pop.offsetWidth || 250;
  const ph = pop.offsetHeight || 110;
  const lx = Math.min(rect.width - pw - 10, Math.max(10, ev.clientX - rect.left + 16));
  const ly = Math.min(rect.height - ph - 10, Math.max(10, ev.clientY - rect.top + 16));
  pop.style.left = `${lx}px`;
  pop.style.top = `${ly}px`;
}

function hideHoverPopover() {
  const pop = $("hover-popover");
  if (pop) pop.classList.add("hidden");
}

function resolveEdgesByScope(edges, chosen, featSet) {
  if (edgeScope === "all") return edges;
  if (edgeScope === "risks") {
    return edges.filter(
      e => e.violation || e.direction === "up" || e.direction === "cycle"
    );
  }
  if (edgeScope === "hop2") {
    const hop1 = new Set([chosen]);
    edges.forEach(e => {
      if (e.u === chosen) hop1.add(e.v);
      if (e.v === chosen) hop1.add(e.u);
    });
    return edges.filter(
      e => hop1.has(e.u) || hop1.has(e.v)
        || (featSet && featSet.has(e.u) && featSet.has(e.v))
    );
  }
  return edges.filter(
    e => e.u === chosen || e.v === chosen
      || (featSet && featSet.has(e.u) && featSet.has(e.v))
  );
}

function markerDefs() {
  const marker = (id, fill) => `<marker id="${id}" viewBox="0 0 10 10" refX="9" refY="5" `
    + `markerUnits="userSpaceOnUse" markerWidth="7" markerHeight="7" orient="auto">`
    + `<path d="M1,1.5 L9,5 L1,8.5 z" fill="${fill}"/></marker>`;
  return `<defs>${marker("m-muted", "var(--muted)")}${marker("m-down", "var(--edge-down)")}`
    + `${marker("m-up", "var(--edge-up)")}${marker("m-bad", "var(--bad)")}`
    + `${marker("m-inh", "var(--g-inherit)")}</defs>`;
}
"""

JS_VIEWS = r"""
function resolveFunctionGraph(fScope) {
  const sg = DATA.symbol_graph || { by_module: {}, by_block: {}, cross_edges: [] };
  if (!fScope) return { symbols: [], edges: [], total_symbols: 0 };
  if (fScope.kind === "block") {
    const g = sg.by_block[fScope.id] || { symbols: [], edges: [] };
    return { ...g, total_symbols: g.total_symbols || (g.symbols || []).length };
  }
  if (fScope.kind === "module") {
    const g = sg.by_module[fScope.id] || { symbols: [], edges: [] };
    return { ...g, total_symbols: g.total_symbols || (g.symbols || []).length };
  }
  const pkg = PKG_MAP[fScope.id];
  if (!pkg) return { symbols: [], edges: [], total_symbols: 0 };
  let allSyms = [];
  let allEdges = [];
  let totalSymCount = 0;
  (pkg.member_modules || []).forEach(fp => {
    const sub = sg.by_module[fp];
    if (sub) {
      allSyms = allSyms.concat(sub.symbols || []);
      allEdges = allEdges.concat(sub.edges || []);
      totalSymCount += sub.total_symbols || (sub.symbols || []).length;
    }
  });
  (sg.cross_edges || []).forEach(ce => allEdges.push(ce));
  allSyms.sort((a, b) => (b.degree - a.degree) || (b.sinks - a.sinks));
  const kept = allSyms.slice(0, 42);
  const keepIds = new Set(kept.map(s => s.id));
  const edgeSeen = new Set();
  const mergedEdges = [];
  allEdges.forEach(e => {
    if (!keepIds.has(e.u) || !keepIds.has(e.v)) return;
    const key = `${e.u}|${e.v}|${e.kind}`;
    if (edgeSeen.has(key)) return;
    edgeSeen.add(key);
    mergedEdges.push(e);
  });
  kept.sort((a, b) => a.file_path.localeCompare(b.file_path) || (a.line - b.line));
  return { symbols: kept, edges: mergedEdges, total_symbols: totalSymCount };
}

function activeNodesAndEdges() {
  if (level === "packages") {
    let nodes = DATA.packages;
    if (scope && scope.level === "blocks") {
      nodes = nodes.filter(p => p.block_id === scope.id);
    }
    if (hideTooling) nodes = nodes.filter(p => p.zone !== "tooling");
    const ids = new Set(nodes.map(n => n.id));
    const edges = DATA.package_edges.filter(e => ids.has(e.u) && ids.has(e.v));
    return { nodes, edges, nodeMap: PKG_MAP };
  }
  const nodes = hideTooling ? DATA.blocks.filter(b => b.zone !== "tooling") : DATA.blocks;
  const ids = new Set(nodes.map(n => n.id));
  const edges = DATA.block_edges.filter(e => ids.has(e.u) && ids.has(e.v));
  return { nodes, edges, nodeMap: BLOCK_MAP };
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

function renderScopeBanner(htmlStr) {
  const banner = $("scope-banner");
  if (!htmlStr) {
    banner.classList.add("hidden");
    banner.innerHTML = "";
  } else {
    banner.innerHTML = htmlStr;
    banner.classList.remove("hidden");
  }
}

function renderCapBanner(label, totalCount, includeTableBtn) {
  const btns = [48, 96, 99999].map(cap => {
    const lbl = cap >= 99999 ? "All" : String(cap);
    const active = nodeCap === cap ? "btn-on" : "";
    return `<button type="button" class="btn btn-xs ${active}" `
      + `data-set-cap="${cap}">${lbl}</button>`;
  }).join("");
  const tbl = includeTableBtn
    ? `<button type="button" class="btn btn-xs" id="switch-mod-table-btn">`
      + `Switch to Table (all ${totalCount})</button>`
    : "";
  renderScopeBanner(
    `<span>Showing top ${Math.min(nodeCap, totalCount)} of ${totalCount} ${label} `
    + `by coupling &amp; LOC.</span>`
    + `<div class="row" style="gap:4px;">Cap: ${btns}${tbl}</div>`
  );
  $("scope-banner").querySelectorAll("[data-set-cap]").forEach(btn => {
    btn.addEventListener("click", () => {
      nodeCap = Number(btn.dataset.setCap);
      refreshAll(true);
    });
  });
  const swBtn = $("switch-mod-table-btn");
  if (swBtn) swBtn.addEventListener("click", () => {
    modViewUser = "table";
    refreshAll(false);
  });
}

function emptyPythonNoticeHtml() {
  return `<div style="padding:24px;">`
    + `<div class="subcard">`
    + `<strong>No Python (.py) files found in this repository.</strong>`
    + `<div class="muted" style="margin-top:4px;">`
    + `For now, CodeOverlook only supports Python projects.`
    + `</div></div></div>`;
}

function renderSvgView(fitOnRender) {
  let { nodes, edges, nodeMap } = activeNodesAndEdges();
  if (!nodes.length) {
    renderScopeBanner("");
    $("viewport-canvas").innerHTML = !DATA.blocks.length
      ? emptyPythonNoticeHtml()
      : `<div class="muted" style="padding:20px;">No nodes.</div>`;
    renderMinimap(null, 0);
    return;
  }

  if (level === "packages" && nodes.length > 48) {
    const totalPkgs = nodes.length;
    if (totalPkgs > nodeCap) {
      nodes = [...nodes].sort((a, b) =>
        ((b.imports.length + b.imported_by.length) - (a.imports.length + a.imported_by.length))
        || (b.prod_loc - a.prod_loc)
        || a.id.localeCompare(b.id)
      ).slice(0, nodeCap);
      const keepIds = new Set(nodes.map(n => n.id));
      edges = edges.filter(e => keepIds.has(e.u) && keepIds.has(e.v));
    }
    renderCapBanner("packages", totalPkgs, false);
  } else {
    renderScopeBanner("");
  }

  if (!picked[level] || !nodeMap[picked[level]] || !nodes.some(n => n.id === picked[level])) {
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

  const density = resolveDensity(nodes.length);
  const shownEdgesRaw = resolveEdgesByScope(edges, chosen, featSet);
  const layout = layoutDiagram(nodes, shownEdgesRaw, density);
  lastLayout = layout;

  const visibleNodes = nodes.filter(n => Boolean(layout.boxes[n.id]));
  const shownEdges = shownEdgesRaw.filter(
    e => Boolean(layout.boxes[e.u]) && Boolean(layout.boxes[e.v])
  );
  const edgePriority = e => {
    if (e.violation || e.direction === "violation") return 4;
    if (e.direction === "cycle" || e.direction === "up") return 3;
    if (e.u === chosen || e.v === chosen) return 2;
    return 1;
  };
  shownEdges.sort((a, b) => edgePriority(a) - edgePriority(b));

  const bandsSvg = layout.bands.map(b => {
    const c = `var(--g-${b.band.group})`;
    const titleStr = b.band.title.length > 26
      ? b.band.title.slice(0, 24) + ".." : b.band.title;
    const filesCnt = b.band.prod_files ?? 0;
    const locCnt = b.band.prod_loc ?? 0;
    const covAvg = b.band.avg_coverage_pct ?? 0;
    const metaStr = `${b.band.blocks_count || b.itemCount || 0} blk · ${filesCnt} files · `
      + `${locCnt.toLocaleString()} LOC · ${covAvg.toFixed(0)}% cov`;
    const toggleTxt = b.collapsed ? `+ ${b.itemCount} hidden` : "Hide";
    const toggleW = toggleTxt.length * 6.1 + 12;
    const toggleBtn = `<g class="band-toggle" data-toggle-band="${esc(b.bandKey)}">`
      + `<rect x="${b.x + b.labelW - toggleW - 8}" y="${b.y + 8}" width="${toggleW}" height="17" `
      + `rx="8.5" fill="var(--card)" stroke="var(--border)"/>`
      + `<text x="${b.x + b.labelW - toggleW / 2 - 8}" y="${b.y + 19.5}" text-anchor="middle" `
      + `font-size="9" font-weight="700" fill="var(--fg)">${esc(toggleTxt)}</text></g>`;
    if (b.collapsed) {
      return `<g>`
        + `<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="8" `
        + `fill="${c}" fill-opacity="0.04" stroke="${c}" stroke-opacity="0.3"/>`
        + `<rect x="${b.x}" y="${b.y}" width="${b.labelW}" height="${b.h}" rx="8" `
        + `fill="${c}" fill-opacity="0.12"/>`
        + `<text x="${b.x + 12}" y="${b.y + 20}" font-size="10.5" font-weight="700" `
        + `fill="${c}">${esc(b.band.label)}</text>`
        + `<text x="${b.x + 12}" y="${b.y + 35}" font-size="11.5" font-weight="700" `
        + `fill="var(--fg)">${esc(titleStr)}</text>`
        + `<text x="${b.x + b.labelW + 16}" y="${b.y + 26}" font-size="11" `
        + `fill="var(--muted)">Collapsed (${b.itemCount} hidden — click pill to expand)</text>`
        + `${toggleBtn}</g>`;
    }
    return `<g>`
      + `<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="8" `
      + `fill="${c}" fill-opacity="0.05" stroke="${c}" stroke-opacity="0.3"/>`
      + `<rect x="${b.x}" y="${b.y}" width="${b.labelW}" height="${b.h}" rx="8" `
      + `fill="${c}" fill-opacity="0.12"/>`
      + `<text x="${b.x + 12}" y="${b.y + 20}" font-size="10.5" font-weight="700" `
      + `fill="${c}">${esc(b.band.label)}</text>`
      + `<text x="${b.x + 12}" y="${b.y + 39}" font-size="12" font-weight="700" `
      + `fill="var(--fg)">${esc(titleStr)}</text>`
      + `<text x="${b.x + 12}" y="${b.y + 57}" font-size="10" `
      + `fill="var(--muted)">${esc(metaStr)}</text>`
      + (b.h >= 102
        ? `<text x="${b.x + 12}" y="${b.y + b.h - 10}" font-size="10" `
          + `fill="var(--muted)">${esc((b.band.desc || "").slice(0, 31))}</text>`
        : "")
      + `${toggleBtn}</g>`;
  }).join("");

  const routed = computeEdgePaths(shownEdges, layout.boxes, layout.width);
  const denseGraph = shownEdges.length > 50;
  const edgeBadges = [];
  const arrowsSvg = shownEdges.map((e, idx) => {
    const route = routed[idx];
    if (!route) return "";
    const isOut = e.u === chosen;
    const isIn = e.v === chosen;
    const dir = e.direction || "";
    let stroke = "var(--muted)";
    let marker = "m-muted";
    let opacity = denseGraph ? "0.20" : "0.42";
    let sw = 1.2;
    let dash = "";
    if (e.violation || dir === "violation") {
      stroke = "var(--bad)"; marker = "m-bad"; opacity = "0.95";
      sw = 2.4; dash = 'stroke-dasharray="5 3"';
    } else if (dir === "up" || dir === "cycle") {
      stroke = dir === "cycle" ? "var(--bad)" : "var(--edge-up)";
      marker = dir === "cycle" ? "m-bad" : "m-up";
      opacity = (isOut || isIn) ? "0.95" : "0.78";
      sw = 1.9; dash = 'stroke-dasharray="4 3"';
    } else if (isOut) {
      stroke = "var(--edge-down)"; marker = "m-down"; opacity = "0.95";
      sw = Math.min(3.5, 1.5 + Math.log2(1 + e.n) * 0.65);
    } else if (isIn) {
      stroke = "var(--edge-up)"; marker = "m-up"; opacity = "0.95";
      sw = Math.min(3.5, 1.5 + Math.log2(1 + e.n) * 0.65);
    }
    const wantBadge = isOut || isIn || e.violation || (!denseGraph && dir === "up");
    if (wantBadge && edgeBadges.length < 14 && e.n > 1) {
      edgeBadges.push({ x: route.midX, y: route.midY, n: e.n, color: stroke });
    }
    return `<path class="svg-edge" d="${route.d}" fill="none" stroke="${stroke}" `
      + `stroke-opacity="${opacity}" stroke-width="${sw}" ${dash} marker-end="url(#${marker})">`
      + `<title>${esc(e.u)} -> ${esc(e.v)} (${e.n} imports${dir ? ", " + dir : ""})</title>`
      + `</path>`;
  }).join("");

  const badgesSvg = edgeBadges.map(b =>
    `<g pointer-events="none">`
    + `<rect x="${(b.x - 11).toFixed(1)}" y="${(b.y - 8).toFixed(1)}" width="22" height="15" `
    + `rx="7.5" fill="var(--card)" stroke="${b.color}" stroke-width="1.2"/>`
    + `<text x="${b.x.toFixed(1)}" y="${(b.y + 3).toFixed(1)}" text-anchor="middle" `
    + `font-size="9" font-weight="700" fill="${b.color}">${b.n}</text></g>`
  ).join("");

  const nodesSvg = visibleNodes.map(n => {
    const p = layout.boxes[n.id];
    const isSel = n.id === chosen;
    const isUse = uses.has(n.id);
    const isUsedBy = usedBy.has(n.id);
    const inFeat = !featSet || featSet.has(n.id);
    const hasViolation = shownEdges.some(
      e => e.violation && ((e.u === chosen && e.v === n.id) || (e.v === chosen && e.u === n.id))
    );
    const dim = featSet
      ? !inFeat
      : (edgeScope === "focus" && !isSel && !isUse && !isUsedBy);
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
    const maxChars = density === "compact" ? 18 : density === "detailed" ? 26 : 23;
    const titleTxt = n.title.length > maxChars
      ? n.title.slice(0, maxChars - 2) + ".." : n.title;
    const covPct = n.file_coverage_pct || 0;
    const barMaxW = p.w - 46;
    const covW = Math.max(0, Math.min(barMaxW, (covPct / 100) * barMaxW));
    const covFill = covPct >= 70 ? "var(--ok)" : covPct >= 35 ? "var(--warn)" : "var(--bad)";
    const inDeg = (n.imported_by || []).length;
    const outDeg = (n.imports || []).length;
    const untSinks = n.untested_sinks || 0;

    let badgeEl = "";
    if (badge && (density !== "compact" || isSel || hasViolation)) {
      badgeEl = `<rect x="${p.x + p.w - bw - 6}" y="${p.y - 8}" width="${bw}" height="15" `
        + `rx="7.5" fill="${badgeBg}"/>`
        + `<text x="${p.x + p.w - bw / 2 - 6}" y="${p.y + 3}" text-anchor="middle" `
        + `font-size="8.5" font-weight="700" fill="var(--on-primary)">${esc(badge)}</text>`;
    }

    let bodyLines = "";
    if (density === "compact") {
      bodyLines =
        `<text x="${p.x + 12}" y="${p.y + 19}" font-size="11.5" font-weight="700" `
        + `fill="var(--fg)">${esc(titleTxt)}</text>`
        + `<text x="${p.x + 12}" y="${p.y + 34}" font-size="9.5" `
        + `fill="var(--muted)">${esc(nodeSubtitle(n))}</text>`;
    } else {
      bodyLines =
        `<text x="${p.x + 14}" y="${p.y + 22}" font-size="12.5" font-weight="700" `
        + `fill="var(--fg)">${esc(titleTxt)}</text>`
        + `<text x="${p.x + 14}" y="${p.y + 39}" font-size="10.5" `
        + `fill="var(--muted)">${esc(nodeSubtitle(n))}</text>`
        + `<text x="${p.x + 14}" y="${p.y + 54}" font-size="10" `
        + `fill="${untSinks > 0 ? "var(--bad)" : "var(--muted)"}">`
        + `in ${inDeg} · out ${outDeg}`
        + `${untSinks > 0 ? ` · ${untSinks} unt. sinks` : ""}</text>`;
      if (density === "detailed") {
        const libsStr = (n.external_libs || []).slice(0, 2).join(", ") || "stdlib";
        const detStr = `${n.role || "module"} · ${libsStr}`;
        const detShort = detStr.length > 29 ? detStr.slice(0, 27) + ".." : detStr;
        bodyLines += `<text x="${p.x + 14}" y="${p.y + 69}" font-size="9.5" `
          + `fill="var(--primary-strong)">${esc(detShort)}</text>`;
      }
    }

    return `<g opacity="${dim ? 0.36 : 1}">`
      + `<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="7" `
      + `fill="var(--card)" stroke="${stroke}" stroke-width="${sw}"/>`
      + `<rect x="${p.x}" y="${p.y}" width="5" height="${p.h}" rx="2" fill="${accent}"/>`
      + bodyLines
      + `<rect x="${p.x + 12}" y="${p.y + p.h - 10}" width="${barMaxW}" height="3.5" `
      + `rx="1.7" fill="var(--border)"/>`
      + `<rect x="${p.x + 12}" y="${p.y + p.h - 10}" width="${covW.toFixed(1)}" height="3.5" `
      + `rx="1.7" fill="${covFill}"/>`
      + `<text x="${p.x + p.w - 8}" y="${p.y + p.h - 6.5}" text-anchor="end" font-size="9.5" `
      + `font-weight="700" fill="${covFill}">${covPct.toFixed(0)}%</text>`
      + badgeEl
      + `<rect class="svg-node" data-node="${esc(n.id)}" x="${p.x}" y="${p.y}" `
      + `width="${p.w}" height="${p.h}" rx="7" fill="transparent"/>`
      + `</g>`;
  }).join("");

  const prodBands = layout.bands.filter(b => b.band.id !== "TOOLING");
  const guideX = layout.width - 14;
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
    + `${markerDefs()}${bandsSvg}${guideSvg}${arrowsSvg}${nodesSvg}${badgesSvg}</svg>`;

  $("viewport-canvas").querySelectorAll("[data-toggle-band]").forEach(el => {
    el.addEventListener("click", ev => {
      ev.stopPropagation();
      toggleBandCollapse(el.dataset.toggleBand);
    });
  });

  $("viewport-canvas").querySelectorAll("[data-node]").forEach(el => {
    const n = nodeMap[el.dataset.node];
    el.addEventListener("click", ev => {
      if (dragMoved) return;
      ev.stopPropagation();
      picked[level] = el.dataset.node;
      refreshAll(false);
    });
    el.addEventListener("dblclick", ev => {
      ev.stopPropagation();
      hideHoverPopover();
      handleDoubleClickNode(el.dataset.node);
    });
    el.addEventListener("mousemove", ev => {
      if (!n) return;
      const libs = (n.external_libs || []).slice(0, 4).join(", ") || "stdlib / internal";
      const wHtml = (n.weakness_tags || []).length
        ? `<div style="margin-top:4px;color:var(--bad);font-weight:600;">`
          + `${esc(n.weakness_tags.join(" · "))}</div>` : "";
      showHoverPopover(ev,
        `<strong>${esc(n.title)}</strong>`
        + `<div class="muted small">${esc(n.role_summary || n.block_id)}</div>`
        + `<div class="small" style="margin-top:4px;">Libs: ${esc(libs)}</div>`
        + wHtml
        + `<div class="muted small" style="margin-top:4px;">Double-click to drill down</div>`
      );
    });
    el.addEventListener("mouseleave", hideHoverPopover);
  });

  $("diagram-legend").innerHTML = `
    <span><i class="swatch" style="background:var(--edge-down)"></i>Focus imports it</span>
    <span>
      <i class="swatch" style="background:var(--edge-up)"></i>Imports the focus / back-edge
    </span>
    <span><i class="swatch" style="background:var(--bad)"></i>Cycle or forbidden violation</span>
    <span>Density: ${esc(layout.density)} | Double-click node for internals</span>`;

  renderMinimap(chosen, visibleNodes.length);
  if (fitOnRender) fitToViewport();
  else applyTransform();
}

function getFilteredModules() {
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
  return rows;
}

function renderModulesSvg(fitOnRender) {
  const allRows = getFilteredModules();
  if (!allRows.length) {
    renderScopeBanner("");
    $("viewport-canvas").innerHTML = !DATA.modules.length
      ? emptyPythonNoticeHtml()
      : `<div class="muted" style="padding:20px;">No matching modules.</div>`;
    renderMinimap(null, 0);
    return;
  }

  let rows = allRows;
  if (allRows.length > 48) {
    if (allRows.length > nodeCap) {
      rows = [...allRows].sort((a, b) =>
        ((b.imports.length + b.imported_by.length) - (a.imports.length + a.imported_by.length))
        || (b.sinks - a.sinks)
        || (b.loc - a.loc)
        || a.path.localeCompare(b.path)
      ).slice(0, nodeCap);
    }
    renderCapBanner("modules", allRows.length, true);
  } else {
    renderScopeBanner(
      `<span>Showing ${rows.length} modules. Double-click any module card for functions.</span>`
    );
  }

  if (!picked.modules || !rows.some(r => r.path === picked.modules)) {
    picked.modules = rows[0].path;
  }
  const chosen = picked.modules;

  const laneMap = new Map();
  const usePkgLane = scope && scope.level === "blocks";
  rows.forEach(m => {
    const lk = usePkgLane ? (m.package || "root") : m.block_id;
    if (!laneMap.has(lk)) laneMap.set(lk, []);
    laneMap.get(lk).push(m);
  });

  const lanes = [...laneMap.entries()];
  const maxItems = Math.max(1, ...lanes.map(([, arr]) => arr.length));
  const density = resolveDensity(rows.length);
  const spec = getDensitySpec(density, maxItems);
  const labelW = Math.min(200, spec.labelW);
  const nodeW = density === "compact" ? 176 : 214;
  const nodeH = density === "compact" ? 54 : 66;
  const gapX = spec.gapX;
  const gapY = density === "compact" ? 16 : 24;
  const padX = 20;
  const padY = density === "compact" ? 12 : 16;
  const colsCap = spec.colsCap;
  const contentW = colsCap * nodeW + (colsCap - 1) * gapX + padX * 2;
  const totalW = labelW + contentW + 100;

  let curY = 14;
  const placedLanes = [];
  const boxes = {};
  lanes.forEach(([title, arr]) => {
    const bKey = `modules:${title}`;
    const isCollapsed = collapsedBands.has(bKey);
    if (isCollapsed) {
      const laneH = 44;
      placedLanes.push({
        band: { title, label: usePkgLane ? "PKG" : "BLK", group: "services" },
        bandKey: bKey, collapsed: true, title, count: arr.length,
        x: 10, y: curY, w: totalW - 88, h: laneH
      });
      curY += laneH + 10;
      return;
    }
    const rowsCount = Math.ceil(arr.length / colsCap);
    const laneH = Math.max(88, padY * 2 + rowsCount * nodeH + (rowsCount - 1) * gapY);
    placedLanes.push({
      band: { title, label: usePkgLane ? "PKG" : "BLK", group: "services" },
      bandKey: bKey, collapsed: false, title, count: arr.length,
      x: 10, y: curY, w: totalW - 88, h: laneH
    });
    arr.forEach((m, idx) => {
      const rIdx = Math.floor(idx / colsCap);
      const cIdx = idx % colsCap;
      boxes[m.path] = {
        x: labelW + padX + cIdx * (nodeW + gapX),
        y: curY + padY + rIdx * (nodeH + gapY),
        w: nodeW, h: nodeH
      };
    });
    curY += laneH + 12;
  });

  lastLayout = { width: totalW, height: curY + 8, bands: placedLanes, boxes, density };

  const visibleRows = rows.filter(m => Boolean(boxes[m.path]));
  const modSet = new Set(visibleRows.map(r => r.path));
  const allEdges = [];
  visibleRows.forEach(m => {
    (m.imports || []).forEach(dst => {
      if (modSet.has(dst) && dst !== m.path) allEdges.push({ u: m.path, v: dst, n: 1 });
    });
  });
  const shownEdges = resolveEdgesByScope(allEdges, chosen, null);
  shownEdges.sort((a, b) =>
    ((a.u === chosen || a.v === chosen) ? 1 : 0)
    - ((b.u === chosen || b.v === chosen) ? 1 : 0)
  );
  const routed = computeEdgePaths(shownEdges, boxes, totalW);
  const denseGraph = shownEdges.length > 50;

  const lanesSvg = placedLanes.map(l => {
    const shortTitle = l.title.length > 22 ? l.title.slice(0, 20) + ".." : l.title;
    const toggleTxt = l.collapsed ? `+ ${l.count}` : "Hide";
    const toggleW = toggleTxt.length * 6.0 + 12;
    const toggleBtn = `<g class="band-toggle" data-toggle-band="${esc(l.bandKey)}">`
      + `<rect x="${l.x + labelW - toggleW - 20}" y="${l.y + 8}" width="${toggleW}" height="16" `
      + `rx="8" fill="var(--card)" stroke="var(--border)"/>`
      + `<text x="${l.x + labelW - toggleW / 2 - 20}" y="${l.y + 19}" text-anchor="middle" `
      + `font-size="9" font-weight="700" fill="var(--fg)">${esc(toggleTxt)}</text></g>`;
    return `<g>`
      + `<rect x="${l.x}" y="${l.y}" width="${l.w}" height="${l.h}" rx="8" `
      + `fill="var(--primary)" fill-opacity="0.04" stroke="var(--border)"/>`
      + `<rect x="${l.x}" y="${l.y}" width="${labelW - 14}" height="${l.h}" rx="8" `
      + `fill="var(--primary)" fill-opacity="0.09"/>`
      + `<text x="${l.x + 12}" y="${l.y + 23}" font-size="12" font-weight="700" `
      + `fill="var(--fg)">${esc(shortTitle)}</text>`
      + `<text x="${l.x + 12}" y="${l.y + 39}" font-size="10" `
      + `fill="var(--muted)">${l.count} modules</text>`
      + (l.collapsed
        ? `<text x="${l.x + labelW + 12}" y="${l.y + 26}" font-size="11" `
          + `fill="var(--muted)">Collapsed (${l.count} modules hidden)</text>`
        : "")
      + `${toggleBtn}</g>`;
  }).join("");

  const arrowsSvg = shownEdges.map((e, idx) => {
    const route = routed[idx];
    if (!route) return "";
    const isOut = e.u === chosen;
    const isIn = e.v === chosen;
    const stroke = isOut ? "var(--edge-down)" : isIn ? "var(--edge-up)" : "var(--muted)";
    const marker = isOut ? "m-down" : isIn ? "m-up" : "m-muted";
    const sw = (isOut || isIn) ? 1.9 : 1.1;
    const op = (isOut || isIn) ? 0.92 : (denseGraph ? 0.18 : 0.35);
    return `<path class="svg-edge" d="${route.d}" fill="none" stroke="${stroke}" `
      + `stroke-opacity="${op}" stroke-width="${sw}" `
      + `marker-end="url(#${marker})"><title>${esc(e.u)} -> ${esc(e.v)}</title></path>`;
  }).join("");

  const selMod = MOD_MAP[chosen] || rows[0];
  const uses = new Set(selMod.imports || []);
  const usedBy = new Set(selMod.imported_by || []);

  const nodesSvg = visibleRows.map(m => {
    const p = boxes[m.path];
    const isSel = m.path === chosen;
    const isOut = uses.has(m.path);
    const isIn = usedBy.has(m.path);
    const dim = edgeScope === "focus" && !isSel && !isOut && !isIn;
    const accent = m.sinks > 0 ? "var(--bad)" : m.tested ? "var(--ok)" : "var(--warn)";
    const stroke = isSel ? "var(--primary)" : isOut ? "var(--edge-down)"
      : isIn ? "var(--edge-up)" : "var(--border)";
    const baseName = m.path.split("/").pop() || m.path;
    const maxN = density === "compact" ? 19 : 24;
    const shortName = baseName.length > maxN ? baseName.slice(0, maxN - 2) + ".." : baseName;
    const meta = `${m.loc} LOC · in ${m.imported_by.length} / out ${m.imports.length}`;
    const tail = `${m.tested ? "TESTED" : "UNTESTED"}${m.sinks > 0 ? ` · ${m.sinks} SINK` : ""}`;
    const textHtml = density === "compact"
      ? `<text x="${p.x + 11}" y="${p.y + 21}" font-size="11.5" font-weight="700" `
        + `fill="var(--fg)">${esc(shortName)}</text>`
        + `<text x="${p.x + 11}" y="${p.y + 39}" font-size="9.5" `
        + `fill="var(--muted)">${esc(meta)}</text>`
      : `<text x="${p.x + 12}" y="${p.y + 21}" font-size="12" font-weight="700" `
        + `fill="var(--fg)">${esc(shortName)}</text>`
        + `<text x="${p.x + 12}" y="${p.y + 38}" font-size="10.5" `
        + `fill="var(--muted)">${esc(meta)}</text>`
        + `<text x="${p.x + 12}" y="${p.y + 54}" font-size="10" font-weight="600" `
        + `fill="${m.sinks > 0 ? "var(--bad)" : m.tested ? "var(--ok)" : "var(--warn)"}">`
        + `${esc(tail)}</text>`;
    return `<g opacity="${dim ? 0.38 : 1}">`
      + `<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="7" `
      + `fill="var(--card)" stroke="${stroke}" stroke-width="${isSel ? 2.4 : 1.3}"/>`
      + `<rect x="${p.x}" y="${p.y}" width="4.5" height="${p.h}" rx="2" fill="${accent}"/>`
      + textHtml
      + `<rect class="svg-node" data-mod-node="${esc(m.path)}" x="${p.x}" y="${p.y}" `
      + `width="${p.w}" height="${p.h}" rx="7" fill="transparent"/>`
      + `</g>`;
  }).join("");

  $("viewport-canvas").innerHTML =
    `<svg id="arch-svg" width="${totalW}" height="${curY + 8}" `
    + `viewBox="0 0 ${totalW} ${curY + 8}">`
    + `${markerDefs()}${lanesSvg}${arrowsSvg}${nodesSvg}</svg>`;

  $("viewport-canvas").querySelectorAll("[data-toggle-band]").forEach(el => {
    el.addEventListener("click", ev => {
      ev.stopPropagation();
      toggleBandCollapse(el.dataset.toggleBand);
    });
  });

  $("viewport-canvas").querySelectorAll("[data-mod-node]").forEach(el => {
    const m = MOD_MAP[el.dataset.modNode];
    el.addEventListener("click", ev => {
      if (dragMoved) return;
      ev.stopPropagation();
      picked.modules = el.dataset.modNode;
      renderModulesSvg(false);
      renderInspector();
      writeHash();
    });
    el.addEventListener("dblclick", ev => {
      ev.stopPropagation();
      hideHoverPopover();
      openFunctionsView("module", el.dataset.modNode);
    });
    el.addEventListener("mousemove", ev => {
      if (!m) return;
      showHoverPopover(ev,
        `<strong class="mono">${esc(m.path)}</strong>`
        + `<div class="muted small" style="margin-top:3px;">`
        + `${esc(m.docstring || "No module docstring.")}</div>`
        + `<div class="small" style="margin-top:4px;">`
        + `${m.loc} LOC · ${m.symbol_count} symbols · ${m.sinks} sinks</div>`
        + `<div class="muted small" style="margin-top:3px;">Double-click for functions</div>`
      );
    });
    el.addEventListener("mouseleave", hideHoverPopover);
  });

  $("diagram-legend").innerHTML = `
    <span><i class="swatch" style="background:var(--edge-down)"></i>Imports</span>
    <span><i class="swatch" style="background:var(--edge-up)"></i>Imported by</span>
    <span>Showing ${visibleRows.length} modules &amp; ${shownEdges.length} edges</span>`;

  renderMinimap(chosen, visibleRows.length);
  if (fitOnRender) fitToViewport();
  else applyTransform();
}

function renderFunctionsSvg(fitOnRender) {
  const graph = resolveFunctionGraph(fnScope);
  let syms = graph.symbols || [];
  const allEdges = graph.edges || [];
  const totalSyms = graph.total_symbols || syms.length;
  const fq = ($("fn-search").value || "").trim().toLowerCase();

  if (!syms.length) {
    renderScopeBanner("");
    $("viewport-canvas").innerHTML =
      `<div class="muted" style="padding:24px;">`
      + `No class or function symbols found in this scope.</div>`;
    renderMinimap(null);
    return;
  }

  const symMap = Object.fromEntries(syms.map(s => [s.id, s]));
  if (!picked.functions || !symMap[picked.functions]) {
    picked.functions = syms[0].id;
  }
  const chosen = picked.functions;

  if (fnConnectedOnly) {
    const conn = new Set([chosen]);
    allEdges.forEach(e => {
      if (e.u === chosen) conn.add(e.v);
      if (e.v === chosen) conn.add(e.u);
    });
    syms = syms.filter(s => conn.has(s.id) || s.degree > 0);
  }
  if (fq) {
    syms = syms.filter(s =>
      `${s.name} ${s.qualname} ${s.signature} ${s.file_path}`.toLowerCase().includes(fq)
    );
  }
  if (!syms.length) {
    renderScopeBanner(`<span>No symbols match the current filter.</span>`);
    $("viewport-canvas").innerHTML =
      `<div class="muted" style="padding:24px;">No symbols match filter.</div>`;
    renderMinimap(null);
    return;
  }

  const shownIds = new Set(syms.map(s => s.id));
  const edges = allEdges.filter(e => shownIds.has(e.u) && shownIds.has(e.v));

  renderScopeBanner(
    `<span>Showing ${syms.length} of ${totalSyms} symbols &amp; `
    + `${edges.length} internal call/inheritance edges.</span>`
    + (fnScope && fnScope.kind !== "module"
      ? `<span class="muted small">Click any file swimlane label to zoom into that file</span>`
      : "")
  );

  const laneKey = fnScope.kind === "module"
    ? (s => s.qualname.includes(".") ? s.qualname.split(".")[0] : "Module Functions")
    : (s => s.file_path);

  const laneMap = new Map();
  syms.forEach(s => {
    const lk = laneKey(s);
    if (!laneMap.has(lk)) laneMap.set(lk, []);
    laneMap.get(lk).push(s);
  });

  const lanes = [...laneMap.entries()];
  const maxItems = Math.max(1, ...lanes.map(([, arr]) => arr.length));
  const density = resolveDensity(syms.length);
  const spec = getDensitySpec(density, maxItems);
  const labelW = Math.min(205, spec.labelW);
  const nodeW = density === "compact" ? 194 : 228;
  const nodeH = density === "compact" ? 56 : 68;
  const gapX = spec.gapX;
  const gapY = density === "compact" ? 16 : 24;
  const padX = 20;
  const padY = density === "compact" ? 12 : 16;
  const colsCap = spec.colsCap;
  const contentW = colsCap * nodeW + (colsCap - 1) * gapX + padX * 2;
  const totalW = labelW + contentW + 100;

  let curY = 14;
  const placedLanes = [];
  const boxes = {};
  lanes.forEach(([title, arr]) => {
    const bKey = `functions:${title}`;
    const isCollapsed = collapsedBands.has(bKey);
    if (isCollapsed) {
      const laneH = 44;
      placedLanes.push({
        bandKey: bKey, collapsed: true, title, count: arr.length,
        x: 10, y: curY, w: totalW - 88, h: laneH
      });
      curY += laneH + 10;
      return;
    }
    const rowsCount = Math.ceil(arr.length / colsCap);
    const laneH = Math.max(88, padY * 2 + rowsCount * nodeH + (rowsCount - 1) * gapY);
    placedLanes.push({
      bandKey: bKey, collapsed: false, title, count: arr.length,
      x: 10, y: curY, w: totalW - 88, h: laneH
    });
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

  lastLayout = { width: totalW, height: curY + 8, bands: placedLanes, boxes, density };

  const visibleSyms = syms.filter(s => Boolean(boxes[s.id]));
  const visibleEdges = edges.filter(e => Boolean(boxes[e.u]) && Boolean(boxes[e.v]));

  const lanesSvg = placedLanes.map(l => {
    const shortTitle = l.title.length > 22 ? "..." + l.title.slice(-20) : l.title;
    const clickable = fnScope.kind !== "module" && MOD_MAP[l.title];
    const toggleTxt = l.collapsed ? `+ ${l.count}` : "Hide";
    const toggleW = toggleTxt.length * 6.0 + 12;
    const toggleBtn = `<g class="band-toggle" data-toggle-band="${esc(l.bandKey)}">`
      + `<rect x="${l.x + labelW - toggleW - 20}" y="${l.y + 8}" width="${toggleW}" height="16" `
      + `rx="8" fill="var(--card)" stroke="var(--border)"/>`
      + `<text x="${l.x + labelW - toggleW / 2 - 20}" y="${l.y + 19}" text-anchor="middle" `
      + `font-size="9" font-weight="700" fill="var(--fg)">${esc(toggleTxt)}</text></g>`;
    return `<g>`
      + `<rect x="${l.x}" y="${l.y}" width="${l.w}" height="${l.h}" rx="8" `
      + `fill="var(--primary)" fill-opacity="0.04" stroke="var(--border)"/>`
      + `<rect x="${l.x}" y="${l.y}" width="${labelW - 14}" height="${l.h}" rx="8" `
      + `fill="var(--primary)" fill-opacity="0.09"/>`
      + `<text x="${l.x + 12}" y="${l.y + 23}" font-size="11.5" font-weight="700" `
      + `fill="var(--fg)" class="${clickable ? "lane-link" : ""}" `
      + `${clickable ? `data-lane-mod="${esc(l.title)}"` : ""}>${esc(shortTitle)}</text>`
      + `<text x="${l.x + 12}" y="${l.y + 39}" font-size="10" `
      + `fill="var(--muted)">${l.count} symbols</text>`
      + (l.collapsed
        ? `<text x="${l.x + labelW + 12}" y="${l.y + 26}" font-size="11" `
          + `fill="var(--muted)">Collapsed (${l.count} symbols hidden)</text>`
        : "")
      + `${toggleBtn}</g>`;
  }).join("");

  const outSet = new Set(visibleEdges.filter(e => e.u === chosen).map(e => e.v));
  const inSet = new Set(visibleEdges.filter(e => e.v === chosen).map(e => e.u));
  const shownEdges = resolveEdgesByScope(visibleEdges, chosen, null);
  shownEdges.sort((a, b) =>
    ((a.u === chosen || a.v === chosen) ? 1 : 0)
    - ((b.u === chosen || b.v === chosen) ? 1 : 0)
  );
  const routed = computeEdgePaths(shownEdges, boxes, totalW);
  const denseGraph = shownEdges.length > 50;

  const arrowsSvg = shownEdges.map((e, idx) => {
    const route = routed[idx];
    if (!route) return "";
    const isInh = e.kind === "INHERITS";
    const isOut = e.u === chosen;
    const isIn = e.v === chosen;
    const stroke = isInh ? "var(--g-inherit)"
      : isOut ? "var(--edge-down)" : isIn ? "var(--edge-up)" : "var(--muted)";
    const marker = isInh ? "m-inh" : isOut ? "m-down" : isIn ? "m-up" : "m-muted";
    const dash = isInh ? 'stroke-dasharray="4 3"' : "";
    const sw = (isOut || isIn) ? 2.0 : 1.2;
    const opacity = (isOut || isIn) ? 0.95 : (denseGraph ? 0.18 : 0.42);
    return `<path class="svg-edge" d="${route.d}" fill="none" stroke="${stroke}" `
      + `stroke-opacity="${opacity}" stroke-width="${sw}" ${dash} marker-end="url(#${marker})">`
      + `<title>${esc(e.u)} ${e.kind} ${esc(e.v)}</title></path>`;
  }).join("");

  const nodesSvg = visibleSyms.map(s => {
    const p = boxes[s.id];
    const isSel = s.id === chosen;
    const isOut = outSet.has(s.id);
    const isIn = inSet.has(s.id);
    const dim = edgeScope === "focus" && !isSel && !isOut && !isIn;
    const accent = s.sinks > 0 ? "var(--bad)"
      : s.kind === "class" ? "var(--g-inherit)"
      : s.tested ? "var(--ok)" : "var(--primary)";
    const stroke = isSel ? "var(--primary)" : isOut ? "var(--edge-down)"
      : isIn ? "var(--edge-up)" : "var(--border)";
    const kindLbl = s.kind === "class" ? "CLASS" : s.kind === "method" ? "METHOD" : "FN";
    const nameTxt = s.name.length > 21 ? s.name.slice(0, 19) + ".." : s.name;
    const sigClean = (s.signature || "")
      .replace(/^(?:async )?def [^(]+/, "")
      .replace(/^class /, "");
    const sigPrev = sigClean.length > 31 ? sigClean.slice(0, 29) + ".." : sigClean;
    const metaTxt = `${kindLbl} · L${s.line} · deg ${s.degree}`
      + (s.tested ? " · TESTED" : "") + (s.sinks > 0 ? ` · ${s.sinks} SINK` : "");

    const bodyHtml = density === "compact"
      ? `<text x="${p.x + 11}" y="${p.y + 21}" font-size="11.5" font-weight="700" `
        + `fill="var(--fg)">${esc(nameTxt)}</text>`
        + `<text x="${p.x + 11}" y="${p.y + 39}" font-size="9.5" `
        + `fill="${s.sinks > 0 ? "var(--bad)" : "var(--muted)"}">${esc(metaTxt)}</text>`
      : `<text x="${p.x + 12}" y="${p.y + 20}" font-size="12" font-weight="700" `
        + `fill="var(--fg)">${esc(nameTxt)}</text>`
        + `<text x="${p.x + 12}" y="${p.y + 37}" font-size="10" class="mono" `
        + `fill="var(--code)">${esc(sigPrev)}</text>`
        + `<text x="${p.x + 12}" y="${p.y + 54}" font-size="10" `
        + `fill="${s.sinks > 0 ? "var(--bad)" : "var(--muted)"}">${esc(metaTxt)}</text>`;

    return `<g opacity="${dim ? 0.42 : 1}">`
      + `<rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="7" `
      + `fill="var(--card)" stroke="${stroke}" stroke-width="${isSel ? 2.4 : 1.3}"/>`
      + `<rect x="${p.x}" y="${p.y}" width="4.5" height="${p.h}" rx="2" fill="${accent}"/>`
      + bodyHtml
      + `<rect class="svg-node" data-fn="${esc(s.id)}" x="${p.x}" y="${p.y}" `
      + `width="${p.w}" height="${p.h}" rx="7" fill="transparent"/>`
      + `</g>`;
  }).join("");

  $("viewport-canvas").innerHTML =
    `<svg id="arch-svg" width="${totalW}" height="${curY + 8}" `
    + `viewBox="0 0 ${totalW} ${curY + 8}">`
    + `${markerDefs()}${lanesSvg}${arrowsSvg}${nodesSvg}</svg>`;

  $("viewport-canvas").querySelectorAll("[data-toggle-band]").forEach(el => {
    el.addEventListener("click", ev => {
      ev.stopPropagation();
      toggleBandCollapse(el.dataset.toggleBand);
    });
  });

  $("viewport-canvas").querySelectorAll("[data-lane-mod]").forEach(el => {
    el.addEventListener("click", ev => {
      ev.stopPropagation();
      openFunctionsView("module", el.dataset.laneMod);
    });
  });

  $("viewport-canvas").querySelectorAll("[data-fn]").forEach(el => {
    const s = symMap[el.dataset.fn];
    el.addEventListener("click", ev => {
      if (dragMoved) return;
      ev.stopPropagation();
      picked.functions = el.dataset.fn;
      renderFunctionsSvg(false);
      renderInspector();
    });
    el.addEventListener("mousemove", ev => {
      if (!s) return;
      showHoverPopover(ev,
        `<strong class="mono">${esc(s.qualname)}</strong>`
        + `<div class="mono small" style="margin-top:3px;">${esc(s.signature)}</div>`
        + (s.doc ? `<div class="muted small" style="margin-top:4px;">${esc(s.doc)}</div>` : "")
        + `<div class="small" style="margin-top:4px;">${esc(s.file_path)}:${s.line}-${s.end_line}`
        + ` · ${s.tested ? "Tested" : "Untested"}${s.sinks ? ` · ${s.sinks} sinks` : ""}</div>`
      );
    });
    el.addEventListener("mouseleave", hideHoverPopover);
  });

  $("diagram-legend").innerHTML = `
    <span><i class="swatch" style="background:var(--edge-down)"></i>Calls</span>
    <span><i class="swatch" style="background:var(--edge-up)"></i>Called by</span>
    <span><i class="swatch" style="background:var(--g-inherit)"></i>Inherits</span>
    <span>
      Showing ${visibleSyms.length}/${totalSyms} symbols &amp; ${shownEdges.length} edges
    </span>`;

  renderMinimap(chosen, visibleSyms.length);
  if (fitOnRender) fitToViewport();
  else applyTransform();
}

function renderCardsView() {
  renderScopeBanner("");
  const { nodes, nodeMap } = activeNodesAndEdges();
  if (!nodes.length) {
    $("cards-arch").innerHTML = !DATA.blocks.length
      ? emptyPythonNoticeHtml()
      : `<div class="muted">No items to display.</div>`;
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
  if (!hideTooling && nodes.some(n => n.zone === "tooling")) {
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

function renderModulesTable() {
  renderScopeBanner("");
  let rows = getFilteredModules();

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
      renderModulesTable();
    });
  });

  $("modules-arch").querySelectorAll("[data-mod]").forEach(tr => {
    tr.addEventListener("click", () => {
      picked.modules = tr.dataset.mod;
      renderModulesTable();
      renderInspector();
      writeHash();
    });
    tr.addEventListener("dblclick", () => openFunctionsView("module", tr.dataset.mod));
  });
}

function renderArchArea(fitOnRender) {
  const isMod = level === "modules";
  const isFn = level === "functions";
  const mView = currentModView();
  const showDiagram = isFn || (isMod && mView === "svg") || (!isMod && viewMode === "svg");

  $("view-toggle-group").classList.toggle("hidden", isMod || isFn);
  $("mod-view-group").classList.toggle("hidden", !isMod);
  $("overlay-toggle-group").classList.toggle("hidden", isMod || isFn);
  $("density-toggle-group").classList.toggle("hidden", !showDiagram);
  $("edge-scope-group").classList.toggle("hidden", !showDiagram);
  $("toggle-tooling-btn").classList.toggle(
    "hidden", isMod || isFn || !(DATA.tooling_blocks || []).length
  );
  $("fn-connected-btn").classList.toggle("hidden", !isFn);
  $("fn-search").classList.toggle("hidden", !isFn);
  $("module-search").classList.toggle("hidden", !isMod);

  $("diagram-wrap-block").classList.toggle("hidden", !showDiagram);
  $("cards-arch").classList.toggle("hidden", isMod || isFn || viewMode !== "cards");
  $("modules-arch").classList.toggle("hidden", !isMod || mView !== "table");

  document.querySelectorAll("[data-view]").forEach(b => {
    b.classList.toggle("btn-on", b.dataset.view === viewMode);
  });
  document.querySelectorAll("[data-modview]").forEach(b => {
    b.classList.toggle("btn-on", b.dataset.modview === mView);
  });
  document.querySelectorAll("[data-overlay]").forEach(b => {
    b.classList.toggle("btn-on", b.dataset.overlay === overlay);
  });
  document.querySelectorAll("[data-density]").forEach(b => {
    b.classList.toggle("btn-on", b.dataset.density === densityMode);
  });
  document.querySelectorAll("[data-edgescope]").forEach(b => {
    b.classList.toggle("btn-on", b.dataset.edgescope === edgeScope);
  });
  $("toggle-tooling-btn").classList.toggle("btn-on", hideTooling);
  $("fn-connected-btn").classList.toggle("btn-on", fnConnectedOnly);

  if (isFn) {
    $("arch-title").textContent = `Functions & Classes: ${fnScope ? fnScope.title : ""}`;
    $("arch-subtitle").textContent =
      "Internal CALLS & INHERITS graph. Click a symbol to inspect or slice.";
    renderFunctionsSvg(fitOnRender);
  } else if (isMod) {
    $("arch-title").textContent =
      mView === "svg" ? "Module Dependency Diagram" : "Module Catalog";
    $("arch-subtitle").textContent =
      "Search docstrings, switch Diagram/Table, or double-click any module for functions.";
    if (mView === "svg") renderModulesSvg(fitOnRender);
    else renderModulesTable();
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
"""

JS_INSPECTOR_AND_EVENTS = r"""
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
    const symFindings = (DATA.findings || []).filter(f => f.symbol_id === sym.id);
    const jumpBtns = (list, key) => list.length
      ? list.map(e => {
          const targetId = e[key];
          const label = symMap[targetId] ? symMap[targetId].name : targetId;
          return `<button class="btn btn-sm" data-jfn="${esc(targetId)}">`
            + `${esc(label)}</button>`;
        }).join("")
      : `<span class="muted">None inside scope</span>`;
    const findingsHtml = symFindings.map(f =>
      `<div class="subcard" style="margin-bottom:5px;">`
      + `<strong>${esc(f.severity)} ${esc(f.rule_id)}</strong> L${f.line}`
      + `<div class="muted small">${esc(f.message)}</div></div>`
    ).join("");

    box.innerHTML = `
      <div style="border-bottom:1px solid var(--border);padding-bottom:10px;">
        <div class="sec" style="color:var(--primary);">${esc(sym.kind)} · ${esc(sym.block_id)}</div>
        <h3 class="mono" style="overflow-wrap:anywhere;">${esc(sym.qualname)}</h3>
        <div class="mono small" style="margin-top:6px;">${esc(sym.signature)}</div>
        ${sym.doc ? `<p class="muted small" style="margin:6px 0 0 0;">${esc(sym.doc)}</p>` : ""}
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
      <div class="row">
        <button class="btn btn-sm" id="back-up-btn">Back up (Backspace)</button>
        <button class="btn btn-sm" id="jump-sym-mod">Jump to module</button>
      </div>
      ${findingsHtml
        ? `<div><div class="sec">Active Sinks &amp; Findings</div>${findingsHtml}</div>`
        : ""}
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
      centerOnNode(picked.functions);
      renderInspector();
    }));
    $("back-up-btn").addEventListener("click", stepUpOneLevel);
    $("jump-sym-mod").addEventListener("click", () => {
      if (!MOD_MAP[sym.file_path]) return;
      picked.modules = sym.file_path;
      level = "modules";
      refreshAll(true);
      centerOnNode(sym.file_path);
    });
    return;
  }

  if (level === "modules") {
    const m = MOD_MAP[picked.modules];
    if (!m) {
      box.innerHTML = `<div class="muted">Select a module to inspect details.</div>`;
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
      if (currentModView() === "svg") {
        renderModulesSvg(false);
        centerOnNode(picked.modules);
      } else {
        renderModulesTable();
      }
      renderInspector();
      writeHash();
    }));
    box.querySelectorAll("[data-zoom]").forEach(b => b.addEventListener("click", () => {
      const [lvl, id] = b.dataset.zoom.split(":");
      level = lvl; picked[lvl] = id; scope = null;
      refreshAll(true);
      centerOnNode(id);
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
    ? `<button class="btn btn-sm btn-on" id="open-node-fns">Functions Diagram</button>`
      + `<button class="btn btn-sm" data-zoom="blocks:${esc(node.block_id)}">`
      + `Level 1 · ${esc(node.block_id)}</button>`
      + `<button class="btn btn-sm" data-zoom-mods="packages:${esc(node.id)}">`
      + `Level 3 · ${node.prod_files} modules</button>`
    : `<button class="btn btn-sm btn-on" id="open-node-fns">Functions Diagram</button>`
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
    centerOnNode(picked[level]);
  }));
  box.querySelectorAll("[data-zoom]").forEach(b => b.addEventListener("click", () => {
    const [lvl, id] = b.dataset.zoom.split(":");
    level = lvl; picked[lvl] = id; scope = null;
    refreshAll(true);
    centerOnNode(id);
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
    refreshAll(true);
  }));
  box.querySelectorAll("[data-open-mod]").forEach(b => b.addEventListener("click", () => {
    if (!MOD_MAP[b.dataset.openMod]) return;
    picked.modules = b.dataset.openMod;
    level = "modules";
    refreshAll(true);
    centerOnNode(picked.modules);
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
document.querySelectorAll("[data-modview]").forEach(b =>
  b.addEventListener("click", () => { modViewUser = b.dataset.modview; refreshAll(true); })
);
document.querySelectorAll("[data-overlay]").forEach(b =>
  b.addEventListener("click", () => { overlay = b.dataset.overlay; refreshAll(false); })
);
document.querySelectorAll("[data-density]").forEach(b =>
  b.addEventListener("click", () => { densityMode = b.dataset.density; refreshAll(true); })
);
document.querySelectorAll("[data-edgescope]").forEach(b =>
  b.addEventListener("click", () => { edgeScope = b.dataset.edgescope; refreshAll(false); })
);
$("toggle-tooling-btn").addEventListener("click", () => {
  hideTooling = !hideTooling;
  refreshAll(true);
});
$("fn-connected-btn").addEventListener("click", () => {
  fnConnectedOnly = !fnConnectedOnly;
  refreshAll(true);
});
$("module-search").addEventListener("input", () => {
  if (currentModView() === "svg") renderModulesSvg(true);
  else renderModulesTable();
});
$("fn-search").addEventListener("input", () => renderFunctionsSvg(true));

const qjInput = $("quick-jump-input");
qjInput.addEventListener("input", () => {
  qjCursor = 0;
  renderQuickJumpDropdown(qjInput.value);
});
qjInput.addEventListener("keydown", ev => {
  if (ev.key === "ArrowDown" && qjMatches.length) {
    ev.preventDefault();
    qjCursor = (qjCursor + 1) % qjMatches.length;
    renderQuickJumpDropdown(qjInput.value);
  } else if (ev.key === "ArrowUp" && qjMatches.length) {
    ev.preventDefault();
    qjCursor = (qjCursor - 1 + qjMatches.length) % qjMatches.length;
    renderQuickJumpDropdown(qjInput.value);
  } else if (ev.key === "Enter" && qjMatches.length) {
    ev.preventDefault();
    jumpToQuickResult(qjMatches[qjCursor]);
  } else if (ev.key === "Escape") {
    $("quick-jump-dropdown").classList.add("hidden");
    qjInput.blur();
  }
});
qjInput.addEventListener("blur", () => {
  setTimeout(() => $("quick-jump-dropdown").classList.add("hidden"), 150);
});

$("zoom-in-btn").addEventListener("click", () => {
  zoom = Math.min(3.2, zoom * 1.2);
  applyTransform();
});
$("zoom-out-btn").addEventListener("click", () => {
  zoom = Math.max(0.25, zoom / 1.2);
  applyTransform();
});
$("zoom-fit-btn").addEventListener("click", fitToViewport);
$("zoom-center-btn").addEventListener("click", () => {
  const activeId = level === "functions" ? picked.functions : picked[level];
  if (activeId) centerOnNode(activeId);
});
$("minimap-toggle").addEventListener("click", () => {
  minimapUserSet = true;
  minimapOpen = !minimapOpen;
  renderMinimap(level === "functions" ? picked.functions : picked[level]);
});
$("fs-btn").addEventListener("click", () => toggleFullscreen());
$("fs-insp-btn").addEventListener("click", () => {
  fsShowInspector = !fsShowInspector;
  $("arch-grid").classList.toggle("fs-hide-insp", isFullscreen && !fsShowInspector);
  $("fs-insp-btn").textContent = fsShowInspector ? "Hide details" : "Show details";
  setTimeout(() => fitToViewport(), 30);
});

document.addEventListener("keydown", ev => {
  const inInput = ["INPUT", "TEXTAREA", "SELECT"].includes(ev.target.tagName);
  if (ev.key === "Escape") {
    if (!$("quick-jump-dropdown").classList.contains("hidden")) {
      $("quick-jump-dropdown").classList.add("hidden");
      return;
    }
    if (isFullscreen) toggleFullscreen(false);
    return;
  }
  if (inInput) return;
  if (ev.key === "/") {
    ev.preventDefault();
    qjInput.focus();
  } else if (ev.key === "Backspace") {
    ev.preventDefault();
    stepUpOneLevel();
  } else if (ev.key === "1") {
    level = "blocks"; scope = null; refreshAll(true);
  } else if (ev.key === "2" && DATA.packages.length) {
    level = "packages"; refreshAll(true);
  } else if (ev.key === "3" && DATA.modules.length) {
    level = "modules"; refreshAll(true);
  } else if (ev.key === "4" && fnScope) {
    level = "functions"; refreshAll(true);
  } else if (ev.key === "+" || ev.key === "=") {
    zoom = Math.min(3.2, zoom * 1.2); applyTransform();
  } else if (ev.key === "-") {
    zoom = Math.max(0.25, zoom / 1.2); applyTransform();
  } else if (ev.key === "0") {
    fitToViewport();
  } else if (ev.key.toLowerCase() === "c") {
    const activeId = level === "functions" ? picked.functions : picked[level];
    if (activeId) centerOnNode(activeId);
  } else if (ev.key.toLowerCase() === "f") {
    toggleFullscreen();
  }
});
document.addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement && isFullscreen) toggleFullscreen(false);
});

const vp = $("viewport-canvas");
vp.addEventListener("mousedown", ev => {
  if (ev.button !== 0) return;
  hideHoverPopover();
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
  mmDragging = false;
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

function panFromMinimap(ev) {
  const mmSvg = $("minimap-svg");
  const rect = mmSvg.getBoundingClientRect();
  if (!rect.width || !rect.height || !lastLayout.width) return;
  const rx = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
  const ry = Math.max(0, Math.min(1, (ev.clientY - rect.top) / rect.height));
  const targetX = rx * lastLayout.width;
  const targetY = ry * lastLayout.height;
  panX = vp.clientWidth / 2 - targetX * zoom;
  panY = vp.clientHeight / 2 - targetY * zoom;
  applyTransform();
}

$("minimap-body").addEventListener("mousedown", ev => {
  ev.stopPropagation();
  mmDragging = true;
  panFromMinimap(ev);
});
window.addEventListener("mousemove", ev => {
  if (mmDragging) panFromMinimap(ev);
});

if (typeof ResizeObserver !== "undefined") {
  let rsRaf = 0;
  const ro = new ResizeObserver(() => {
    if (rsRaf) cancelAnimationFrame(rsRaf);
    rsRaf = requestAnimationFrame(() => updateMinimapViewport());
  });
  ro.observe(vp);
}

readHash();
if (!location.hash && DATA.profile && DATA.profile.recommended_level) {
  const rec = DATA.profile.recommended_level;
  if (rec === "modules" && DATA.modules.length) level = "modules";
  else if (rec === "packages" && DATA.packages.length) level = "packages";
  else level = "blocks";
}
renderHeader();
renderDiagnosis();
refreshAll(true);
"""


def build_explorer_js(data_json: str) -> str:
    """Assemble the standalone explorer JS script with embedded JSON data."""
    combined = "\n".join([JS_CORE, JS_LAYOUT, JS_VIEWS, JS_INSPECTOR_AND_EVENTS])
    return combined.replace("__DATA_JSON__", data_json)
