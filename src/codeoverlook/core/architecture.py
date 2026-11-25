"""Semantic architecture analyzer: roles, SCC layering, features, and weaknesses."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Literal

_TOOLING_NAMES: frozenset[str] = frozenset(
    {
        "dev_scripts",
        "scripts",
        "scratch",
        "tools",
        "docs",
        "examples",
        "benchmarks",
        "migrations",
        "sandbox",
        "notebooks",
    }
)

_INTERFACE_LIBS: frozenset[str] = frozenset(
    {
        "streamlit",
        "fastapi",
        "flask",
        "django",
        "click",
        "typer",
        "argparse",
        "gradio",
        "dash",
        "tornado",
        "aiohttp",
        "starlette",
    }
)

_CONNECTOR_LIBS: frozenset[str] = frozenset(
    {
        "sqlalchemy",
        "duckdb",
        "psycopg",
        "psycopg2",
        "pymongo",
        "redis",
        "requests",
        "httpx",
        "urllib3",
        "openai",
        "anthropic",
        "langchain_core",
        "langchain",
        "qdrant_client",
        "chromadb",
        "boto3",
        "sqlite3",
        "aiofiles",
        "mistralai",
    }
)

_ENGINE_LIBS: frozenset[str] = frozenset(
    {
        "numpy",
        "scipy",
        "pandas",
        "statsmodels",
        "sklearn",
        "torch",
        "tensorflow",
        "plotly",
        "matplotlib",
        "polars",
        "pyarrow",
    }
)

_ROLE_ORDER: dict[str, int] = {
    "interface": 0,
    "service": 1,
    "connector": 2,
    "engine": 3,
    "foundation": 4,
}

_ROLE_LABELS: dict[str, str] = {
    "interface": "Interface & Entrypoints",
    "service": "Application & Services",
    "connector": "Connectors & Storage",
    "engine": "Compute & Domain Engine",
    "foundation": "Foundation & Shared Core",
}

_ROLE_GROUPS: dict[str, str] = {
    "interface": "entry",
    "service": "services",
    "connector": "services",
    "engine": "engine",
    "foundation": "foundation",
}


def _is_tooling_name(block_id: str) -> bool:
    norm = block_id.lower().strip()
    if norm in _TOOLING_NAMES:
        return True
    parts = [p for p in norm.replace("-", "_").split("/") if p]
    return any(part in _TOOLING_NAMES for part in parts)


def classify_block_zone(
    block_id: str,
    inbound_from_non_tooling: int,
) -> Literal["production", "tooling"]:
    """Separate non-production scripts/scratch blocks from production architecture."""
    if _is_tooling_name(block_id) and inbound_from_non_tooling == 0:
        return "tooling"
    return "production"


def infer_block_role(
    block_id: str,
    *,
    ext_libs: list[str],
    sinks: int,
    prod_files: int,
    prod_loc: int,
    in_deg: int,
    out_deg: int,
    instability: float,
) -> tuple[str, str]:
    """Infer semantic architectural role and factual 1-line description for a block."""
    lib_set = {lib.lower() for lib in ext_libs}
    lower_id = block_id.lower()
    iface_hits = len(lib_set & _INTERFACE_LIBS)
    conn_hits = len(lib_set & _CONNECTOR_LIBS)
    eng_hits = len(lib_set & _ENGINE_LIBS)

    if in_deg == 0 and out_deg > 0:
        role = "interface"
    elif (
        (iface_hits > 0 or any(tok in lower_id for tok in ("ui", "page", "cli", "web", "app")))
        and in_deg <= 2
    ):
        role = "interface"
    elif (in_deg >= 3 and instability <= 0.35 and out_deg <= 2) or (
        out_deg == 0 and in_deg > 0 and eng_hits == 0
    ):
        role = "foundation"
    elif eng_hits > conn_hits and eng_hits > 0:
        role = "engine"
    elif conn_hits > 0 or sinks >= 3:
        role = "connector"
    elif prod_files > 0 and (prod_loc / max(1, prod_files)) >= 200 and out_deg <= 2:
        role = "engine"
    else:
        role = "service"

    libs_str = ", ".join(ext_libs[:3]) if ext_libs else "stdlib / internal"
    role_title = _ROLE_LABELS[role]
    summary = (
        f"{role_title} ({libs_str}) - {prod_files} files, {prod_loc:,} LOC, "
        f"{in_deg} callers"
    )
    return role, summary


def _tarjan_scc(nodes: list[str], adj: dict[str, set[str]]) -> list[list[str]]:
    """Compute strongly connected components in deterministic reverse-topological order."""
    index_counter = 0
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    sccs: list[list[str]] = []

    def _strongconnect(node: str) -> None:
        nonlocal index_counter
        indices[node] = index_counter
        lowlink[node] = index_counter
        index_counter += 1
        stack.append(node)
        on_stack.add(node)

        for nxt in sorted(adj.get(node, ())):
            if nxt not in indices:
                _strongconnect(nxt)
                lowlink[node] = min(lowlink[node], lowlink[nxt])
            elif nxt in on_stack:
                lowlink[node] = min(lowlink[node], indices[nxt])

        if lowlink[node] == indices[node]:
            comp: list[str] = []
            while True:
                member = stack.pop()
                on_stack.remove(member)
                comp.append(member)
                if member == node:
                    break
            sccs.append(sorted(comp))

    for node in sorted(nodes):
        if node not in indices:
            _strongconnect(node)
    return sccs


def compute_layered_architecture(
    prod_blocks: list[str],
    edges: list[dict[str, Any]],
    roles_by_block: dict[str, str],
    ext_libs_by_block: dict[str, list[str]],
    violation_pairs: set[tuple[str, str]],
) -> tuple[dict[str, str], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Condense production graph via Tarjan SCCs and infer project-specific bands."""
    if not prod_blocks:
        return {}, [], [], {}

    prod_set = set(prod_blocks)
    adj: dict[str, set[str]] = {b: set() for b in prod_blocks}
    for e in edges:
        u, v = str(e["u"]), str(e["v"])
        if u in prod_set and v in prod_set and u != v:
            adj[u].add(v)

    sccs = _tarjan_scc(prod_blocks, adj)
    scc_of: dict[str, int] = {}
    scc_sizes: dict[int, int] = {}
    for idx, comp in enumerate(sccs):
        scc_sizes[idx] = len(comp)
        for node in comp:
            scc_of[node] = idx

    dag_adj: dict[int, set[int]] = {i: set() for i in range(len(sccs))}
    dag_rev: dict[int, set[int]] = {i: set() for i in range(len(sccs))}
    for u in prod_blocks:
        su = scc_of[u]
        for v in adj[u]:
            sv = scc_of[v]
            if su != sv:
                dag_adj[su].add(sv)
                dag_rev[sv].add(su)

    # Topological longest-path rank over the condensed DAG.
    in_deg = {i: len(dag_rev[i]) for i in range(len(sccs))}
    queue = sorted(
        [i for i, deg in in_deg.items() if deg == 0],
        key=lambda i: min(_ROLE_ORDER.get(roles_by_block.get(n, "service"), 1) for n in sccs[i]),
    )
    depth: dict[int, int] = {i: 0 for i in range(len(sccs))}
    while queue:
        curr = queue.pop(0)
        for nxt in sorted(dag_adj[curr]):
            depth[nxt] = max(depth[nxt], depth[curr] + 1)
            in_deg[nxt] -= 1
            if in_deg[nxt] == 0:
                queue.append(nxt)

    # Anchor pure leaf blocks (no outgoing edges, >=1 incoming) near the bottom.
    max_depth = max(depth.values(), default=0)
    prod_in_deg = {
        b: sum(1 for other in prod_blocks if b in adj[other])
        for b in prod_blocks
    }
    raw_rank: dict[str, int] = {}
    for b in prod_blocks:
        base = depth[scc_of[b]]
        role = roles_by_block.get(b, "service")
        if not adj[b] and prod_in_deg[b] > 0:
            base = max(base, max_depth)
        # Keep non-interface blocks that have callers below zero-caller entrypoints.
        caller_offset = 1 if (prod_in_deg[b] > 0 and role != "interface") else 0
        tier_offset = 1 if role in {"engine", "foundation"} and max_depth > 0 else 0
        raw_rank[b] = base * 2 + caller_offset + tier_offset

    distinct = sorted(set(raw_rank.values()))
    if len(distinct) <= 4:
        tier_map = {val: f"L{idx + 1}" for idx, val in enumerate(distinct)}
    elif distinct[0] == 0:
        # Keep zero-caller interface entrypoints (`raw_rank == 0`) in L1,
        # and distribute downstream tiers across L2..L4.
        rest_min, rest_max = distinct[1], distinct[-1]
        rest_span = max(1, rest_max - rest_min)
        tier_map = {0: "L1"}
        for val in distinct[1:]:
            tier_map[val] = f"L{min(4, 2 + ((val - rest_min) * 2) // rest_span)}"
    else:
        min_r, max_r = distinct[0], distinct[-1]
        span = max(1, max_r - min_r)
        tier_map = {
            val: f"L{min(4, 1 + ((val - min_r) * 3) // span)}"
            for val in distinct
        }

    used_nums = sorted({int(tier_map[raw_rank[b]][1:]) for b in prod_blocks})
    remap = {f"L{num}": f"L{idx + 1}" for idx, num in enumerate(used_nums)}
    band_of = {b: remap[tier_map[raw_rank[b]]] for b in prod_blocks}
    band_num = {b: int(band_of[b][1:]) for b in prod_blocks}

    # Annotate edge architectural direction.
    annotated_edges: list[dict[str, Any]] = []
    for e in edges:
        u, v = str(e["u"]), str(e["v"])
        if u not in prod_set or v not in prod_set:
            annotated_edges.append({**e, "direction": "tooling"})
            continue
        if (u, v) in violation_pairs:
            direction = "violation"
        elif scc_of[u] == scc_of[v] and scc_sizes[scc_of[u]] > 1:
            direction = "cycle"
        elif band_num[u] > band_num[v]:
            direction = "up"
        elif band_num[u] == band_num[v]:
            direction = "lateral"
        else:
            direction = "down"
        annotated_edges.append({**e, "direction": direction})

    # Name each band specifically from its dominant role and distinctive external libraries.
    lib_block_freq: dict[str, int] = defaultdict(int)
    for b in prod_blocks:
        for lib in set(ext_libs_by_block.get(b, [])):
            lib_block_freq[lib] += 1
    distinctive_pool = _INTERFACE_LIBS | _CONNECTOR_LIBS | _ENGINE_LIBS

    bands_meta: list[dict[str, Any]] = []
    for idx in range(1, len(used_nums) + 1):
        bid = f"L{idx}"
        members = [b for b in prod_blocks if band_of[b] == bid]
        role_counts: dict[str, int] = defaultdict(int)
        lib_scores: dict[str, float] = defaultdict(float)
        for m in members:
            role_counts[roles_by_block.get(m, "service")] += 1
            for lib in ext_libs_by_block.get(m, []):
                boost = 1.5 if lib.lower() in distinctive_pool else 1.0
                lib_scores[lib] += boost / max(1, lib_block_freq.get(lib, 1))

        dominant_role = max(
            role_counts,
            key=lambda r: (role_counts[r], -_ROLE_ORDER.get(r, 9)),
        )
        top_libs = [
            lib
            for lib, _ in sorted(lib_scores.items(), key=lambda kv: (-kv[1], kv[0]))[:2]
        ]
        base_title = _ROLE_LABELS[dominant_role]
        title = f"{base_title} ({', '.join(top_libs)})" if top_libs else base_title
        desc = f"{len(members)} blocks: {', '.join(sorted(members)[:4])}"
        if len(members) > 4:
            desc += f" +{len(members) - 4}"
        bands_meta.append(
            {
                "id": bid,
                "label": bid,
                "group": _ROLE_GROUPS[dominant_role],
                "title": title,
                "desc": desc,
            }
        )

    return band_of, bands_meta, annotated_edges, {b: scc_sizes[scc_of[b]] for b in prod_blocks}


