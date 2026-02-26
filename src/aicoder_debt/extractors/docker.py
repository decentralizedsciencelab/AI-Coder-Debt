"""Docker Compose analyzer for DDG extraction."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from ..constants import DOCKER_PATTERNS, Confidence, EdgeType
from ..models import DDGEdge, DDGNode
from .base import BaseExtractor


class DockerComposeExtractor(BaseExtractor):
    """Extract DDG nodes and edges from docker-compose files."""

    def __init__(self, project_path: str | Path) -> None:
        """Initialize the Docker Compose extractor.

        Args:
            project_path: Path to the project directory.
        """
        super().__init__(project_path)
        self._compose_files: list[Path] = []
        self._services: dict[str, dict[str, Any]] = {}

    def extract_nodes(self) -> list[DDGNode]:
        """Extract service nodes from docker-compose files.

        Returns:
            List of DDGNode objects representing services.
        """
        self._compose_files = self.find_files(DOCKER_PATTERNS)
        nodes: list[DDGNode] = []

        for compose_file in self._compose_files:
            content = self.read_file(compose_file)
            if not content:
                continue

            try:
                compose_data = yaml.safe_load(content)
                if not compose_data or not isinstance(compose_data, dict):
                    continue

                services = compose_data.get("services", {})
                if not isinstance(services, dict):
                    continue

                for service_name, service_config in services.items():
                    if not isinstance(service_config, dict):
                        continue

                    node_id = f"docker:{service_name}"
                    node_type = self._detect_service_type(service_name, service_config)

                    node = DDGNode(
                        id=node_id,
                        name=service_name,
                        type=node_type,
                        file_path=self.relative_path(compose_file),
                        metadata={
                            "image": service_config.get("image", ""),
                            "build": service_config.get("build", {}),
                            "ports": service_config.get("ports", []),
                            "environment": self._extract_env_keys(service_config),
                        },
                    )
                    nodes.append(node)
                    self._services[service_name] = service_config

            except yaml.YAMLError:
                continue

        return nodes

    def extract_edges(self, nodes: list[DDGNode]) -> list[DDGEdge]:
        """Extract dependency edges from docker-compose files.

        Args:
            nodes: List of previously extracted nodes.

        Returns:
            List of DDGEdge objects representing dependencies.
        """
        edges: list[DDGEdge] = []
        node_ids = {node.id for node in nodes}
        node_names = {node.name: node.id for node in nodes if node.id.startswith("docker:")}

        for compose_file in self._compose_files:
            content = self.read_file(compose_file)
            if not content:
                continue

            try:
                compose_data = yaml.safe_load(content)
                if not compose_data or not isinstance(compose_data, dict):
                    continue

                services = compose_data.get("services", {})
                if not isinstance(services, dict):
                    continue

                for service_name, service_config in services.items():
                    if not isinstance(service_config, dict):
                        continue

                    source_id = f"docker:{service_name}"
                    if source_id not in node_ids:
                        continue

                    # Extract depends_on edges
                    depends_on = service_config.get("depends_on", [])
                    edges.extend(
                        self._extract_depends_on_edges(
                            source_id,
                            depends_on,
                            node_names,
                            compose_file,
                        )
                    )

                    # Extract link edges
                    links = service_config.get("links", [])
                    edges.extend(
                        self._extract_link_edges(
                            source_id,
                            links,
                            node_names,
                            compose_file,
                        )
                    )

                    # Extract network alias edges
                    edges.extend(
                        self._extract_network_edges(
                            source_id,
                            service_config,
                            node_names,
                            compose_file,
                        )
                    )

            except yaml.YAMLError:
                continue

        return edges

    def _detect_service_type(
        self, service_name: str, config: dict[str, Any]
    ) -> str:
        """Detect the type of service based on name and configuration.

        Args:
            service_name: Name of the service.
            config: Service configuration.

        Returns:
            Service type string.
        """
        name_lower = service_name.lower()
        image = str(config.get("image", "")).lower()

        # Database patterns
        db_patterns = ["postgres", "mysql", "mariadb", "mongo", "redis", "memcache"]
        for pattern in db_patterns:
            if pattern in name_lower or pattern in image:
                return "database"

        # Queue patterns
        queue_patterns = ["rabbit", "kafka", "celery", "redis"]
        for pattern in queue_patterns:
            if pattern in name_lower or pattern in image:
                if "redis" in pattern and "cache" in name_lower:
                    return "cache"
                return "queue"

        # API/Web patterns
        api_patterns = ["api", "web", "app", "backend", "frontend", "nginx"]
        for pattern in api_patterns:
            if pattern in name_lower or pattern in image:
                return "service"

        return "service"

    def _extract_env_keys(self, config: dict[str, Any]) -> list[str]:
        """Extract environment variable keys from service config.

        Args:
            config: Service configuration.

        Returns:
            List of environment variable keys.
        """
        env = config.get("environment", [])
        keys: list[str] = []

        if isinstance(env, dict):
            keys = list(env.keys())
        elif isinstance(env, list):
            for item in env:
                if isinstance(item, str) and "=" in item:
                    keys.append(item.split("=")[0])
                elif isinstance(item, str):
                    keys.append(item)

        return keys

    def _extract_depends_on_edges(
        self,
        source_id: str,
        depends_on: Any,
        node_names: dict[str, str],
        compose_file: Path,
    ) -> list[DDGEdge]:
        """Extract edges from depends_on configuration.

        Args:
            source_id: Source node ID.
            depends_on: depends_on configuration.
            node_names: Map of service names to node IDs.
            compose_file: Path to the compose file.

        Returns:
            List of DDGEdge objects.
        """
        edges: list[DDGEdge] = []

        if isinstance(depends_on, list):
            # Simple list format
            for dep in depends_on:
                if dep in node_names:
                    edges.append(
                        DDGEdge(
                            source=source_id,
                            target=node_names[dep],
                            edge_type=EdgeType.STATE,
                            confidence=Confidence.HIGH,
                            description=f"depends_on: {dep}",
                            file_path=self.relative_path(compose_file),
                        )
                    )
        elif isinstance(depends_on, dict):
            # Extended format with conditions
            for dep, condition in depends_on.items():
                if dep in node_names:
                    # Determine edge type based on condition
                    edge_type = EdgeType.STATE
                    requires_atomicity = False

                    if isinstance(condition, dict):
                        cond_type = condition.get("condition", "")
                        if cond_type == "service_healthy":
                            requires_atomicity = True
                        elif cond_type == "service_started":
                            edge_type = EdgeType.ADDR

                    edges.append(
                        DDGEdge(
                            source=source_id,
                            target=node_names[dep],
                            edge_type=edge_type,
                            confidence=Confidence.HIGH,
                            requires_atomicity=requires_atomicity,
                            description=f"depends_on: {dep}",
                            file_path=self.relative_path(compose_file),
                        )
                    )

        return edges

    def _extract_link_edges(
        self,
        source_id: str,
        links: list[Any],
        node_names: dict[str, str],
        compose_file: Path,
    ) -> list[DDGEdge]:
        """Extract edges from links configuration.

        Args:
            source_id: Source node ID.
            links: links configuration.
            node_names: Map of service names to node IDs.
            compose_file: Path to the compose file.

        Returns:
            List of DDGEdge objects.
        """
        edges: list[DDGEdge] = []

        for link in links:
            if isinstance(link, str):
                # Handle alias format: "service:alias"
                service = link.split(":")[0]
                if service in node_names:
                    edges.append(
                        DDGEdge(
                            source=source_id,
                            target=node_names[service],
                            edge_type=EdgeType.ADDR,
                            confidence=Confidence.HIGH,
                            description=f"link: {link}",
                            file_path=self.relative_path(compose_file),
                        )
                    )

        return edges

    def _extract_network_edges(
        self,
        source_id: str,
        config: dict[str, Any],
        node_names: dict[str, str],
        compose_file: Path,
    ) -> list[DDGEdge]:
        """Extract edges from environment variables referencing other services.

        Args:
            source_id: Source node ID.
            config: Service configuration.
            node_names: Map of service names to node IDs.
            compose_file: Path to the compose file.

        Returns:
            List of DDGEdge objects.
        """
        edges: list[DDGEdge] = []
        env = config.get("environment", [])

        # Convert to list of strings
        env_strings: list[str] = []
        if isinstance(env, dict):
            env_strings = [f"{k}={v}" for k, v in env.items()]
        elif isinstance(env, list):
            env_strings = [str(e) for e in env]

        # Look for service references in environment values
        for env_str in env_strings:
            for service_name, target_id in node_names.items():
                # Match service name in URLs or hostnames
                if re.search(rf"\b{re.escape(service_name)}\b", env_str):
                    source_service = source_id.replace("docker:", "")
                    if service_name != source_service:
                        edges.append(
                            DDGEdge(
                                source=source_id,
                                target=target_id,
                                edge_type=EdgeType.RUNTIME,
                                confidence=Confidence.MEDIUM,
                                description=f"environment reference: {env_str}",
                                file_path=self.relative_path(compose_file),
                            )
                        )
                        break

        return edges
