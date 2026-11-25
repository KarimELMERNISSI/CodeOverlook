"""Tests for explorer catalog extraction, multi-level layout, and full-screen HTML views."""

from __future__ import annotations

import json
from pathlib import Path

from codeoverlook.core.architecture import analyze_architecture
from codeoverlook.core.blocks import BlockResolver
from codeoverlook.core.coverage import TestCoverageAnalyzer
from codeoverlook.core.store import FactStore
from codeoverlook.ingesters.python_ast import PythonASTIngester
from codeoverlook.interfaces.cli import main
from codeoverlook.views.explorer_layout import build_explorer_model
from codeoverlook.views.html_renderer import render_atlas_html
from codeoverlook.views.workbench import render_workbench_html


def test_module_docstring_and_explorer_catalog(sample_repo: Path) -> None:
    """Extract module docstrings, symbol call graphs, and clean external imports."""
    (sample_repo / "engine" / "service.py").write_text(
        '"""Core reporting service orchestrating summaries and storage lookups."""\n\n'
        "import pandas as pd\n\n"
        + (sample_repo / "engine" / "service.py").read_text(encoding="utf-8")
        + "\ndef helper_calls_error() -> None:\n    raise ValueError('bad')\n",
        encoding="utf-8",
    )

    assert main(["scan", str(sample_repo), "--force"]) == 0

    with FactStore(sample_repo / ".codeoverlook" / "index.db") as store:
        catalog = store.get_explorer_catalog()

    mods = {m["path"]: m for m in catalog["modules"]}
    svc = mods["engine/service.py"]
    assert svc["docstring"].startswith("Core reporting service")
    assert svc["block_id"] == "engine"
    assert "storage/db.py" in svc["imports"]
    assert "ui/view.py" in svc["imported_by"]
    assert "tests/test_engine.py" in svc["test_files"]
    assert any(s["name"] == "ReportBuilder" for s in svc["symbols"])

    # External libs must include real external imports only, never builtins like ValueError.
    assert "pandas" in svc["external_libs"]
    assert "ValueError" not in svc["external_libs"]
    assert "ValueError" not in catalog["block_external_libs"].get("engine", [])

    # Symbol call graph captures real intra-module/intra-block calls and totals.
    eng_graph = catalog["symbol_graph"]["by_block"]["engine"]
    assert eng_graph["total_symbols"] >= len(eng_graph["symbols"]) >= 1
    assert isinstance(catalog["symbol_graph"]["cross_edges"], list)
    eng_edges = {(e["u"], e["v"]) for e in eng_graph["edges"]}
    assert (
        "engine/service.py::run_report",
        "engine/service.py::ReportBuilder.build_summary",
    ) in eng_edges

    db_mod = mods["storage/db.py"]
    assert any(f["rule_id"] == "SINK-SQL-01" for f in db_mod["findings"])
    assert any(f["rule_id"] == "SINK-SQL-01" and "symbol_id" in f for f in catalog["all_findings"])


def test_python_ast_ingester_truncates_long_module_docstring(tmp_path: Path) -> None:
    """Long module docstrings are summarized cleanly to a single compact paragraph."""
    mod = tmp_path / "long_doc.py"
    long_text = " ".join(["architecture"] * 40)
    mod.write_text(f'"""{long_text}\n\nSecond paragraph ignored."""\n\nx = 1\n', encoding="utf-8")

    ingester = PythonASTIngester(tmp_path)
    parsed = ingester.parse_file(mod)
    assert parsed is not None
    mod_sym = parsed.symbols[0]
    assert mod_sym.kind == "module"
    assert mod_sym.docstring is not None
    assert len(mod_sym.docstring) <= 240
    assert "Second paragraph" not in mod_sym.docstring