def discover_features(
    prod_blocks: list[str],
    prod_edges: list[dict[str, Any]],
    block_data: dict[str, dict[str, Any]],
    packages: list[dict[str, Any]],
    roles_by_block: dict[str, str],
) -> list[dict[str, Any]]:
    """Auto-discover vertical feature slices across layers with hub dampening."""
    if len(prod_blocks) <= 1:
        return []

    prod_set = set(prod_blocks)
    in_neighbors: dict[str, set[str]] = defaultdict(set)
    out_neighbors: dict[str, set[str]] = defaultdict(set)
    for e in prod_edges:
        u, v = str(e["u"]), str(e["v"])
        if u in prod_set and v in prod_set and u != v:
            out_neighbors[u].add(v)
            in_neighbors[v].add(u)

    # Identify universal foundation hubs imported by >= 45% of production blocks.
    hub_threshold = max(3, int(math.ceil(len(prod_blocks) * 0.45)))
    hubs = {
        b
        for b in prod_blocks
        if len(in_neighbors[b]) >= hub_threshold
        or (roles_by_block.get(b) == "foundation" and len(in_neighbors[b]) >= 4)
    }

    # Seed vertical slices from non-hub blocks (prioritizing services/interfaces/engines).
    seeds = [b for b in prod_blocks if b not in hubs]
    if not seeds:
        seeds = list(prod_blocks)

    seeds.sort(
        key=lambda b: (
            _ROLE_ORDER.get(roles_by_block.get(b, "service"), 2),
            -int(block_data[b].get("prod_loc", 0)),
            b,
        )
    )

    pkg_by_block: dict[str, list[str]] = defaultdict(list)
    for p in packages:
        pkg_by_block[str(p["block_id"])].append(str(p["id"]))

    features: list[dict[str, Any]] = []
    seen_sets: list[set[str]] = []

    for seed in seeds:
        slice_blocks: set[str] = {seed}
        # Follow non-hub callees up to 2 hops and direct non-hub callers.
        for nxt in out_neighbors[seed]:
            if nxt not in hubs:
                slice_blocks.add(nxt)
                for nxt2 in out_neighbors[nxt]:
                    if nxt2 not in hubs:
                        slice_blocks.add(nxt2)
        for caller in in_neighbors[seed]:
            if caller not in hubs:
                slice_blocks.add(caller)

        if len(slice_blocks) < 2 and len(prod_blocks) > 2:
            # Include immediate hub target if block would otherwise be a singleton.
            slice_blocks.update(out_neighbors[seed])

        # Deduplicate overlapping slices (Jaccard >= 0.70).
        is_dup = False
        for prev in seen_sets:
            inter = len(slice_blocks & prev)
            union = len(slice_blocks | prev)
            if union > 0 and (inter / union) >= 0.70:
                is_dup = True
                break
        if is_dup:
            continue

        seen_sets.append(slice_blocks)
        ordered = sorted(slice_blocks)
        mod_count = sum(int(block_data[b].get("prod_files", 0)) for b in ordered)
        loc_count = sum(int(block_data[b].get("prod_loc", 0)) for b in ordered)
        pkgs = sorted({pid for b in ordered for pid in pkg_by_block.get(b, [])})
        features.append(
            {
                "id": f"feat_{seed}",
                "label": seed,
                "summary": (
                    f"Vertical flow centered on '{seed}' across {len(ordered)} blocks "
                    f"({mod_count} modules, {loc_count:,} LOC)"
                ),
                "blocks": ordered,
                "packages": pkgs,
                "modules_count": mod_count,
                "loc": loc_count,
            }
        )
        if len(features) >= 8:
            break

    return features


