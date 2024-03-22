import sys
from contextlib import asynccontextmanager, contextmanager

import pytest

if sys.version_info < (3, 10):
    pytest.skip("Annotated is available only for python 3.10+", allow_module_level=True)

from typing import Annotated, AsyncGenerator, Generator, Generic, Tuple, TypeVar

from taskiq_dependencies import DependencyGraph, Depends


def test_annotated_func() -> None:
    def get_int() -> int:
        return 1

    def target_func(dep: Annotated[int, Depends(get_int)]) -> int:
        return dep

    with DependencyGraph(target_func).sync_ctx() as ctx:
        res = target_func(**ctx.resolve_kwargs())
    assert res == 1


def test_annotated_class() -> None:
    class TestClass:
        pass

    def target_func(dep: Annotated[TestClass, Depends()]) -> TestClass:
        return dep

    with DependencyGraph(target_func).sync_ctx() as ctx:
        res = target_func(**ctx.resolve_kwargs())
    assert isinstance(res, TestClass)


def test_annotated_generic() -> None:
    _T = TypeVar("_T")

    class MyClass:
        pass

    class MainClass(Generic[_T]):
        def __init__(self, val: _T = Depends()) -> None:
            self.val = val

    def test_func(a: Annotated[MainClass[MyClass], Depends()]) -> MyClass:
        return a.val

    with DependencyGraph(target=test_func).sync_ctx(exception_propagation=False) as g:
        value = test_func(**(g.resolve_kwargs()))

    assert isinstance(value, MyClass)


@pytest.mark.anyio
async def test_annotated_gen() -> None:
    opened = False
    closed = False

    def my_gen() -> Generator[int, None, None]:
        nonlocal opened, closed
        opened = True

        yield 1

        closed = True

    def test_func(dep: Annotated[int, Depends(my_gen)]) -> int:
        return dep

    with DependencyGraph(target=test_func).sync_ctx() as sctx:
        value = test_func(**sctx.resolve_kwargs())
        assert value == 1

    assert opened and closed

    opened = False
    closed = False

    async with DependencyGraph(target=test_func).async_ctx() as actx:
        value = test_func(**(await actx.resolve_kwargs()))
        assert value == 1

    assert opened and closed


@pytest.mark.anyio
async def test_annotated_asyncgen() -> None:
    opened = False
    closed = False

    async def my_gen() -> AsyncGenerator[int, None]:
        nonlocal opened, closed
        opened = True

        yield 1

        closed = True

    def test_func(dep: Annotated[int, Depends(my_gen)]) -> int:
        return dep

    async with DependencyGraph(target=test_func).async_ctx() as g:
        value = test_func(**(await g.resolve_kwargs()))
        assert value == 1

    assert opened and closed


@pytest.mark.anyio
async def test_annotated_manager() -> None:
    opened = False
    closed = False

    @contextmanager
    def my_gen() -> Generator[int, None, None]:
        nonlocal opened, closed
        opened = True

        try:
            yield 1
        finally:
            closed = True

    def test_func(dep: Annotated[int, Depends(my_gen)]) -> int:
        return dep

    with DependencyGraph(target=test_func).sync_ctx() as sctx:
        value = test_func(**sctx.resolve_kwargs())
        assert value == 1

    assert opened and closed

    opened = False
    closed = False

    async with DependencyGraph(target=test_func).async_ctx() as actx:
        value = test_func(**(await actx.resolve_kwargs()))
        assert value == 1

    assert opened and closed


@pytest.mark.anyio
async def test_annotated_asyncmanager() -> None:
    opened = False
    closed = False

    @asynccontextmanager
    async def my_gen() -> AsyncGenerator[int, None]:
        nonlocal opened, closed
        opened = True

        try:
            yield 1
        finally:
            closed = True

    def test_func(dep: Annotated[int, Depends(my_gen)]) -> int:
        return dep

    async with DependencyGraph(target=test_func).async_ctx() as g:
        value = test_func(**(await g.resolve_kwargs()))
        assert value == 1

    assert opened and closed


def test_multiple() -> None:
    class TestClass:
        pass

    MyType = Annotated[TestClass, Depends(use_cache=False)]

    def test_func(dep: MyType, dep2: MyType) -> Tuple[MyType, MyType]:
        return dep, dep2

    with DependencyGraph(target=test_func).sync_ctx(exception_propagation=False) as g:
        value = test_func(**(g.resolve_kwargs()))
        assert value[0] != value[1]
        assert isinstance(value[0], TestClass)
        assert isinstance(value[1], TestClass)


def test_multiple_with_cache() -> None:
    class TestClass:
        pass

    MyType = Annotated[TestClass, Depends()]

    def test_func(dep: MyType, dep2: MyType) -> Tuple[MyType, MyType]:
        return dep, dep2

    with DependencyGraph(target=test_func).sync_ctx(exception_propagation=False) as g:
        value = test_func(**(g.resolve_kwargs()))
        assert id(value[0]) == id(value[1])
        assert isinstance(value[0], TestClass)


def test_override() -> None:
    class TestClass:
        pass

    MyType = Annotated[TestClass, Depends()]

    def test_func(
        dep: MyType,
        dep2: Annotated[MyType, Depends(use_cache=False)],
    ) -> Tuple[MyType, MyType]:
        return dep, dep2

    with DependencyGraph(target=test_func).sync_ctx(exception_propagation=False) as g:
        value = test_func(**(g.resolve_kwargs()))
        assert id(value[0]) != id(value[1])
        assert isinstance(value[0], TestClass)
        assert isinstance(value[1], TestClass)


def test_skip_not_decorated_managers() -> None:
    """
    Test that synct context skip context managers.

    Tests that even is class implements a context manager,
    it won't be called during the context resolution,
    because it's not annotated with contextmanager decorator.
    """

    class TestCM:
        def __init__(self) -> None:
            self.opened = False

        def __enter__(self) -> None:
            self.opened = True

        def __exit__(self, *args: object) -> None:
            pass

    test_cm = TestCM()

    def get_test_cm() -> TestCM:
        nonlocal test_cm
        return test_cm

    def target(cm: Annotated[TestCM, Depends(get_test_cm)]) -> None:
        pass

    graph = DependencyGraph(target=target)
    with graph.sync_ctx() as ctx:
        kwargs = ctx.resolve_kwargs()
        assert kwargs["cm"] == test_cm
        assert not test_cm.opened


@pytest.mark.anyio
async def test_skip_not_decorated_async_managers() -> None:
    """
    Test that synct context skip context managers.

    Tests that even is class implements a context manager,
    it won't be called during the context resolution,
    because it's not annotated with contextmanager decorator.
    """

    class TestACM:
        def __init__(self) -> None:
            self.opened = False

        async def __aenter__(self) -> None:
            self.opened = True

        async def __aexit__(self, *args: object) -> None:
            pass

    test_acm = TestACM()

    def get_test_acm() -> TestACM:
        nonlocal test_acm
        return test_acm

    def target(acm: Annotated[TestACM, Depends(get_test_acm)]) -> None:
        pass

    graph = DependencyGraph(target=target)
    async with graph.async_ctx() as ctx:
        kwargs = await ctx.resolve_kwargs()
        assert kwargs["acm"] == test_acm
        assert not test_acm.opened
