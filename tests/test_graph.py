import re
import uuid
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncGenerator, Generator, Generic, Tuple, TypeVar

import pytest

from taskiq_dependencies import DependencyGraph, Depends, ParamInfo


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
        return 1

    def testfunc(a: int = Depends(dep1)) -> int:
        return a

    with DependencyGraph(testfunc).sync_ctx({}) as sctx, pytest.warns(
        match=re.compile(".*was never awaited.*"),
    ), pytest.raises(RuntimeError):
        assert sctx.resolve_kwargs() == {"a": 1}

    async with DependencyGraph(testfunc).async_ctx({}) as actx:
        assert await actx.resolve_kwargs() == {"a": 1}


@pytest.mark.anyio
async def test_dependency_gen_successful() -> None:
    """Tests that generators work as expected."""
    starts = 0
    closes = 0

    def dep1() -> Generator[int, None, None]:
        nonlocal starts
        nonlocal closes

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
        nonlocal starts
        nonlocal closes

        starts += 1

        yield 1

        closes += 1

    def testfunc(a: int = Depends(dep1)) -> int:
        return a

    with DependencyGraph(testfunc).sync_ctx({}) as sctx, pytest.raises(RuntimeError):
        assert sctx.resolve_kwargs() == {"a": 1}

    async with DependencyGraph(testfunc).async_ctx({}) as actx:
        assert await actx.resolve_kwargs() == {"a": 1}
        assert starts == 1
        assert closes == 0
    assert closes == 1


@pytest.mark.anyio
async def test_dependency_contextmanager_successful() -> None:
    """Tests that contextmanagers work as expected."""
    starts = 0
    closes = 0

    @contextmanager
    def dep1() -> Generator[int, None, None]:
        nonlocal starts
        nonlocal closes

        starts += 1

        try:
            yield 1
        finally:
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
async def test_dependency_async_manager_successful() -> None:
    """This test checks that async contextmanagers work."""
    starts = 0
    closes = 0

    @asynccontextmanager
    async def dep1() -> AsyncGenerator[int, None]:
        nonlocal starts
        nonlocal closes

        starts += 1

        try:
            yield 1
        finally:
            closes += 1

    def testfunc(a: int = Depends(dep1)) -> int:
        return a

    with DependencyGraph(testfunc).sync_ctx({}) as sctx, pytest.raises(RuntimeError):
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
        nonlocal dep_exec
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
        nonlocal dep_exec
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

    def target(dep=Depends()) -> None:  # type: ignore  # noqa: ANN001
        pass

    with pytest.raises(ValueError):
        DependencyGraph(target)


def test_unknown_dependency_class() -> None:
    """Tests that error is raised for unknown deps."""

    class Target:
        def __init__(self, dep=Depends()) -> None:  # type: ignore  # noqa: ANN001
            pass

    with pytest.raises(ValueError):
        DependencyGraph(Target)


def test_get_param_info() -> None:
    """Tests that param info resolved correctly."""

    def dep(info: ParamInfo = Depends()) -> ParamInfo:
        return info

    def target(my_test_param: ParamInfo = Depends(dep)) -> None:
        return None

    graph = DependencyGraph(target=target)
    with graph.sync_ctx() as g:
        kwargs = g.resolve_kwargs()

    info: ParamInfo = kwargs["my_test_param"]
    assert info.name == "my_test_param"
    assert info.definition
    assert info.definition.annotation == ParamInfo
    assert info.graph == graph


def test_param_info_no_dependant() -> None:
    """Tests that if ParamInfo is used on the target, no error is raised."""

    def target(info: ParamInfo = Depends()) -> None:
        return None

    graph = DependencyGraph(target=target)
    with graph.sync_ctx() as g:
        kwargs = g.resolve_kwargs()

    info: ParamInfo = kwargs["info"]
    assert info.name == ""
    assert info.definition is None
    assert info.graph == graph


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


