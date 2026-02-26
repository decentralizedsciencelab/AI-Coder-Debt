"""Dependency extractor for package manifest files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from ..constants import DEPENDENCY_PATTERNS
from .base import BaseExtractor


class ExternalDependency:
    """Represents an external package dependency."""

    def __init__(
        self,
        name: str,
        version: str | None,
        ecosystem: str,
        file_path: str,
        is_dev: bool = False,
    ):
        self.name = name
        self.version = version
        self.ecosystem = ecosystem
        self.file_path = file_path
        self.is_dev = is_dev

    def __repr__(self) -> str:
        return f"ExternalDependency({self.name}, {self.ecosystem})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ExternalDependency):
            return False
        return self.name == other.name and self.ecosystem == other.ecosystem

    def __hash__(self) -> int:
        return hash((self.name, self.ecosystem))


class DependencyExtractor(BaseExtractor):
    """Extract external dependencies from package manifests."""

    def __init__(self, project_path: str | Path) -> None:
        """Initialize the dependency extractor.

        Args:
            project_path: Path to the project directory.
        """
        super().__init__(project_path)

    def extract_nodes(self) -> list:
        """Not used for dependency extraction."""
        return []

    def extract_edges(self, nodes: list) -> list:
        """Not used for dependency extraction."""
        return []

    def extract_dependencies(self) -> list[ExternalDependency]:
        """Extract all external dependencies from the project.

        Returns:
            List of ExternalDependency objects.
        """
        dependencies: list[ExternalDependency] = []

        # Find dependency files
        dep_files = self.find_files(DEPENDENCY_PATTERNS)

        for dep_file in dep_files:
            file_name = dep_file.name.lower()

            if file_name == "requirements.txt" or file_name.endswith(".txt"):
                dependencies.extend(self._parse_requirements_txt(dep_file))
            elif file_name == "setup.py":
                dependencies.extend(self._parse_setup_py(dep_file))
            elif file_name == "setup.cfg":
                dependencies.extend(self._parse_setup_cfg(dep_file))
            elif file_name == "pyproject.toml":
                dependencies.extend(self._parse_pyproject_toml(dep_file))
            elif file_name == "package.json":
                dependencies.extend(self._parse_package_json(dep_file))
            elif file_name == "cargo.toml":
                dependencies.extend(self._parse_cargo_toml(dep_file))
            elif file_name == "go.mod":
                dependencies.extend(self._parse_go_mod(dep_file))

        return dependencies

    def _parse_requirements_txt(self, file_path: Path) -> list[ExternalDependency]:
        """Parse a requirements.txt file.

        Args:
            file_path: Path to the requirements.txt file.

        Returns:
            List of ExternalDependency objects.
        """
        dependencies: list[ExternalDependency] = []
        content = self.read_file(file_path)
        if not content:
            return dependencies

        for line in content.splitlines():
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#") or line.startswith("-"):
                continue

            # Parse package name and version
            match = re.match(r"([a-zA-Z0-9_-]+)(?:\[.*\])?(?:([<>=!~]+.*))?", line)
            if match:
                name = match.group(1)
                version = match.group(2)

                dependencies.append(
                    ExternalDependency(
                        name=name,
                        version=version.strip() if version else None,
                        ecosystem="pypi",
                        file_path=self.relative_path(file_path),
                    )
                )

        return dependencies

    def _parse_setup_py(self, file_path: Path) -> list[ExternalDependency]:
        """Parse a setup.py file.

        Args:
            file_path: Path to the setup.py file.

        Returns:
            List of ExternalDependency objects.
        """
        dependencies: list[ExternalDependency] = []
        content = self.read_file(file_path)
        if not content:
            return dependencies

        # Look for install_requires
        match = re.search(r"install_requires\s*=\s*\[(.*?)\]", content, re.DOTALL)
        if match:
            requires = match.group(1)
            for pkg in re.findall(r"['\"]([^'\"]+)['\"]", requires):
                name_match = re.match(r"([a-zA-Z0-9_-]+)(?:\[.*\])?(?:.*)?", pkg)
                if name_match:
                    dependencies.append(
                        ExternalDependency(
                            name=name_match.group(1),
                            version=None,
                            ecosystem="pypi",
                            file_path=self.relative_path(file_path),
                        )
                    )

        # Look for extras_require
        match = re.search(r"extras_require\s*=\s*{(.*?)}", content, re.DOTALL)
        if match:
            extras = match.group(1)
            for pkg in re.findall(r"['\"]([^'\"]+)['\"]", extras):
                if ":" not in pkg:  # Skip key names
                    name_match = re.match(r"([a-zA-Z0-9_-]+)", pkg)
                    if name_match:
                        dependencies.append(
                            ExternalDependency(
                                name=name_match.group(1),
                                version=None,
                                ecosystem="pypi",
                                file_path=self.relative_path(file_path),
                                is_dev=True,
                            )
                        )

        return dependencies

    def _parse_setup_cfg(self, file_path: Path) -> list[ExternalDependency]:
        """Parse a setup.cfg file.

        Args:
            file_path: Path to the setup.cfg file.

        Returns:
            List of ExternalDependency objects.
        """
        dependencies: list[ExternalDependency] = []
        content = self.read_file(file_path)
        if not content:
            return dependencies

        in_install_requires = False
        for line in content.splitlines():
            line = line.strip()

            if line.startswith("["):
                in_install_requires = False
            if line.startswith("install_requires"):
                in_install_requires = True
                # Handle inline values
                if "=" in line:
                    _, _, value = line.partition("=")
                    value = value.strip()
                    if value:
                        name_match = re.match(r"([a-zA-Z0-9_-]+)", value)
                        if name_match:
                            dependencies.append(
                                ExternalDependency(
                                    name=name_match.group(1),
                                    version=None,
                                    ecosystem="pypi",
                                    file_path=self.relative_path(file_path),
                                )
                            )
                continue

            if in_install_requires and line and not line.startswith("#"):
                name_match = re.match(r"([a-zA-Z0-9_-]+)", line)
                if name_match:
                    dependencies.append(
                        ExternalDependency(
                            name=name_match.group(1),
                            version=None,
                            ecosystem="pypi",
                            file_path=self.relative_path(file_path),
                        )
                    )

        return dependencies

    def _parse_pyproject_toml(self, file_path: Path) -> list[ExternalDependency]:
        """Parse a pyproject.toml file.

        Args:
            file_path: Path to the pyproject.toml file.

        Returns:
            List of ExternalDependency objects.
        """
        dependencies: list[ExternalDependency] = []
        content = self.read_file(file_path)
        if not content:
            return dependencies

        # Simple regex-based parsing for dependencies
        # Look for dependencies in [project.dependencies] or [tool.poetry.dependencies]
        in_deps = False
        in_dev_deps = False

        for line in content.splitlines():
            line = line.strip()

            if line.startswith("["):
                in_deps = "dependencies" in line.lower() and "dev" not in line.lower()
                in_dev_deps = "dev" in line.lower()
                continue

            if (in_deps or in_dev_deps) and "=" in line:
                # Parse package name
                name, _, _ = line.partition("=")
                name = name.strip().strip('"\'')
                if name and not name.startswith("["):
                    dependencies.append(
                        ExternalDependency(
                            name=name,
                            version=None,
                            ecosystem="pypi",
                            file_path=self.relative_path(file_path),
                            is_dev=in_dev_deps,
                        )
                    )

        # Also look for inline dependencies array
        match = re.search(r'dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if match:
            deps_str = match.group(1)
            for pkg in re.findall(r'["\']([^"\']+)["\']', deps_str):
                name_match = re.match(r"([a-zA-Z0-9_-]+)", pkg)
                if name_match:
                    dependencies.append(
                        ExternalDependency(
                            name=name_match.group(1),
                            version=None,
                            ecosystem="pypi",
                            file_path=self.relative_path(file_path),
                        )
                    )

        return dependencies

    def _parse_package_json(self, file_path: Path) -> list[ExternalDependency]:
        """Parse a package.json file.

        Args:
            file_path: Path to the package.json file.

        Returns:
            List of ExternalDependency objects.
        """
        import json

        dependencies: list[ExternalDependency] = []
        content = self.read_file(file_path)
        if not content:
            return dependencies

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return dependencies

        # Regular dependencies
        for name, version in data.get("dependencies", {}).items():
            dependencies.append(
                ExternalDependency(
                    name=name,
                    version=version if isinstance(version, str) else None,
                    ecosystem="npm",
                    file_path=self.relative_path(file_path),
                )
            )

        # Dev dependencies
        for name, version in data.get("devDependencies", {}).items():
            dependencies.append(
                ExternalDependency(
                    name=name,
                    version=version if isinstance(version, str) else None,
                    ecosystem="npm",
                    file_path=self.relative_path(file_path),
                    is_dev=True,
                )
            )

        # Peer dependencies
        for name, version in data.get("peerDependencies", {}).items():
            dependencies.append(
                ExternalDependency(
                    name=name,
                    version=version if isinstance(version, str) else None,
                    ecosystem="npm",
                    file_path=self.relative_path(file_path),
                )
            )

        return dependencies

    def _parse_cargo_toml(self, file_path: Path) -> list[ExternalDependency]:
        """Parse a Cargo.toml file.

        Args:
            file_path: Path to the Cargo.toml file.

        Returns:
            List of ExternalDependency objects.
        """
        dependencies: list[ExternalDependency] = []
        content = self.read_file(file_path)
        if not content:
            return dependencies

        in_deps = False
        in_dev_deps = False

        for line in content.splitlines():
            line = line.strip()

            if line.startswith("["):
                in_deps = line == "[dependencies]"
                in_dev_deps = line == "[dev-dependencies]"
                continue

            if (in_deps or in_dev_deps) and "=" in line:
                name, _, _ = line.partition("=")
                name = name.strip()
                if name:
                    dependencies.append(
                        ExternalDependency(
                            name=name,
                            version=None,
                            ecosystem="crates",
                            file_path=self.relative_path(file_path),
                            is_dev=in_dev_deps,
                        )
                    )

        return dependencies

    def _parse_go_mod(self, file_path: Path) -> list[ExternalDependency]:
        """Parse a go.mod file.

        Args:
            file_path: Path to the go.mod file.

        Returns:
            List of ExternalDependency objects.
        """
        dependencies: list[ExternalDependency] = []
        content = self.read_file(file_path)
        if not content:
            return dependencies

        in_require = False

        for line in content.splitlines():
            line = line.strip()

            if line.startswith("require"):
                in_require = True
                # Handle single-line require
                match = re.match(r"require\s+(\S+)\s+(\S+)", line)
                if match:
                    dependencies.append(
                        ExternalDependency(
                            name=match.group(1),
                            version=match.group(2),
                            ecosystem="go",
                            file_path=self.relative_path(file_path),
                        )
                    )
                continue

            if line == ")":
                in_require = False
                continue

            if in_require and line and not line.startswith("//"):
                parts = line.split()
                if len(parts) >= 1:
                    name = parts[0]
                    version = parts[1] if len(parts) >= 2 else None
                    dependencies.append(
                        ExternalDependency(
                            name=name,
                            version=version,
                            ecosystem="go",
                            file_path=self.relative_path(file_path),
                        )
                    )

        return dependencies

    def get_python_dependencies(self) -> list[ExternalDependency]:
        """Get all Python dependencies.

        Returns:
            List of Python ExternalDependency objects.
        """
        return [d for d in self.extract_dependencies() if d.ecosystem == "pypi"]

    def get_npm_dependencies(self) -> list[ExternalDependency]:
        """Get all npm dependencies.

        Returns:
            List of npm ExternalDependency objects.
        """
        return [d for d in self.extract_dependencies() if d.ecosystem == "npm"]
