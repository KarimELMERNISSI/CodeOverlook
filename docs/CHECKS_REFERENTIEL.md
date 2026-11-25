# CodeOverlook Checks and Vulnerability Referentiel

This document is the authoritative technical catalog of all static security sink rules, parse integrity checks, architectural weakness heuristics, test-coverage gap scoring, and built-in tool safety guards currently implemented in CodeOverlook (`codeoverlook==0.1.0`), together with known scope limits and planned extensions.

---

## Overview and Taxonomy

CodeOverlook evaluates inspected Python (`>= 3.12`) repositories across two verification planes:

1. **Persisted AST Findings (`findings` table in `.codeoverlook/index.db`)**
   Defined in [src/codeoverlook/core/schema.sql](../src/codeoverlook/core/schema.sql) and emitted during indexing by `PythonASTIngester` ([src/codeoverlook/ingesters/python_ast.py](../src/codeoverlook/ingesters/python_ast.py)) with `tool = "codeoverlook-ast"`:
   - **Severities:** `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`
   - **Implemented Categories:** `SINK` (security-sensitive API/SQL surfaces), `ARCH` (parse/syntax integrity)
   - **Schema-Reserved Categories (planned):** `SAST`, `CVE`

2. **Graph, Boundary, and Coverage Diagnostics**
   Computed deterministically over the `files`, `symbols`, `edges`, and `findings` tables by:
   - `BlockResolver` ([src/codeoverlook/core/blocks.py](../src/codeoverlook/core/blocks.py))
   - `FactStore` ([src/codeoverlook/core/store.py](../src/codeoverlook/core/store.py))
   - `analyze_architecture()` ([src/codeoverlook/core/architecture.py](../src/codeoverlook/core/architecture.py))
   - `TestCoverageAnalyzer` ([src/codeoverlook/core/coverage.py](../src/codeoverlook/core/coverage.py))

3. **Built-In Tool Self-Defense Guards**
   Enforced at repository resolution, archive extraction, and local web-workbench boundaries in [src/codeoverlook/core/sources.py](../src/codeoverlook/core/sources.py) and [src/codeoverlook/interfaces/web_server.py](../src/codeoverlook/interfaces/web_server.py).

---

## 1. Static AST Security Sinks (21 Rules)

All sink rules run in `PythonASTIngester` (`tool = "codeoverlook-ast"`, `category = "SINK"`). Import aliases (for example `import pickle as p` or `from yaml import load`), local type annotations, class instantiations (`cursor = sqlite3.Connection(...)`), and `@pytest.fixture` return/yield types are normalized through `alias_map`, `local_types_stack`, and `_resolve_call_name()` before matching.

