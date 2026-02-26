"""Interface extractor for API calls and endpoints."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from ..constants import JS_PATTERNS, PYTHON_PATTERNS
from ..models import APICall, APIEndpoint
from .base import BaseExtractor


class InterfaceExtractor(BaseExtractor):
    """Extract API calls and endpoint definitions from code."""

    # Python HTTP client patterns
    PYTHON_HTTP_PATTERNS = {
        "requests": re.compile(
            r"requests\.(get|post|put|delete|patch|head|options)\s*\(\s*['\"]?([^'\")\s,]+)",
            re.IGNORECASE,
        ),
        "httpx": re.compile(
            r"httpx\.(get|post|put|delete|patch|head|options)\s*\(\s*['\"]?([^'\")\s,]+)",
            re.IGNORECASE,
        ),
        "aiohttp": re.compile(
            r"session\.(get|post|put|delete|patch|head|options)\s*\(\s*['\"]?([^'\")\s,]+)",
            re.IGNORECASE,
        ),
        "urllib": re.compile(
            r"urlopen\s*\(\s*['\"]([^'\"]+)['\"]",
        ),
    }

    # Python endpoint patterns (Flask, FastAPI, Django)
    PYTHON_ENDPOINT_PATTERNS = {
        "flask": re.compile(
            r"@\w+\.route\s*\(\s*['\"]([^'\"]+)['\"](?:.*?methods\s*=\s*\[([^\]]+)\])?",
            re.DOTALL,
        ),
        "fastapi": re.compile(
            r"@\w+\.(get|post|put|delete|patch|options|head)\s*\(\s*['\"]([^'\"]+)['\"]",
        ),
        "django": re.compile(
            r"path\s*\(\s*['\"]([^'\"]+)['\"]",
        ),
    }

    # JavaScript HTTP client patterns
    JS_HTTP_PATTERNS = {
        "axios": re.compile(
            r"axios\.(get|post|put|delete|patch)\s*\(\s*['\"`]([^'\"`]+)['\"`]",
            re.IGNORECASE,
        ),
        "fetch": re.compile(
            r"fetch\s*\(\s*['\"`]([^'\"`]+)['\"`](?:.*?method\s*:\s*['\"`](\w+)['\"`])?",
            re.DOTALL,
        ),
        "request": re.compile(
            r"request\.(get|post|put|delete|patch)\s*\(\s*['\"`]([^'\"`]+)['\"`]",
            re.IGNORECASE,
        ),
    }

    # JavaScript endpoint patterns (Express, Koa, etc.)
    JS_ENDPOINT_PATTERNS = {
        "express": re.compile(
            r"(?:app|router)\.(get|post|put|delete|patch|all)\s*\(\s*['\"`]([^'\"`]+)['\"`]",
        ),
        "nestjs": re.compile(
            r"@(Get|Post|Put|Delete|Patch)\s*\(\s*['\"`]?([^'\"`)\s]*)['\"`]?\s*\)",
        ),
        "koa": re.compile(
            r"router\.(get|post|put|delete|patch)\s*\(\s*['\"`]([^'\"`]+)['\"`]",
        ),
    }

    def __init__(self, project_path: str | Path) -> None:
        """Initialize the interface extractor.

        Args:
            project_path: Path to the project directory.
        """
        super().__init__(project_path)

    def extract_nodes(self) -> list:
        """Not used for interface extraction."""
        return []

    def extract_edges(self, nodes: list) -> list:
        """Not used for interface extraction."""
        return []

    def extract_api_calls(self) -> list[APICall]:
        """Extract all API calls from the project.

        Returns:
            List of APICall objects.
        """
        calls: list[APICall] = []

        # Process Python files
        for py_file in self.find_files(PYTHON_PATTERNS):
            content = self.read_file(py_file)
            if content:
                calls.extend(self._extract_python_calls(py_file, content))

        # Process JavaScript files
        for js_file in self.find_files(JS_PATTERNS):
            content = self.read_file(js_file)
            if content:
                calls.extend(self._extract_js_calls(js_file, content))

        return calls

    def extract_endpoints(self) -> list[APIEndpoint]:
        """Extract all API endpoint definitions from the project.

        Returns:
            List of APIEndpoint objects.
        """
        endpoints: list[APIEndpoint] = []

        # Process Python files
        for py_file in self.find_files(PYTHON_PATTERNS):
            content = self.read_file(py_file)
            if content:
                endpoints.extend(self._extract_python_endpoints(py_file, content))

        # Process JavaScript files
        for js_file in self.find_files(JS_PATTERNS):
            content = self.read_file(js_file)
            if content:
                endpoints.extend(self._extract_js_endpoints(js_file, content))

        return endpoints

    def _extract_python_calls(self, file_path: Path, content: str) -> list[APICall]:
        """Extract API calls from Python code.

        Args:
            file_path: Path to the Python file.
            content: File content.

        Returns:
            List of APICall objects.
        """
        calls: list[APICall] = []

        for lib_name, pattern in self.PYTHON_HTTP_PATTERNS.items():
            for match in pattern.finditer(content):
                line_num = content[: match.start()].count("\n") + 1

                if lib_name == "urllib":
                    method = "GET"
                    endpoint = match.group(1)
                else:
                    method = match.group(1).upper()
                    endpoint = match.group(2)

                is_internal = self._is_internal_url(endpoint)

                calls.append(
                    APICall(
                        file_path=self.relative_path(file_path),
                        line_number=line_num,
                        method=method,
                        endpoint=endpoint,
                        is_internal=is_internal,
                    )
                )

        return calls

    def _extract_python_endpoints(
        self, file_path: Path, content: str
    ) -> list[APIEndpoint]:
        """Extract API endpoints from Python code.

        Args:
            file_path: Path to the Python file.
            content: File content.

        Returns:
            List of APIEndpoint objects.
        """
        endpoints: list[APIEndpoint] = []

        # Flask routes
        for match in self.PYTHON_ENDPOINT_PATTERNS["flask"].finditer(content):
            path = match.group(1)
            methods_str = match.group(2)
            line_num = content[: match.start()].count("\n") + 1

            methods = ["GET"]
            if methods_str:
                methods = [m.strip().strip("'\"") for m in methods_str.split(",")]

            for method in methods:
                endpoints.append(
                    APIEndpoint(
                        file_path=self.relative_path(file_path),
                        line_number=line_num,
                        method=method.upper(),
                        path=path,
                        handler=self._find_handler_name(content, match.end()),
                    )
                )

        # FastAPI routes
        for match in self.PYTHON_ENDPOINT_PATTERNS["fastapi"].finditer(content):
            method = match.group(1).upper()
            path = match.group(2)
            line_num = content[: match.start()].count("\n") + 1

            endpoints.append(
                APIEndpoint(
                    file_path=self.relative_path(file_path),
                    line_number=line_num,
                    method=method,
                    path=path,
                    handler=self._find_handler_name(content, match.end()),
                )
            )

        # Django URLs
        for match in self.PYTHON_ENDPOINT_PATTERNS["django"].finditer(content):
            path = match.group(1)
            line_num = content[: match.start()].count("\n") + 1

            endpoints.append(
                APIEndpoint(
                    file_path=self.relative_path(file_path),
                    line_number=line_num,
                    method="*",  # Django doesn't specify method in URL
                    path=path,
                )
            )

        return endpoints

    def _extract_js_calls(self, file_path: Path, content: str) -> list[APICall]:
        """Extract API calls from JavaScript code.

        Args:
            file_path: Path to the JavaScript file.
            content: File content.

        Returns:
            List of APICall objects.
        """
        calls: list[APICall] = []

        for lib_name, pattern in self.JS_HTTP_PATTERNS.items():
            for match in pattern.finditer(content):
                line_num = content[: match.start()].count("\n") + 1

                if lib_name == "fetch":
                    endpoint = match.group(1)
                    method = match.group(2).upper() if match.group(2) else "GET"
                else:
                    method = match.group(1).upper()
                    endpoint = match.group(2)

                is_internal = self._is_internal_url(endpoint)

                calls.append(
                    APICall(
                        file_path=self.relative_path(file_path),
                        line_number=line_num,
                        method=method,
                        endpoint=endpoint,
                        is_internal=is_internal,
                    )
                )

        return calls

    def _extract_js_endpoints(
        self, file_path: Path, content: str
    ) -> list[APIEndpoint]:
        """Extract API endpoints from JavaScript code.

        Args:
            file_path: Path to the JavaScript file.
            content: File content.

        Returns:
            List of APIEndpoint objects.
        """
        endpoints: list[APIEndpoint] = []

        for framework, pattern in self.JS_ENDPOINT_PATTERNS.items():
            for match in pattern.finditer(content):
                method = match.group(1).upper()
                path = match.group(2) if match.group(2) else "/"
                line_num = content[: match.start()].count("\n") + 1

                endpoints.append(
                    APIEndpoint(
                        file_path=self.relative_path(file_path),
                        line_number=line_num,
                        method=method,
                        path=path,
                    )
                )

        return endpoints

    def _is_internal_url(self, url: str) -> bool:
        """Check if a URL is internal (relative or localhost).

        Args:
            url: URL to check.

        Returns:
            True if the URL is internal.
        """
        # Check for template variables
        if "${" in url or "{" in url or "{{" in url:
            return True

        # Check for relative URLs
        if url.startswith("/") or url.startswith("./"):
            return True

        # Check for localhost
        if "localhost" in url or "127.0.0.1" in url:
            return True

        # Check for environment variable placeholders
        if url.startswith("$") or "process.env" in url or "os.environ" in url:
            return True

        return False

    def _find_handler_name(self, content: str, start_pos: int) -> str | None:
        """Find the handler function name after a decorator.

        Args:
            content: File content.
            start_pos: Position after the decorator.

        Returns:
            Handler function name or None.
        """
        # Look for def/async def after the decorator
        remaining = content[start_pos:start_pos + 200]
        match = re.search(r"(?:async\s+)?def\s+(\w+)", remaining)
        if match:
            return match.group(1)
        return None