def test_exception_generators() -> None:
    errors_found = 0

    def my_generator() -> Generator[int, None, None]:
        nonlocal errors_found
        try:
            yield 1
        except ValueError:
            errors_found += 1

    def target(_: int = Depends(my_generator)) -> None:
        raise ValueError

    with pytest.raises(ValueError), DependencyGraph(target=target).sync_ctx() as g:
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
        raise ValueError

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
        raise ValueError

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
        except ValueError as verr:
            errors_found += 1
            raise Exception from verr

    def target(_: int = Depends(my_generator)) -> None:
        raise ValueError

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
        except ValueError as verr:
            errors_found += 1
            raise Exception from verr

    def target(_: int = Depends(my_generator)) -> None:
        raise ValueError

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
        except ValueError as verr:
            errors_found += 1
            raise Exception from verr

    def target(_: int = Depends(my_generator)) -> None:
        raise ValueError

    with pytest.raises(ValueError), DependencyGraph(target=target).sync_ctx(
        exception_propagation=False,
    ) as g:
        target(**(g.resolve_kwargs()))

    assert errors_found == 0


def test_generic_classes() -> None:
    errors_found = 0

    _T = TypeVar("_T")

    class MyClass:
        pass

    class MainClass(Generic[_T]):
        def __init__(self, val: _T = Depends()) -> None:
            self.val = val

    def test_func(a: MainClass[MyClass] = Depends()) -> MyClass:
        return a.val

    with DependencyGraph(target=test_func).sync_ctx(exception_propagation=False) as g:
        value = test_func(**(g.resolve_kwargs()))

    assert errors_found == 0
    assert isinstance(value, MyClass)


def test_generic_multiple() -> None:
    errors_found = 0

    _T = TypeVar("_T")
    _V = TypeVar("_V")

    class MyClass1:
        pass

    class MyClass2:
        pass

    class MainClass(Generic[_T, _V]):
        def __init__(self, t_val: _T = Depends(), v_val: _V = Depends()) -> None:
            self.t_val = t_val
            self.v_val = v_val

    def test_func(
        a: MainClass[MyClass1, MyClass2] = Depends(),
    ) -> MainClass[MyClass1, MyClass2]:
        return a

    with DependencyGraph(target=test_func).sync_ctx(exception_propagation=False) as g:
        result = test_func(**(g.resolve_kwargs()))

    assert errors_found == 0
    assert isinstance(result.t_val, MyClass1)
    assert isinstance(result.v_val, MyClass2)


def test_generic_unordered() -> None:
    errors_found = 0

    _T = TypeVar("_T")
    _V = TypeVar("_V")

    class MyClass1:
        pass

    class MyClass2:
        pass

    class MainClass(Generic[_T, _V]):
        def __init__(self, v_val: _V = Depends(), t_val: _T = Depends()) -> None:
            self.t_val = t_val
            self.v_val = v_val

    def test_func(
        a: MainClass[MyClass1, MyClass2] = Depends(),
    ) -> MainClass[MyClass1, MyClass2]:
        return a

    with DependencyGraph(target=test_func).sync_ctx(exception_propagation=False) as g:
        result = test_func(**(g.resolve_kwargs()))

    assert errors_found == 0
    assert isinstance(result.t_val, MyClass1)
    assert isinstance(result.v_val, MyClass2)


def test_generic_classes_nesting() -> None:
    errors_found = 0

    _T = TypeVar("_T")
    _V = TypeVar("_V")

    class DummyClass:
        pass

    class DependantClass(Generic[_V]):
        def __init__(self, var: _V = Depends()) -> None:
            self.var = var

    class MainClass(Generic[_T]):
        def __init__(self, var: _T = Depends()) -> None:
            self.var = var

    def test_func(a: MainClass[DependantClass[DummyClass]] = Depends()) -> DummyClass:
        return a.var.var

    with DependencyGraph(target=test_func).sync_ctx(exception_propagation=False) as g:
        value = test_func(**(g.resolve_kwargs()))

    assert errors_found == 0
    assert isinstance(value, DummyClass)


def test_generic_class_based_dependencies() -> None:
    """Tests that if ParamInfo is used on the target, no error is raised."""
    _T = TypeVar("_T")

    class GenericClass(Generic[_T]):
        def __init__(self, class_val: _T = Depends()) -> None:
            self.return_val = class_val

    def func_dep() -> GenericClass[int]:
        return GenericClass(123)

    def target(my_dep: GenericClass[int] = Depends(func_dep)) -> int:
        return my_dep.return_val

    with DependencyGraph(target=target).sync_ctx() as g:
        result = target(**g.resolve_kwargs())

    assert result == 123