| Rule ID | Domain | Target Call / Pattern | Severity | Default Message | Detection and Exemption Notes |
| --- | --- | --- | --- | --- | --- |
| `SINK-EXEC-01` | Dynamic Code Execution | `eval(...)` | `HIGH` | `Dynamic execution via eval()` | Alias-resolved call match in `SENSITIVE_SINKS`. |
| `SINK-EXEC-02` | Dynamic Code Execution | `exec(...)` | `HIGH` | `Dynamic execution via exec()` | Alias-resolved call match in `SENSITIVE_SINKS`. |
| `SINK-OS-01` | OS and Subprocess | `os.system(...)` | `HIGH` | `Shell execution via os.system()` | Alias-resolved call match (`os.system`, `from os import system`). |
| `SINK-PROC-01` | OS and Subprocess | `subprocess.Popen(...)` | `MEDIUM` | `Subprocess launch via subprocess.Popen` | Unconditional surface indicator (does not inspect `shell=True`). |
| `SINK-PROC-02` | OS and Subprocess | `subprocess.run(...)` | `MEDIUM` | `Subprocess launch via subprocess.run` | Unconditional surface indicator (does not inspect `shell=True`). |
| `SINK-PROC-03` | OS and Subprocess | `subprocess.call(...)` | `MEDIUM` | `Subprocess launch via subprocess.call` | Unconditional surface indicator (does not inspect `shell=True`). |
| `SINK-PROC-04` | OS and Subprocess | `subprocess.check_call(...)` | `MEDIUM` | `Subprocess launch via subprocess.check_call` | Unconditional surface indicator (does not inspect `shell=True`). |
| `SINK-PROC-05` | OS and Subprocess | `subprocess.check_output(...)` | `MEDIUM` | `Subprocess launch via subprocess.check_output` | Unconditional surface indicator (does not inspect `shell=True`). |
| `SINK-DESER-01` | Unsafe Deserialization | `pickle.load(...)` | `HIGH` | `Potentially unsafe pickle.load deserialization` | Alias-resolved call match. |
| `SINK-DESER-02` | Unsafe Deserialization | `pickle.loads(...)` | `HIGH` | `Potentially unsafe pickle.loads deserialization` | Alias-resolved call match. |
| `SINK-DESER-03` | Unsafe Deserialization | `yaml.load(...)` | `HIGH` | `yaml.load() without SafeLoader detected` | **Exemption:** skipped when keyword `Loader=` unparses to a string containing `"Safe"` (such as `SafeLoader` or `CSafeLoader`). |
| `SINK-DESER-04` | Unsafe Deserialization | `yaml.unsafe_load(...)` | `CRITICAL` | `Unsafe YAML deserialization via yaml.unsafe_load()` | Unconditional `CRITICAL` finding. |
| `SINK-ARCHIVE-01` | Archive Extraction | `zipfile.ZipFile(...)` | `MEDIUM` | `ZIP archive handling (check for Zip Slip)` | Surface indicator flagging archive handling for manual/AI review. |
| `SINK-ARCHIVE-02` | Archive Extraction | `tarfile.open(...)` | `MEDIUM` | `TAR archive handling (check for Path Traversal)` | Surface indicator flagging archive handling for manual/AI review. |
| `SINK-ARCHIVE-03` | Archive Extraction | `shutil.unpack_archive(...)` | `MEDIUM` | `Archive extraction via shutil.unpack_archive` | Surface indicator flagging archive extraction. |
| `SINK-NET-01` | Outbound Network | `requests.get(...)` | `LOW` | `Outbound HTTP request (requests.get)` | Egress / SSRF / external telemetry surface indicator. |
| `SINK-NET-02` | Outbound Network | `requests.post(...)` | `LOW` | `Outbound HTTP request (requests.post)` | Egress / SSRF / external telemetry surface indicator. |
| `SINK-NET-03` | Outbound Network | `httpx.get(...)` | `LOW` | `Outbound HTTP request (httpx.get)` | Egress / SSRF / external telemetry surface indicator. |
| `SINK-NET-04` | Outbound Network | `httpx.post(...)` | `LOW` | `Outbound HTTP request (httpx.post)` | Egress / SSRF / external telemetry surface indicator. |
| `SINK-NET-05` | Outbound Network | `urllib.request.urlopen(...)` | `LOW` | `Outbound network call via urlopen` | Egress / SSRF surface indicator. |
| `SINK-SQL-01` | Dynamic SQL Injection | `*.execute(arg, ...)` | `HIGH` | `Dynamic SQL constructed inside .execute() (potential SQL injection risk)` | Triggers when the first positional argument is an f-string (`ast.JoinedStr`), binary `+` or `%` (`ast.BinOp`), `.format(...)` call, or a variable tracked in `dynamic_vars_stack` for the current lexical scope (cleared if reassigned to a literal `ast.Constant`). |

---

## 2. Parse and Static Integrity (1 Rule)

| Rule ID | Tool / Category | Trigger | Severity | Default Message | Behavior |
| --- | --- | --- | --- | --- | --- |
| `PARSE-SYNTAX-ERR` | `codeoverlook-ast` / `ARCH` | `ast.parse()` raises `SyntaxError` | `MEDIUM` | `Python syntax error: <exc.msg>` | Records line number (`exc.lineno or 1`), file SHA-256, and LOC while allowing the rest of the repository scan to complete. |

---

## 3. Architectural and Structural Weakness Checks (7 Checks)

These checks diagnose boundary contracts, dependency cycles, layering inversions, coupling bottlenecks, and unguarded blast radii across the codebase.