def analyze_architecture(
    *,
    blocks_payload: list[dict[str, Any]],
    block_edges: list[dict[str, Any]],
    packages_payload: list[dict[str, Any]],
    modules_payload: list[dict[str, Any]],
    cycles: list[list[str]],
    violations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute project-specific roles, SCC layering, features, and weaknesses."""
    block_map = {str(b["id"]): b for b in blocks_payload}
    all_ids = sorted(block_map.keys())
    violation_pairs = {
        (str(v["src_block"]), str(v["dst_block"]))
        for v in violations
    }

    # 1. Quarantine tooling/scripts blocks that have zero callers from production blocks.
    non_tooling_candidates = {bid for bid in all_ids if not _is_tooling_name(bid)}
    inbound_non_tooling: dict[str, int] = defaultdict(int)
    for e in block_edges:
        u, v = str(e["u"]), str(e["v"])
        if u in non_tooling_candidates and u != v:
            inbound_non_tooling[v] += 1

    zones: dict[str, Literal["production", "tooling"]] = {
        bid: classify_block_zone(bid, inbound_non_tooling.get(bid, 0))
        for bid in all_ids
    }
    prod_blocks = [bid for bid in all_ids if zones[bid] == "production"]
    tooling_blocks = [bid for bid in all_ids if zones[bid] == "tooling"]
    prod_set = set(prod_blocks)

    # 2. Compute degrees, instability, and semantic roles on production blocks.
    in_deg: dict[str, int] = defaultdict(int)
    out_deg: dict[str, int] = defaultdict(int)
    for e in block_edges:
        u, v = str(e["u"]), str(e["v"])
        if u in prod_set and v in prod_set and u != v:
            out_deg[u] += 1
            in_deg[v] += 1

    instability: dict[str, float] = {}
    roles_by_block: dict[str, str] = {}
    role_summaries: dict[str, str] = {}
    ext_libs_by_block: dict[str, list[str]] = {}

    for bid in all_ids:
        b = block_map[bid]
        ca = in_deg.get(bid, 0)
        ce = out_deg.get(bid, 0)
        inst = round(ce / max(1, ca + ce), 2)
        instability[bid] = inst
        ext = list(b.get("external_libs", []))
        ext_libs_by_block[bid] = ext
        if zones[bid] == "tooling":
            roles_by_block[bid] = "tooling"
            role_summaries[bid] = (
                f"Developer Tooling / Scripts - {b.get('prod_files', 0)} files, "
                f"{b.get('prod_loc', 0):,} LOC"
            )
        else:
            role, summary = infer_block_role(
                bid,
                ext_libs=ext,
                sinks=int(b.get("sensitive_sinks", 0)),
                prod_files=int(b.get("prod_files", 0)),
                prod_loc=int(b.get("prod_loc", 0)),
                in_deg=ca,
                out_deg=ce,
                instability=inst,
            )
            roles_by_block[bid] = role
            role_summaries[bid] = summary

    # 3. Tarjan SCC condensation + exact longest-path layering.
    band_of, bands_meta, annotated_edges, scc_sizes = compute_layered_architecture(
        prod_blocks,
        block_edges,
        roles_by_block,
        ext_libs_by_block,
        violation_pairs,
    )
    for bid in tooling_blocks:
        band_of[bid] = "TOOLING"

    # 4. Count per-block cycle/back-edge exposure and detect God modules.
    cycle_block_counts: dict[str, int] = defaultdict(int)
    mod_to_block = {str(m["path"]): str(m["block_id"]) for m in modules_payload}
    for cyc in cycles:
        touched_blocks = {mod_to_block[p] for p in cyc if p in mod_to_block}
        for bid in touched_blocks:
            cycle_block_counts[bid] += 1

    back_edge_counts: dict[str, int] = defaultdict(int)
    for e in annotated_edges:
        if e.get("direction") in {"up", "violation"}:
            back_edge_counts[str(e["u"])] += 1

    god_modules: list[dict[str, Any]] = []
    god_blocks: set[str] = set()
    for m in modules_payload:
        bid = str(m["block_id"])
        if zones.get(bid) == "tooling":
            continue
        loc = int(m.get("loc", 0))
        degree = len(m.get("imports", [])) + len(m.get("imported_by", []))
        if loc >= 450 and degree >= 5:
            god_blocks.add(bid)
            god_modules.append(
                {
                    "path": str(m["path"]),
                    "block_id": bid,
                    "loc": loc,
                    "imports": len(m.get("imports", [])),
                    "imported_by": len(m.get("imported_by", [])),
                    "sinks": int(m.get("sinks", 0)),
                    "tested": bool(m.get("tested")),
                    "score": loc * degree,
                }
            )
    god_modules.sort(key=lambda item: (-item["score"], item["path"]))
    god_modules = god_modules[:8]

    block_metrics: dict[str, dict[str, Any]] = {}
    for bid in all_ids:
        b = block_map[bid]
        ca = in_deg.get(bid, 0)
        cov_pct = float(b.get("file_coverage_pct", 0.0))
        loc = int(b.get("prod_loc", 0))
        untested_sinks = int(b.get("untested_sinks", 0))
        blast = round(ca * max(0.15, 1.0 - cov_pct / 100.0) * math.log2(1 + max(1, loc)), 1)

        tags: list[str] = []
        if cycle_block_counts.get(bid, 0) > 0 or scc_sizes.get(bid, 1) > 1:
            tags.append("CYCLE")
        if back_edge_counts.get(bid, 0) > 0:
            tags.append("BACK-EDGE")
        if ca >= 4 and cov_pct < 75.0:
            tags.append("HIGH BLAST RADIUS")
        if untested_sinks > 0:
            tags.append("UNTESTED SINKS")
        if bid in god_blocks:
            tags.append("GOD MODULE")

        block_metrics[bid] = {
            "zone": zones[bid],
            "role": roles_by_block[bid],
            "role_summary": role_summaries[bid],
            "band": band_of.get(bid, "L1"),
            "instability": instability[bid],
            "blast_radius": blast,
            "cycle_count": cycle_block_counts.get(bid, 0),
            "back_edge_count": back_edge_counts.get(bid, 0),
            "weakness_tags": tags,
        }

    # 5. Discover vertical features across production blocks.
    prod_edges = [e for e in annotated_edges if zones.get(str(e["u"])) == "production"]
    features = discover_features(
        prod_blocks,
        prod_edges,
        block_map,
        packages_payload,
        roles_by_block,
    )

    # 6. Synthesize factual Executive Diagnosis findings.
    diagnosis: list[dict[str, Any]] = []
    if violations:
        top_v = violations[0]
        diagnosis.append(
            {
                "severity": "HIGH",
                "kind": "VIOLATION",
                "title": f"{len(violations)} forbidden architecture dependency violation(s)",
                "detail": (
                    f"{top_v['src_block']} -> {top_v['dst_block']}: {top_v.get('reason', '')}"
                ),
                "jump_level": "blocks",
                "jump_id": str(top_v["src_block"]),
            }
        )
    if cycles:
        top_cycled = max(
            ((cnt, bid) for bid, cnt in cycle_block_counts.items()),
            default=(0, prod_blocks[0] if prod_blocks else ""),
        )
        diagnosis.append(
            {
                "severity": "HIGH",
                "kind": "CYCLE",
                "title": f"{len(cycles)} internal import cycle(s) detected",
                "detail": (
                    f"Concentrated around '{top_cycled[1]}' ({top_cycled[0]} cycle(s)), "
                    f"starting at {cycles[0][0]}."
                ),
                "jump_level": "blocks",
                "jump_id": top_cycled[1],
            }
        )
    upward = [e for e in annotated_edges if e.get("direction") == "up"]
    if upward:
        sample = upward[0]
        diagnosis.append(
            {
                "severity": "MEDIUM",
                "kind": "BACK-EDGE",
                "title": f"{len(upward)} upward layering back-edge(s)",
                "detail": (
                    f"Lower-band block '{sample['u']}' imports higher-band '{sample['v']}' "
                    f"({sample['n']} imports)."
                ),
                "jump_level": "blocks",
                "jump_id": str(sample["u"]),
            }
        )
    if prod_blocks:
        riskiest = max(
            prod_blocks,
            key=lambda bid: (block_metrics[bid]["blast_radius"], in_deg.get(bid, 0)),
        )
        rb = block_map[riskiest]
        if block_metrics[riskiest]["blast_radius"] > 0:
            diagnosis.append(
                {
                    "severity": "MEDIUM" if float(rb.get("file_coverage_pct", 0)) < 75 else "INFO",
                    "kind": "BLAST-RADIUS",
                    "title": f"Highest structural gravity: '{riskiest}'",
                    "detail": (
                        f"Imported by {in_deg.get(riskiest, 0)} blocks with "
                        f"{float(rb.get('file_coverage_pct', 0)):.0f}% file coverage and "
                        f"{rb.get('untested_sinks', 0)} untested sinks."
                    ),
                    "jump_level": "blocks",
                    "jump_id": riskiest,
                }
            )
    if god_modules:
        gm = god_modules[0]
        diagnosis.append(
            {
                "severity": "MEDIUM",
                "kind": "GOD-MODULE",
                "title": f"Largest coupling bottleneck: {gm['path']}",
                "detail": (
                    f"{gm['loc']:,} LOC with {gm['imports']} imports and "
                    f"{gm['imported_by']} callers."
                ),
                "jump_level": "modules",
                "jump_id": gm["path"],
            }
        )
    if tooling_blocks:
        diagnosis.append(
            {
                "severity": "INFO",
                "kind": "TOOLING",
                "title": f"{len(tooling_blocks)} non-production tooling/scratch block(s) isolated",
                "detail": f"Quarantined from production layers: {', '.join(tooling_blocks)}.",
                "jump_level": "blocks",
                "jump_id": tooling_blocks[0],
            }
        )

    return {
        "bands": bands_meta,
        "block_metrics": block_metrics,
        "block_edges": annotated_edges,
        "tooling_blocks": tooling_blocks,
        "features": features,
        "god_modules": god_modules,
        "diagnosis": diagnosis[:5],
    }
