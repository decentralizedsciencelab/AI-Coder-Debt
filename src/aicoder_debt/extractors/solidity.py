"""Solidity smart contract analyzer for DDG extraction."""

from __future__ import annotations

import re
from pathlib import Path

from ..constants import SOLIDITY_PATTERNS, Confidence, EdgeType
from ..models import DDGEdge, DDGNode
from .base import BaseExtractor


class SolidityExtractor(BaseExtractor):
    """Extract DDG nodes and edges from Solidity smart contracts."""

    # Patterns for Solidity analysis
    CONTRACT_PATTERN = re.compile(
        r"^\s*(contract|interface|library|abstract\s+contract)\s+(\w+)",
        re.MULTILINE,
    )
    INHERITANCE_PATTERN = re.compile(
        r"^\s*(?:contract|interface|library|abstract\s+contract)\s+\w+\s+is\s+([^{]+)",
        re.MULTILINE,
    )
    STATE_VAR_PATTERN = re.compile(
        r"^\s*(\w+)\s+(?:public|private|internal)?\s*(\w+)\s*;",
        re.MULTILINE,
    )
    CONSTRUCTOR_PATTERN = re.compile(
        r"constructor\s*\([^)]*\)[^{]*\{([^}]*)\}",
        re.DOTALL,
    )
    FUNCTION_CALL_PATTERN = re.compile(
        r"(\w+)\s*\.\s*(\w+)\s*\(",
    )
    ADDRESS_PATTERN = re.compile(
        r"(\w+)\s*=\s*(?:address\s*\()?(?:0x[a-fA-F0-9]+|\w+)(?:\))?",
    )
    IMPORT_PATTERN = re.compile(
        r'import\s+(?:{[^}]+}|[^;]+)\s+from\s+["\']([^"\']+)["\']',
    )

    def __init__(self, project_path: str | Path) -> None:
        """Initialize the Solidity extractor.

        Args:
            project_path: Path to the project directory.
        """
        super().__init__(project_path)
        self._contracts: dict[str, dict] = {}
        self._sol_files: list[Path] = []

    def extract_nodes(self) -> list[DDGNode]:
        """Extract contract nodes from Solidity files.

        Returns:
            List of DDGNode objects representing contracts.
        """
        self._sol_files = self.find_files(SOLIDITY_PATTERNS)
        nodes: list[DDGNode] = []

        for sol_file in self._sol_files:
            content = self.read_file(sol_file)
            if not content:
                continue

            # Find all contracts in the file
            for match in self.CONTRACT_PATTERN.finditer(content):
                contract_type = match.group(1).strip()
                contract_name = match.group(2)

                # Get line number
                line_num = content[: match.start()].count("\n") + 1

                node_id = f"sol:{contract_name}"
                node = DDGNode(
                    id=node_id,
                    name=contract_name,
                    type=self._get_contract_type(contract_type),
                    file_path=self.relative_path(sol_file),
                    line_number=line_num,
                    metadata={
                        "contract_type": contract_type,
                        "has_constructor": bool(
                            self.CONSTRUCTOR_PATTERN.search(content)
                        ),
                    },
                )
                nodes.append(node)

                # Store contract info for edge extraction
                self._contracts[contract_name] = {
                    "file": sol_file,
                    "content": content,
                    "type": contract_type,
                }

        return nodes

    def extract_edges(self, nodes: list[DDGNode]) -> list[DDGEdge]:
        """Extract dependency edges from Solidity contracts.

        Args:
            nodes: List of previously extracted nodes.

        Returns:
            List of DDGEdge objects representing dependencies.
        """
        edges: list[DDGEdge] = []
        node_ids = {node.id for node in nodes}
        contract_to_id = {
            node.name: node.id for node in nodes if node.id.startswith("sol:")
        }

        for contract_name, contract_info in self._contracts.items():
            source_id = f"sol:{contract_name}"
            if source_id not in node_ids:
                continue

            content = contract_info["content"]
            file_path = contract_info["file"]

            # Extract inheritance edges
            edges.extend(
                self._extract_inheritance_edges(
                    source_id,
                    content,
                    contract_to_id,
                    file_path,
                )
            )

            # Extract constructor dependency edges
            edges.extend(
                self._extract_constructor_edges(
                    source_id,
                    content,
                    contract_to_id,
                    file_path,
                )
            )

            # Extract state variable edges
            edges.extend(
                self._extract_state_var_edges(
                    source_id,
                    content,
                    contract_to_id,
                    file_path,
                )
            )

            # Extract function call edges
            edges.extend(
                self._extract_function_call_edges(
                    source_id,
                    content,
                    contract_to_id,
                    file_path,
                )
            )

        return edges

    def _get_contract_type(self, contract_keyword: str) -> str:
        """Map Solidity contract keyword to node type.

        Args:
            contract_keyword: The contract keyword (contract, interface, etc.)

        Returns:
            Node type string.
        """
        type_map = {
            "contract": "contract",
            "interface": "interface",
            "library": "library",
            "abstract contract": "abstract_contract",
        }
        return type_map.get(contract_keyword.strip(), "contract")

    def _extract_inheritance_edges(
        self,
        source_id: str,
        content: str,
        contract_to_id: dict[str, str],
        file_path: Path,
    ) -> list[DDGEdge]:
        """Extract inheritance edges.

        Args:
            source_id: Source node ID.
            content: File content.
            contract_to_id: Map of contract names to node IDs.
            file_path: Path to the source file.

        Returns:
            List of DDGEdge objects.
        """
        edges: list[DDGEdge] = []

        for match in self.INHERITANCE_PATTERN.finditer(content):
            parents = match.group(1)
            line_num = content[: match.start()].count("\n") + 1

            # Parse parent contracts
            for parent in parents.split(","):
                parent_name = parent.strip().split("(")[0].strip()
                if parent_name in contract_to_id:
                    edges.append(
                        DDGEdge(
                            source=source_id,
                            target=contract_to_id[parent_name],
                            edge_type=EdgeType.STATE,
                            confidence=Confidence.HIGH,
                            description=f"inherits from {parent_name}",
                            file_path=self.relative_path(file_path),
                            line_number=line_num,
                        )
                    )

        return edges

    def _extract_constructor_edges(
        self,
        source_id: str,
        content: str,
        contract_to_id: dict[str, str],
        file_path: Path,
    ) -> list[DDGEdge]:
        """Extract edges from constructor dependencies.

        Constructor dependencies are STATE edges because they require
        the dependency to exist at deployment time.

        Args:
            source_id: Source node ID.
            content: File content.
            contract_to_id: Map of contract names to node IDs.
            file_path: Path to the source file.

        Returns:
            List of DDGEdge objects.
        """
        edges: list[DDGEdge] = []

        for match in self.CONSTRUCTOR_PATTERN.finditer(content):
            constructor_body = match.group(1)
            line_num = content[: match.start()].count("\n") + 1

            # Look for contract instantiations
            for contract_name in contract_to_id:
                if contract_name == source_id.replace("sol:", ""):
                    continue

                # Check for new ContractName(...) pattern
                if re.search(rf"\bnew\s+{contract_name}\s*\(", constructor_body):
                    edges.append(
                        DDGEdge(
                            source=source_id,
                            target=contract_to_id[contract_name],
                            edge_type=EdgeType.STATE,
                            confidence=Confidence.HIGH,
                            requires_atomicity=True,
                            description=f"instantiates {contract_name} in constructor",
                            file_path=self.relative_path(file_path),
                            line_number=line_num,
                        )
                    )

                # Check for address assignment from parameter
                if re.search(
                    rf"{contract_name}\s*\(\s*\w+\s*\)", constructor_body
                ):
                    edges.append(
                        DDGEdge(
                            source=source_id,
                            target=contract_to_id[contract_name],
                            edge_type=EdgeType.ADDR,
                            confidence=Confidence.MEDIUM,
                            description=f"receives {contract_name} address in constructor",
                            file_path=self.relative_path(file_path),
                            line_number=line_num,
                        )
                    )

        return edges

    def _extract_state_var_edges(
        self,
        source_id: str,
        content: str,
        contract_to_id: dict[str, str],
        file_path: Path,
    ) -> list[DDGEdge]:
        """Extract edges from state variable declarations.

        Args:
            source_id: Source node ID.
            content: File content.
            contract_to_id: Map of contract names to node IDs.
            file_path: Path to the source file.

        Returns:
            List of DDGEdge objects.
        """
        edges: list[DDGEdge] = []

        for match in self.STATE_VAR_PATTERN.finditer(content):
            var_type = match.group(1)
            line_num = content[: match.start()].count("\n") + 1

            if var_type in contract_to_id and var_type != source_id.replace("sol:", ""):
                edges.append(
                    DDGEdge(
                        source=source_id,
                        target=contract_to_id[var_type],
                        edge_type=EdgeType.STATE,
                        confidence=Confidence.MEDIUM,
                        description=f"has state variable of type {var_type}",
                        file_path=self.relative_path(file_path),
                        line_number=line_num,
                    )
                )

        return edges

    def _extract_function_call_edges(
        self,
        source_id: str,
        content: str,
        contract_to_id: dict[str, str],
        file_path: Path,
    ) -> list[DDGEdge]:
        """Extract edges from function calls to other contracts.

        These are typically RUNTIME edges unless in constructor.

        Args:
            source_id: Source node ID.
            content: File content.
            contract_to_id: Map of contract names to node IDs.
            file_path: Path to the source file.

        Returns:
            List of DDGEdge objects.
        """
        edges: list[DDGEdge] = []
        seen_targets: set[str] = set()

        for match in self.FUNCTION_CALL_PATTERN.finditer(content):
            caller = match.group(1)
            line_num = content[: match.start()].count("\n") + 1

            # Check if the caller is a known contract type
            for contract_name in contract_to_id:
                if contract_name == source_id.replace("sol:", ""):
                    continue

                # Check if variable name suggests contract type
                if contract_name.lower() in caller.lower():
                    target_id = contract_to_id[contract_name]
                    if target_id not in seen_targets:
                        seen_targets.add(target_id)
                        edges.append(
                            DDGEdge(
                                source=source_id,
                                target=target_id,
                                edge_type=EdgeType.RUNTIME,
                                confidence=Confidence.LOW,
                                description=f"calls methods on {contract_name}",
                                file_path=self.relative_path(file_path),
                                line_number=line_num,
                            )
                        )

        return edges
