"""Deterministic Python static AST extractor with sink and fixture type inference."""

from __future__ import annotations

import ast
import hashlib
import os
import sys
from collections.abc import Callable
from pathlib import Path

from codeoverlook.core.blocks import is_default_test_path
from codeoverlook.core.store import (
    EdgeRecord,
    FileParseResult,
    FindingRecord,
    SymbolRecord,
)

# Sensitive surfaces detected natively during the AST pass
SENSITIVE_SINKS: dict[str, tuple[str, str, str]] = {
    "eval": ("SINK-EXEC-01", "HIGH", "Dynamic execution via eval()"),
    "exec": ("SINK-EXEC-02", "HIGH", "Dynamic execution via exec()"),
    "os.system": ("SINK-OS-01", "HIGH", "Shell execution via os.system()"),
    "subprocess.Popen": (
        "SINK-PROC-01",
        "MEDIUM",
        "Subprocess launch via subprocess.Popen",
    ),
    "subprocess.run": (
        "SINK-PROC-02",
        "MEDIUM",
        "Subprocess launch via subprocess.run",
    ),
    "subprocess.call": (
        "SINK-PROC-03",
        "MEDIUM",
        "Subprocess launch via subprocess.call",
    ),
    "subprocess.check_call": (
        "SINK-PROC-04",
        "MEDIUM",
        "Subprocess launch via subprocess.check_call",
    ),
    "subprocess.check_output": (
        "SINK-PROC-05",
        "MEDIUM",
        "Subprocess launch via subprocess.check_output",
    ),
    "pickle.load": (
        "SINK-DESER-01",
        "HIGH",
        "Potentially unsafe pickle.load deserialization",
    ),
    "pickle.loads": (
        "SINK-DESER-02",
        "HIGH",
        "Potentially unsafe pickle.loads deserialization",
    ),
    "yaml.load": ("SINK-DESER-03", "HIGH", "yaml.load() without SafeLoader detected"),
    "yaml.unsafe_load": (
        "SINK-DESER-04",
        "CRITICAL",
        "Unsafe YAML deserialization via yaml.unsafe_load()",
    ),
    "zipfile.ZipFile": (
        "SINK-ARCHIVE-01",
        "MEDIUM",
        "ZIP archive handling (check for Zip Slip)",
    ),
    "tarfile.open": (
        "SINK-ARCHIVE-02",
        "MEDIUM",
        "TAR archive handling (check for Path Traversal)",
    ),
    "shutil.unpack_archive": (
        "SINK-ARCHIVE-03",
        "MEDIUM",
        "Archive extraction via shutil.unpack_archive",
    ),
    "requests.get": ("SINK-NET-01", "LOW", "Outbound HTTP request (requests.get)"),
    "requests.post": ("SINK-NET-02", "LOW", "Outbound HTTP request (requests.post)"),
    "httpx.get": ("SINK-NET-03", "LOW", "Outbound HTTP request (httpx.get)"),
    "httpx.post": ("SINK-NET-04", "LOW", "Outbound HTTP request (httpx.post)"),
    "urllib.request.urlopen": (
        "SINK-NET-05",
        "LOW",
        "Outbound network call via urlopen",
    ),
}

DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".codeoverlook",
    "node_modules",
    "build",
    "dist",
}

_WRAPPER_TYPES = {
    "Generator",
    "Iterator",
    "AsyncGenerator",
    "AsyncIterator",
    "Iterable",
    "Optional",
    "Sequence",
    "list",
    "set",
}


def _extract_dotted(expr: ast.expr) -> str | None:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        parent = _extract_dotted(expr.value)
        return f"{parent}.{expr.attr}" if parent else expr.attr
    return None


def _extract_annotation_type(expr: ast.expr) -> str | None:
    """Extract a concrete class/type name from a type annotation expression."""
    if isinstance(expr, (ast.Name, ast.Attribute)):
        return _extract_dotted(expr)
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.BitOr):
        for side in (expr.left, expr.right):
            if isinstance(side, ast.Constant) and side.value is None:
                continue
            resolved = _extract_annotation_type(side)
            if resolved:
                return resolved
        return None
    if isinstance(expr, ast.Subscript):
        base = _extract_dotted(expr.value)
        base_tail = base.split(".")[-1] if base else ""
        if base_tail in _WRAPPER_TYPES:
            inner = expr.slice.elts[0] if isinstance(expr.slice, ast.Tuple) else expr.slice
            return _extract_annotation_type(inner)
        return base
    return None


