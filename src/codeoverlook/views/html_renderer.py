"""Standalone interactive multi-level HTML explorer for architecture and coverage."""

from __future__ import annotations

import html
import json
from typing import Any

from codeoverlook.core.coverage import RepoCoverageReport
from codeoverlook.views.explorer_layout import build_explorer_model
from codeoverlook.views.explorer_scripts import build_explorer_js
from codeoverlook.views.explorer_styles import EXPLORER_CSS


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
    js_code = build_explorer_js(data_json)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>CodeOverlook Inspector - {escaped_repo}</title>
<style>{EXPLORER_CSS}</style>
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
        <div class="between" style="align-items:center;">
          <span class="sec" style="margin:0;">Level of Detail</span>
          <span class="muted small">
            Keys: / Search | 1-4 Levels | c Center | 0 Fit | f Full screen | Backspace Up
          </span>
        </div>
        <div id="levels" class="levels"></div>
        <div id="feature-row" class="row">
          <span class="sec" style="margin:0;">Highlight a feature:</span>
          <div id="feature-chips" class="row"></div>
          <span id="feature-desc" class="muted small"></span>
        </div>
      </div>

      <div id="arch-grid" class="grid-arch">
        <div class="card" id="arch-panel">
          <div class="panel-nav">
            <div class="row">
              <div id="fs-levels" class="fs-levels"></div>
              <div id="breadcrumbs" class="crumbs"></div>
            </div>
            <div class="qj-wrap">
              <input id="quick-jump-input" class="qj-input" type="search"
                     placeholder="Quick jump to block, package, module, or symbol (/)"
                     autocomplete="off" />
              <div id="quick-jump-dropdown" class="qj-dropdown hidden"></div>
            </div>
          </div>

          <div class="between" style="padding-bottom:10px;border-bottom:1px solid var(--border);
                                      margin-bottom:10px;">
            <div>
              <h2 id="arch-title"></h2>
              <p class="muted" id="arch-subtitle" style="margin:2px 0 0 0;"></p>
            </div>
            <div class="row" id="arch-tools">
              <div id="view-toggle-group" class="seg">
                <button class="btn btn-sm" data-view="svg" type="button">Diagram</button>
                <button class="btn btn-sm" data-view="cards" type="button">Cards</button>
              </div>
              <div id="mod-view-group" class="seg hidden">
                <button class="btn btn-sm" data-modview="svg" type="button">Diagram</button>
                <button class="btn btn-sm" data-modview="table" type="button">Table</button>
              </div>
              <div id="overlay-toggle-group" class="seg">
                <button class="btn btn-sm" data-overlay="arch" type="button">Architecture</button>
                <button class="btn btn-sm" data-overlay="weaknesses" type="button">
                  Weaknesses
                </button>
                <button class="btn btn-sm" data-overlay="coverage" type="button">Coverage</button>
                <button class="btn btn-sm" data-overlay="security" type="button">Security</button>
              </div>
              <div id="edge-scope-group" class="seg">
                <button class="btn btn-sm" data-edgescope="focus" type="button">Focus</button>
                <button class="btn btn-sm" data-edgescope="hop2" type="button">2-hop</button>
                <button class="btn btn-sm" data-edgescope="risks" type="button">Risks</button>
                <button class="btn btn-sm" data-edgescope="all" type="button">All</button>
              </div>
              <button class="btn btn-sm hidden" id="toggle-tooling-btn" type="button">
                Hide tooling
              </button>
              <button class="btn btn-sm hidden" id="fn-connected-btn" type="button">
                Connected only
              </button>
              <input id="fn-search" class="hidden" type="search"
                     placeholder="Filter symbols..." />
              <input id="module-search" class="hidden" type="search"
                     placeholder="Filter path, block, docstring, library..." />
              <button class="btn btn-sm hidden" id="fs-insp-btn" type="button">
                Hide details
              </button>
              <button class="btn btn-sm btn-on" id="fs-btn" type="button">Full screen</button>
            </div>
          </div>

          <div id="scope-banner" class="scope-banner hidden"></div>

          <div id="diagram-wrap-block">
            <div class="viewport-wrap">
              <div id="viewport-canvas" class="viewport-canvas"></div>
              <div class="vp-controls">
                <button class="btn btn-xs" id="zoom-out-btn" type="button">-</button>
                <span class="muted small" id="zoom-label">100%</span>
                <button class="btn btn-xs" id="zoom-in-btn" type="button">+</button>
                <button class="btn btn-xs" id="zoom-fit-btn" type="button">Fit</button>
                <button class="btn btn-xs" id="zoom-center-btn" type="button">Center</button>
              </div>
              <div id="minimap-box" class="minimap-box">
                <div class="minimap-head">
                  <span>Map</span>
                  <button class="btn btn-xs" id="minimap-toggle" type="button">-</button>
                </div>
                <div id="minimap-body" class="minimap-body">
                  <svg id="minimap-svg" width="178" height="106"></svg>
                </div>
              </div>
              <div id="hover-popover" class="hover-popover hidden"></div>
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
