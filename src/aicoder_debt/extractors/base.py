"""Base extractor class for AI Coder Debt analysis."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..constants import MAX_FILE_SIZE, SKIP_DIRS
from ..models import DDGEdge, DDGNode


class BaseExtractor(ABC):
    """Abstract base class for code extractors."""

    def __init__(self, project_path: str | Path) -> None:
        """Initialize the extractor.

        Args:
            project_path: Path to the project directory to analyze.
        """
        self.project_path = Path(project_path).resolve()
        if not self.project_path.exists():
            raise FileNotFoundError(f"Project path does not exist: {self.project_path}")
        if not self.project_path.is_dir():
            raise NotADirectoryError(f"Project path is not a directory: {self.project_path}")

    @abstractmethod
    def extract_nodes(self) -> list[DDGNode]:
        """Extract nodes from the project.

        Returns:
            List of DDGNode objects representing components.
        """
        pass

    @abstractmethod
    def extract_edges(self, nodes: list[DDGNode]) -> list[DDGEdge]:
        """Extract edges between nodes.

        Args:
            nodes: List of previously extracted nodes.

        Returns:
            List of DDGEdge objects representing dependencies.
        """
        pass

    def find_files(self, patterns: list[str]) -> list[Path]:
        """Find files matching the given patterns.

        Args:
            patterns: List of glob patterns to match.

        Returns:
            List of matching file paths.
        """
        files: list[Path] = []
        for pattern in patterns:
            for file_path in self.project_path.rglob(pattern):
                if self._should_skip_path(file_path):
                    continue
                if file_path.is_file() and self._is_valid_file(file_path):
                    files.append(file_path)
        return sorted(set(files))

    def _should_skip_path(self, path: Path) -> bool:
        """Check if a path should be skipped.

        Args:
            path: Path to check.

        Returns:
            True if the path should be skipped.
        """
        for part in path.parts:
            if part in SKIP_DIRS:
                return True
            # Check for wildcard patterns like *.egg-info
            for skip_pattern in SKIP_DIRS:
                if "*" in skip_pattern:
                    import fnmatch
                    if fnmatch.fnmatch(part, skip_pattern):
                        return True
        return False

    def _is_valid_file(self, path: Path) -> bool:
        """Check if a file is valid for analysis.

        Args:
            path: Path to the file.

        Returns:
            True if the file is valid for analysis.
        """
        try:
            return path.stat().st_size <= MAX_FILE_SIZE
        except OSError:
            return False

    def read_file(self, path: Path) -> str:
        """Read file contents safely.

        Args:
            path: Path to the file.

        Returns:
            File contents as string, or empty string on error.
        """
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            return ""

    def relative_path(self, path: Path) -> str:
        """Get path relative to project root.

        Args:
            path: Absolute path.

        Returns:
            Path relative to project root.
        """
        try:
            return str(path.relative_to(self.project_path))
        except ValueError:
            return str(path)

    def get_project_info(self) -> dict[str, Any]:
        """Get basic project information.

        Returns:
            Dictionary with project information.
        """
        return {
            "path": str(self.project_path),
            "name": self.project_path.name,
        }
