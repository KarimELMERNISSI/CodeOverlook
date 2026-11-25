# CodeOverlook

Panoramic visual code map, deterministic architectural boundary inspector, test-gap radar, and token-budgeted Context Slicer for Python (`>= 3.12`).

## Why CodeOverlook

CodeOverlook is built as an offline-first **verification and blind-spot inspector** for engineers and AI coding agents:

1. **Test-to-Block Radar & Untested-Sink Prioritization:** Links test files and `@pytest.fixture` targets directly to production functional blocks (`WELL_COVERED`, `PARTIAL`, `LOW`, `UNTESTED`) and ranks untested high-fan-in or sink-bearing modules first.
2. **Deterministic Boundary Contracts & Sensitive Sinks:** Enforces `[architecture.forbid]` rules declared in `.codeoverlook.toml` and detects risky AST sinks (`eval`, `exec`, `subprocess`, unsafe YAML/pickle, archives, dynamic SQL `.execute()`) without relying on LLM guesswork.
3. **Static + Runtime Convergence Ready:** Stores all module, symbol, edge, trace, and finding facts in a single local SQLite Fact Store (`.codeoverlook/index.db`) with `WITH RECURSIVE` graph traversals.
4. **Surgical Hard-Budgeted Context (`slice`):** Gives AI coding agents one strict token-bounded Markdown slice (block metadata, test coverage status, active sinks, exact source span, and k-hop signatures without neighbor bodies).
5. **Online & Offline Repository Inspection:** Inspect local directories directly offline, or fetch GitHub repositories (via shallow `git clone` with zipball fallback) into a persistent cache (`~/.codeoverlook/cache/`) for repeated offline inspection through the CLI or local Web Workbench (`codeoverlook ui`).

## Installation

```bash
uv sync
```

## CLI Quickstart (Local Folders & GitHub Repositories)

```bash
# Index a local folder (100% offline)
uv run codeoverlook scan /path/to/repo

# Fetch and index a GitHub repository (cached under ~/.codeoverlook/cache/)
uv run codeoverlook scan https://github.com/owner/repo
uv run codeoverlook scan owner/repo --ref main --subpath packages/core

# Re-inspect a previously cached GitHub repository strictly offline
uv run codeoverlook scan owner/repo --offline
uv run codeoverlook blocks owner/repo --offline
uv run codeoverlook tests owner/repo --offline
uv run codeoverlook cache

# Refresh a cached GitHub repository from upstream or force a full AST re-index
uv run codeoverlook scan owner/repo --refresh --force

# Extract a token-bounded Markdown context slice for an AI agent
uv run codeoverlook slice core/registry.py::Catalogue.find --repo /path/to/repo --budget 2500

# Generate Mermaid graphs (architecture risks or test coverage)
uv run codeoverlook mermaid /path/to/repo --mode arch
uv run codeoverlook mermaid /path/to/repo --mode coverage

# Generate a standalone interactive HTML inspector (.codeoverlook/overlook.html)
uv run codeoverlook html /path/to/repo
```

## Local Web Workbench (`ui`)

Start the zero-dependency local web workbench to switch between local folders and GitHub URLs, browse cached offline checkouts, explore block coverage, slice symbols, and export standalone HTML reports:

```bash
uv run codeoverlook ui
uv run codeoverlook ui --target /path/to/repo --offline
uv run codeoverlook ui --target owner/repo --port 8765 --no-browser
```

For private GitHub repositories, set `GITHUB_TOKEN` in your environment before fetching online.

## Optional Configuration (`.codeoverlook.toml`)

```toml
[scan]
exclude = ["tests/**", "docs/**", "**/migrations/**"]

[tests]
patterns = ["tests/**", "**/test_*.py", "conftest.py", "**/conftest.py"]

[blocks.ui]
description = "Interface & Workflows"
patterns = ["app_pages/**", "ui/**"]

[blocks.engine]
description = "Core Business Logic"
patterns = ["core/**", "analytics/**"]

[blocks.storage]
description = "Persistence & Exports"
patterns = ["manage/**", "db/**"]

[[architecture.forbid]]
from = "ui"
to = "storage"
reason = "UI must go through engine rather than importing storage directly."
```

## Checks and Vulnerability Referentiel

See [docs/CHECKS_REFERENTIEL.md](docs/CHECKS_REFERENTIEL.md) for the exact catalog of implemented AST sink rules (`SINK-*`), parse integrity checks (`PARSE-SYNTAX-ERR`), architectural weakness diagnostics (`VIOLATION`, `CYCLE`, `BACK-EDGE`, `HIGH BLAST RADIUS`, `GOD MODULE`, `UNTESTED SINKS`, `TOOLING` quarantine), test-gap scoring formulas, built-in safety guards, and current scope limits.
