from typing import Any
from unittest.mock import patch

from taskiq_dependencies import DependencyGraph


class MyFastapiDepends:
    def __init__(self, dependency: Any, use_cache: bool = False) -> None:
        self.dependency = dependency
        self.use_cache = use_cache


def test_dependency_swap() -> None:
    """
    Test that dependency classes are swapped.

    This test checks that if function depends on FastAPI depends, it will
    be swapped and resolved.
    """
    with patch("taskiq_dependencies.graph.FastapiDepends", MyFastapiDepends):

        def func_a() -> int:
            return 1

        def func_b(dep_a: int = MyFastapiDepends(func_a)) -> int:  # type: ignore
            return dep_a

        with DependencyGraph(func_b).sync_ctx() as ctx:
            kwargs = ctx.resolve_kwargs()

        assert kwargs == {"dep_a": 1}
