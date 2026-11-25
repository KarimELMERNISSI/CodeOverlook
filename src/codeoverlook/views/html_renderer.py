"""Standalone interactive HTML renderer for architecture and test coverage gaps."""

from __future__ import annotations

import html
import json
from dataclasses import asdict
from typing import Any

from codeoverlook.core.coverage import RepoCoverageReport


def _safe_json_for_script(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def render_atlas_html(
    repo_name: str,
    coverage: RepoCoverageReport,
    block_summary: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
    cycles: list[list[str]],
    violations: list[dict[str, Any]],
) -> str:
    """Build a self-contained HTML explorer for block coverage, tests, and sinks.

    Args:
        repo_name: Display name of the scanned repository.
        coverage: Output from `TestCoverageAnalyzer.analyze()`.
        block_summary: Production block summary from `FactStore.get_block_risk_summary()`.
        dependencies: Production inter-block dependency edges.
        cycles: Detected internal production import cycles.
        violations: Architectural boundary violations from `.codeoverlook.toml`.

    Returns:
        Standalone HTML document string requiring no external network requests.
    """
    total_prod_files = sum(b.prod_files for b in coverage.blocks)
    total_prod_loc = sum(b.prod_loc for b in coverage.blocks)
    total_untested_sinks = sum(b.untested_sinks for b in coverage.blocks)
    risk_by_block = {str(r["block_id"]): r for r in block_summary}

    blocks_payload: list[dict[str, Any]] = []
    for blk in coverage.blocks:
        risk = risk_by_block.get(blk.block_id, {})
        linked_tests = [
            {
                "test_file": assoc.test_file,
                "test_functions": assoc.test_functions,
                "link_mode": assoc.link_mode,
                "target_symbols_count": assoc.target_symbols_count,
            }
            for assoc in coverage.test_associations
            if blk.block_id in assoc.target_blocks
        ]
        linked_tests.sort(key=lambda item: (-item["test_functions"], item["test_file"]))

        gaps = [
            asdict(tgt)
            for tgt in coverage.untested_targets
            if tgt.block_id == blk.block_id
        ][:12]

        blocks_payload.append(
            {
                "block_id": blk.block_id,
                "prod_files": blk.prod_files,
                "tested_files": blk.tested_files,
                "file_coverage_pct": blk.file_coverage_pct,
                "prod_loc": blk.prod_loc,
                "prod_symbols": blk.prod_symbols,
                "tested_symbols": blk.tested_symbols,
                "symbol_coverage_pct": blk.symbol_coverage_pct,
                "test_files_count": blk.test_files_count,
                "test_functions_count": blk.test_functions_count,
                "sensitive_sinks": blk.sensitive_sinks,
                "untested_sinks": blk.untested_sinks,
                "high_risk_findings": int(risk.get("high_risk_findings", 0)),
                "inbound_prod_edges": blk.inbound_prod_edges,
                "coverage_status": blk.coverage_status,
                "priority_score": blk.priority_score,
                "linked_tests": linked_tests,
                "gaps": gaps,
            }
        )

    data_blob = _safe_json_for_script(
        {
            "repo_name": repo_name,
            "blocks": blocks_payload,
            "dependencies": [d for d in dependencies if d.get("kind") == "IMPORTS"],
            "cycles": cycles[:20],
            "violations": violations,
            "total_test_files": coverage.total_test_files,
            "linked_test_files": coverage.linked_test_files,
            "total_test_functions": coverage.total_test_functions,
        }
    )

    escaped_repo = html.escape(repo_name)
    tests_kpi = (
        f"{coverage.linked_test_files}/{coverage.total_test_files} "
        f"({coverage.total_test_functions} fns)"
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>CodeOverlook Inspector - {escaped_repo}</title>
<style>
  :root {{
    --bg: #0f172a;
    --surface: #1e293b;
    --surface-2: #263348;
    --border: #334155;
    --text: #f1f5f9;
    --muted: #94a3b8;
    --accent: #38bdf8;
    --well: #16a34a;
    --partial: #ca8a04;
    --low: #ea580c;
    --untested: #dc2626;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 20px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 14px;
    line-height: 1.45;
  }}
  .header {{
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
  }}
  h1 {{ margin: 0; font-size: 20px; font-weight: 600; }}
  .subtitle {{ color: var(--muted); font-size: 13px; }}
  .kpis {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 10px;
    margin-bottom: 16px;
  }}
  .kpi {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 12px;
  }}
  .kpi-label {{
    color: var(--muted);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}
  .kpi-val {{
    font-size: 20px;
    font-weight: 700;
    margin-top: 2px;
    font-variant-numeric: tabular-nums;
  }}
  .controls {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    margin-bottom: 14px;
  }}
  .btn {{
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
    cursor: pointer;
  }}
  .btn.active {{ border-color: var(--accent); background: #0c4a6e; color: #e0f2fe; }}
  .grid {{
    display: grid;
    grid-template-columns: 1.35fr 1fr;
    gap: 16px;
  }}
  @media (max-width: 1080px) {{
    .grid {{ grid-template-columns: 1fr; }}
  }}
  .panel {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px;
  }}
  .panel-title {{
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    margin: 0 0 10px 0;
  }}
  svg {{
    width: 100%;
    height: 360px;
    background: #0b1120;
    border: 1px solid var(--border);
    border-radius: 6px;
    display: block;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }}
  th, td {{
    text-align: left;
    padding: 7px 6px;
    border-bottom: 1px solid var(--border);
    font-variant-numeric: tabular-nums;
  }}
  th {{ color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; }}
  tr.block-row {{ cursor: pointer; }}
  tr.block-row:hover {{ background: var(--surface-2); }}
  tr.block-row.selected {{ background: #0c4a6e; }}
  .badge {{
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.03em;
  }}
  .status-WELL_COVERED {{ background: #14532d; color: #bbf7d0; }}
  .status-PARTIAL {{ background: #713f12; color: #fef08a; }}
  .status-LOW {{ background: #7c2d12; color: #fed7aa; }}
  .status-UNTESTED {{ background: #7f1d1d; color: #fecaca; }}
  .bar-bg {{
    width: 72px;
    height: 7px;
    background: #0f172a;
    border-radius: 4px;
    overflow: hidden;
    display: inline-block;
    vertical-align: middle;
    margin-right: 6px;
  }}
  .bar-fill {{ height: 100%; }}
  .list-item {{
    padding: 8px 10px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 6px;
    margin-bottom: 8px;
    font-size: 12px;
  }}
  code {{
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
    font-size: 11px;
    background: #0f172a;
    padding: 2px 5px;
    border-radius: 4px;
    color: #bae6fd;
  }}
  .legend {{
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    font-size: 11px;
    color: var(--muted);
    margin-top: 8px;
  }}
  .dot {{
    display: inline-block;
    width: 9px;
    height: 9px;
    border-radius: 50%;
    margin-right: 4px;
  }}
</style>
</head>
<body>
  <div class="header">
    <div>
      <h1>CodeOverlook Coverage &amp; Architecture Inspector -- {escaped_repo}</h1>
      <div class="subtitle">
        Functional block map, test-to-block linkage, and prioritized gap targets
      </div>
    </div>
  </div>

  <div class="kpis">
    <div class="kpi">
      <div class="kpi-label">Prod Blocks</div>
      <div class="kpi-val">{len(coverage.blocks)}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Prod Files / LOC</div>
      <div class="kpi-val">{total_prod_files} / {total_prod_loc:,}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Linked Tests</div>
      <div class="kpi-val">{tests_kpi}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">File Coverage</div>
      <div class="kpi-val">{coverage.overall_file_coverage_pct:.1f}%</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Symbol Coverage</div>
      <div class="kpi-val">{coverage.overall_symbol_coverage_pct:.1f}%</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Untested Sinks / Cycles</div>
      <div class="kpi-val">{total_untested_sinks} / {len(cycles)}</div>
    </div>
  </div>

  <div class="controls">
    <span class="subtitle">Layer:</span>
    <button id="layer-cov" class="btn active" onclick="setLayer('coverage')">
      Test Coverage
    </button>
    <button id="layer-sec" class="btn" onclick="setLayer('security')">
      Sinks &amp; Risk
    </button>
    <span class="subtitle" style="margin-left:10px;">Filter status:</span>
    <button class="btn filter-btn active" data-status="ALL" onclick="setFilter('ALL')">
      ALL
    </button>
    <button class="btn filter-btn" data-status="UNTESTED" onclick="setFilter('UNTESTED')">
      UNTESTED
    </button>
    <button class="btn filter-btn" data-status="LOW" onclick="setFilter('LOW')">
      LOW
    </button>
    <button class="btn filter-btn" data-status="PARTIAL" onclick="setFilter('PARTIAL')">
      PARTIAL
    </button>
    <button class="btn filter-btn" data-status="WELL_COVERED" onclick="setFilter('WELL_COVERED')">
      WELL_COVERED
    </button>
  </div>

  <div class="grid">
    <div style="display:flex; flex-direction:column; gap:14px;">
      <div class="panel">
        <div class="panel-title">Block Dependency &amp; Test Harness Graph</div>
        <svg id="graph-svg" viewBox="0 0 820 360"></svg>
        <div class="legend">
          <span><span class="dot" style="background:var(--well)"></span>Well Covered</span>
          <span><span class="dot" style="background:var(--partial)"></span>Partial</span>
          <span><span class="dot" style="background:var(--low)"></span>Low</span>
          <span><span class="dot" style="background:var(--untested)"></span>Untested</span>
          <span>Dashed line: Test Suite link | Solid line: Production Imports</span>
        </div>
      </div>

      <div class="panel">
        <div class="panel-title">Functional Blocks Ranked by Test Gap Priority</div>
        <div style="overflow-x:auto;">
          <table>
            <thead>
              <tr>
                <th>Block</th>
                <th>Status</th>
                <th>Files</th>
                <th>Sym Cov</th>
                <th>Tests</th>
                <th>Untested Sinks</th>
                <th>Priority</th>
              </tr>
            </thead>
            <tbody id="block-tbody"></tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="panel" id="inspector">
      <div class="panel-title">Block Inspector</div>
      <div id="inspector-body" class="subtitle">Select a block from the graph or table.</div>
    </div>
  </div>

<script>
const ATLAS = {data_blob};
let activeLayer = 'coverage';
let activeFilter = 'ALL';
let selectedBlockId = ATLAS.blocks.length ? ATLAS.blocks[0].block_id : null;

const STATUS_COLOR = {{
  WELL_COVERED: '#16a34a',
  PARTIAL: '#ca8a04',
  LOW: '#ea580c',
  UNTESTED: '#dc2626'
}};

function esc(val) {{
  return String(val)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}}

function setLayer(layer) {{
  activeLayer = layer;
  document.getElementById('layer-cov').classList.toggle('active', layer === 'coverage');
  document.getElementById('layer-sec').classList.toggle('active', layer === 'security');
  renderGraph();
}}

function setFilter(status) {{
  activeFilter = status;
  document.querySelectorAll('.filter-btn').forEach(btn => {{
    btn.classList.toggle('active', btn.dataset.status === status);
  }});
  renderTable();
}}

function selectBlock(blockId) {{
  selectedBlockId = blockId;
  renderGraph();
  renderTable();
  renderInspector();
}}

function renderGraph() {{
  const svg = document.getElementById('graph-svg');
  const blocks = ATLAS.blocks;
  if (!blocks.length) {{
    svg.innerHTML = '';
    return;
  }}

  const pos = {{}};
  const testCenter = {{ x: 92, y: 180 }};
  const cols = Math.max(1, Math.ceil(Math.sqrt(blocks.length)));
  const startX = 240;
  const width = 540;
  const height = 300;

  blocks.forEach((b, idx) => {{
    const col = idx % cols;
    const row = Math.floor(idx / cols);
    const totalRows = Math.ceil(blocks.length / cols);
    const x = cols === 1 ? startX + width / 2 : startX + (col / (cols - 1)) * width;
    const y = totalRows === 1 ? 180 : 48 + (row / (totalRows - 1)) * height;
    pos[b.block_id] = {{ x, y }};
  }});

  let out = '<defs><marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" '
    + 'markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
    + '<path d="M 0 1 L 10 5 L 0 9 z" fill="#64748b"/></marker></defs>';

  ATLAS.dependencies.forEach(dep => {{
    const p1 = pos[dep.src_block];
    const p2 = pos[dep.dst_block];
    if (!p1 || !p2) return;
    const hi = selectedBlockId && (
      dep.src_block === selectedBlockId || dep.dst_block === selectedBlockId
    );
    const stroke = hi ? '#38bdf8' : '#334155';
    const op = hi ? '0.9' : '0.45';
    const w = hi ? '2' : '1';
    out += `<line x1="${{p1.x}}" y1="${{p1.y}}" x2="${{p2.x}}" y2="${{p2.y}}" `
      + `stroke="${{stroke}}" stroke-opacity="${{op}}" stroke-width="${{w}}" `
      + `marker-end="url(#arr)" />`;
  }});

  blocks.forEach(b => {{
    if (b.test_files_count <= 0) return;
    const p = pos[b.block_id];
    const hi = b.block_id === selectedBlockId;
    const stroke = hi ? '#60a5fa' : '#1d4ed8';
    const op = hi ? '0.95' : '0.45';
    out += `<line x1="${{testCenter.x + 56}}" y1="${{testCenter.y}}" `
      + `x2="${{p.x - 42}}" y2="${{p.y}}" stroke="${{stroke}}" stroke-opacity="${{op}}" `
      + `stroke-dasharray="4 3" stroke-width="1.5" />`;
  }});

  const linkTxt = `${{ATLAS.linked_test_files}}/${{ATLAS.total_test_files}} linked`;
  out += `<g><rect x="${{testCenter.x - 56}}" y="${{testCenter.y - 26}}" width="112" `
    + `height="52" rx="8" fill="#1e3a8a" stroke="#60a5fa" stroke-width="1.5" />`
    + `<text x="${{testCenter.x}}" y="${{testCenter.y - 4}}" text-anchor="middle" `
    + `fill="#eff6ff" font-size="11" font-weight="700">TEST SUITE</text>`
    + `<text x="${{testCenter.x}}" y="${{testCenter.y + 13}}" text-anchor="middle" `
    + `fill="#bfdbfe" font-size="10">${{linkTxt}}</text></g>`;

  blocks.forEach(b => {{
    const p = pos[b.block_id];
    const isSel = b.block_id === selectedBlockId;
    const fill = '#1e293b';
    let stroke = STATUS_COLOR[b.coverage_status] || '#64748b';
    let subline = `${{b.file_coverage_pct.toFixed(0)}}% files | ${{b.test_files_count}} tests`;
    if (activeLayer === 'security') {{
      stroke = b.untested_sinks > 0 ? '#dc2626' : (b.sensitive_sinks > 0 ? '#ca8a04' : '#16a34a');
      subline = `${{b.sensitive_sinks}} sinks (${{b.untested_sinks}} unt.)`;
    }}
    const sw = isSel ? 3 : 2;
    out += `<g style="cursor:pointer" onclick="selectBlock('${{esc(b.block_id)}}')">`
      + `<rect x="${{p.x - 54}}" y="${{p.y - 22}}" width="108" height="44" rx="7" `
      + `fill="${{fill}}" stroke="${{stroke}}" stroke-width="${{sw}}" />`
      + `<text x="${{p.x}}" y="${{p.y - 3}}" text-anchor="middle" fill="#f8fafc" `
      + `font-size="11" font-weight="600">${{esc(b.block_id)}}</text>`
      + `<text x="${{p.x}}" y="${{p.y + 12}}" text-anchor="middle" fill="#cbd5e1" `
      + `font-size="9.5">${{esc(subline)}}</text></g>`;
  }});

  svg.innerHTML = out;
}}

function renderTable() {{
  const tbody = document.getElementById('block-tbody');
  const filtered = ATLAS.blocks.filter(
    b => activeFilter === 'ALL' || b.coverage_status === activeFilter
  );
  tbody.innerHTML = filtered.map(b => {{
    const color = STATUS_COLOR[b.coverage_status] || '#64748b';
    const selClass = b.block_id === selectedBlockId ? 'selected' : '';
    const symPct = b.symbol_coverage_pct.toFixed(0);
    return `<tr class="block-row ${{selClass}}" onclick="selectBlock('${{esc(b.block_id)}}')">`
      + `<td><strong>${{esc(b.block_id)}}</strong></td>`
      + `<td><span class="badge status-${{b.coverage_status}}">`
      + `${{esc(b.coverage_status)}}</span></td>`
      + `<td>${{b.tested_files}}/${{b.prod_files}} (${{b.file_coverage_pct.toFixed(0)}}%)</td>`
      + `<td><span class="bar-bg"><span class="bar-fill" `
      + `style="width:${{b.symbol_coverage_pct}}%;background:${{color}}"></span></span>`
      + `${{symPct}}%</td>`
      + `<td>${{b.test_files_count}} (${{b.test_functions_count}} fns)</td>`
      + `<td>${{b.untested_sinks}} / ${{b.sensitive_sinks}}</td>`
      + `<td>${{b.priority_score.toFixed(1)}}</td>`
      + `</tr>`;
  }}).join('');
}}

function renderInspector() {{
  const body = document.getElementById('inspector-body');
  const blk = ATLAS.blocks.find(b => b.block_id === selectedBlockId);
  if (!blk) {{
    body.innerHTML = '<div class="subtitle">No block selected.</div>';
    return;
  }}

  const fCov = blk.file_coverage_pct.toFixed(1);
  const sCov = blk.symbol_coverage_pct.toFixed(1);
  let htmlOut = `<div style="margin-bottom:12px;">`
    + `<div style="display:flex;justify-content:space-between;align-items:center;">`
    + `<strong style="font-size:16px;">${{esc(blk.block_id)}}</strong>`
    + `<span class="badge status-${{blk.coverage_status}}">`
    + `${{esc(blk.coverage_status)}}</span></div>`
    + `<div class="subtitle" style="margin-top:4px;">`
    + `Files: ${{blk.tested_files}}/${{blk.prod_files}} (${{fCov}}%) | `
    + `Symbols: ${{blk.tested_symbols}}/${{blk.prod_symbols}} (${{sCov}}%) | `
    + `LOC: ${{blk.prod_loc}} | Inbound block refs: ${{blk.inbound_prod_edges}}</div></div>`;

  htmlOut += `<div class="panel-title">Associated Test Files (${{blk.linked_tests.length}})</div>`;
  if (!blk.linked_tests.length) {{
    htmlOut += `<div class="list-item">No test files currently exercise this block.</div>`;
  }} else {{
    htmlOut += blk.linked_tests.slice(0, 12).map(t =>
      `<div class="list-item"><div><code>${{esc(t.test_file)}}</code></div>`
      + `<div class="subtitle">${{t.test_functions}} test_* fns | `
      + `${{t.target_symbols_count}} linked symbols (${{esc(t.link_mode)}})</div></div>`
    ).join('');
  }}

  htmlOut += `<div class="panel-title" style="margin-top:12px;">`
    + `Priority Targets to Test Next (${{blk.gaps.length}})</div>`;
  if (!blk.gaps.length) {{
    htmlOut += `<div class="list-item">All symbols in this block have test coverage links.</div>`;
  }} else {{
    htmlOut += blk.gaps.map(g => {{
      const sliceTarget = g.sample_symbols.length
        ? `${{g.file_path}}::${{g.sample_symbols[0]}}`
        : g.file_path;
      const syms = g.sample_symbols.length
        ? g.sample_symbols.map(s => `<code>${{esc(s)}}</code>`).join(' ')
        : 'module-level';
      return `<div class="list-item">`
        + `<div><strong>${{esc(g.file_path)}}</strong> `
        + `<span class="subtitle">(prio ${{g.priority_score}}, ${{g.loc}} LOC, `
        + `${{g.untested_sinks}} unt. sinks)</span></div>`
        + `<div style="margin:4px 0;">Untested symbols (${{g.untested_symbols}}): ${{syms}}</div>`
        + `<div class="subtitle">AI Context: `
        + `<code>codeoverlook slice ${{esc(sliceTarget)}} --budget 2500</code></div>`
        + `</div>`;
    }}).join('');
  }}

  body.innerHTML = htmlOut;
}}

renderGraph();
renderTable();
renderInspector();
</script>
</body>
</html>
"""
