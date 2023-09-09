import sys
from typing import Any
from unittest.mock import patch

import pytest

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


@pytest.mark.skipif(sys.version_info < (3, 10), reason="Only for python 3.10+")
def test_dependency_swap_annotated() -> None:
    """
    Test that dependency classes are swapped.

    This test checks that if function depends on FastAPI depends, it will
    be swapped and resolved.
    """
    from typing import Annotated

    with patch("taskiq_dependencies.graph.FastapiDepends", MyFastapiDepends):

        def func_a() -> int:
            return 1

        def func_b(dep_a: Annotated[int, MyFastapiDepends(func_a)]) -> int:  # type: ignore
            return dep_a

        with DependencyGraph(func_b).sync_ctx() as ctx:
            kwargs = ctx.resolve_kwargs()

        assert kwargs == {"dep_a": 1}
