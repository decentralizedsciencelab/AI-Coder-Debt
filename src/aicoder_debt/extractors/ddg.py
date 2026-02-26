"""Unified DDG extractor with Tarjan's SCC algorithm."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..constants import (
    DOCKER_PATTERNS,
    JS_PATTERNS,
    PYTHON_PATTERNS,
    SOLIDITY_PATTERNS,
    Confidence,
    EdgeType,
)
from ..models import Cycle, DDGAnalysis, DDGEdge, DDGNode, DDGStatistics
from .base import BaseExtractor


class DDGExtractor(BaseExtractor):
    """Unified DDG extractor that auto-detects project type."""

    def __init__(self, project_path: str | Path) -> None:
        """Initialize the DDG extractor.

        Args:
            project_path: Path to the project directory.
        """
        super().__init__(project_path)
        self._nodes: list[DDGNode] = []
        self._edges: list[DDGEdge] = []
        self._extractors: list[BaseExtractor] = []

    def detect_project_types(self) -> list[str]:
        """Detect which project types are present.

        Returns:
            List of detected project types.
        """
        types: list[str] = []

        if self.find_files(PYTHON_PATTERNS):
            types.append("python")
        if self.find_files(JS_PATTERNS):
            types.append("javascript")
        if self.find_files(SOLIDITY_PATTERNS):
            types.append("solidity")
        if self.find_files(DOCKER_PATTERNS):
            types.append("docker")

        return types

    def extract_nodes(self) -> list[DDGNode]:
        """Extract nodes from all detected project types.

        Returns:
            List of DDGNode objects.
        """
        from .docker import DockerComposeExtractor
        from .javascript import JavaScriptExtractor
        from .python_analyzer import PythonExtractor
        from .solidity import SolidityExtractor

        nodes: list[DDGNode] = []
        project_types = self.detect_project_types()

        extractors: dict[str, type[BaseExtractor]] = {
            "python": PythonExtractor,
            "javascript": JavaScriptExtractor,
            "solidity": SolidityExtractor,
            "docker": DockerComposeExtractor,
        }

        for ptype in project_types:
            if ptype in extractors:
                extractor = extractors[ptype](self.project_path)
                self._extractors.append(extractor)
                nodes.extend(extractor.extract_nodes())

        self._nodes = nodes
        return nodes

    def extract_edges(self, nodes: list[DDGNode]) -> list[DDGEdge]:
        """Extract edges from all extractors.

        Args:
            nodes: List of previously extracted nodes.

        Returns:
            List of DDGEdge objects.
        """
        edges: list[DDGEdge] = []

        for extractor in self._extractors:
            edges.extend(extractor.extract_edges(nodes))

        self._edges = edges
        return edges

    def extract(self) -> DDGAnalysis:
        """Run full DDG extraction.

        Returns:
            Complete DDGAnalysis with nodes, edges, cycles, and statistics.
        """
        nodes = self.extract_nodes()
        edges = self.extract_edges(nodes)
        cycles = self.find_cycles(nodes, edges)
        statistics = self._compute_statistics(nodes, edges, cycles)

        return DDGAnalysis(
            nodes=nodes,
            edges=edges,
            cycles=cycles,
            statistics=statistics,
        )

    def find_cycles(
        self, nodes: list[DDGNode], edges: list[DDGEdge]
    ) -> list[Cycle]:
        """Find cycles using Tarjan's SCC algorithm.

        Args:
            nodes: List of nodes in the graph.
            edges: List of edges in the graph.

        Returns:
            List of Cycle objects representing SCCs.
        """
        # Build adjacency list
        node_ids = {node.id for node in nodes}
        adj: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
        edge_map: dict[tuple[str, str], DDGEdge] = {}

        for edge in edges:
            if edge.source in node_ids and edge.target in node_ids:
                adj[edge.source].append(edge.target)
                edge_map[(edge.source, edge.target)] = edge

        # Find SCCs using iterative Tarjan's algorithm
        sccs = self._find_cycles_tarjan(adj)

        # Convert SCCs to Cycle objects
        cycles: list[Cycle] = []
        for scc in sccs:
            if len(scc) > 1 or self._has_self_loop(scc[0], adj):
                cycle_edges = self._get_cycle_edges(scc, edge_map)
                has_state = any(e.edge_type == EdgeType.STATE for e in cycle_edges)
                is_irreparable = self._check_irreparable(cycle_edges)

                cycles.append(
                    Cycle(
                        nodes=scc,
                        edges=cycle_edges,
                        has_state_edge=has_state,
                        is_irreparable=is_irreparable,
                    )
                )

        return cycles

    def _find_cycles_tarjan(self, adj: dict[str, list[str]]) -> list[list[str]]:
        """Find strongly connected components using iterative Tarjan's algorithm.

        This iterative implementation avoids stack overflow on large graphs.

        Args:
            adj: Adjacency list representation of the graph.

        Returns:
            List of SCCs, where each SCC is a list of node IDs.
        """
        index_counter = [0]
        stack: list[str] = []
        lowlinks: dict[str, int] = {}
        index: dict[str, int] = {}
        on_stack: dict[str, bool] = {}
        sccs: list[list[str]] = []

        # Iterative implementation using call stack simulation
        # Each entry is (node, successor_index, phase)
        # Phase 0: initial visit, Phase 1: post-processing
        call_stack: list[tuple[str, int, int]] = []

        for start_node in adj:
            if start_node in index:
                continue

            call_stack.append((start_node, 0, 0))

            while call_stack:
                node, succ_idx, phase = call_stack.pop()

                if phase == 0:
                    # Initial visit
                    if node in index:
                        continue

                    index[node] = index_counter[0]
                    lowlinks[node] = index_counter[0]
                    index_counter[0] += 1
                    on_stack[node] = True
                    stack.append(node)

                    # Push post-processing phase
                    call_stack.append((node, 0, 1))

                    # Push all successors
                    successors = adj.get(node, [])
                    for i, successor in enumerate(successors):
                        if successor not in index:
                            call_stack.append((node, i, 2))  # Return point
                            call_stack.append((successor, 0, 0))  # Visit successor
                            break
                        elif on_stack.get(successor, False):
                            lowlinks[node] = min(
                                lowlinks[node], index[successor]
                            )

                elif phase == 1:
                    # Post-processing: check if root of SCC
                    if lowlinks[node] == index[node]:
                        scc: list[str] = []
                        while True:
                            w = stack.pop()
                            on_stack[w] = False
                            scc.append(w)
                            if w == node:
                                break
                        sccs.append(scc)

                elif phase == 2:
                    # Return from recursive call
                    successors = adj.get(node, [])
                    if succ_idx < len(successors):
                        successor = successors[succ_idx]
                        if successor in lowlinks:
                            lowlinks[node] = min(
                                lowlinks[node], lowlinks[successor]
                            )

                        # Continue with next successor
                        for i in range(succ_idx + 1, len(successors)):
                            next_succ = successors[i]
                            if next_succ not in index:
                                call_stack.append((node, i, 2))
                                call_stack.append((next_succ, 0, 0))
                                break
                            elif on_stack.get(next_succ, False):
                                lowlinks[node] = min(
                                    lowlinks[node], index[next_succ]
                                )

        return sccs

    def _has_self_loop(self, node: str, adj: dict[str, list[str]]) -> bool:
        """Check if a node has a self-loop.

        Args:
            node: Node ID to check.
            adj: Adjacency list.

        Returns:
            True if node has a self-loop.
        """
        return node in adj.get(node, [])

    def _get_cycle_edges(
        self, scc: list[str], edge_map: dict[tuple[str, str], DDGEdge]
    ) -> list[DDGEdge]:
        """Get all edges within a cycle.

        Args:
            scc: List of node IDs in the SCC.
            edge_map: Map from (source, target) to edge.

        Returns:
            List of edges within the cycle.
        """
        scc_set = set(scc)
        edges: list[DDGEdge] = []

        for source in scc:
            for target in scc_set:
                if (source, target) in edge_map:
                    edges.append(edge_map[(source, target)])

        return edges

    def _check_irreparable(self, edges: list[DDGEdge]) -> bool:
        """Check if a cycle is irreparable.

        A cycle is irreparable if it contains bidirectional STATE edges
        where at least one has atomicity requirements.

        Args:
            edges: List of edges in the cycle.

        Returns:
            True if the cycle is irreparable.
        """
        # Build edge direction map
        state_edges: dict[tuple[str, str], DDGEdge] = {}
        for edge in edges:
            if edge.edge_type == EdgeType.STATE:
                state_edges[(edge.source, edge.target)] = edge

        # Check for bidirectional STATE edges with atomicity
        for (src, tgt), edge in state_edges.items():
            if (tgt, src) in state_edges:
                reverse_edge = state_edges[(tgt, src)]
                if edge.requires_atomicity or reverse_edge.requires_atomicity:
                    return True

        return False

    def _compute_statistics(
        self,
        nodes: list[DDGNode],
        edges: list[DDGEdge],
        cycles: list[Cycle],
    ) -> DDGStatistics:
        """Compute statistics for the DDG.

        Args:
            nodes: List of nodes.
            edges: List of edges.
            cycles: List of cycles.

        Returns:
            DDGStatistics object.
        """
        addr_count = sum(1 for e in edges if e.edge_type == EdgeType.ADDR)
        state_count = sum(1 for e in edges if e.edge_type == EdgeType.STATE)
        runtime_count = sum(1 for e in edges if e.edge_type == EdgeType.RUNTIME)
        stateful_count = sum(1 for c in cycles if c.has_state_edge)
        irreparable_count = sum(1 for c in cycles if c.is_irreparable)

        return DDGStatistics(
            total_nodes=len(nodes),
            total_edges=len(edges),
            addr_edges=addr_count,
            state_edges=state_count,
            runtime_edges=runtime_count,
            total_cycles=len(cycles),
            stateful_cycles=stateful_count,
            irreparable_cycles=irreparable_count,
        )

    def to_dict(self, analysis: DDGAnalysis) -> dict[str, Any]:
        """Convert DDGAnalysis to dictionary for JSON serialization.

        Args:
            analysis: DDGAnalysis object.

        Returns:
            Dictionary representation.
        """
        return analysis.model_dump()
