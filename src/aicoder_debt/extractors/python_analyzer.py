"""Python AST analyzer for DDG extraction."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from ..constants import PYTHON_PATTERNS, Confidence, EdgeType
from ..models import DDGEdge, DDGNode
from .ast_utils import find_imports as _ast_find_imports
from .ast_utils import safe_parse
from .base import BaseExtractor


class PythonExtractor(BaseExtractor):
    """Extract DDG nodes and edges from Python code using AST."""

    # Connection patterns for detecting dependencies
    CONNECTION_PATTERNS = {
        # Database connections
        "sqlalchemy": re.compile(r"create_engine\s*\(|sessionmaker\s*\("),
        "psycopg2": re.compile(r"psycopg2\.connect\s*\("),
        "pymongo": re.compile(r"MongoClient\s*\("),
        "redis": re.compile(r"Redis\s*\(|StrictRedis\s*\("),
        # HTTP clients
        "requests": re.compile(r"requests\.(get|post|put|delete|patch)\s*\("),
        "httpx": re.compile(r"httpx\.(get|post|put|delete|patch|AsyncClient)\s*\("),
        "aiohttp": re.compile(r"aiohttp\.ClientSession\s*\("),
        # Message queues
        "pika": re.compile(r"pika\.BlockingConnection\s*\("),
        "celery": re.compile(r"Celery\s*\("),
        "kafka": re.compile(r"KafkaProducer\s*\(|KafkaConsumer\s*\("),
    }

    def __init__(self, project_path: str | Path) -> None:
        """Initialize the Python extractor.

        Args:
            project_path: Path to the project directory.
        """
        super().__init__(project_path)
        self._modules: dict[str, dict] = {}
        self._py_files: list[Path] = []

    def extract_nodes(self) -> list[DDGNode]:
        """Extract component nodes from Python files.

        Returns:
            List of DDGNode objects representing Python modules/classes.
        """
        self._py_files = self.find_files(PYTHON_PATTERNS)
        nodes: list[DDGNode] = []

        for py_file in self._py_files:
            content = self.read_file(py_file)
            if not content:
                continue

            tree = safe_parse(content)
            if tree is None:
                continue

            module_name = self._get_module_name(py_file)
            module_type = self._detect_module_type(content, tree)

            node = DDGNode(
                id=f"py:{module_name}",
                name=module_name,
                type=module_type,
                file_path=self.relative_path(py_file),
                metadata={
                    "classes": self._get_class_names(tree),
                    "functions": self._get_function_names(tree),
                    "imports": self._get_imports(tree),
                },
            )
            nodes.append(node)

            self._modules[module_name] = {
                "file": py_file,
                "content": content,
                "tree": tree,
                "type": module_type,
            }

        return nodes

    def extract_edges(self, nodes: list[DDGNode]) -> list[DDGEdge]:
        """Extract dependency edges from Python modules.

        Args:
            nodes: List of previously extracted nodes.

        Returns:
            List of DDGEdge objects representing dependencies.
        """
        edges: list[DDGEdge] = []
        node_ids = {node.id for node in nodes}
        module_to_id = {
            node.name: node.id for node in nodes if node.id.startswith("py:")
        }

        for module_name, module_info in self._modules.items():
            source_id = f"py:{module_name}"
            if source_id not in node_ids:
                continue

            tree = module_info["tree"]
            content = module_info["content"]
            file_path = module_info["file"]

            # Extract import edges
            edges.extend(
                self._extract_import_edges(
                    source_id,
                    tree,
                    module_to_id,
                    file_path,
                )
            )

            # Extract connection edges
            edges.extend(
                self._extract_connection_edges(
                    source_id,
                    content,
                    file_path,
                    nodes,
                )
            )

            # Extract class dependency edges
            edges.extend(
                self._extract_class_edges(
                    source_id,
                    tree,
                    module_to_id,
                    file_path,
                )
            )

        return edges

    def _get_module_name(self, file_path: Path) -> str:
        """Convert file path to module name.

        Args:
            file_path: Path to the Python file.

        Returns:
            Module name string.
        """
        try:
            rel_path = file_path.relative_to(self.project_path)
        except ValueError:
            rel_path = file_path

        # Convert path to module name
        parts = list(rel_path.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1].replace(".py", "").replace(".pyi", "")

        return ".".join(parts)

    def _detect_module_type(self, content: str, tree: ast.AST) -> str:
        """Detect the type of Python module.

        A module is typed by its PRIMARY role. Web frameworks and entry
        points take precedence over connection patterns: a Flask app that
        connects to redis is a "service", not a "cache".

        Args:
            content: File content.
            tree: AST tree.

        Returns:
            Module type string.
        """
        # Check for web framework patterns FIRST — a Flask/FastAPI app
        # that connects to redis is a service, not infrastructure.
        if "Flask" in content or "FastAPI" in content or "Django" in content:
            return "service"

        # Check for test files
        if "test_" in content or "pytest" in content:
            return "test"

        # Check for worker/task patterns (Celery workers, background tasks)
        if "celery" in content.lower() and (
            "@app.task" in content or "@celery.task" in content
            or "worker" in str(tree).lower()
        ):
            return "service"

        # Check for entry-point patterns (if __name__ == "__main__")
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                test = node.test
                if (isinstance(test, ast.Compare)
                    and isinstance(test.left, ast.Name)
                    and test.left.id == "__name__"):
                    return "service"

        # Check for worker loop patterns: "while True:" with queue
        # consumption (brpop, blpop, consume, get, recv) — this is a
        # background worker process, not infrastructure.
        for node in ast.walk(tree):
            if isinstance(node, ast.While):
                if isinstance(node.test, ast.Constant) and node.test.value is True:
                    return "service"

        # Only classify as infrastructure type if the module is purely
        # an infrastructure wrapper, not an application that USES infrastructure.
        # Since we've already checked for frameworks and entry points above,
        # remaining modules with connection patterns are likely utility/config.
        for lib_name, pattern in self.CONNECTION_PATTERNS.items():
            if pattern.search(content):
                if lib_name in ("sqlalchemy", "psycopg2", "pymongo"):
                    return "database"
                elif lib_name == "redis":
                    return "cache"
                elif lib_name in ("pika", "celery", "kafka"):
                    return "queue"
                elif lib_name in ("requests", "httpx", "aiohttp"):
                    return "client"

        return "module"

    def _get_class_names(self, tree: ast.AST) -> list[str]:
        """Get all class names in the module.

        Args:
            tree: AST tree.

        Returns:
            List of class names.
        """
        return [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]

    def _get_function_names(self, tree: ast.AST) -> list[str]:
        """Get top-level function names in the module.

        Args:
            tree: AST tree.

        Returns:
            List of function names.
        """
        return [
            node.name
            for node in ast.iter_child_nodes(tree)
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef)
        ]

    def _get_imports(self, tree: ast.AST) -> list[str]:
        """Get all imported modules.

        Delegates to shared ``ast_utils.find_imports`` and flattens to
        a plain list of module-name strings for backwards compatibility.

        Args:
            tree: AST tree.

        Returns:
            List of imported module names.
        """
        return [imp.module for imp in _ast_find_imports(tree) if imp.module]

    def _extract_import_edges(
        self,
        source_id: str,
        tree: ast.AST,
        module_to_id: dict[str, str],
        file_path: Path,
    ) -> list[DDGEdge]:
        """Extract edges from import statements.

        Args:
            source_id: Source node ID.
            tree: AST tree.
            module_to_id: Map of module names to node IDs.
            file_path: Path to the source file.

        Returns:
            List of DDGEdge objects.
        """
        edges: list[DDGEdge] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target_id = self._find_module_id(alias.name, module_to_id)
                    if target_id and target_id != source_id:
                        edges.append(
                            DDGEdge(
                                source=source_id,
                                target=target_id,
                                edge_type=EdgeType.RUNTIME,
                                confidence=Confidence.HIGH,
                                description=f"imports {alias.name}",
                                file_path=self.relative_path(file_path),
                                line_number=node.lineno,
                            )
                        )

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    target_id = self._find_module_id(node.module, module_to_id)
                    if target_id and target_id != source_id:
                        edges.append(
                            DDGEdge(
                                source=source_id,
                                target=target_id,
                                edge_type=EdgeType.RUNTIME,
                                confidence=Confidence.HIGH,
                                description=f"imports from {node.module}",
                                file_path=self.relative_path(file_path),
                                line_number=node.lineno,
                            )
                        )

        return edges

    def _find_module_id(
        self, import_name: str, module_to_id: dict[str, str]
    ) -> str | None:
        """Find the node ID for an imported module.

        Args:
            import_name: Name of the imported module.
            module_to_id: Map of module names to node IDs.

        Returns:
            Node ID or None if not found.
        """
        # Direct match
        if import_name in module_to_id:
            return module_to_id[import_name]

        # Try prefix matches for submodule imports
        for module_name, node_id in module_to_id.items():
            if import_name.startswith(module_name + "."):
                return node_id
            if module_name.startswith(import_name + "."):
                return node_id

        return None

    def _extract_connection_edges(
        self,
        source_id: str,
        content: str,
        file_path: Path,
        nodes: list[DDGNode],
    ) -> list[DDGEdge]:
        """Extract edges from connection patterns.

        Args:
            source_id: Source node ID.
            content: File content.
            file_path: Path to the source file.
            nodes: All nodes in the graph.

        Returns:
            List of DDGEdge objects.
        """
        edges: list[DDGEdge] = []

        # Find database/cache/queue nodes
        db_nodes = [n for n in nodes if n.type in ("database", "cache", "queue")]

        for lib_name, pattern in self.CONNECTION_PATTERNS.items():
            matches = list(pattern.finditer(content))
            if matches:
                # Find appropriate target based on library
                for db_node in db_nodes:
                    if self._matches_connection_type(lib_name, db_node):
                        for match in matches:
                            line_num = content[: match.start()].count("\n") + 1
                            edges.append(
                                DDGEdge(
                                    source=source_id,
                                    target=db_node.id,
                                    edge_type=EdgeType.STATE,
                                    confidence=Confidence.MEDIUM,
                                    description=f"connects to {db_node.name} via {lib_name}",
                                    file_path=self.relative_path(file_path),
                                    line_number=line_num,
                                )
                            )
                            break

        return edges

    def _matches_connection_type(self, lib_name: str, node: DDGNode) -> bool:
        """Check if a library matches a node's type AND name.

        Matching requires both:
        1. The node is infrastructure (not an application service)
        2. The node's name/id suggests it's the RIGHT infrastructure
           (e.g., redis connections target redis nodes, not postgres)

        Args:
            lib_name: Name of the library.
            node: Node to check.

        Returns:
            True if they match.
        """
        # Never target application nodes — only infrastructure
        if node.type in ("service", "api", "client", "module", "test"):
            return False

        # Must be infrastructure type
        if node.type not in ("database", "cache", "queue"):
            return False

        node_name = (node.id + " " + node.name).lower()

        # Match by library → expected infrastructure name patterns
        lib_to_names: dict[str, list[str]] = {
            "sqlalchemy": ["postgres", "mysql", "sqlite", "db", "database", "sql", "mariadb"],
            "psycopg2": ["postgres", "db", "database"],
            "pymongo": ["mongo", "db", "database"],
            "redis": ["redis", "cache"],
            "pika": ["rabbit", "amqp", "mq", "queue"],
            "celery": ["redis", "rabbit", "celery", "broker", "queue"],
            "kafka": ["kafka", "queue", "broker"],
        }

        expected_names = lib_to_names.get(lib_name, [])
        return any(name in node_name for name in expected_names)

    def _extract_class_edges(
        self,
        source_id: str,
        tree: ast.AST,
        module_to_id: dict[str, str],
        file_path: Path,
    ) -> list[DDGEdge]:
        """Extract edges from class definitions and usage.

        Args:
            source_id: Source node ID.
            tree: AST tree.
            module_to_id: Map of module names to node IDs.
            file_path: Path to the source file.

        Returns:
            List of DDGEdge objects.
        """
        edges: list[DDGEdge] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Check base classes
                for base in node.bases:
                    if isinstance(base, ast.Attribute):
                        # Check if module is imported
                        if isinstance(base.value, ast.Name):
                            module_name = base.value.id
                            target_id = self._find_module_id(module_name, module_to_id)
                            if target_id and target_id != source_id:
                                edges.append(
                                    DDGEdge(
                                        source=source_id,
                                        target=target_id,
                                        edge_type=EdgeType.STATE,
                                        confidence=Confidence.HIGH,
                                        description=f"class {node.name} inherits from {module_name}",
                                        file_path=self.relative_path(file_path),
                                        line_number=node.lineno,
                                    )
                                )

        return edges
