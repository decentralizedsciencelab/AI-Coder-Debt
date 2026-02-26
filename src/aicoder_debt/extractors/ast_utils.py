"""
Shared AST utilities for Python code analysis.
================================================

Provides standalone functions that extract structural information from
Python AST trees.  Used by both the ``src/aicoder_debt/extractors``
classes (PythonExtractor, ReferenceExtractor, InterfaceExtractor) and
the ``pipeline/`` batch extractors (APS, SID).

Only stdlib ``ast`` + ``re`` — no new dependencies.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ImportInfo:
    """Represents a single import statement."""
    module: str          # e.g. "os.path" or "flask"
    names: list[str] = field(default_factory=list)  # imported names
    is_from: bool = False
    level: int = 0       # relative import level (0 = absolute)
    lineno: int = 0


@dataclass
class CallInfo:
    """Represents a function/method call."""
    func_name: str       # e.g. "requests.get", "create_engine"
    lineno: int = 0
    args_count: int = 0


@dataclass
class RouteInfo:
    """Represents a Flask/FastAPI route decorator."""
    path: str            # e.g. "/api/users"
    methods: list[str] = field(default_factory=list)
    decorator_name: str = ""
    lineno: int = 0


@dataclass
class EnvAccess:
    """Represents an environment variable access."""
    key: Optional[str]   # env var name if extractable, else None
    access_type: str     # "environ_subscript", "environ_get", "getenv"
    lineno: int = 0


@dataclass
class ClassInfo:
    """Represents a class definition."""
    name: str
    has_body: bool = False
    bases: list[str] = field(default_factory=list)
    lineno: int = 0


# ---------------------------------------------------------------------------
# Core parsing  (mirrors PythonExtractor's ast.parse try/except pattern)
# ---------------------------------------------------------------------------

def safe_parse(code: str) -> Optional[ast.Module]:
    """Try to parse Python code, returning None on any failure.

    Same guarding pattern as ``PythonExtractor.extract_nodes`` but
    usable on raw strings without a project directory.
    """
    try:
        return ast.parse(code)
    except (SyntaxError, ValueError, TypeError, RecursionError, MemoryError):
        return None


def safe_parse_sections(text: str) -> list[tuple[str, ast.Module]]:
    """Parse markdown-fenced code blocks, returning (code, tree) pairs.

    Skips non-Python fences and blocks that fail to parse.
    """
    results: list[tuple[str, ast.Module]] = []
    pattern = re.compile(r"```(\w*)\s*\n(.*?)```", re.DOTALL)
    for m in pattern.finditer(text):
        lang = m.group(1).lower()
        code = m.group(2)
        if lang and lang not in ("python", "py", "python3", ""):
            continue
        tree = safe_parse(code)
        if tree is not None:
            results.append((code, tree))

    if not results:
        tree = safe_parse(text)
        if tree is not None:
            results.append((text, tree))

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_call_name(node: ast.expr) -> str:
    """Resolve a call's func node to a dotted name string.

    ``os.environ.get(...)`` → ``"os.environ.get"``
    ``requests.get(...)``   → ``"requests.get"``
    ``create_engine(...)``  → ``"create_engine"``
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value_name = _resolve_call_name(node.value)
        if value_name:
            return f"{value_name}.{node.attr}"
        return node.attr
    if isinstance(node, ast.Subscript):
        return _resolve_call_name(node.value)
    return ""


def _resolve_decorator_name(node: ast.expr) -> str:
    """Resolve a decorator expression (ignoring call args)."""
    if isinstance(node, ast.Call):
        return _resolve_call_name(node.func)
    return _resolve_call_name(node)


