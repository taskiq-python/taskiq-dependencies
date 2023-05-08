import asyncio
import uuid
from typing import Any, AsyncGenerator, Generator, Generic, TypeVar

import pytest

from taskiq_dependencies import DependencyGraph, Depends, ParamInfo

_T = TypeVar("_T")


@pytest.mark.anyio
async def test_dependency_successful() -> None:
    """Test that a simlpe dependencies work."""

    def dep1() -> int:
        return 1

    def testfunc(a: int = Depends(dep1)) -> int:
        return a

    with DependencyGraph(testfunc).sync_ctx({}) as sctx:
        assert sctx.resolve_kwargs() == {"a": 1}

    async with DependencyGraph(testfunc).async_ctx({}) as actx:
        assert await actx.resolve_kwargs() == {"a": 1}


@pytest.mark.anyio
async def test_dependency_async_successful() -> None:
    """Test that async dependencies work fine."""

    async def dep1() -> int:
        await asyncio.sleep(0.001)
        return 1

    def testfunc(a: int = Depends(dep1)) -> int:
        return a

    with DependencyGraph(testfunc).sync_ctx({}) as sctx:
        with pytest.raises(RuntimeError):
            assert sctx.resolve_kwargs() == {"a": 1}

    async with DependencyGraph(testfunc).async_ctx({}) as actx:
        assert await actx.resolve_kwargs() == {"a": 1}


@pytest.mark.anyio
async def test_dependency_gen_successful() -> None:
    """Tests that generators work as expected."""
    starts = 0
    closes = 0

    def dep1() -> Generator[int, None, None]:
        nonlocal starts  # noqa: WPS420
        nonlocal closes  # noqa: WPS420

        starts += 1

        yield 1

        closes += 1

    def testfunc(a: int = Depends(dep1)) -> int:
        return a

    with DependencyGraph(testfunc).sync_ctx({}) as sctx:
        assert sctx.resolve_kwargs() == {"a": 1}
        assert starts == 1
        assert closes == 0
        starts = 0
    assert closes == 1
    closes = 0

    async with DependencyGraph(testfunc).async_ctx({}) as actx:
        assert await actx.resolve_kwargs() == {"a": 1}
        assert starts == 1
        assert closes == 0
    assert closes == 1


@pytest.mark.anyio
async def test_dependency_async_gen_successful() -> None:
    """This test checks that async generators work."""
    starts = 0
    closes = 0

    async def dep1() -> AsyncGenerator[int, None]:
        nonlocal starts  # noqa: WPS420
        nonlocal closes  # noqa: WPS420

        await asyncio.sleep(0.001)
        starts += 1

        yield 1

        await asyncio.sleep(0.001)
        closes += 1

    def testfunc(a: int = Depends(dep1)) -> int:
        return a

    with DependencyGraph(testfunc).sync_ctx({}) as sctx:
        with pytest.raises(RuntimeError):
            assert sctx.resolve_kwargs() == {"a": 1}

    async with DependencyGraph(testfunc).async_ctx({}) as actx:
        assert await actx.resolve_kwargs() == {"a": 1}
        assert starts == 1
        assert closes == 0
    assert closes == 1


@pytest.mark.anyio
async def test_dependency_subdeps() -> None:
    """Tests how subdependencies work."""

    def dep1() -> int:
        return 1

    def dep2(a: int = Depends(dep1)) -> int:
        return a + 1

    def testfunc(a: int = Depends(dep2)) -> int:
        return a

    with DependencyGraph(testfunc).sync_ctx({}) as sctx:
        assert sctx.resolve_kwargs() == {"a": 2}

    async with DependencyGraph(testfunc).async_ctx({}) as actx:
        assert await actx.resolve_kwargs() == {"a": 2}


