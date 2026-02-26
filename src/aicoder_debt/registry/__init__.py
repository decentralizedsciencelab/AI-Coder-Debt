"""Package registry checkers for AI Coder Debt."""

from .npm import NpmRegistry
from .pypi import PyPIRegistry

__all__ = [
    "NpmRegistry",
    "PyPIRegistry",
]
