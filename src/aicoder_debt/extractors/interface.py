"""Interface extractor for API calls and endpoints."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from ..constants import JS_PATTERNS, PYTHON_PATTERNS
from ..models import APICall, APIEndpoint
from .base import BaseExtractor

# Hosts that always denote this machine, and therefore this system.
LOOPBACK_HOSTS: frozenset[str] = frozenset(
    {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}
)

# HTTP methods recognised in file-based and Go route declarations.
HTTP_METHODS: tuple[str, ...] = (
    "GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS",
)

# Go source, for router registrations.
GO_PATTERNS: list[str] = ["*.go"]


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
        # The options object must be the one belonging to *this* call, so
        # it is matched immediately after the URL and bounded to a single
        # level of nesting. An unbounded ``.*?`` under re.DOTALL reached
        # into later functions, borrowing their method and swallowing the
        # calls in between.
        "fetch": re.compile(
            r"fetch\s*\(\s*['\"`]([^'\"`]+)['\"`]"
            r"(?:\s*,\s*\{(?P<opts>(?:[^{}]|\{[^{}]*\})*)\})?"
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

        # Routes declared by file location rather than by a call
        endpoints.extend(self._extract_file_based_endpoints())

        # Go routers
        for go_file in self.find_files(GO_PATTERNS):
            content = self.read_file(go_file)
            if content:
                endpoints.extend(self._extract_go_endpoints(go_file, content))

        return endpoints

    def _extract_file_based_endpoints(self) -> list[APIEndpoint]:
        """Extract Next.js routes, which are declared by file path.

        Neither router writes a path anywhere in the source: ``app`` puts
        the route at ``app/api/<segments>/route.ts`` and names the method
        by exporting a function called after it, while ``pages`` puts it
        at ``pages/api/<segments>.ts`` behind one method-agnostic handler.
        A project using either convention therefore declares no endpoints
        the call-site patterns can see, and every call to its own API
        reads as unmatched.
        """
        endpoints: list[APIEndpoint] = []
        suffixes = {".js", ".jsx", ".ts", ".tsx", ".mjs"}

        for base in ("app", "src/app"):
            root = self.project_path / base / "api"
            if not root.is_dir():
                continue
            for route_file in root.rglob("route.*"):
                if route_file.suffix not in suffixes or self._should_skip_path(
                    route_file
                ):
                    continue
                path = self._file_route_path(route_file.parent.relative_to(root))
                content = self.read_file(route_file)
                methods = [
                    m
                    for m in HTTP_METHODS
                    if re.search(
                        rf"export\s+(?:async\s+)?(?:function\s+{m}\b"
                        rf"|const\s+{m}\b)",
                        content,
                    )
                ]
                for method in methods or ["*"]:
                    endpoints.append(
                        APIEndpoint(
                            file_path=self.relative_path(route_file),
                            line_number=1,
                            method=method,
                            path=path,
                            handler=None,
                        )
                    )

        for base in ("pages", "src/pages"):
            root = self.project_path / base / "api"
            if not root.is_dir():
                continue
            for handler_file in root.rglob("*"):
                if (
                    not handler_file.is_file()
                    or handler_file.suffix not in suffixes
                    or self._should_skip_path(handler_file)
                ):
                    continue
                rel = handler_file.relative_to(root).with_suffix("")
                if rel.name == "index":
                    rel = rel.parent
                endpoints.append(
                    APIEndpoint(
                        file_path=self.relative_path(handler_file),
                        line_number=1,
                        method="*",
                        path=self._file_route_path(rel),
                        handler=None,
                    )
                )

        return endpoints

    @staticmethod
    def _file_route_path(relative: Path) -> str:
        """Turn a route directory into a path, normalising parameters.

        ``users/[id]`` becomes ``/api/users/{id}`` so the existing
        parameter handling in pattern building treats it as a wildcard.
        Catch-all segments (``[...slug]``) match any remaining path.
        """
        segments = []
        for part in relative.parts:
            if part in (".", ""):
                continue
            if part.startswith("[") and part.endswith("]"):
                inner = part[1:-1].lstrip(".")
                segments.append("{" + inner + "}")
            else:
                segments.append(part)
        return "/api" + ("/" + "/".join(segments) if segments else "")

    def _extract_go_endpoints(
        self, file_path: Path, content: str
    ) -> list[APIEndpoint]:
        """Extract routes registered through a Go router.

        Handles the common ``router.GET("/path", handler)`` form together
        with ``Group`` prefixes, since a route registered on
        ``api := router.Group("/api")`` serves ``/api/...`` rather than
        the literal string at the call site.
        """
        endpoints: list[APIEndpoint] = []

        prefixes: dict[str, str] = {}
        for match in re.finditer(
            r"(\w+)\s*:?=\s*[\w.]+\.Group\(\s*[\"`]([^\"`]*)[\"`]", content
        ):
            prefixes[match.group(1)] = match.group(2).rstrip("/")

        method_pattern = re.compile(
            r"(\w+)\.(" + "|".join(HTTP_METHODS) + r")\(\s*[\"`]([^\"`]*)[\"`]"
        )
        for match in method_pattern.finditer(content):
            receiver, method, route = match.groups()
            path = prefixes.get(receiver, "") + route
            endpoints.append(
                APIEndpoint(
                    file_path=self.relative_path(file_path),
                    line_number=content[: match.start()].count("\n") + 1,
                    method=method,
                    path=path or "/",
                    handler=None,
                )
            )

        for match in re.finditer(
            r"(\w+)\.(?:HandleFunc|Handle)\(\s*[\"`]([^\"`]*)[\"`]", content
        ):
            receiver, route = match.groups()
            path = prefixes.get(receiver, "") + route
            endpoints.append(
                APIEndpoint(
                    file_path=self.relative_path(file_path),
                    line_number=content[: match.start()].count("\n") + 1,
                    method="*",
                    path=path or "/",
                    handler=None,
                )
            )

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
                    opts = match.groupdict().get("opts") or ""
                    verb = re.search(
                        r"method\s*:\s*['\"`](\w+)['\"`]", opts
                    )
                    method = verb.group(1).upper() if verb else "GET"
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
        """Check whether a call can be attributed to this system.

        Internal means the target is plausibly served by this project, so
        ICR can ask whether a matching endpoint exists. Three forms
        qualify: a host-relative path, an absolute URL on a loopback
        host, and a URL whose host comes from configuration -- the
        ``${API_URL}/api/tasks`` shape is how a frontend is *supposed* to
        reach its own backend, and treating it as unattributable discards
        correct measurements.

        What must not qualify is an explicit third-party host. A key or
        id interpolated into the path does not make the host ours, so
        ``https://api.github.com/orgs/${owner}`` is external: counting it
        as internal guarantees an unmatched call that no local endpoint
        could ever satisfy.

        The residual imprecision is a configured host that points at a
        third party (an LLM API, a managed GraphQL endpoint), or a
        loopback port served by a different product running locally.
        Both still read as internal, because nothing in the source
        distinguishes them from the project's own service.
        """
        url = url.strip()
        if not url:
            return False

        if "://" in url:
            authority = url.split("://", 1)[1].split("/", 1)[0]
            # Strip any credentials, keeping the host[:port] portion.
            authority = authority.rsplit("@", 1)[-1]
            if "$" in authority or "{" in authority:
                # Host supplied by configuration; conventionally our own.
                return True
            host = authority
            if host.startswith("["):  # bracketed IPv6 literal
                host = host.partition("]")[0] + "]"
            elif host.count(":") == 1:
                host = host.rsplit(":", 1)[0]
            return host.lower() in LOOPBACK_HOSTS

        if url.startswith("/") or url.startswith("./"):
            return True

        # A leading placeholder is a configured base URL for our own API.
        if url.startswith("$") or url.startswith("{"):
            return True
        if "process.env" in url or "os.environ" in url:
            return True

        # Extractors capture the first token after the call parenthesis,
        # which for ``requests.get(video_url)`` is an identifier rather
        # than a URL. Require a path separator before treating it as one.
        return "/" in url

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