| Check / Tag | Kind / Severity | Implementing Module | Trigger / Condition | Formula or Output Details |
| --- | --- | --- | --- | --- |
| Explicit Forbidden Dependency | `VIOLATION` (`HIGH`) | `BlockResolver.check_violations()` (`core/blocks.py`) | Aggregated internal dependency matches `[[architecture.forbid]]` (`from` -> `to`) in `.codeoverlook.toml`. | Emits `src_block`, `dst_block`, edge `kind`, `edge_count`, and configured `reason`; marks block edge `direction = "violation"`. |
| Production Import Cycle (File Level) | `CYCLE` (`HIGH`) | `FactStore.detect_import_cycles()` (`core/store.py`) | Directed cycle across internal `IMPORTS` edges among production files (`is_test = 0`, `max_depth = 6`). | SQLite `WITH RECURSIVE ... UNION` reachability CTE followed by BFS canonical shortest-ring reconstruction `[a.py, ..., a.py]`. |
| Production Block Cycle (SCC) | `CYCLE` tag (`HIGH`) | `compute_layered_architecture()` (`core/architecture.py`) | Block belongs to a Tarjan Strongly Connected Component with `len(scc) > 1` or touches a file import cycle. | Marks intra-SCC block edges with `direction = "cycle"` and tags affected blocks `CYCLE`. |
| Upward Layering Back-Edge | `BACK-EDGE` (`MEDIUM`) | `compute_layered_architecture()` (`core/architecture.py`) | Production block in a lower architectural band imports a block in a higher band (`band_num[u] > band_num[v]`). | Bands `L1..L4` are derived from condensed Tarjan SCC topological longest path + role/caller tie-breakers; upward edges get `direction = "up"` and tag `BACK-EDGE`. |
| High Blast Radius | `HIGH BLAST RADIUS` / `BLAST-RADIUS` (`MEDIUM` if `< 75%` file coverage, else `INFO`) | `analyze_architecture()` (`core/architecture.py`) | Production block with inbound block degree `Ca >= 4` and `file_coverage_pct < 75.0`. | Quantifies gravity as `blast_radius = round(Ca * max(0.15, 1.0 - cov_pct / 100.0) * log2(1 + max(1, loc)), 1)` alongside Martin's Instability `I = round(Ce / max(1, Ca + Ce), 2)`. |
| God Module Bottleneck | `GOD MODULE` / `GOD-MODULE` (`MEDIUM`) | `analyze_architecture()` (`core/architecture.py`) | Non-tooling module with `loc >= 450` and `degree = len(imports) + len(imported_by) >= 5`. | Ranks top 8 modules by `score = loc * degree` and tags owning production blocks `GOD MODULE`. |
| Untested Sinks | `UNTESTED SINKS` tag | `TestCoverageAnalyzer.analyze()` (`core/coverage.py`), `analyze_architecture()` | Production block or file contains one or more `category = 'SINK'` findings whose enclosing symbol (or file) is not covered by linked tests. | Surfaces both per-block `untested_sinks` count and per-file `UntestedTarget` priority boost. |
| Tooling / Scratch Quarantine | `TOOLING` (`INFO`) | `classify_block_zone()` (`core/architecture.py`) | Block ID or segment matches `dev_scripts`, `scripts`, `scratch`, `tools`, `docs`, `examples`, `benchmarks`, `migrations`, `sandbox`, or `notebooks` with `0` inbound imports from non-tooling blocks. | Isolated into band `TOOLING` so utility scripts do not distort production layer inference or diagnosis counts. |

---

## 4. Test Coverage and Blind-Spot Radar (`core/coverage.py`)

`TestCoverageAnalyzer` links `is_test = 1` files to production files and symbols without running user code.

### Test-to-Production Linkage Modes

1. **`static_graph`:** Follows internal `IMPORTS`, `CALLS`, and `INHERITS` edges from test files to production files/symbols (including `@pytest.fixture` return/yield type inference and typed function parameters), plus **1-hop intra-block `CALLS` reachability** so private helpers invoked by directly tested entry points are counted as covered.
2. **`naming_heuristic`:** Applied only when a test file has zero static graph edges; matches stripped `test_*` / `*_test` stems against production filenames.
3. **`unlinked`:** Test files with neither graph edges nor filename matches.

### Block Coverage Status Thresholds

| Status | Condition |
| --- | --- |
| `UNTESTED` | `tested_files == 0` |
| `LOW` | `file_coverage_pct < 35.0 and symbol_coverage_pct < 25.0` |
| `PARTIAL` | `file_coverage_pct < 70.0 and symbol_coverage_pct < 55.0` |
| `WELL_COVERED` | All remaining blocks |

### Priority Ranking Formulas

- **Per-File `UntestedTarget.priority_score`:**
  `(0.0 if is_file_tested else 20.0) + untested_sinks * 20.0 + inbound_prod_refs * 3.0 + untested_symbols * 2.0 + loc * 0.05`
- **Per-Block `BlockCoverageSummary.priority_score`:**
  `(1.0 - (0.5 * file_cov_pct + 0.5 * symbol_cov_pct) / 100.0) * (prod_loc * 0.04 + untested_symbols * 1.5 + untested_sinks * 15.0 + inbound_prod_edges * 1.2)`