@pytest.mark.anyio
async def test_dependency_caches() -> None:
    """
    Tests how caches work.

    This test checks that
    if multiple functions depend on one function,
    This function must be calculated only once.
    """
    dep_exec = 0

    def dep1() -> int:
        nonlocal dep_exec  # noqa: WPS420
        dep_exec += 1

        return 1

    def dep2(a: int = Depends(dep1)) -> int:
        return a + 1

    def dep3(a: int = Depends(dep1)) -> int:
        return a + 1

    def testfunc(
        a: int = Depends(dep2),
        b: int = Depends(dep3),
    ) -> int:
        return a + b

    with DependencyGraph(testfunc).sync_ctx({}) as sctx:
        assert sctx.resolve_kwargs() == {"a": 2, "b": 2}

    assert dep_exec == 1
    dep_exec = 0

    async with DependencyGraph(testfunc).async_ctx({}) as actx:
        assert await actx.resolve_kwargs() == {"a": 2, "b": 2}

    assert dep_exec == 1


@pytest.mark.anyio
async def test_dependency_subgraph() -> None:
    """
    Tests how subgraphs work.

    If use_cache is False it must force
    dependency graph to reevaluate it's subdependencies.
    """
    dep_exec = 0

    def dep1() -> int:
        nonlocal dep_exec  # noqa: WPS420
        dep_exec += 1

        return 1

    def dep2(a: int = Depends(dep1)) -> int:
        return a + 1

    def dep3(a: int = Depends(dep1, use_cache=False)) -> int:
        return a + 1

    def testfunc(
        a: int = Depends(dep2),
        b: int = Depends(dep3),
    ) -> int:
        return a + b

    with DependencyGraph(testfunc).sync_ctx({}) as sctx:
        assert sctx.resolve_kwargs() == {"a": 2, "b": 2}

    assert dep_exec == 2
    dep_exec = 0

    async with DependencyGraph(testfunc).async_ctx({}) as actx:
        assert await actx.resolve_kwargs() == {"a": 2, "b": 2}

    assert dep_exec == 2


@pytest.mark.anyio
async def test_initial_ctx() -> None:
    """
    Tests that initial context is resolved.

    We pass a TeCtx instance as the default
    dependency. And now we want to know if
    it resolved in a value that we passed.
    """

    class TeCtx:
        def __init__(self, val: Any) -> None:
            self.val = val

    val = uuid.uuid4()

    def dependency(t: TeCtx = Depends()) -> bool:
        return t.val == val

    def target(test: bool = Depends(dependency)) -> bool:
        return test

    with DependencyGraph(target).sync_ctx({TeCtx: TeCtx(val)}) as sctx:
        assert sctx.resolve_kwargs() == {"test": True}

    async with DependencyGraph(target).async_ctx({TeCtx: TeCtx(val)}) as actx:
        assert await actx.resolve_kwargs() == {"test": True}


def test_unknown_dependency_func() -> None:
    """Tests that error is raised for unknown deps."""

    def target(dep=Depends()) -> None:  # type: ignore
        pass

    with pytest.raises(ValueError):
        DependencyGraph(target)


def test_unknown_dependency_class() -> None:
    """Tests that error is raised for unknown deps."""

    class Target:
        def __init__(self, dep=Depends()) -> None:  # type: ignore
            pass

    with pytest.raises(ValueError):
        DependencyGraph(Target)


def test_get_param_info() -> None:
    """Tests that param info resolved correctly."""

    def dep(info: ParamInfo = Depends()) -> ParamInfo:
        return info

    def target(my_test_param: ParamInfo = Depends(dep)) -> None:
        return None

    with DependencyGraph(target=target).sync_ctx() as g:
        kwargs = g.resolve_kwargs()

    info: ParamInfo = kwargs["my_test_param"]
    assert info.name == "my_test_param"
    assert info.definition
    assert info.definition.annotation == ParamInfo


def test_param_info_no_dependant() -> None:
    """Tests that if ParamInfo is used on the target, no error is raised."""

    def target(info: ParamInfo = Depends()) -> None:
        return None

    with DependencyGraph(target=target).sync_ctx() as g:
        kwargs = g.resolve_kwargs()

    info: ParamInfo = kwargs["info"]
    assert info.name == ""
    assert info.definition is None


def test_class_based_dependencies() -> None:
    """Tests that if ParamInfo is used on the target, no error is raised."""

    class TeClass:
        def __init__(self, return_val: str) -> None:
            self.return_val = return_val

        def __call__(self) -> str:
            return self.return_val

    def target(class_val: str = Depends(TeClass("tval"))) -> None:
        return None

    with DependencyGraph(target=target).sync_ctx() as g:
        kwargs = g.resolve_kwargs()

    info: str = kwargs["class_val"]
    assert info == "tval"


