"""Multi-level architecture and test-coverage layout model for the HTML explorer."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from typing import Any

from codeoverlook.core.coverage import RepoCoverageReport

_BAND_SPECS: tuple[tuple[str, str, str, str], ...] = (
    ("L1", "Entry & Consumers", "entry", "Interfaces, pages, CLI, and top-level workflows"),
    ("L2", "Application & Services", "services", "Service coordination and intermediate blocks"),
    ("L3", "Core & Domain", "engine", "Domain logic, analytics, and core engines"),
    ("L4", "Foundation & Storage", "foundation", "Persistence, exports, and low-level utilities"),
)


def _compute_block_layers(
    block_ids: list[str],
    edges: list[tuple[str, str]],
) -> dict[str, str]:
    """Assign each production block to an architectural band (`L1`..`L4`) by dependency flow."""
    if not block_ids:
        return {}

    adj: dict[str, set[str]] = {bid: set() for bid in block_ids}
    rev: dict[str, set[str]] = {bid: set() for bid in block_ids}
    for src, dst in edges:
        if src in adj and dst in adj and src != dst:
            adj[src].add(dst)
            rev[dst].add(src)

    # Condense strongly connected cycles via greedy topological layering:
    # nodes with fewer remaining callers sit higher (`L1`), leaf providers sit lower (`L4`).
    remaining = set(block_ids)
    depth: dict[str, int] = {bid: 0 for bid in block_ids}
    ordered_layers: list[str] = []

    while remaining:
        roots = sorted(
            [bid for bid in remaining if not (rev[bid] & remaining)],
            key=lambda bid: (-len(adj[bid]), bid),
        )
        if not roots:
            # Break cycle by choosing node with fewest incoming edges inside remaining set.
            roots = [
                min(
                    remaining,
                    key=lambda bid: (len(rev[bid] & remaining), -len(adj[bid]), bid),
                )
            ]
        for node in roots:
            remaining.remove(node)
            ordered_layers.append(node)

    for node in ordered_layers:
        for dst in adj[node]:
            if depth[dst] < depth[node] + 1:
                depth[dst] = depth[node] + 1

    # Leaf nodes with zero outgoing imports belong at the bottom-most tier.
    max_depth = max(depth.values(), default=0)
    if max_depth == 0:
        return {bid: "L1" for bid in block_ids}

    for bid in block_ids:
        if not adj[bid] and rev[bid]:
            depth[bid] = max(depth[bid], max_depth)

    # Compress active depth levels into up to 4 contiguous bands (`L1`..`L4`).
    distinct = sorted(set(depth.values()))
    if len(distinct) <= 4:
        tier_map = {val: f"L{idx + 1}" for idx, val in enumerate(distinct)}
    else:
        max_d = distinct[-1]
        tier_map = {
            val: f"L{min(4, 1 + (val * 3) // max(1, max_d))}"
            for val in distinct
        }

    # Ensure band labels stay strictly contiguous (`L1`, `L2`, ...) with no gaps.
    used_nums = sorted({int(tier_map[d][1:]) for d in depth.values()})
    remap = {f"L{num}": f"L{idx + 1}" for idx, num in enumerate(used_nums)}
    return {bid: remap[tier_map[depth[bid]]] for bid in block_ids}


def _classify_package_status(tested_files: int, total_files: int) -> str:
    if tested_files <= 0:
        return "UNTESTED"
    pct = (tested_files / max(1, total_files)) * 100.0
    if pct < 35.0:
        return "LOW"
    if pct < 70.0:
        return "PARTIAL"
    return "WELL_COVERED"


def build_explorer_model(
    repo_name: str,
    coverage: RepoCoverageReport,
    block_summary: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
    cycles: list[list[str]],
    violations: list[dict[str, Any]],
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the synchronized 3-level data model consumed by `html_renderer.py`.

    Levels:
    1. `blocks`: functional blocks layered automatically into architectural bands.
    2. `packages`: sub-package bricks within each functional block.
    3. `modules`: production modules with docstrings, symbols, imports, and findings.
    """
    risk_by_block = {str(r["block_id"]): r for r in block_summary}
    violation_map: dict[tuple[str, str], str] = {
        (str(v["src_block"]), str(v["dst_block"])): str(v.get("reason", "Forbidden import"))
        for v in violations
    }

    import_deps = [d for d in dependencies if d.get("kind") == "IMPORTS"]
    block_ids = [b.block_id for b in coverage.blocks]
    block_bands = _compute_block_layers(
        block_ids,
        [(str(d["src_block"]), str(d["dst_block"])) for d in import_deps],
    )

    block_imports: dict[str, list[str]] = defaultdict(list)
    block_imported_by: dict[str, list[str]] = defaultdict(list)
    block_edges: list[dict[str, Any]] = []
    for dep in import_deps:
        u = str(dep["src_block"])
        v = str(dep["dst_block"])
        if u not in block_bands or v not in block_bands:
            continue
        block_imports[u].append(v)
        block_imported_by[v].append(u)
        reason = violation_map.get((u, v), "")
        block_edges.append(
            {
                "u": u,
                "v": v,
                "n": int(dep.get("edge_count", 1)),
                "violation": bool(reason),
                "reason": reason,
            }
        )

    raw_modules = list((catalog or {}).get("modules", []))
    block_ext_libs = dict((catalog or {}).get("block_external_libs", {}))
    all_findings = list((catalog or {}).get("all_findings", []))

    modules_by_block: dict[str, list[dict[str, Any]]] = defaultdict(list)
    modules_by_pkg: dict[str, list[dict[str, Any]]] = defaultdict(list)
    path_to_pkg_id: dict[str, str] = {}
    enriched_modules: list[dict[str, Any]] = []

    for mod in raw_modules:
        bid = str(mod["block_id"])
        pkg = str(mod.get("package") or "root")
        pkg_id = f"{bid}::{pkg}"
        path = str(mod["path"])
        path_to_pkg_id[path] = pkg_id

        sinks_cnt = sum(1 for f in mod.get("findings", []) if f.get("category") == "SINK")
        entry = {
            **mod,
            "package_id": pkg_id,
            "band": block_bands.get(bid, "L1"),
            "tested": bool(mod.get("test_files")),
            "sinks": sinks_cnt,
        }
        enriched_modules.append(entry)
        modules_by_block[bid].append(entry)
        modules_by_pkg[pkg_id].append(entry)

    # Build Level 2 package bricks and inter-package edges.
    pkg_edge_counts: dict[tuple[str, str], int] = defaultdict(int)
    for mod in enriched_modules:
        src_pkg = str(mod["package_id"])
        for dst_path in mod.get("imports", []):
            dst_pkg = path_to_pkg_id.get(str(dst_path))
            if dst_pkg and dst_pkg != src_pkg:
                pkg_edge_counts[(src_pkg, dst_pkg)] += 1

    pkg_imports: dict[str, set[str]] = defaultdict(set)
    pkg_imported_by: dict[str, set[str]] = defaultdict(set)
    package_edges: list[dict[str, Any]] = []
    for (u_pkg, v_pkg), count in sorted(pkg_edge_counts.items()):
        u_blk = u_pkg.split("::", 1)[0]
        v_blk = v_pkg.split("::", 1)[0]
        pkg_imports[u_pkg].add(v_pkg)
        pkg_imported_by[v_pkg].add(u_pkg)
        package_edges.append(
            {
                "u": u_pkg,
                "v": v_pkg,
                "n": count,
                "violation": (u_blk, v_blk) in violation_map,
                "reason": violation_map.get((u_blk, v_blk), ""),
            }
        )

    packages_payload: list[dict[str, Any]] = []
    for pkg_id, mods in sorted(modules_by_pkg.items()):
        bid, pkg_name = pkg_id.split("::", 1)
        total_files = len(mods)
        tested_files = sum(1 for m in mods if m["tested"])
        total_loc = sum(int(m.get("loc", 0)) for m in mods)
        total_sinks = sum(int(m.get("sinks", 0)) for m in mods)
        untested_sinks = sum(int(m.get("sinks", 0)) for m in mods if not m["tested"])
        ext_libs = sorted({lib for m in mods for lib in m.get("external_libs", [])})
        test_files = sorted({tf for m in mods for tf in m.get("test_files", [])})
        pkg_findings = [f for m in mods for f in m.get("findings", [])][:20]
        largest = sorted(mods, key=lambda m: (-int(m.get("loc", 0)), str(m["path"])))[:6]

        packages_payload.append(
            {
                "id": pkg_id,
                "title": pkg_name if pkg_name != "root" else f"{bid} (root)",
                "block_id": bid,
                "band": block_bands.get(bid, "L1"),
                "prod_files": total_files,
                "tested_files": tested_files,
                "file_coverage_pct": round((tested_files / max(1, total_files)) * 100.0, 1),
                "prod_loc": total_loc,
                "sensitive_sinks": total_sinks,
                "untested_sinks": untested_sinks,
                "coverage_status": _classify_package_status(tested_files, total_files),
                "imports": sorted(pkg_imports.get(pkg_id, ())),
                "imported_by": sorted(pkg_imported_by.get(pkg_id, ())),
                "external_libs": ext_libs,
                "test_files": test_files,
                "findings": pkg_findings,
                "largest_files": [
                    {"path": m["path"], "loc": m["loc"], "tested": m["tested"]}
                    for m in largest
                ],
                "member_modules": [str(m["path"]) for m in mods],
            }
        )

    # Build Level 1 blocks payload.
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

        blk_mods = modules_by_block.get(blk.block_id, [])
        largest = sorted(blk_mods, key=lambda m: (-int(m.get("loc", 0)), str(m["path"])))[:6]
        blk_pkgs = [p["id"] for p in packages_payload if p["block_id"] == blk.block_id]
        blk_findings = [f for m in blk_mods for f in m.get("findings", [])][:20]

        blocks_payload.append(
            {
                "id": blk.block_id,
                "block_id": blk.block_id,
                "title": blk.block_id,
                "band": block_bands.get(blk.block_id, "L1"),
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
                "imports": sorted(set(block_imports.get(blk.block_id, []))),
                "imported_by": sorted(set(block_imported_by.get(blk.block_id, []))),
                "external_libs": block_ext_libs.get(blk.block_id, []),
                "packages": blk_pkgs,
                "linked_tests": linked_tests,
                "gaps": gaps,
                "findings": blk_findings,
                "largest_files": [
                    {"path": m["path"], "loc": m["loc"], "tested": m["tested"]}
                    for m in largest
                ],
                "member_modules": [str(m["path"]) for m in blk_mods],
            }
        )

    active_band_ids = {b["band"] for b in blocks_payload}
    bands = [
        {"id": bid, "label": bid, "group": grp, "title": title, "desc": desc}
        for bid, title, grp, desc in _BAND_SPECS
        if bid in active_band_ids
    ]
    if not bands:
        bands = [
            {
                "id": "L1",
                "label": "L1",
                "group": "entry",
                "title": _BAND_SPECS[0][1],
                "desc": _BAND_SPECS[0][3],
            }
        ]

    total_prod_files = sum(b.prod_files for b in coverage.blocks)
    total_tested_files = sum(b.tested_files for b in coverage.blocks)
    total_prod_loc = sum(b.prod_loc for b in coverage.blocks)
    total_prod_symbols = sum(b.prod_symbols for b in coverage.blocks)
    total_tested_symbols = sum(b.tested_symbols for b in coverage.blocks)
    total_sinks = sum(b.sensitive_sinks for b in coverage.blocks)
    total_untested_sinks = sum(b.untested_sinks for b in coverage.blocks)

    return {
        "repo_name": repo_name,
        "summary": {
            "blocks_count": len(blocks_payload),
            "packages_count": len(packages_payload),
            "modules_count": len(enriched_modules) or total_prod_files,
            "prod_files": total_prod_files,
            "tested_files": total_tested_files,
            "prod_loc": total_prod_loc,
            "prod_symbols": total_prod_symbols,
            "tested_symbols": total_tested_symbols,
            "overall_file_coverage_pct": coverage.overall_file_coverage_pct,
            "overall_symbol_coverage_pct": coverage.overall_symbol_coverage_pct,
            "total_test_files": coverage.total_test_files,
            "linked_test_files": coverage.linked_test_files,
            "total_test_functions": coverage.total_test_functions,
            "sensitive_sinks": total_sinks,
            "untested_sinks": total_untested_sinks,
            "cycles_count": len(cycles),
            "violations_count": len(violations),
        },
        "bands": bands,
        "blocks": blocks_payload,
        "block_edges": block_edges,
        "packages": packages_payload,
        "package_edges": package_edges,
        "modules": enriched_modules,
        "cycles": cycles[:30],
        "violations": violations,
        "findings": all_findings,
        "dependencies": import_deps,
        "total_test_files": coverage.total_test_files,
        "linked_test_files": coverage.linked_test_files,
        "total_test_functions": coverage.total_test_functions,
    }