def test_explorer_layout_levels_bands_and_violations(sample_repo: Path) -> None:
    """Build 3-level layout model with layered bands, packages, modules, and violations."""
    assert main(["scan", str(sample_repo)]) == 0
    resolver = BlockResolver(sample_repo)

    with FactStore(sample_repo / ".codeoverlook" / "index.db") as store:
        summary = store.get_block_risk_summary()
        deps = store.get_block_dependencies()
        cycles = store.detect_import_cycles()
        violations = resolver.check_violations(deps)
        coverage = TestCoverageAnalyzer(store).analyze()
        catalog = store.get_explorer_catalog()

    model = build_explorer_model(
        repo_name="sample_repo",
        coverage=coverage,
        block_summary=summary,
        dependencies=deps,
        cycles=cycles,
        violations=violations,
        catalog=catalog,
    )

    assert model["summary"]["blocks_count"] == 3
    assert model["summary"]["violations_count"] >= 1
    assert len(model["bands"]) >= 2
    assert all("prod_loc" in band and "avg_coverage_pct" in band for band in model["bands"])
    assert "cross_edges" in model["symbol_graph"]
    assert "budget" in model["symbol_graph"]
    assert model["profile"]["size_tier"] == "micro"
    assert model["profile"]["recommended_density"] == "spacious"

    blocks_by_id = {b["id"]: b for b in model["blocks"]}
    # `ui` depends on `engine` and `storage`, so `ui` sits in L1 above `storage`.
    assert blocks_by_id["ui"]["band"] == "L1"
    assert any(edge["violation"] for edge in model["block_edges"])
    assert len(model["packages"]) >= 3
    assert len(model["modules"]) >= 5


def test_html_explorer_and_workbench_render_controls_and_fullscreen(sample_repo: Path) -> None:
    """Verify multi-level controls, pan/zoom, full-screen, and backward-compatible catalog."""
    assert main(["scan", str(sample_repo)]) == 0
    resolver = BlockResolver(sample_repo)

    with FactStore(sample_repo / ".codeoverlook" / "index.db") as store:
        summary = store.get_block_risk_summary()
        deps = store.get_block_dependencies()
        cycles = store.detect_import_cycles()
        violations = resolver.check_violations(deps)
        coverage = TestCoverageAnalyzer(store).analyze()
        catalog = store.get_explorer_catalog()

    full_html = render_atlas_html(
        repo_name="sample_repo",
        coverage=coverage,
        block_summary=summary,
        dependencies=deps,
        cycles=cycles,
        violations=violations,
        catalog=catalog,
    )
    assert "CodeOverlook Coverage &amp; Architecture Inspector" in full_html
    assert 'id="theme-btn"' in full_html
    assert 'id="fs-btn"' in full_html
    assert 'id="zoom-fit-btn"' in full_html
    assert 'id="breadcrumbs"' in full_html
    assert 'id="diag-card"' in full_html
    assert 'id="feature-chips"' in full_html
    assert 'data-overlay="weaknesses"' in full_html
    assert 'data-density="compact"' in full_html
    assert 'data-density="detailed"' in full_html
    assert 'data-edgescope="hop2"' in full_html
    assert 'id="pill-scale"' in full_html
    assert 'id="quick-jump-input"' in full_html
    assert 'id="minimap-box"' in full_html
    assert 'id="hover-popover"' in full_html
    assert 'id="zoom-center-btn"' in full_html
    assert "handleDoubleClickNode" in full_html
    assert "openFunctionsView" in full_html
    assert "orderNodesInBands" in full_html
    assert "computeEdgePaths" in full_html
    assert "renderModulesSvg" in full_html
    assert "centerOnNode" in full_html
    assert "getDensitySpec" in full_html
    assert "toggleBandCollapse" in full_html
    assert "ResizeObserver" in full_html
    assert "resolveDensity" in full_html
    assert "Tooling &amp; Scripts" in full_html or "Tooling & Scripts" in full_html
    assert "IMPORTS FLOW DOWN" in full_html
    assert "Packages &amp; Bricks" in full_html or "Packages & Bricks" in full_html
    assert "SINK-SQL-01" in full_html

    # Backward compatibility when `catalog` is omitted (`None`).
    minimal_html = render_atlas_html(
        repo_name="sample_repo",
        coverage=coverage,
        block_summary=summary,
        dependencies=deps,
        cycles=cycles,
        violations=violations,
    )
    assert "CodeOverlook Coverage &amp; Architecture Inspector" in minimal_html

    wb_html = render_workbench_html(initial_target=str(sample_repo), offline_default=True)
    assert "CodeOverlook Inspection Workbench" in wb_html
    assert 'id="wb-theme-btn"' in wb_html
    assert "allowfullscreen" in wb_html
    assert "toggleExplorerFullscreen" in wb_html
    assert json.dumps(str(sample_repo)) in wb_html