def _is_pytest_fixture(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        dotted = _extract_dotted(target)
        if dotted and (dotted == "fixture" or dotted.endswith(".fixture")):
            return True
    return False


def _infer_fixture_return_type(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    if node.returns is not None:
        ret_type = _extract_annotation_type(node.returns)
        if ret_type and ret_type.split(".")[-1][:1].isupper():
            return ret_type

    local_vars: dict[str, str] = {}
    for stmt in ast.walk(node):
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
            cls_name = _extract_dotted(stmt.value.func)
            if cls_name and cls_name.split(".")[-1][:1].isupper():
                for tgt in stmt.targets:
                    if isinstance(tgt, ast.Name):
                        local_vars[tgt.id] = cls_name
        elif isinstance(stmt, (ast.Return, ast.Yield)) and stmt.value is not None:
            if isinstance(stmt.value, ast.Call):
                cls_name = _extract_dotted(stmt.value.func)
                if cls_name and cls_name.split(".")[-1][:1].isupper():
                    return cls_name
            elif isinstance(stmt.value, ast.Name) and stmt.value.id in local_vars:
                return local_vars[stmt.value.id]
    return None


def _extract_fixture_types(tree: ast.Module) -> dict[str, str]:
    fixtures: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_pytest_fixture(node):
            inferred = _infer_fixture_return_type(node)
            if inferred:
                fixtures[node.name] = inferred
    return fixtures


class PythonASTIngester:
    """Deterministic Python static extractor built on the standard `ast` module."""

    def __init__(
        self,
        repo_root: Path,
        block_resolver: Callable[[str], str] | None = None,
        exclude_checker: Callable[[str], bool] | None = None,
        test_detector: Callable[[str], bool] | None = None,
    ) -> None:
        """Initialize the extractor and pre-index local repository modules.

        Args:
            repo_root: Root directory of the target Python repository.
            block_resolver: Optional callable mapping relative POSIX paths to block IDs.
            exclude_checker: Optional predicate skipping excluded relative paths.
            test_detector: Optional predicate classifying a relative path as a test file.
        """
        self.repo_root = repo_root.resolve()
        self.block_resolver = block_resolver or self._default_block_resolver
        self.exclude_checker = exclude_checker
        self.test_detector = test_detector or is_default_test_path
        self.stdlib_modules = set(sys.stdlib_module_names)
        self.module_index = self._build_module_index()

    def _build_module_index(self) -> dict[str, str]:
        """Map each local Python module name to its relative POSIX file path."""
        index: dict[str, str] = {}
        for py_file in self.iter_python_files():
            rel = py_file.relative_to(self.repo_root).as_posix()
            mod_name = self._path_to_module(rel)
            if mod_name:
                index[mod_name] = rel
                if mod_name.startswith("src."):
                    index[mod_name.removeprefix("src.")] = rel
        return index

    def iter_python_files(self) -> list[Path]:
        """Return sorted list of eligible `.py` files inside the repository."""
        files: list[Path] = []
        for root, dirnames, filenames in os.walk(self.repo_root):
            dirnames[:] = sorted(d for d in dirnames if d not in DEFAULT_EXCLUDED_DIRS)
            root_path = Path(root)
            for fname in sorted(filenames):
                if not fname.endswith(".py"):
                    continue
                full_path = root_path / fname
                rel = full_path.relative_to(self.repo_root).as_posix()
                if self.exclude_checker is not None and self.exclude_checker(rel):
                    continue
                files.append(full_path)
        return sorted(files)

    @staticmethod
    def _path_to_module(rel_posix: str) -> str:
        no_ext = rel_posix[:-3] if rel_posix.endswith(".py") else rel_posix
        if no_ext.endswith("/__init__"):
            no_ext = no_ext[:-9]
        elif no_ext == "__init__":
            return ""
        return no_ext.replace("/", ".")

    @staticmethod
    def _default_block_resolver(rel_posix: str) -> str:
        parts = Path(rel_posix).parts
        if len(parts) <= 1:
            return "root"
        if parts[0] == "src":
            if len(parts) >= 4:
                return parts[2]
            if len(parts) == 3:
                return parts[1]
        return parts[0]

    def parse_file(self, file_path: Path) -> FileParseResult | None:
        """Parse a Python source file and extract symbols, edges, and findings.

        Args:
            file_path: Path to the `.py` file to parse.

        Returns:
            A populated `FileParseResult`, a `PARSE-SYNTAX-ERR` finding record on
            syntax errors, or `None` if the file cannot be read.
        """
        try:
            resolved_path = file_path.resolve()
            raw_bytes = resolved_path.read_bytes()
            rel_path = resolved_path.relative_to(self.repo_root).as_posix()
        except (OSError, ValueError):
            return None

        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        source = raw_bytes.decode("utf-8", errors="replace")
        loc = sum(1 for line in source.splitlines() if line.strip())
        block_id = self.block_resolver(rel_path)
        is_test = bool(self.test_detector(rel_path))

        try:
            tree = ast.parse(source, filename=rel_path)
        except SyntaxError as exc:
            return FileParseResult(
                file_path=rel_path,
                sha256=sha256,
                loc=loc,
                block_id=block_id,
                is_test=is_test,
                findings=[
                    FindingRecord(
                        file_path=rel_path,
                        symbol_id=rel_path,
                        tool="codeoverlook-ast",
                        rule_id="PARSE-SYNTAX-ERR",
                        severity="MEDIUM",
                        category="ARCH",
                        line=exc.lineno or 1,
                        message=f"Python syntax error: {exc.msg}",
                    )
                ],
            )

        top_level_symbols = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        fixture_return_types = _extract_fixture_types(tree)
        module_docstring = _summarize_docstring(ast.get_docstring(tree))

        visitor = _ModuleVisitor(
            rel_path=rel_path,
            module_name=self._path_to_module(rel_path),
            module_index=self.module_index,
            stdlib_modules=self.stdlib_modules,
            top_level_symbols=top_level_symbols,
            fixture_return_types=fixture_return_types,
            module_docstring=module_docstring,
        )
        visitor.visit(tree)

        return FileParseResult(
            file_path=rel_path,
            sha256=sha256,
            loc=loc,
            block_id=block_id,
            is_test=is_test,
            symbols=visitor.symbols,
            edges=visitor.edges,
            findings=visitor.findings,
        )


def _summarize_docstring(raw: str | None, max_len: int = 240) -> str | None:
    """Collapse a module docstring into a single concise summary line."""
    if not raw:
        return None
    first_para = raw.strip().split("\n\n", 1)[0]
    collapsed = " ".join(first_para.split())
    if not collapsed:
        return None
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 3].rstrip() + "..."


def _is_dynamic_sql_expr(expr: ast.expr) -> bool:
    """Detect Python expressions constructing a SQL string dynamically."""
    if isinstance(expr, ast.JoinedStr):
        return True
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, (ast.Add, ast.Mod)):
        return True
    if (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Attribute)
        and expr.func.attr == "format"
    ):
        return True
    return False


