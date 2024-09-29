"""
Taskiq dependencies package.

This package is used to add dependency injection
in your project easily.

Github repo: https://github.com/taskiq-python/taskiq-dependencies
"""

from taskiq_dependencies.dependency import Depends
from taskiq_dependencies.graph import DependencyGraph
from taskiq_dependencies.utils import ParamInfo

__all__ = ["DependencyGraph", "Depends", "ParamInfo"]
