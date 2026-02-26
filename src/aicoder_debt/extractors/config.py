"""Configuration extractor for definitions and references."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from ..constants import CONFIG_PATTERNS, JS_PATTERNS, PYTHON_PATTERNS
from ..models import ConfigDefinition, ConfigReference
from .base import BaseExtractor


class ConfigExtractor(BaseExtractor):
    """Extract configuration definitions and references from code."""

    # Python config reference patterns
    PYTHON_CONFIG_PATTERNS = [
        # os.environ / os.getenv
        re.compile(r"os\.environ(?:\.get)?\s*\[\s*['\"](\w+)['\"]\s*\]"),
        re.compile(r"os\.getenv\s*\(\s*['\"](\w+)['\"]"),
        re.compile(r"os\.environ\.get\s*\(\s*['\"](\w+)['\"]"),
        # Python-decouple
        re.compile(r"config\s*\(\s*['\"](\w+)['\"]"),
        # Pydantic settings
        re.compile(r"Settings\s*\(\s*\)"),
    ]

    # JavaScript config reference patterns
    JS_CONFIG_PATTERNS = [
        # process.env
        re.compile(r"process\.env\.(\w+)"),
        re.compile(r"process\.env\s*\[\s*['\"](\w+)['\"]\s*\]"),
        # dotenv
        re.compile(r"dotenv\.config\s*\("),
    ]

    def __init__(self, project_path: str | Path) -> None:
        """Initialize the config extractor.

        Args:
            project_path: Path to the project directory.
        """
        super().__init__(project_path)
        self._definitions: dict[str, ConfigDefinition] = {}

    def extract_nodes(self) -> list:
        """Not used for config extraction."""
        return []

    def extract_edges(self, nodes: list) -> list:
        """Not used for config extraction."""
        return []

    def extract_definitions(self) -> list[ConfigDefinition]:
        """Extract all configuration definitions from the project.

        Returns:
            List of ConfigDefinition objects.
        """
        definitions: list[ConfigDefinition] = []

        # Find config files
        config_files = self.find_files(CONFIG_PATTERNS)

        for config_file in config_files:
            file_name = config_file.name.lower()

            if file_name.startswith(".env"):
                definitions.extend(self._parse_env_file(config_file))
            elif file_name.endswith((".yaml", ".yml")):
                definitions.extend(self._parse_yaml_file(config_file))
            elif file_name.endswith(".json"):
                definitions.extend(self._parse_json_file(config_file))
            elif file_name.endswith(".toml"):
                definitions.extend(self._parse_toml_file(config_file))
            elif file_name.endswith((".ini", ".cfg")):
                definitions.extend(self._parse_ini_file(config_file))

        # Store for reference resolution
        for defn in definitions:
            self._definitions[defn.key] = defn

        return definitions

    def extract_references(self) -> list[ConfigReference]:
        """Extract all configuration references from code.

        Returns:
            List of ConfigReference objects.
        """
        references: list[ConfigReference] = []

        # Process Python files
        for py_file in self.find_files(PYTHON_PATTERNS):
            content = self.read_file(py_file)
            if content:
                references.extend(self._extract_python_refs(py_file, content))

        # Process JavaScript files
        for js_file in self.find_files(JS_PATTERNS):
            content = self.read_file(js_file)
            if content:
                references.extend(self._extract_js_refs(js_file, content))

        return references

    def _parse_env_file(self, file_path: Path) -> list[ConfigDefinition]:
        """Parse a .env file.

        Args:
            file_path: Path to the .env file.

        Returns:
            List of ConfigDefinition objects.
        """
        definitions: list[ConfigDefinition] = []
        content = self.read_file(file_path)
        if not content:
            return definitions

        for line_num, line in enumerate(content.splitlines(), 1):
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Parse KEY=VALUE
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")

                definitions.append(
                    ConfigDefinition(
                        file_path=self.relative_path(file_path),
                        key=key,
                        value=value if value else None,
                        line_number=line_num,
                    )
                )

        return definitions

    def _parse_yaml_file(self, file_path: Path) -> list[ConfigDefinition]:
        """Parse a YAML config file.

        Args:
            file_path: Path to the YAML file.

        Returns:
            List of ConfigDefinition objects.
        """
        definitions: list[ConfigDefinition] = []
        content = self.read_file(file_path)
        if not content:
            return definitions

        try:
            data = yaml.safe_load(content)
            if isinstance(data, dict):
                definitions.extend(
                    self._flatten_dict(data, file_path, "")
                )
        except yaml.YAMLError:
            pass

        return definitions

    def _parse_json_file(self, file_path: Path) -> list[ConfigDefinition]:
        """Parse a JSON config file.

        Args:
            file_path: Path to the JSON file.

        Returns:
            List of ConfigDefinition objects.
        """
        import json

        definitions: list[ConfigDefinition] = []
        content = self.read_file(file_path)
        if not content:
            return definitions

        try:
            data = json.loads(content)
            if isinstance(data, dict):
                definitions.extend(
                    self._flatten_dict(data, file_path, "")
                )
        except json.JSONDecodeError:
            pass

        return definitions

    def _parse_toml_file(self, file_path: Path) -> list[ConfigDefinition]:
        """Parse a TOML config file.

        Args:
            file_path: Path to the TOML file.

        Returns:
            List of ConfigDefinition objects.
        """
        definitions: list[ConfigDefinition] = []

        # TOML parsing requires external library, use basic regex
        content = self.read_file(file_path)
        if not content:
            return definitions

        for line_num, line in enumerate(content.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("["):
                continue

            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")

                definitions.append(
                    ConfigDefinition(
                        file_path=self.relative_path(file_path),
                        key=key,
                        value=value if value else None,
                        line_number=line_num,
                    )
                )

        return definitions

    def _parse_ini_file(self, file_path: Path) -> list[ConfigDefinition]:
        """Parse an INI/CFG config file.

        Args:
            file_path: Path to the INI file.

        Returns:
            List of ConfigDefinition objects.
        """
        definitions: list[ConfigDefinition] = []
        content = self.read_file(file_path)
        if not content:
            return definitions

        current_section = ""
        for line_num, line in enumerate(content.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith(("#", ";")):
                continue

            # Section header
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1] + "."
                continue

            # Key-value pair
            if "=" in line:
                key, _, value = line.partition("=")
                key = current_section + key.strip()
                value = value.strip()

                definitions.append(
                    ConfigDefinition(
                        file_path=self.relative_path(file_path),
                        key=key,
                        value=value if value else None,
                        line_number=line_num,
                    )
                )

        return definitions

    def _flatten_dict(
        self,
        data: dict[str, Any],
        file_path: Path,
        prefix: str,
    ) -> list[ConfigDefinition]:
        """Flatten a nested dictionary into config definitions.

        Args:
            data: Dictionary to flatten.
            file_path: Source file path.
            prefix: Key prefix.

        Returns:
            List of ConfigDefinition objects.
        """
        definitions: list[ConfigDefinition] = []

        for key, value in data.items():
            key = str(key)
            full_key = f"{prefix}{key}" if prefix else key

            if isinstance(value, dict):
                definitions.extend(
                    self._flatten_dict(value, file_path, f"{full_key}.")
                )
            else:
                str_value = str(value) if value is not None else None
                definitions.append(
                    ConfigDefinition(
                        file_path=self.relative_path(file_path),
                        key=full_key,
                        value=str_value,
                    )
                )

        return definitions

    def _extract_python_refs(
        self, file_path: Path, content: str
    ) -> list[ConfigReference]:
        """Extract config references from Python code.

        Args:
            file_path: Path to the Python file.
            content: File content.

        Returns:
            List of ConfigReference objects.
        """
        references: list[ConfigReference] = []

        for pattern in self.PYTHON_CONFIG_PATTERNS:
            for match in pattern.finditer(content):
                if match.lastindex and match.lastindex >= 1:
                    key = match.group(1)
                    line_num = content[: match.start()].count("\n") + 1

                    resolved = key in self._definitions

                    references.append(
                        ConfigReference(
                            file_path=self.relative_path(file_path),
                            line_number=line_num,
                            key=key,
                            resolved=resolved,
                        )
                    )

        return references

    def _extract_js_refs(
        self, file_path: Path, content: str
    ) -> list[ConfigReference]:
        """Extract config references from JavaScript code.

        Args:
            file_path: Path to the JavaScript file.
            content: File content.

        Returns:
            List of ConfigReference objects.
        """
        references: list[ConfigReference] = []

        for pattern in self.JS_CONFIG_PATTERNS:
            for match in pattern.finditer(content):
                if match.lastindex and match.lastindex >= 1:
                    key = match.group(1)
                    line_num = content[: match.start()].count("\n") + 1

                    resolved = key in self._definitions

                    references.append(
                        ConfigReference(
                            file_path=self.relative_path(file_path),
                            line_number=line_num,
                            key=key,
                            resolved=resolved,
                        )
                    )

        return references