def test_generic_class_based_dependencies() -> None:
    """Tests that if ParamInfo is used on the target, no error is raised."""

    class TeClass:
        def __init__(self, return_val: str) -> None:
            self.return_val = return_val

        def __call__(self) -> str:
            return self.return_val

    class GenericClass(Generic[_T]):
        def __init__(self, class_val: str = Depends(TeClass("tval"))):
            self.return_val = class_val

    def target(class_val: GenericClass = Depends()) -> None:
        return None

    with DependencyGraph(target=target).sync_ctx() as g:
        kwargs = g.resolve_kwargs()

    info: str = kwargs["class_val"]
    assert info.return_val == "tval"


def test_exception_generators() -> None:
    errors_found = 0

    def my_generator() -> Generator[int, None, None]:
        nonlocal errors_found
        try:
            yield 1
        except ValueError:
            errors_found += 1

    def target(_: int = Depends(my_generator)) -> None:
        raise ValueError()

    with pytest.raises(ValueError):
        with DependencyGraph(target=target).sync_ctx() as g:
            target(**g.resolve_kwargs())

    assert errors_found == 1


@pytest.mark.anyio
async def test_async_exception_generators() -> None:
    errors_found = 0

    async def my_generator() -> AsyncGenerator[int, None]:
        nonlocal errors_found
        try:
            yield 1
        except ValueError:
            errors_found += 1

    def target(_: int = Depends(my_generator)) -> None:
        raise ValueError()

    with pytest.raises(ValueError):
        async with DependencyGraph(target=target).async_ctx() as g:
            target(**(await g.resolve_kwargs()))

    assert errors_found == 1


@pytest.mark.anyio
async def test_async_exception_generators_multiple() -> None:
    errors_found = 0

    async def my_generator() -> AsyncGenerator[int, None]:
        nonlocal errors_found
        try:
            yield 1
        except ValueError:
            errors_found += 1

    def target(
        _a: int = Depends(my_generator, use_cache=False),
        _b: int = Depends(my_generator, use_cache=False),
        _c: int = Depends(my_generator, use_cache=False),
    ) -> None:
        raise ValueError()

    with pytest.raises(ValueError):
        async with DependencyGraph(target=target).async_ctx() as g:
            target(**(await g.resolve_kwargs()))

    assert errors_found == 3


@pytest.mark.anyio
async def test_async_exception_in_teardown() -> None:
    errors_found = 0

    async def my_generator() -> AsyncGenerator[int, None]:
        nonlocal errors_found
        try:
            yield 1
        except ValueError:
            errors_found += 1
            raise Exception()

    def target(_: int = Depends(my_generator)) -> None:
        raise ValueError()

    with pytest.raises(ValueError):
        async with DependencyGraph(target=target).async_ctx() as g:
            target(**(await g.resolve_kwargs()))


@pytest.mark.anyio
async def test_async_propagation_disabled() -> None:
    errors_found = 0

    async def my_generator() -> AsyncGenerator[int, None]:
        nonlocal errors_found
        try:
            yield 1
        except ValueError:
            errors_found += 1
            raise Exception()

    def target(_: int = Depends(my_generator)) -> None:
        raise ValueError()

    with pytest.raises(ValueError):
        async with DependencyGraph(target=target).async_ctx(
            exception_propagation=False,
        ) as g:
            target(**(await g.resolve_kwargs()))

    assert errors_found == 0


def test_sync_propagation_disabled() -> None:
    errors_found = 0

    def my_generator() -> Generator[int, None, None]:
        nonlocal errors_found
        try:
            yield 1
        except ValueError:
            errors_found += 1
            raise Exception()

    def target(_: int = Depends(my_generator)) -> None:
        raise ValueError()

    with pytest.raises(ValueError):
        with DependencyGraph(target=target).sync_ctx(exception_propagation=False) as g:
            target(**(g.resolve_kwargs()))

    assert errors_found == 0
