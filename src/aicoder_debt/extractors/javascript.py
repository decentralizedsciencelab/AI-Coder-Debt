"""JavaScript/TypeScript analyzer for DDG extraction."""

from __future__ import annotations

import re
from pathlib import Path

from ..constants import JS_PATTERNS, Confidence, EdgeType
from ..models import DDGEdge, DDGNode
from .base import BaseExtractor


class JavaScriptExtractor(BaseExtractor):
    """Extract DDG nodes and edges from JavaScript/TypeScript code."""

    # Import patterns
    ES6_IMPORT_PATTERN = re.compile(
        r"import\s+(?:{[^}]+}|\*\s+as\s+\w+|\w+)?\s*(?:,\s*{[^}]+})?\s*from\s+['\"]([^'\"]+)['\"]",
        re.MULTILINE,
    )
    REQUIRE_PATTERN = re.compile(
        r"(?:const|let|var)\s+(?:{[^}]+}|\w+)\s*=\s*require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
        re.MULTILINE,
    )
    DYNAMIC_IMPORT_PATTERN = re.compile(
        r"import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
    )

    # Export patterns
    EXPORT_DEFAULT_PATTERN = re.compile(
        r"export\s+default\s+(?:class|function|const|let|var)?\s*(\w+)?",
        re.MULTILINE,
    )
    EXPORT_NAMED_PATTERN = re.compile(
        r"export\s+(?:const|let|var|function|class)\s+(\w+)",
        re.MULTILINE,
    )

    # Class/Function patterns
    CLASS_PATTERN = re.compile(
        r"class\s+(\w+)(?:\s+extends\s+(\w+))?",
        re.MULTILINE,
    )
    FUNCTION_PATTERN = re.compile(
        r"(?:function|const|let|var)\s+(\w+)\s*(?:=\s*(?:async\s*)?\([^)]*\)\s*=>|\([^)]*\)\s*{)",
        re.MULTILINE,
    )

    # Connection patterns
    CONNECTION_PATTERNS = {
        "mongoose": re.compile(r"mongoose\.connect\s*\("),
        "mongodb": re.compile(r"MongoClient\.connect\s*\(|new\s+MongoClient\s*\("),
        "pg": re.compile(r"new\s+Pool\s*\(|new\s+Client\s*\("),
        "mysql": re.compile(r"mysql\.createConnection\s*\(|mysql\.createPool\s*\("),
        "redis": re.compile(r"redis\.createClient\s*\(|new\s+Redis\s*\("),
        "amqplib": re.compile(r"amqp\.connect\s*\("),
        "kafkajs": re.compile(r"new\s+Kafka\s*\("),
        "axios": re.compile(r"axios\.(get|post|put|delete|patch)\s*\(|axios\.create\s*\("),
        "fetch": re.compile(r"\bfetch\s*\("),
    }

    def __init__(self, project_path: str | Path) -> None:
        """Initialize the JavaScript extractor.

        Args:
            project_path: Path to the project directory.
        """
        super().__init__(project_path)
        self._modules: dict[str, dict] = {}
        self._js_files: list[Path] = []

    def extract_nodes(self) -> list[DDGNode]:
        """Extract component nodes from JavaScript/TypeScript files.

        Returns:
            List of DDGNode objects representing JS modules.
        """
        self._js_files = self.find_files(JS_PATTERNS)
        nodes: list[DDGNode] = []

        for js_file in self._js_files:
            content = self.read_file(js_file)
            if not content:
                continue

            module_name = self._get_module_name(js_file)
            module_type = self._detect_module_type(content)

            node = DDGNode(
                id=f"js:{module_name}",
                name=module_name,
                type=module_type,
                file_path=self.relative_path(js_file),
                metadata={
                    "classes": self._get_class_names(content),
                    "exports": self._get_exports(content),
                    "imports": self._get_imports(content),
                },
            )
            nodes.append(node)

            self._modules[module_name] = {
                "file": js_file,
                "content": content,
                "type": module_type,
            }

        return nodes

    def extract_edges(self, nodes: list[DDGNode]) -> list[DDGEdge]:
        """Extract dependency edges from JavaScript modules.

        Args:
            nodes: List of previously extracted nodes.

        Returns:
            List of DDGEdge objects representing dependencies.
        """
        edges: list[DDGEdge] = []
        node_ids = {node.id for node in nodes}
        module_to_id = {
            node.name: node.id for node in nodes if node.id.startswith("js:")
        }

        for module_name, module_info in self._modules.items():
            source_id = f"js:{module_name}"
            if source_id not in node_ids:
                continue

            content = module_info["content"]
            file_path = module_info["file"]

            # Extract import edges
            edges.extend(
                self._extract_import_edges(
                    source_id,
                    content,
                    module_to_id,
                    file_path,
                )
            )

            # Extract class inheritance edges
            edges.extend(
                self._extract_class_edges(
                    source_id,
                    content,
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

        return edges

    def _get_module_name(self, file_path: Path) -> str:
        """Convert file path to module name.

        Args:
            file_path: Path to the JavaScript file.

        Returns:
            Module name string.
        """
        try:
            rel_path = file_path.relative_to(self.project_path)
        except ValueError:
            rel_path = file_path

        # Convert path to module name
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

    def _detect_module_type(self, content: str) -> str:
        """Detect the type of JavaScript module.

        A module is typed by its PRIMARY role. Web frameworks and entry
        points take precedence: an Express app that connects to redis
        is a "service", not a "cache".

        Args:
            content: File content.

        Returns:
            Module type string.
        """
        # Check for web framework patterns FIRST — an Express app
        # that connects to redis is a service, not infrastructure.
        if re.search(r"express\s*\(\)|new\s+Koa\s*\(|new\s+Hapi\.Server\s*\(", content):
            return "service"
        if re.search(r"@Controller|@Get|@Post|@Put|@Delete", content):
            return "service"  # NestJS
        if re.search(r"createServer\s*\(|\.listen\s*\(\s*\d", content):
            return "service"

        # Check for React components
        if re.search(r"React\.Component|useState\s*\(|useEffect\s*\(", content):
            return "component"

        # Check for test files
        if re.search(r"describe\s*\(|it\s*\(|test\s*\(|expect\s*\(", content):
            return "test"

        # Only classify as infrastructure type if NOT an application.
        for lib_name, pattern in self.CONNECTION_PATTERNS.items():
            if pattern.search(content):
                if lib_name in ("mongoose", "mongodb", "pg", "mysql"):
                    return "database"
                elif lib_name == "redis":
                    return "cache"
                elif lib_name in ("amqplib", "kafkajs"):
                    return "queue"
                elif lib_name in ("axios", "fetch"):
                    return "client"

        return "module"

    def _get_class_names(self, content: str) -> list[str]:
        """Get all class names in the module.

        Args:
            content: File content.

        Returns:
            List of class names.
        """
        return [match.group(1) for match in self.CLASS_PATTERN.finditer(content)]

    def _get_exports(self, content: str) -> list[str]:
        """Get all exported names.

        Args:
            content: File content.

        Returns:
            List of exported names.
        """
        exports: list[str] = []
        for match in self.EXPORT_DEFAULT_PATTERN.finditer(content):
            if match.group(1):
                exports.append(match.group(1))
        for match in self.EXPORT_NAMED_PATTERN.finditer(content):
            exports.append(match.group(1))
        return exports

    def _get_imports(self, content: str) -> list[str]:
        """Get all imported modules.

        Args:
            content: File content.

        Returns:
            List of imported module paths.
        """
        imports: list[str] = []
        for pattern in [
            self.ES6_IMPORT_PATTERN,
            self.REQUIRE_PATTERN,
            self.DYNAMIC_IMPORT_PATTERN,
        ]:
            for match in pattern.finditer(content):
                imports.append(match.group(1))
        return imports

    def _extract_import_edges(
        self,
        source_id: str,
        content: str,
        module_to_id: dict[str, str],
        file_path: Path,
    ) -> list[DDGEdge]:
        """Extract edges from import statements.

        Args:
            source_id: Source node ID.
            content: File content.
            module_to_id: Map of module names to node IDs.
            file_path: Path to the source file.

        Returns:
            List of DDGEdge objects.
        """
        edges: list[DDGEdge] = []

        for pattern in [self.ES6_IMPORT_PATTERN, self.REQUIRE_PATTERN]:
            for match in pattern.finditer(content):
                import_path = match.group(1)
                line_num = content[: match.start()].count("\n") + 1

                # Only process relative imports (internal modules)
                if import_path.startswith("."):
                    target_id = self._resolve_import(import_path, file_path, module_to_id)
                    if target_id and target_id != source_id:
                        edges.append(
                            DDGEdge(
                                source=source_id,
                                target=target_id,
                                edge_type=EdgeType.RUNTIME,
                                confidence=Confidence.HIGH,
                                description=f"imports {import_path}",
                                file_path=self.relative_path(file_path),
                                line_number=line_num,
                            )
                        )

        # Dynamic imports are lower confidence
        for match in self.DYNAMIC_IMPORT_PATTERN.finditer(content):
            import_path = match.group(1)
            line_num = content[: match.start()].count("\n") + 1

            if import_path.startswith("."):
                target_id = self._resolve_import(import_path, file_path, module_to_id)
                if target_id and target_id != source_id:
                    edges.append(
                        DDGEdge(
                            source=source_id,
                            target=target_id,
                            edge_type=EdgeType.RUNTIME,
                            confidence=Confidence.MEDIUM,
                            description=f"dynamically imports {import_path}",
                            file_path=self.relative_path(file_path),
                            line_number=line_num,
                        )
                    )

        return edges

    def _resolve_import(
        self,
        import_path: str,
        from_file: Path,
        module_to_id: dict[str, str],
    ) -> str | None:
        """Resolve a relative import path to a module ID.

        Args:
            import_path: Relative import path.
            from_file: File containing the import.
            module_to_id: Map of module names to node IDs.

        Returns:
            Node ID or None if not found.
        """
        # Get the directory of the importing file
        from_dir = from_file.parent

        # Resolve the relative path
        if import_path.startswith("./"):
            import_path = import_path[2:]
        elif import_path.startswith("../"):
            parts = import_path.split("/")
            up_count = 0
            while parts and parts[0] == "..":
                up_count += 1
                parts.pop(0)
            for _ in range(up_count):
                from_dir = from_dir.parent
            import_path = "/".join(parts)

        # Try to find the module
        try:
            resolved = from_dir / import_path
            resolved = resolved.relative_to(self.project_path)
            module_name = str(resolved)
        except ValueError:
            return None

        # Try exact match
        if module_name in module_to_id:
            return module_to_id[module_name]

        # Try with common extensions
        for ext in ["", "/index"]:
            test_name = module_name + ext
            if test_name in module_to_id:
                return module_to_id[test_name]

        return None

    def _extract_class_edges(
        self,
        source_id: str,
        content: str,
        module_to_id: dict[str, str],
        file_path: Path,
    ) -> list[DDGEdge]:
        """Extract edges from class inheritance.

        Args:
            source_id: Source node ID.
            content: File content.
            module_to_id: Map of module names to node IDs.
            file_path: Path to the source file.

        Returns:
            List of DDGEdge objects.
        """
        edges: list[DDGEdge] = []

        for match in self.CLASS_PATTERN.finditer(content):
            if match.group(2):  # Has extends clause
                parent_class = match.group(2)
                line_num = content[: match.start()].count("\n") + 1

                # Look for the import of the parent class
                for module_name, node_id in module_to_id.items():
                    # Check if this module might contain the parent class
                    if parent_class.lower() in module_name.lower():
                        if node_id != source_id:
                            edges.append(
                                DDGEdge(
                                    source=source_id,
                                    target=node_id,
                                    edge_type=EdgeType.STATE,
                                    confidence=Confidence.LOW,
                                    description=f"class extends {parent_class}",
                                    file_path=self.relative_path(file_path),
                                    line_number=line_num,
                                )
                            )
                            break

        return edges

    def _extract_connection_edges(
        self,
        source_id: str,
        content: str,
        file_path: Path,
        nodes: list[DDGNode],
    ) -> list[DDGEdge]:
        """Extract edges from database/service connections.

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
        target_nodes = [n for n in nodes if n.type in ("database", "cache", "queue")]

        for lib_name, pattern in self.CONNECTION_PATTERNS.items():
            matches = list(pattern.finditer(content))
            if matches:
                for target_node in target_nodes:
                    if self._matches_connection_type(lib_name, target_node):
                        for match in matches:
                            line_num = content[: match.start()].count("\n") + 1
                            edges.append(
                                DDGEdge(
                                    source=source_id,
                                    target=target_node.id,
                                    edge_type=EdgeType.STATE,
                                    confidence=Confidence.MEDIUM,
                                    description=f"connects via {lib_name}",
                                    file_path=self.relative_path(file_path),
                                    line_number=line_num,
                                )
                            )
                            break

        return edges

    def _matches_connection_type(self, lib_name: str, node: DDGNode) -> bool:
        """Check if a library matches a node's type AND name.

        Matching requires both infrastructure type and matching name.

        Args:
            lib_name: Name of the library.
            node: Node to check.

        Returns:
            True if they match.
        """
        # Never target application nodes — only infrastructure
        if node.type in ("service", "api", "client", "module", "component", "test"):
            return False

        if node.type not in ("database", "cache", "queue"):
            return False

        node_name = (node.id + " " + node.name).lower()

        lib_to_names: dict[str, list[str]] = {
            "mongoose": ["mongo", "db", "database"],
            "mongodb": ["mongo", "db", "database"],
            "pg": ["postgres", "db", "database", "sql"],
            "mysql": ["mysql", "db", "database", "mariadb"],
            "redis": ["redis", "cache"],
            "amqplib": ["rabbit", "amqp", "mq", "queue"],
            "kafkajs": ["kafka", "queue", "broker"],
        }

        expected_names = lib_to_names.get(lib_name, [])
        return any(name in node_name for name in expected_names)
