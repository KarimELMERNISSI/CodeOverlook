# CodeOverlook

Panoramic visual code map, deterministic architectural boundary inspector, test-gap radar, and token-budgeted Context Slicer for Python (`>= 3.12`).

## Why CodeOverlook

CodeOverlook is built as an offline-first **verification and blind-spot inspector** for engineers and AI coding agents:

1. **Test-to-Block Radar & Untested-Sink Prioritization:** Links test files and `@pytest.fixture` targets directly to production functional blocks (`WELL_COVERED`, `PARTIAL`, `LOW`, `UNTESTED`) and ranks untested high-fan-in or sink-bearing modules first.
2. **Deterministic Boundary Contracts & Sensitive Sinks:** Enforces `[architecture.forbid]` rules declared in `.codeoverlook.toml` and detects risky AST sinks (`eval`, `exec`, `subprocess`, unsafe YAML/pickle, archives, dynamic SQL `.execute()`) without relying on LLM guesswork.
3. **Static + Runtime Convergence Ready:** Stores all module, symbol, edge, trace, and finding facts in a single local SQLite Fact Store (`.codeoverlook/index.db`) with `WITH RECURSIVE` graph traversals.
4. **Surgical Hard-Budgeted Context (`slice`):** Gives AI coding agents one strict token-bounded Markdown slice (block metadata, test coverage status, active sinks, exact source span, and k-hop signatures without neighbor bodies).
5. **Zero-Daemon, Zero-Telemetry, Zero-Dependency Core:** Runs purely on Python stdlib (`ast`, `sqlite3`, `tomllib`) and outputs standalone interactive HTML explorers (`.codeoverlook/overlook.html`) and Mermaid graphs without background services or external network calls.

## Installation

```bash
uv sync
```

## CLI Quickstart

```bash
# Index or incrementally update a Python repository
uv run codeoverlook scan /path/to/repo

# Force a full re-index
uv run codeoverlook scan /path/to/repo --force

# Summarize functional blocks, risk sinks, and test coverage
uv run codeoverlook blocks /path/to/repo
uv run codeoverlook blocks /path/to/repo --json

# Inspect test-to-block associations and top untested targets
uv run codeoverlook tests /path/to/repo
uv run codeoverlook tests /path/to/repo --block core

# Extract a token-bounded Markdown context slice for an AI agent
uv run codeoverlook slice core/registry.py::Catalogue.find --repo /path/to/repo --budget 2500

# Generate Mermaid graphs (architecture risks or test coverage)
uv run codeoverlook mermaid /path/to/repo --mode arch
uv run codeoverlook mermaid /path/to/repo --mode coverage

# Generate a standalone interactive HTML inspector (.codeoverlook/overlook.html)
uv run codeoverlook html /path/to/repo
```

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