---

## 5. Built-In Tool Self-Defense and Input Safety Guards

| Component | Guard | Enforcement Details | Source |
| --- | --- | --- | --- |
| GitHub `--ref` Validation | Option / traversal rejection | `_validate_ref()` rejects values starting with `-`, containing `..` or `\`, or containing whitespace/control characters (`ord(ch) < 32`). | [core/sources.py](../src/codeoverlook/core/sources.py) |
| Repository `--subpath` Validation | Path escape prevention | `_validate_subpath()` and `_apply_subpath()` reject drive prefixes, leading slashes, `.` / `..` segments, and verify `sub_root.is_relative_to(checkout_resolved)`. | [core/sources.py](../src/codeoverlook/core/sources.py) |
| GitHub Zipball Extraction | Zip Slip and resource limits | `_download_zipball()` enforces a `250 MiB` (`_MAX_ZIP_BYTES`) download limit; `_safe_extract_zipball()` rejects absolute/drive paths and `..` segments, skips POSIX symlinks (`0o120000`), and verifies `target_path.is_relative_to(dest_resolved)` before extraction. | [core/sources.py](../src/codeoverlook/core/sources.py) |
| GitHub Token Hygiene | Non-persisted auth & log scrubbing | `GITHUB_TOKEN` is passed transiently via `-c http.https://github.com/.extraheader=...` (never written into `.git/config`) and masked by `_scrub_secret()` in error messages. | [core/sources.py](../src/codeoverlook/core/sources.py) |
| Local Web Workbench | Loopback bind & body limit | Binds `127.0.0.1` by default and rejects JSON POST payloads above `1 MiB` (`_MAX_REQUEST_BYTES = 1_048_576`) with HTTP `413` (`Request Entity Too Large`). | [interfaces/web_server.py](../src/codeoverlook/interfaces/web_server.py) |

---

## 6. Current Scope Limits and Planned Extensions

CodeOverlook does **not** currently perform the following checks (listed here so audit expectations remain exact):

1. **External SAST and CVE Ingestion (Planned MVP 3):** The SQLite schema defines `SAST` and `CVE` categories for `bandit`, `semgrep`, `pip-audit`, and `ruff`, but a universal SARIF ingester (`ingesters/sarif.py`) is not yet implemented.
2. **Hardcoded Secrets and Credentials:** No regex or entropy detection for API keys, tokens, passwords, or private key material inside scanned repositories.
3. **Dependency / Lockfile Vulnerability Auditing:** No CVE matching against `pyproject.toml`, `requirements.txt`, or `uv.lock`.
4. **Inter-Procedural Dataflow / Taint Tracking:** Dynamic SQL tracking (`SINK-SQL-01`) only follows single-scope local variable assignments (`dynamic_vars_stack`) and does not trace tainted parameters across function/module boundaries or through helper builders.
5. **Context-Sensitive Filtering on Subprocess and Archive Sinks:**
   - All `subprocess.*` calls (`Popen`, `run`, `call`, `check_call`, `check_output`) are flagged uniformly as `MEDIUM` without distinguishing `shell=True` from safe argument lists.
   - `zipfile.ZipFile`, `tarfile.open`, and `shutil.unpack_archive` are flagged unconditionally without verifying whether caller code validates member paths or passes `filter="data"`.
6. **Additional Uncovered Python Sink Families:** Not yet included in `SENSITIVE_SINKS`:
   - Other code/process execution surfaces: `os.popen`, `os.spawn*`, `os.exec*`, `pty.spawn`, `compile`
   - Additional deserialization / pickle-backed loaders: `marshal.loads`, `shelve.open`, `jsonpickle.decode`, `dill.load*`, `joblib.load`, `torch.load` (without `weights_only=True`)
   - Additional HTTP client surfaces: `requests.put`, `requests.delete`, `requests.request`, `requests.Session`, `httpx.Client`, `httpx.AsyncClient`, `aiohttp.ClientSession`
   - XML parsing / XXE surfaces (`xml.etree.ElementTree`, `xml.dom.minidom`, `lxml.etree`)
   - Weak cryptography, insecure randomness (`md5`, `sha1`, `random` for secrets), insecure temp files (`tempfile.mktemp`), disabled TLS verification (`verify=False`, `ssl._create_unverified_context`), and template injection (`jinja2.Template(..., autoescape=False)`).
