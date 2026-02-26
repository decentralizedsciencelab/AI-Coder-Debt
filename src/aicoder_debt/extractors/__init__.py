"""Extractors for AI Coder Debt analysis."""

from .ast_utils import (
    CallInfo,
    ClassInfo,
    EnvAccess,
    ImportInfo,
    RouteInfo,
    find_class_definitions,
    find_decorator_routes,
    find_env_access,
    find_framework_apps,
    find_function_calls,
    find_imports,
    has_call,
    has_decorator,
    has_import,
    safe_parse,
    safe_parse_sections,
)
from .base import BaseExtractor
from .config import ConfigExtractor
from .ddg import DDGExtractor
from .dependency import DependencyExtractor
from .docker import DockerComposeExtractor
from .interface import InterfaceExtractor
from .javascript import JavaScriptExtractor
from .python_analyzer import PythonExtractor
from .reference import ReferenceExtractor
from .solidity import SolidityExtractor

__all__ = [
    # AST utilities
    "safe_parse",
    "safe_parse_sections",
    "find_imports",
    "has_import",
    "find_function_calls",
    "has_call",
    "find_decorator_routes",
    "has_decorator",
    "find_env_access",
    "find_class_definitions",
    "find_framework_apps",
    "ImportInfo",
    "CallInfo",
    "RouteInfo",
    "EnvAccess",
    "ClassInfo",
    # Extractor classes
    "BaseExtractor",
    "DDGExtractor",
    "DockerComposeExtractor",
    "SolidityExtractor",
    "PythonExtractor",
    "JavaScriptExtractor",
    "InterfaceExtractor",
    "ConfigExtractor",
    "ReferenceExtractor",
    "DependencyExtractor",
]