def test_semantic_architecture_analyzer_layers_tooling_and_weaknesses() -> None:
    """Verify semantic roles, tooling quarantine, SCC cycles, God modules, and features."""
    blocks = [
        {
            "id": "ui",
            "prod_files": 4,
            "prod_loc": 800,
            "file_coverage_pct": 80.0,
            "sensitive_sinks": 0,
            "untested_sinks": 0,
            "external_libs": ["streamlit"],
        },
        {
            "id": "service",
            "prod_files": 5,
            "prod_loc": 1200,
            "file_coverage_pct": 50.0,
            "sensitive_sinks": 2,
            "untested_sinks": 1,
            "external_libs": ["requests"],
        },
        {
            "id": "core",
            "prod_files": 6,
            "prod_loc": 2400,
            "file_coverage_pct": 40.0,
            "sensitive_sinks": 0,
            "untested_sinks": 0,
            "external_libs": ["numpy"],
        },
        {
            "id": "dev_scripts",
            "prod_files": 3,
            "prod_loc": 300,
            "file_coverage_pct": 0.0,
            "sensitive_sinks": 1,
            "untested_sinks": 1,
            "external_libs": [],
        },
    ]
    edges = [
        {"u": "ui", "v": "service", "n": 3, "violation": False, "reason": ""},
        {"u": "service", "v": "core", "n": 4, "violation": False, "reason": ""},
        # Upward back-edge creating a cycle between service and core
        {"u": "core", "v": "service", "n": 1, "violation": False, "reason": ""},
        {"u": "dev_scripts", "v": "core", "n": 1, "violation": False, "reason": ""},
    ]
    modules = [
        {
            "path": "core/mega.py",
            "block_id": "core",
            "loc": 620,
            "imports": ["a.py", "b.py", "c.py"],
            "imported_by": ["x.py", "y.py", "z.py"],
            "sinks": 1,
            "tested": False,
        }
    ]
    arch = analyze_architecture(
        blocks_payload=blocks,
        block_edges=edges,
        packages_payload=[
            {"id": "ui::ui", "block_id": "ui"},
            {"id": "service::service", "block_id": "service"},
        ],
        modules_payload=modules,
        cycles=[["service/a.py", "core/mega.py", "service/a.py"]],
        violations=[],
    )

    assert arch["tooling_blocks"] == ["dev_scripts"]
    bm = arch["block_metrics"]
    assert bm["dev_scripts"]["zone"] == "tooling"
    assert bm["ui"]["role"] == "interface"
    assert bm["ui"]["band"] == "L1"
    assert "CYCLE" in bm["service"]["weakness_tags"]
    assert "GOD MODULE" in bm["core"]["weakness_tags"]
    assert len(arch["god_modules"]) == 1
    assert arch["god_modules"][0]["path"] == "core/mega.py"
    assert len(arch["features"]) >= 1
    assert any(d["kind"] == "CYCLE" for d in arch["diagnosis"])
    assert any(d["kind"] == "GOD-MODULE" for d in arch["diagnosis"])
    assert any(d["kind"] == "TOOLING" for d in arch["diagnosis"])