class _ModuleVisitor(ast.NodeVisitor):
    """AST visitor extracting symbols, import/call/inheritance edges, and sinks."""

    def __init__(
        self,
        rel_path: str,
        module_name: str,
        module_index: dict[str, str],
        stdlib_modules: set[str],
        top_level_symbols: set[str] | None = None,
        fixture_return_types: dict[str, str] | None = None,
        module_docstring: str | None = None,
    ) -> None:
        self.rel_path = rel_path
        self.module_name = module_name
        self.module_index = module_index
        self.stdlib_modules = stdlib_modules
        self.top_level_symbols = top_level_symbols or set()
        self.fixture_return_types = fixture_return_types or {}

        self.scope_stack: list[str] = []
        self.dynamic_vars_stack: list[set[str]] = [set()]
        self.local_types_stack: list[dict[str, str]] = [{}]
        self.alias_map: dict[str, str] = {}

        self.symbols: list[SymbolRecord] = [
            SymbolRecord(
                id=rel_path,
                file_path=rel_path,
                kind="module",
                name=Path(rel_path).stem,
                qualname=module_name or Path(rel_path).stem,
                signature=f"module {module_name or Path(rel_path).stem}",
                start_line=1,
                end_line=1,
                docstring=module_docstring,
            )
        ]
        self.edges: list[EdgeRecord] = []
        self.findings: list[FindingRecord] = []

    @property
    def current_symbol_id(self) -> str:
        if not self.scope_stack:
            return self.rel_path
        return f"{self.rel_path}::{'.'.join(self.scope_stack)}"

    def _classify_target(self, dotted_name: str) -> tuple[str, str]:
        parts = dotted_name.split(".")
        for i in range(len(parts), 0, -1):
            candidate = ".".join(parts[:i])
            if candidate in self.module_index:
                target_file = self.module_index[candidate]
                remainder = ".".join(parts[i:])
                dst_id = f"{target_file}::{remainder}" if remainder else target_file
                return dst_id, "INTERNAL"

        root_pkg = parts[0]
        if root_pkg in self.stdlib_modules:
            return dotted_name, "STDLIB"
        return dotted_name, "EXTERNAL"

    def _resolve_relative_module(self, module: str | None, level: int) -> str:
        if level == 0:
            return module or ""
        pkg_parts = self.module_name.split(".") if self.module_name else []
        if not self.rel_path.endswith("__init__.py") and pkg_parts:
            pkg_parts = pkg_parts[:-1]
        base = pkg_parts[: max(0, len(pkg_parts) - (level - 1))]
        if module:
            base.append(module)
        return ".".join(base)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".")[0]
            self.alias_map[local_name] = alias.name
            dst_id, scope = self._classify_target(alias.name)
            self.edges.append(
                EdgeRecord(
                    src_id=self.current_symbol_id,
                    dst_id=dst_id,
                    kind="IMPORTS",
                    target_scope=scope,
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base_mod = self._resolve_relative_module(node.module, node.level)
        for alias in node.names:
            if alias.name == "*":
                full_target = base_mod
            else:
                full_target = f"{base_mod}.{alias.name}" if base_mod else alias.name
                local_name = alias.asname or alias.name
                self.alias_map[local_name] = full_target

            dst_id, scope = self._classify_target(full_target)
            self.edges.append(
                EdgeRecord(
                    src_id=self.current_symbol_id,
                    dst_id=dst_id,
                    kind="IMPORTS",
                    target_scope=scope,
                )
            )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope_stack.append(node.name)
        sym_id = self.current_symbol_id
        bases = [ast.unparse(b) for b in node.bases]
        sig = f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"

        self.symbols.append(
            SymbolRecord(
                id=sym_id,
                file_path=self.rel_path,
                kind="class",
                name=node.name,
                qualname=".".join(self.scope_stack),
                signature=sig,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                docstring=ast.get_docstring(node),
            )
        )

        for base_str in bases:
            resolved = self._resolve_call_name(base_str)
            dst_id, scope = self._classify_target(resolved)
            self.edges.append(
                EdgeRecord(
                    src_id=sym_id,
                    dst_id=dst_id,
                    kind="INHERITS",
                    target_scope=scope,
                )
            )

        self.generic_visit(node)
        self.scope_stack.pop()

    def _bind_parameter_types(self, args: ast.arguments) -> None:
        local_types = self.local_types_stack[-1]
        all_args = [*args.posonlyargs, *args.args, *args.kwonlyargs]
        for arg in all_args:
            if arg.arg in ("self", "cls"):
                continue
            ann_type = _extract_annotation_type(arg.annotation) if arg.annotation else None
            if ann_type and ann_type.split(".")[-1][:1].isupper():
                local_types[arg.arg] = self._resolve_call_name(ann_type)
            elif arg.arg in self.fixture_return_types:
                local_types[arg.arg] = self._resolve_call_name(
                    self.fixture_return_types[arg.arg]
                )

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        is_method = bool(self.scope_stack)
        self.scope_stack.append(node.name)
        self.dynamic_vars_stack.append(set())
        self.local_types_stack.append({})
        self._bind_parameter_types(node.args)
        sym_id = self.current_symbol_id

        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        args_str = ast.unparse(node.args)
        ret_str = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        sig = f"{prefix} {node.name}({args_str}){ret_str}"

        self.symbols.append(
            SymbolRecord(
                id=sym_id,
                file_path=self.rel_path,
                kind="method" if is_method else "function",
                name=node.name,
                qualname=".".join(self.scope_stack),
                signature=sig,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                docstring=ast.get_docstring(node),
            )
        )

        self.generic_visit(node)
        self.local_types_stack.pop()
        self.dynamic_vars_stack.pop()
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        self._track_dynamic_assignment(node.targets, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._track_dynamic_assignment([node.target], node.value)
        self.generic_visit(node)

    def _track_dynamic_assignment(self, targets: list[ast.expr], value: ast.expr) -> None:
        current_vars = self.dynamic_vars_stack[-1]
        current_types = self.local_types_stack[-1]
        is_dynamic = _is_dynamic_sql_expr(value)

        inferred_type: str | None = None
        if isinstance(value, ast.Call):
            raw_cls = _extract_dotted(value.func)
            if raw_cls:
                tail = raw_cls.split(".")[-1]
                if tail[:1].isupper():
                    inferred_type = self._resolve_call_name(raw_cls)

        for target in targets:
            if isinstance(target, ast.Name):
                if is_dynamic:
                    current_vars.add(target.id)
                elif isinstance(value, ast.Constant):
                    current_vars.discard(target.id)

                if inferred_type is not None:
                    current_types[target.id] = inferred_type
                else:
                    current_types.pop(target.id, None)

    def visit_Call(self, node: ast.Call) -> None:
        raw_name = _extract_dotted(node.func)
        if raw_name:
            resolved = self._resolve_call_name(raw_name)
            dst_id, scope = self._classify_target(resolved)
            self.edges.append(
                EdgeRecord(
                    src_id=self.current_symbol_id,
                    dst_id=dst_id,
                    kind="CALLS",
                    target_scope=scope,
                )
            )
            self._check_sensitive_sink(node, resolved)

        self.generic_visit(node)

    def _resolve_call_name(self, raw_name: str) -> str:
        parts = raw_name.split(".")
        head = parts[0]
        rest = ".".join(parts[1:])
        if head == "self" and len(self.scope_stack) >= 2 and len(parts) >= 2:
            prefix = f"{self.module_name}." if self.module_name else ""
            return f"{prefix}{self.scope_stack[0]}.{rest}"
        if head in self.local_types_stack[-1]:
            base_type = self.local_types_stack[-1][head]
            return f"{base_type}.{rest}" if rest else base_type
        if head in self.alias_map:
            mapped = self.alias_map[head]
            return f"{mapped}.{rest}" if rest else mapped
        if head in self.top_level_symbols and self.module_name:
            local_sym = f"{self.module_name}.{head}"
            return f"{local_sym}.{rest}" if rest else local_sym
        return raw_name

    def _check_sensitive_sink(self, node: ast.Call, resolved_name: str) -> None:
        if resolved_name in SENSITIVE_SINKS:
            rule_id, severity, desc = SENSITIVE_SINKS[resolved_name]
            if resolved_name == "yaml.load" and any(
                kw.arg == "Loader" and "Safe" in ast.unparse(kw.value)
                for kw in node.keywords
            ):
                return
            self.findings.append(
                FindingRecord(
                    file_path=self.rel_path,
                    symbol_id=self.current_symbol_id,
                    tool="codeoverlook-ast",
                    rule_id=rule_id,
                    severity=severity,
                    category="SINK",
                    line=node.lineno,
                    message=desc,
                )
            )

        if resolved_name.endswith(".execute") and node.args:
            first_arg = node.args[0]
            is_dynamic_sql = _is_dynamic_sql_expr(first_arg) or (
                isinstance(first_arg, ast.Name)
                and first_arg.id in self.dynamic_vars_stack[-1]
            )
            if is_dynamic_sql:
                self.findings.append(
                    FindingRecord(
                        file_path=self.rel_path,
                        symbol_id=self.current_symbol_id,
                        tool="codeoverlook-ast",
                        rule_id="SINK-SQL-01",
                        severity="HIGH",
                        category="SINK",
                        line=node.lineno,
                        message=(
                            "Dynamic SQL constructed inside .execute() "
                            "(potential SQL injection risk)"
                        ),
                    )
                )
