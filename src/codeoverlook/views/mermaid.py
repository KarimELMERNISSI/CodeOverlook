"""Mermaid diagram generators for architecture blocks and test coverage maps."""

from __future__ import annotations

from typing import Any

from codeoverlook.core.coverage import RepoCoverageReport

_COVERAGE_STYLES: dict[str, str] = {
    "WELL_COVERED": "fill:#dcfce7,stroke:#15803d,stroke-width:2px",
    "PARTIAL": "fill:#fef9c3,stroke:#a16207,stroke-width:2px",
    "LOW": "fill:#ffedd5,stroke:#c2410c,stroke-width:2px",
    "UNTESTED": "fill:#fde2e2,stroke:#b91c1c,stroke-width:3px",
}


def _safe_mermaid_id(block_id: str) -> str:
    return block_id.replace("-", "_").replace(".", "_").replace("/", "_")


def render_block_mermaid(
    summary: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
) -> str:
    """Render a `graph LR` Mermaid diagram of functional blocks and imports.

    Args:
        summary: Block risk summary produced by `FactStore.get_block_risk_summary()`.
        dependencies: Inter-block edges from `FactStore.get_block_dependencies()`.

    Returns:
        Mermaid graph string ready for rendering.
    """
    lines = ["graph LR"]
    for block in summary:
        bid = str(block["block_id"])
        safe_id = _safe_mermaid_id(bid)
        label = (
            f"{bid}\\n({block['file_count']} files | {block['sensitive_sinks']} sinks)"
        )
        lines.append(f'    {safe_id}["{label}"]')
        if int(block["high_risk_findings"]) > 0:
            lines.append(
                f"    style {safe_id} fill:#fde2e2,stroke:#c53030,stroke-width:2px"
            )

    for dep in dependencies:
        if dep.get("kind") != "IMPORTS":
            continue
        src = _safe_mermaid_id(str(dep["src_block"]))
        dst = _safe_mermaid_id(str(dep["dst_block"]))
        lines.append(f"    {src} -->|{dep['edge_count']}| {dst}")

    return "\n".join(lines)


def render_coverage_mermaid(
    coverage: RepoCoverageReport,
    dependencies: list[dict[str, Any]],
) -> str:
    """Render a `graph LR` Mermaid map linking tests to functional blocks by coverage status.

    Args:
        coverage: Repository test coverage report from `TestCoverageAnalyzer`.
        dependencies: Production inter-block dependencies (`IMPORTS`).

    Returns:
        Mermaid diagram highlighting well-covered vs untested blocks.
    """
    lines = ["graph LR"]
    suite_label = (
        f"Test Suite\\n({coverage.linked_test_files}/{coverage.total_test_files} linked files | "
        f"{coverage.total_test_functions} tests)"
    )
    lines.append(f'    test_suite["{suite_label}"]')
    lines.append("    style test_suite fill:#dbeafe,stroke:#1d4ed8,stroke-width:2px")

    for block in coverage.blocks:
        safe_id = _safe_mermaid_id(block.block_id)
        label = (
            f"{block.block_id}\\n"
            f"Files: {block.tested_files}/{block.prod_files} ({block.file_coverage_pct:.0f}%) | "
            f"Syms: {block.symbol_coverage_pct:.0f}%\\n"
            f"Tests: {block.test_files_count} files ({block.test_functions_count} fns)"
        )
        lines.append(f'    {safe_id}["{label}"]')
        style = _COVERAGE_STYLES.get(block.coverage_status)
        if style:
            lines.append(f"    style {safe_id} {style}")

    for block in coverage.blocks:
        if block.test_files_count > 0:
            safe_id = _safe_mermaid_id(block.block_id)
            lines.append(f"    test_suite -.->|{block.test_files_count} files| {safe_id}")

    for dep in dependencies:
        if dep.get("kind") != "IMPORTS":
            continue
        src = _safe_mermaid_id(str(dep["src_block"]))
        dst = _safe_mermaid_id(str(dep["dst_block"]))
        lines.append(f"    {src} -->|{dep['edge_count']}| {dst}")

    return "\n".join(lines)