def test_architecture_scales_from_micro_to_large_monorepo() -> None:
    """Verify project profiles and thresholds adapt cleanly across repository scales."""
    micro_arch = analyze_architecture(
        blocks_payload=[
            {
                "id": "pkg",
                "prod_files": 4,
                "prod_loc": 280,
                "file_coverage_pct": 100.0,
                "sensitive_sinks": 0,
                "untested_sinks": 0,
                "external_libs": [],
            }
        ],
        block_edges=[],
        packages_payload=[{"id": "pkg::root", "block_id": "pkg"}],
        modules_payload=[
            {
                "path": f"mod_{i}.py",
                "block_id": "pkg",
                "loc": 70,
                "imports": [],
                "imported_by": [],
                "sinks": 0,
                "tested": True,
            }
            for i in range(4)
        ],
        cycles=[],
        violations=[],
    )
    m_prof = micro_arch["profile"]
    assert m_prof["size_tier"] == "micro"
    assert m_prof["recommended_level"] == "modules"
    assert m_prof["recommended_density"] == "spacious"

    large_blocks = [
        {
            "id": f"blk_{i:02d}",
            "prod_files": 14 if i < 20 else 12,
            "prod_loc": 1400,
            "file_coverage_pct": 60.0,
            "sensitive_sinks": 0,
            "untested_sinks": 0,
            "external_libs": [],
        }
        for i in range(30)
    ]
    # Build a 6-layer linear chain + siblings so layers distribute across 5+ bands.
    large_edges = [
        {"u": f"blk_{i:02d}", "v": f"blk_{i + 5:02d}", "n": 2, "violation": False, "reason": ""}
        for i in range(25)
    ]
    large_arch = analyze_architecture(
        blocks_payload=large_blocks,
        block_edges=large_edges,
        packages_payload=[
            {"id": f"blk_{i:02d}::sub", "block_id": f"blk_{i:02d}"} for i in range(30)
        ],
        modules_payload=[],
        cycles=[],
        violations=[],
    )
    l_prof = large_arch["profile"]
    assert l_prof["size_tier"] == "large"
    assert l_prof["recommended_level"] == "blocks"
    assert l_prof["recommended_density"] == "compact"
    assert l_prof["max_bands"] >= 5
    assert l_prof["blast_in_deg_min"] >= 7


def test_explorer_js_has_no_duplicate_scope_declarations() -> None:
    """Guard against duplicate top-level or function-scope JS `const`/`let` bindings."""
    import re
    from collections import Counter

    from codeoverlook.views.explorer_scripts import build_explorer_js

    js = build_explorer_js("{}")
    top_funcs = re.findall(r"^function\s+(\w+)", js, re.M)
    assert [k for k, v in Counter(top_funcs).items() if v > 1] == []
    top_vars = re.findall(r"^(?:const|let)\s+(\w+)\b", js, re.M)
    assert [k for k, v in Counter(top_vars).items() if v > 1] == []

    current_fn: str | None = None
    depth = 0
    fn_decls: dict[str, list[str]] = {}
    for line in js.splitlines():
        m_fn = re.match(r"^function\s+(\w+)\s*\(", line)
        if m_fn and depth == 0:
            current_fn = m_fn.group(1)
            fn_decls[current_fn] = []
        if current_fn is not None and depth == 1:
            m_var = re.match(r"^\s{2}(?:const|let)\s+(\w+)\b", line)
            if m_var:
                fn_decls[current_fn].append(m_var.group(1))
        depth += line.count("{") - line.count("}")
        if depth <= 0:
            depth = 0
            current_fn = None

    dups = {
        fn: [name for name, cnt in Counter(decls).items() if cnt > 1]
        for fn, decls in fn_decls.items()
    }
    assert {fn: names for fn, names in dups.items() if names} == {}