@pytest.mark.anyio
async def test_graph_type_hints() -> None:
    def dep() -> int:
        return 123

    def target(class_val: int = Depends(dep, use_cache=False)) -> None:
        return None

    g = DependencyGraph(target=target)
    for dep_obj in g.subgraphs:
        assert dep_obj.param_name == "class_val"
        assert dep_obj.dependency == dep
        assert dep_obj.signature.name == "class_val"
        assert dep_obj.signature.annotation == int  # noqa: E721


@pytest.mark.anyio
async def test_graph_generic_type_hints() -> None:
    _T = TypeVar("_T")

    def dep3() -> int:
        return 123

    class GenericClass(Generic[_T]):
        def __init__(self, class_val: int = Depends(dep3)) -> None:
            self.return_val = class_val

    def target(
        class_val: GenericClass[Tuple[str, int]] = Depends(use_cache=False),
    ) -> None:
        return None

    g = DependencyGraph(target=target)
    for dep_obj in g.subgraphs:
        assert dep_obj.param_name == "class_val"
        assert dep_obj.dependency == GenericClass[Tuple[str, int]]
        assert dep_obj.signature.name == "class_val"
        assert dep_obj.signature.annotation == GenericClass[Tuple[str, int]]


@pytest.mark.anyio
async def test_replaced_dep_simple() -> None:
    def replaced() -> int:
        return 321

    def dep() -> int:
        return 123

    def target(val: int = Depends(dep)) -> None:
        return None

    graph = DependencyGraph(target=target)
    async with graph.async_ctx(replaced_deps={dep: replaced}) as ctx:
        kwargs = await ctx.resolve_kwargs()
    assert kwargs["val"] == 321


@pytest.mark.anyio
async def test_replaced_dep_generators() -> None:
    call_count = 0

    def replaced() -> Generator[int, None, None]:
        nonlocal call_count
        yield 321
        call_count += 1

    def dep() -> int:
        return 123

    def target(val: int = Depends(dep)) -> None:
        return None

    graph = DependencyGraph(target=target)
    async with graph.async_ctx(replaced_deps={dep: replaced}) as ctx:
        kwargs = await ctx.resolve_kwargs()
    assert kwargs["val"] == 321
    assert call_count == 1


@pytest.mark.anyio
async def test_replaced_dep_exception_propogation() -> None:
    exc_count = 0

    def replaced() -> Generator[int, None, None]:
        nonlocal exc_count
        try:
            yield 321
        except ValueError:
            exc_count += 1

    def dep() -> int:
        return 123

    def target(val: int = Depends(dep)) -> None:
        raise ValueError("lol")

    graph = DependencyGraph(target=target)
    with pytest.raises(ValueError):
        async with graph.async_ctx(
            replaced_deps={dep: replaced},
            exception_propagation=True,
        ) as ctx:
            kwargs = await ctx.resolve_kwargs()
            assert kwargs["val"] == 321
            target(**kwargs)
    assert exc_count == 1


@pytest.mark.anyio
async def test_replaced_dep_subdependencies() -> None:
    def subdep() -> int:
        return 321

    def replaced(ret_val: int = Depends(subdep)) -> int:
        return ret_val

    def dep() -> int:
        return 123

    def target(val: int = Depends(dep)) -> None:
        """Stub function."""

    graph = DependencyGraph(target=target)
    async with graph.async_ctx(
        replaced_deps={dep: replaced},
        exception_propagation=True,
    ) as ctx:
        kwargs = await ctx.resolve_kwargs()
        assert kwargs["val"] == 321


def test_kwargs_caches() -> None:
    """
    Test that kwarged caches work.

    If user wants to pass kwargs to the dependency
    multiple times, we must verify that it works.

    And dependency calculated multiple times,
    even with caches.
    """

    def random_dep(a: int) -> int:
        return a

    A = Depends(random_dep, kwargs={"a": 1})
    B = Depends(random_dep, kwargs={"a": 2})

    def target(a: int = A, b: int = B) -> int:
        return a + b

    graph = DependencyGraph(target=target)
    with graph.sync_ctx() as ctx:
        kwargs = ctx.resolve_kwargs()
        assert target(**kwargs) == 3


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

    def target(cm: TestCM = Depends(get_test_cm)) -> None:
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

    def target(acm: TestACM = Depends(get_test_acm)) -> None:
        pass

    graph = DependencyGraph(target=target)
    async with graph.async_ctx() as ctx:
        kwargs = await ctx.resolve_kwargs()
        assert kwargs["acm"] == test_acm
        assert not test_acm.opened