def _get_string_value(node: ast.expr) -> Optional[str]:
    """Extract a constant string value from an AST node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


# ---------------------------------------------------------------------------
# Import analysis  (generalises PythonExtractor._get_imports and
#                    ReferenceExtractor._extract_python_refs)
# ---------------------------------------------------------------------------

def find_imports(tree: ast.Module) -> list[ImportInfo]:
    """Extract all Import and ImportFrom nodes from an AST."""
    imports: list[ImportInfo] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportInfo(
                    module=alias.name,
                    names=[alias.asname or alias.name],
                    is_from=False,
                    level=0,
                    lineno=node.lineno,
                ))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = [alias.name for alias in node.names]
            imports.append(ImportInfo(
                module=module,
                names=names,
                is_from=True,
                level=node.level or 0,
                lineno=node.lineno,
            ))
    return imports


def has_import(tree: ast.Module, module: str) -> bool:
    """Check if *module* (or a submodule) is imported."""
    module_lower = module.lower()
    for imp in find_imports(tree):
        if imp.module.lower() == module_lower:
            return True
        if imp.module.lower().startswith(module_lower + "."):
            return True
        if module_lower in [n.lower() for n in imp.names]:
            return True
    return False


# ---------------------------------------------------------------------------
# Function-call analysis  (generalises PythonExtractor.CONNECTION_PATTERNS
#                          from regex to AST-based matching)
# ---------------------------------------------------------------------------

def find_function_calls(tree: ast.Module, func_names: list[str]) -> list[CallInfo]:
    """Find calls matching any of *func_names* (case-insensitive).

    Supports exact and prefix matching:
        ``"requests.get"`` matches ``requests.get(...)``
        ``"requests"``     matches ``requests.get(...)``
    """
    results: list[CallInfo] = []
    func_names_lower = [n.lower() for n in func_names]

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        resolved = _resolve_call_name(node.func).lower()
        if not resolved:
            continue
        for fn in func_names_lower:
            if resolved == fn or resolved.startswith(fn + "."):
                results.append(CallInfo(
                    func_name=resolved,
                    lineno=getattr(node, "lineno", 0),
                    args_count=len(node.args) + len(node.keywords),
                ))
                break
    return results


def has_call(tree: ast.Module, func_name: str) -> bool:
    """Shorthand: check if a matching function call exists."""
    return len(find_function_calls(tree, [func_name])) > 0


# ---------------------------------------------------------------------------
# Decorator / route analysis  (generalises InterfaceExtractor's
#                              PYTHON_ENDPOINT_PATTERNS from regex to AST)
# ---------------------------------------------------------------------------

_HTTP_METHODS = frozenset({
    "get", "post", "put", "delete", "patch", "options", "head", "api_route",
})


def find_decorator_routes(tree: ast.Module) -> list[RouteInfo]:
    """Extract Flask/FastAPI route definitions from decorators."""
    routes: list[RouteInfo] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            deco_name = _resolve_decorator_name(deco)
            if not deco_name:
                continue
            parts = deco_name.split(".")
            if len(parts) < 2:
                continue
            method_part = parts[-1].lower()

            if method_part == "route":
                if isinstance(deco, ast.Call) and deco.args:
                    path = _get_string_value(deco.args[0])
                    methods = ["GET"]
                    for kw in deco.keywords:
                        if kw.arg == "methods" and isinstance(kw.value, ast.List):
                            methods = []
                            for elt in kw.value.elts:
                                s = _get_string_value(elt)
                                if s:
                                    methods.append(s.upper())
                    routes.append(RouteInfo(
                        path=path or "",
                        methods=methods or ["GET"],
                        decorator_name=deco_name,
                        lineno=node.lineno,
                    ))

            elif method_part in _HTTP_METHODS:
                path = ""
                if isinstance(deco, ast.Call) and deco.args:
                    path = _get_string_value(deco.args[0]) or ""
                routes.append(RouteInfo(
                    path=path,
                    methods=[method_part.upper()] if method_part != "api_route" else ["GET"],
                    decorator_name=deco_name,
                    lineno=node.lineno,
                ))

            elif deco_name == "api_view" or method_part == "api_view":
                methods = ["GET"]
                if isinstance(deco, ast.Call) and deco.args:
                    if isinstance(deco.args[0], ast.List):
                        methods = []
                        for elt in deco.args[0].elts:
                            s = _get_string_value(elt)
                            if s:
                                methods.append(s.upper())
                routes.append(RouteInfo(
                    path="",
                    methods=methods,
                    decorator_name=deco_name,
                    lineno=node.lineno,
                ))

    return routes


def has_decorator(tree: ast.Module, pattern: str) -> bool:
    """Check if any function/class has a decorator matching *pattern*."""
    pattern_lower = pattern.lower()
    regex_pat = re.compile(
        "^" + re.escape(pattern_lower).replace(r"\*", ".*") + "$"
    )
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for deco in node.decorator_list:
                deco_name = _resolve_decorator_name(deco)
                if deco_name and regex_pat.match(deco_name.lower()):
                    return True
    return False


# ---------------------------------------------------------------------------
# Environment-variable access  (generalises ConfigExtractor's
#                               PYTHON_CONFIG_PATTERNS from regex to AST)
# ---------------------------------------------------------------------------

def find_env_access(tree: ast.Module) -> list[EnvAccess]:
    """Find os.environ[], os.environ.get(), and os.getenv() references."""
    results: list[EnvAccess] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            value_name = _resolve_call_name(node.value)
            if value_name.lower() == "os.environ":
                key = None
                if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                    key = node.slice.value
                results.append(EnvAccess(
                    key=key,
                    access_type="environ_subscript",
                    lineno=getattr(node, "lineno", 0),
                ))

        elif isinstance(node, ast.Call):
            func_name = _resolve_call_name(node.func).lower()
            if func_name == "os.environ.get":
                key = None
                if node.args:
                    key = _get_string_value(node.args[0])
                results.append(EnvAccess(
                    key=key,
                    access_type="environ_get",
                    lineno=getattr(node, "lineno", 0),
                ))
            elif func_name == "os.getenv":
                key = None
                if node.args:
                    key = _get_string_value(node.args[0])
                results.append(EnvAccess(
                    key=key,
                    access_type="getenv",
                    lineno=getattr(node, "lineno", 0),
                ))

    return results


# ---------------------------------------------------------------------------
# Class definitions
# ---------------------------------------------------------------------------

def find_class_definitions(tree: ast.Module, pattern: str) -> list[ClassInfo]:
    """Find class definitions whose name matches *pattern* (regex)."""
    regex = re.compile(pattern, re.IGNORECASE)
    results: list[ClassInfo] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not regex.search(node.name):
            continue

        has_body = False
        for stmt in node.body:
            if isinstance(stmt, ast.Pass):
                continue
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                continue
            has_body = True
            break

        bases = []
        for base in node.bases:
            base_name = _resolve_call_name(base)
            if base_name:
                bases.append(base_name)

        results.append(ClassInfo(
            name=node.name,
            has_body=has_body,
            bases=bases,
            lineno=node.lineno,
        ))

    return results


# ---------------------------------------------------------------------------
# Framework app detection  (used by SID extractor for component detection)
# ---------------------------------------------------------------------------

def find_framework_apps(tree: ast.Module) -> list[tuple[str, str]]:
    """Detect ``app = Flask(...)`` / ``app = FastAPI(...)`` assignments.

    Returns list of (variable_name, framework) tuples.
    """
    results: list[tuple[str, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Call):
            continue

        call_name = _resolve_call_name(node.value.func)
        framework = None
        if call_name in ("Flask", "flask.Flask"):
            framework = "flask"
        elif call_name in ("FastAPI", "fastapi.FastAPI"):
            framework = "fastapi"
        elif call_name in ("Starlette", "starlette.Starlette"):
            framework = "starlette"

        if framework:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    results.append((target.id, framework))

    return results
