"""Reference extractor for import resolution."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..constants import JS_PATTERNS, PYTHON_PATTERNS
from ..models import ImportReference
from .ast_utils import find_imports as _ast_find_imports
from .ast_utils import safe_parse
from .base import BaseExtractor

# TypeScript/JavaScript extensions to try when resolving bare imports
_JS_EXTENSIONS = (
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".d.ts",
)

# Index file basenames to try when a path resolves to a directory
_JS_INDEX_NAMES = tuple(f"index{ext}" for ext in _JS_EXTENSIONS[:6])


class ReferenceExtractor(BaseExtractor):
    """Extract and resolve import references from code."""

    # JavaScript import patterns
    JS_IMPORT_PATTERNS = [
        # ES6 imports
        re.compile(
            r"import\s+(?:{[^}]+}|\*\s+as\s+\w+|\w+)?\s*(?:,\s*{[^}]+})?\s*from\s+['\"]([^'\"]+)['\"]"
        ),
        # CommonJS require
        re.compile(
            r"(?:const|let|var)\s+(?:{[^}]+}|\w+)\s*=\s*require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
        ),
        # Dynamic import
        re.compile(r"import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"),
    ]

    def __init__(self, project_path: str | Path) -> None:
        """Initialize the reference extractor.

        Args:
            project_path: Path to the project directory.
        """
        super().__init__(project_path)
        self._internal_modules: set[str] = set()
        # Workspace package names (e.g. {"@paynless/store", "@paynless/types"})
        self._workspace_packages: dict[str, Path] = {}
        # tsconfig path aliases: mapping from pattern prefix to list of
        # physical directory prefixes (relative to project root).
        # E.g. {"@paynless/store": ["packages/store/src/index.ts"]}
        self._ts_path_aliases: dict[str, list[str]] = {}

    def extract_nodes(self) -> list:
        """Not used for reference extraction."""
        return []

    def extract_edges(self, nodes: list) -> list:
        """Not used for reference extraction."""
        return []

    def extract_references(self) -> list[ImportReference]:
        """Extract all import references from the project.

        Returns:
            List of ImportReference objects.
        """
        # First, collect all internal module names
        self._collect_internal_modules()
        # Discover workspace packages and tsconfig path aliases
        self._discover_workspace_packages()
        self._discover_tsconfig_paths()

        references: list[ImportReference] = []

        # Process Python files
        for py_file in self.find_files(PYTHON_PATTERNS):
            content = self.read_file(py_file)
            if content:
                refs = self._extract_python_refs(py_file, content)
                references.extend(refs)

        # Process JavaScript files
        for js_file in self.find_files(JS_PATTERNS):
            content = self.read_file(js_file)
            if content:
                refs = self._extract_js_refs(js_file, content)
                references.extend(refs)

        return references

    # ------------------------------------------------------------------
    # Workspace / tsconfig discovery
    # ------------------------------------------------------------------

    def _discover_workspace_packages(self) -> None:
        """Discover monorepo workspace packages.

        Reads the root ``package.json`` for ``workspaces`` globs and checks
        ``pnpm-workspace.yaml`` for ``packages`` globs.  For each matched
        subdirectory that contains a ``package.json`` with a ``name`` field,
        records the mapping from package name to directory path.
        """
        workspace_dirs: list[Path] = []

        # 1. pnpm-workspace.yaml
        pnpm_ws = self.project_path / "pnpm-workspace.yaml"
        if pnpm_ws.is_file():
            workspace_dirs.extend(self._parse_pnpm_workspace(pnpm_ws))

        # 2. package.json workspaces field
        root_pkg = self.project_path / "package.json"
        if root_pkg.is_file():
            workspace_dirs.extend(self._parse_npm_workspaces(root_pkg))

        # 3. Resolve globs into actual directories
        seen: set[Path] = set()
        for ws_dir in workspace_dirs:
            if ws_dir in seen:
                continue
            seen.add(ws_dir)
            pkg_json = ws_dir / "package.json"
            if pkg_json.is_file():
                try:
                    data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                    name = data.get("name", "")
                    if name:
                        self._workspace_packages[name] = ws_dir
                except (json.JSONDecodeError, OSError):
                    pass

    def _parse_pnpm_workspace(self, path: Path) -> list[Path]:
        """Parse pnpm-workspace.yaml for workspace directory globs.

        Uses a minimal parser (no PyYAML dependency).
        """
        dirs: list[Path] = []
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return dirs

        in_packages = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("packages:"):
                in_packages = True
                continue
            if in_packages:
                if stripped.startswith("-"):
                    # Extract the glob value
                    value = stripped.lstrip("- ").strip("'\"")
                    if value.startswith("!"):
                        continue  # exclusion pattern
                    dirs.extend(self._expand_workspace_glob(value))
                elif stripped and not stripped.startswith("#"):
                    # New top-level key
                    in_packages = False
        return dirs

    def _parse_npm_workspaces(self, pkg_json_path: Path) -> list[Path]:
        """Parse ``package.json`` ``workspaces`` field for directory globs."""
        dirs: list[Path] = []
        try:
            data = json.loads(pkg_json_path.read_text(encoding="utf-8", errors="ignore"))
        except (json.JSONDecodeError, OSError):
            return dirs

        workspaces = data.get("workspaces", [])
        # workspaces can be a list or an object with "packages" key
        if isinstance(workspaces, dict):
            workspaces = workspaces.get("packages", [])
        if not isinstance(workspaces, list):
            return dirs

        for pattern in workspaces:
            if isinstance(pattern, str) and not pattern.startswith("!"):
                dirs.extend(self._expand_workspace_glob(pattern))
        return dirs

    def _expand_workspace_glob(self, pattern: str) -> list[Path]:
        """Expand a workspace glob like ``packages/*`` into directories."""
        dirs: list[Path] = []
        # Handle simple trailing /* glob
        if pattern.endswith("/*"):
            parent = self.project_path / pattern[:-2]
            if parent.is_dir():
                for child in sorted(parent.iterdir()):
                    if child.is_dir() and not child.name.startswith("."):
                        dirs.append(child)
        else:
            # Try as a literal directory
            literal = self.project_path / pattern
            if literal.is_dir():
                dirs.append(literal)
        return dirs

    def _discover_tsconfig_paths(self) -> None:
        """Discover tsconfig.json ``compilerOptions.paths`` from all tsconfigs.

        Reads tsconfig.json files (root + subdirectories) for path aliases.
        """
        tsconfig_files = list(self.project_path.rglob("tsconfig.json"))
        tsconfig_files += list(self.project_path.rglob("tsconfig.app.json"))
        tsconfig_files += list(self.project_path.rglob("tsconfig.base.json"))

        for tsconfig_path in tsconfig_files:
            # Skip node_modules
            if "node_modules" in tsconfig_path.parts:
                continue
            self._read_tsconfig_paths(tsconfig_path)

    def _read_tsconfig_paths(self, tsconfig_path: Path) -> None:
        """Read ``compilerOptions.paths`` from a single tsconfig file.

        Resolves the paths relative to the tsconfig's ``baseUrl`` (default ".").
        """
        try:
            # Strip JS-style comments for JSON parsing
            raw = tsconfig_path.read_text(encoding="utf-8", errors="ignore")
            raw = re.sub(r"//.*$", "", raw, flags=re.MULTILINE)
            raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError):
            return

        compiler_opts = data.get("compilerOptions", {})
        paths = compiler_opts.get("paths", {})
        base_url = compiler_opts.get("baseUrl", ".")

        tsconfig_dir = tsconfig_path.parent
        base_dir = (tsconfig_dir / base_url).resolve()

        for alias_pattern, target_patterns in paths.items():
            if not isinstance(target_patterns, list):
                continue
            # Strip trailing /* from wildcard aliases (e.g. "@paynless/*" -> "@paynless/")
            alias_key = alias_pattern.rstrip("*").rstrip("/")
            for target in target_patterns:
                if not isinstance(target, str):
                    continue
                # Resolve the target relative to baseUrl
                target_clean = target.rstrip("*").rstrip("/")
                resolved = base_dir / target_clean
                try:
                    rel = str(resolved.resolve().relative_to(self.project_path.resolve()))
                except ValueError:
                    continue
                if alias_key not in self._ts_path_aliases:
                    self._ts_path_aliases[alias_key] = []
                if rel not in self._ts_path_aliases[alias_key]:
                    self._ts_path_aliases[alias_key].append(rel)

    # ------------------------------------------------------------------
    # Internal module collection
    # ------------------------------------------------------------------

    def _collect_internal_modules(self) -> None:
        """Collect names of all internal modules."""
        # Python modules
        for py_file in self.find_files(PYTHON_PATTERNS):
            module_name = self._python_path_to_module(py_file)
            self._internal_modules.add(module_name)
            # Also add parent packages
            parts = module_name.split(".")
            for i in range(1, len(parts)):
                self._internal_modules.add(".".join(parts[:i]))

        # JavaScript modules
        for js_file in self.find_files(JS_PATTERNS):
            module_name = self._js_path_to_module(js_file)
            self._internal_modules.add(module_name)

    def _python_path_to_module(self, file_path: Path) -> str:
        """Convert Python file path to module name.

        Args:
            file_path: Path to the Python file.

        Returns:
            Module name.
        """
        try:
            rel_path = file_path.relative_to(self.project_path)
        except ValueError:
            rel_path = file_path

        parts = list(rel_path.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1].replace(".py", "").replace(".pyi", "")

        return ".".join(parts)

    def _js_path_to_module(self, file_path: Path) -> str:
        """Convert JavaScript file path to module name.

        Args:
            file_path: Path to the JavaScript file.

        Returns:
            Module name.
        """
        try:
            rel_path = file_path.relative_to(self.project_path)
        except ValueError:
            rel_path = file_path

        name = str(rel_path)
        # Remove extension
        for ext in [".tsx", ".ts", ".jsx", ".js", ".mjs", ".cjs"]:
            if name.endswith(ext):
                name = name[: -len(ext)]
                break
        # Handle index files
        if name.endswith("/index"):
            name = name[:-6]

        return name

    # ------------------------------------------------------------------
    # Python reference extraction (unchanged)
    # ------------------------------------------------------------------

    def _extract_python_refs(
        self, file_path: Path, content: str
    ) -> list[ImportReference]:
        """Extract import references from Python code.

        Delegates AST walking to shared ``ast_utils.find_imports``.

        Args:
            file_path: Path to the Python file.
            content: File content.

        Returns:
            List of ImportReference objects.
        """
        references: list[ImportReference] = []

        tree = safe_parse(content)
        if tree is None:
            return references

        for imp in _ast_find_imports(tree):
            module_name = imp.module
            if not module_name and imp.level > 0:
                # Relative import with no module (``from . import X``)
                module_name = "." * imp.level
            if not module_name:
                continue

            is_internal = self._is_internal_python_module(module_name)

            if imp.is_from:
                for name in imp.names:
                    references.append(
                        ImportReference(
                            file_path=self.relative_path(file_path),
                            line_number=imp.lineno,
                            module=module_name,
                            name=name,
                            is_internal=is_internal,
                            resolved=self._is_python_resolved(
                                module_name, is_internal
                            ),
                        )
                    )
            else:
                references.append(
                    ImportReference(
                        file_path=self.relative_path(file_path),
                        line_number=imp.lineno,
                        module=module_name,
                        name=imp.names[0] if imp.names else None,
                        is_internal=is_internal,
                        resolved=self._is_python_resolved(module_name, is_internal),
                    )
                )

        return references

    # ------------------------------------------------------------------
    # JS/TS reference extraction
    # ------------------------------------------------------------------

    def _extract_js_refs(
        self, file_path: Path, content: str
    ) -> list[ImportReference]:
        """Extract import references from JavaScript code.

        Args:
            file_path: Path to the JavaScript file.
            content: File content.

        Returns:
            List of ImportReference objects.
        """
        references: list[ImportReference] = []

        for pattern in self.JS_IMPORT_PATTERNS:
            for match in pattern.finditer(content):
                import_path = match.group(1)
                line_num = content[: match.start()].count("\n") + 1

                is_internal = self._is_js_internal(import_path)
                resolved = self._is_js_resolved(import_path, file_path, is_internal)

                references.append(
                    ImportReference(
                        file_path=self.relative_path(file_path),
                        line_number=line_num,
                        module=import_path,
                        is_internal=is_internal,
                        resolved=resolved,
                    )
                )

        return references

    def _is_js_internal(self, import_path: str) -> bool:
        """Determine if a JS/TS import path is internal.

        An import is internal if:
        - It starts with ``.`` (relative import)
        - It matches a workspace package name (e.g. ``@paynless/store``)
        - It matches a tsconfig path alias prefix

        Args:
            import_path: The raw import specifier string.

        Returns:
            True if the import is internal.
        """
        # 1. Relative imports are always internal
        if import_path.startswith("."):
            return True

        # 2. Workspace package match
        # For "@scope/pkg/sub/path", the package name is "@scope/pkg"
        pkg_name = self._extract_npm_package_name(import_path)
        if pkg_name in self._workspace_packages:
            return True

        # 3. tsconfig path alias match
        if self._match_ts_path_alias(import_path) is not None:
            return True

        return False

    def _extract_npm_package_name(self, import_path: str) -> str:
        """Extract the npm package name from an import path.

        ``@scope/pkg/foo/bar`` -> ``@scope/pkg``
        ``lodash/fp`` -> ``lodash``
        """
        if import_path.startswith("@"):
            parts = import_path.split("/")
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
            return import_path
        return import_path.split("/")[0]

    def _match_ts_path_alias(self, import_path: str) -> str | None:
        """Match an import path against tsconfig path aliases.

        Returns the resolved filesystem path prefix if matched, else None.
        """
        # Try exact match first, then prefix match
        for alias_prefix, targets in self._ts_path_aliases.items():
            if import_path == alias_prefix or import_path.startswith(alias_prefix + "/"):
                if targets:
                    # Return the first target
                    suffix = import_path[len(alias_prefix):].lstrip("/")
                    return targets[0] + ("/" + suffix if suffix else "")
        return None

    # ------------------------------------------------------------------
    # JS/TS resolution
    # ------------------------------------------------------------------

    def _is_js_resolved(
        self, import_path: str, from_file: Path, is_internal: bool
    ) -> bool:
        """Check if a JavaScript import is resolved.

        Handles:
        - Relative imports with TypeScript extension inference
        - Workspace package imports
        - tsconfig path alias imports

        Args:
            import_path: Import path.
            from_file: File containing the import.
            is_internal: Whether it's an internal import.

        Returns:
            True if the import is resolved.
        """
        if not is_internal:
            # External modules - assume resolved (will be checked by registry)
            return True

        # 1. Try workspace package resolution
        pkg_name = self._extract_npm_package_name(import_path)
        if pkg_name in self._workspace_packages:
            return self._resolve_workspace_import(import_path, pkg_name)

        # 2. Try tsconfig path alias resolution
        alias_resolved = self._match_ts_path_alias(import_path)
        if alias_resolved is not None:
            return self._resolve_module_name(alias_resolved)

        # 3. Relative import resolution
        return self._resolve_relative_js_import(import_path, from_file)

    def _resolve_workspace_import(self, import_path: str, pkg_name: str) -> bool:
        """Resolve an import to a workspace package.

        For ``@paynless/store``, checks if the package directory has source files
        registered as internal modules.
        """
        pkg_dir = self._workspace_packages.get(pkg_name)
        if pkg_dir is None:
            return False

        try:
            pkg_rel = str(pkg_dir.relative_to(self.project_path))
        except ValueError:
            return False

        # Get the sub-path within the package (e.g. "@paynless/api/mocks" -> "mocks")
        suffix = import_path[len(pkg_name):].lstrip("/")

        # Try to find the module in internal modules
        # The package might export from src/index.ts, so try several candidates
        candidates = []
        if suffix:
            # Import like @paynless/api/mocks
            candidates.append(f"{pkg_rel}/src/{suffix}")
            candidates.append(f"{pkg_rel}/{suffix}")
        else:
            # Bare package import like @paynless/store
            candidates.append(f"{pkg_rel}/src")
            candidates.append(f"{pkg_rel}/src/index")
            candidates.append(pkg_rel)

        for candidate in candidates:
            if self._resolve_module_name(candidate):
                return True

        return False

    def _resolve_relative_js_import(self, import_path: str, from_file: Path) -> bool:
        """Resolve a relative JS/TS import (starting with . or ..).

        Tries TypeScript extension inference and index file resolution.
        """
        from_dir = from_file.parent

        # Strip leading ./
        path = import_path
        if path.startswith("./"):
            path = path[2:]
        elif path.startswith("../"):
            parts = path.split("/")
            up_count = 0
            while parts and parts[0] == "..":
                up_count += 1
                parts.pop(0)
            for _ in range(up_count):
                from_dir = from_dir.parent
            path = "/".join(parts)

        # Compute the resolved absolute path then get relative to project
        try:
            resolved = from_dir / path
            resolved = resolved.relative_to(self.project_path)
            module_name = str(resolved)
        except ValueError:
            return False

        return self._resolve_module_name(module_name)

    def _resolve_module_name(self, module_name: str) -> bool:
        """Try to resolve a module name against internal modules.

        Tries the name as-is, then with TS/JS extensions stripped, then with
        extensions appended, and finally with /index variants.

        Args:
            module_name: A project-relative path (without extension).

        Returns:
            True if a matching internal module is found.
        """
        # 1. Exact match
        if module_name in self._internal_modules:
            return True

        # 2. If the import includes an explicit extension, strip it and retry
        stripped = self._strip_js_extension(module_name)
        if stripped != module_name and stripped in self._internal_modules:
            return True

        # 3. Try appending extensions (for extensionless imports)
        base = stripped  # use the stripped version as the base
        for ext_suffix in ("", "/index"):
            candidate = base + ext_suffix
            if candidate in self._internal_modules:
                return True

        # 4. Check if any internal module is a child path (directory match)
        # This handles cases like importing a directory that has an index file
        prefix = base + "/"
        for internal in self._internal_modules:
            if internal.startswith(prefix):
                return True

        return False

    @staticmethod
    def _strip_js_extension(name: str) -> str:
        """Strip a JS/TS extension from a module path if present.

        Handles ``.d.ts`` as well as simple extensions.
        """
        if name.endswith(".d.ts"):
            return name[:-5]
        for ext in (".tsx", ".ts", ".jsx", ".js", ".mjs", ".cjs"):
            if name.endswith(ext):
                return name[: -len(ext)]
        return name

    # ------------------------------------------------------------------
    # Python helpers (unchanged)
    # ------------------------------------------------------------------

    def _is_internal_python_module(self, module_name: str) -> bool:
        """Check if a Python module is internal.

        Args:
            module_name: Name of the module.

        Returns:
            True if the module is internal.
        """
        # Check if it's in our internal modules
        if module_name in self._internal_modules:
            return True

        # Check if any internal module starts with this name
        for internal in self._internal_modules:
            if internal.startswith(module_name + "."):
                return True
            if module_name.startswith(internal + "."):
                return True

        return False

    def _is_python_resolved(self, module_name: str, is_internal: bool) -> bool:
        """Check if a Python import is resolved.

        Args:
            module_name: Name of the module.
            is_internal: Whether it's an internal module.

        Returns:
            True if the import is resolved.
        """
        if is_internal:
            # Check if the module exists in our project
            return module_name in self._internal_modules or any(
                internal.startswith(module_name + ".")
                for internal in self._internal_modules
            )
        else:
            # External modules - assume resolved (will be checked by registry)
            return True

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_unresolved_internal_refs(self) -> list[ImportReference]:
        """Get all unresolved internal references.

        Returns:
            List of unresolved ImportReference objects.
        """
        all_refs = self.extract_references()
        return [ref for ref in all_refs if ref.is_internal and not ref.resolved]

    def get_external_packages(self) -> list[tuple[str, str]]:
        """Get all external package references.

        Returns:
            List of (package_name, ecosystem) tuples.
        """
        all_refs = self.extract_references()
        packages: set[tuple[str, str]] = set()

        for ref in all_refs:
            if not ref.is_internal:
                # Get the top-level package name
                if "/" in ref.module:
                    # Scoped npm package or path
                    if ref.module.startswith("@"):
                        # @scope/package
                        parts = ref.module.split("/")
                        if len(parts) >= 2:
                            package = f"{parts[0]}/{parts[1]}"
                    else:
                        package = ref.module.split("/")[0]
                else:
                    package = ref.module.split(".")[0]

                # Determine ecosystem
                if ref.file_path.endswith((".py", ".pyi")):
                    packages.add((package, "pypi"))
                elif ref.file_path.endswith(
                    (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
                ):
                    packages.add((package, "npm"))

        return list(packages)
