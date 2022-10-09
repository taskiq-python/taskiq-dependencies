import asyncio
import inspect
from copy import copy
from typing import TYPE_CHECKING, Any, Dict, Generator, List, Optional

if TYPE_CHECKING:
    from taskiq_dependencies.graph import DependencyGraph  # pragma: no cover


class BaseResolveContext:
    """Base resolver context."""

    def __init__(
        self,
        graph: "DependencyGraph",
        initial_cache: Optional[Dict[Any, Any]] = None,
    ) -> None:
        self.graph = graph
        self.opened_dependencies: List[Any] = []
        self.sub_contexts: "List[Any]" = []
        self.initial_cache = initial_cache or {}

    def traverse_deps(  # noqa: C901, WPS210
        self,
    ) -> "Generator[DependencyGraph | Any, None, Dict[str, Any]]":
        """
        This function is used to traverse all dependencies and resolve them.

        It travels to all dependencies, everytime it need to resolve
        something it yields it and waits for the resolving result.

        :return: resolved kwargs.
        :yield: a function or a graph to resolve.
        """
        # If we have nothing to calculate, we return
        # an empty dict.
        if self.graph.is_empty():
            return {}
        kwargs: Dict[str, Any] = {}
        # We need to copy cache, in order
        # to separate dependencies that use cache,
        # from dependencies that aren't.
        cache = copy(self.initial_cache)
        # We iterate over topologicaly sorted list of dependencies.
        for index, dep in enumerate(self.graph.ordered_deps):
            # If this dependency doesn't use cache,
            # we don't need to calculate it, since it may be met
            # later.
            if not dep.use_cache:
                continue
            # If somehow we have dependency with unknwon function.
            if dep.dependency is None:
                continue
            # If dependency is already calculated.
            if dep.dependency in cache:
                continue
            kwargs = {}
            # Now we get list of dependencies for current top-level dependency
            # and iterate over it.
            for subdep in self.graph.dependencies[dep]:
                # If we don't have known dependency function,
                # we skip it.
                if subdep.dependency is None:
                    continue
                if subdep.use_cache:
                    # If this dependency can be calculated, using cache,
                    # we try to get it from cache.
                    kwargs[subdep.param_name] = cache[subdep.dependency]
                else:
                    # If this dependency doesn't use cache,
                    # we resolve it's dependencies and
                    # run it.
                    resolved_kwargs = yield self.graph.subgraphs[subdep]
                    # Subgraph wasn't resolved.
                    if resolved_kwargs is None:
                        continue
                    if subdep.kwargs:
                        resolved_kwargs.update(subdep.kwargs)
                    kwargs[subdep.param_name] = yield subdep.dependency(
                        **resolved_kwargs,
                    )

            # We don't want to calculate least function,
            # Because it's a target function.
            if index < len(self.graph.ordered_deps) - 1:
                user_kwargs = dep.kwargs
                user_kwargs.update(kwargs)
                cache[dep.dependency] = yield dep.dependency(**user_kwargs)
        return kwargs


class SyncResolveContext(BaseResolveContext):
    """
    Resolver context.

    This class is used to resolve dependencies
    with custom initial caches.

    The main idea is to separate resolving and graph building.
    It uses graph, but it doesn't modify it.
    """

    def __enter__(self) -> "SyncResolveContext":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        """
        Close all opened dependencies.

        This function runs teardown of all dependencies.
        """
        for ctx in self.sub_contexts:
            ctx.close()
        for dep in reversed(self.opened_dependencies):
            if inspect.isgenerator(dep):
                for _ in dep:  # noqa: WPS328
                    pass  # noqa: WPS420

    def resolver(self, executed_func: Any, initial_cache: Dict[Any, Any]) -> Any:
        """
        Sync resolver.

        This function is used to execute functions
        to resolve dependencies.

        :param executed_func: function to resolve.
        :param initial_cache: cache to build a context if graph was passed.
        :raises RuntimeError: if async function is passed as the dependency.

        :return: dict with resolved kwargs.
        """
        if getattr(executed_func, "dep_graph", False):
            ctx = SyncResolveContext(executed_func, initial_cache)
            self.sub_contexts.append(ctx)
            sub_result = ctx.resolve_kwargs()
        elif inspect.isgenerator(executed_func):
            sub_result = next(executed_func)
            self.opened_dependencies.append(executed_func)
        elif asyncio.iscoroutine(executed_func):
            raise RuntimeError(
                "Coroutines cannot be used in sync context. "
                "Please use async context instead.",
            )
        elif inspect.isasyncgen(executed_func):
            raise RuntimeError(
                "Coroutines cannot be used in sync context. "
                "Please use async context instead.",
            )
        else:
            sub_result = executed_func
        return sub_result

    def resolve_kwargs(
        self,
    ) -> Dict[str, Any]:
        """
        Resolve dependencies and return them as a dict.

        This function runs all dependencies
        and calculates key word arguments required to run target function.

        :return: Dict with keyword arguments.
        """
        try:
            generator = self.traverse_deps()
            dependency = generator.send(None)
            while True:  # noqa: WPS457
                kwargs = self.resolver(dependency, self.initial_cache)
                dependency = generator.send(kwargs)
        except StopIteration as exc:
            return exc.value  # type: ignore


class AsyncResolveContext(BaseResolveContext):
    """
    Resolver context.

    This class is used to resolve dependencies
    with custom initial caches.

    The main idea is to separate resolving and graph building.
    It uses graph, but it doesn't modify it.
    """

    async def __aenter__(self) -> "AsyncResolveContext":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:  # noqa: C901
        """
        Close all opened dependencies.

        This function runs teardown of all dependencies.
        """
        for ctx in self.sub_contexts:
            await ctx.close()  # type: ignore
        for dep in reversed(self.opened_dependencies):
            if inspect.isgenerator(dep):
                for _ in dep:  # noqa: WPS328
                    pass  # noqa: WPS420
            elif inspect.isasyncgen(dep):
                async for _ in dep:  # noqa: WPS328
                    pass  # noqa: WPS420

    async def resolver(self, executed_func: Any, initial_cache: Dict[Any, Any]) -> Any:
        """
        Async resolver.

        This function is used to execute functions
        to resolve dependencies.

        :param executed_func: function to resolve.
        :param initial_cache: cache to build a context if graph was passed.
        :return: dict with resolved kwargs.
        """
        if getattr(executed_func, "dep_graph", False):
            ctx = AsyncResolveContext(executed_func, initial_cache)  # type: ignore
            self.sub_contexts.append(ctx)
            sub_result = await ctx.resolve_kwargs()
        elif inspect.isgenerator(executed_func):
            sub_result = next(executed_func)
            self.opened_dependencies.append(executed_func)
        elif asyncio.iscoroutine(executed_func):
            sub_result = await executed_func
        elif inspect.isasyncgen(executed_func):
            sub_result = await executed_func.__anext__()  # noqa: WPS609
            self.opened_dependencies.append(executed_func)
        else:
            sub_result = executed_func
        return sub_result

    async def resolve_kwargs(
        self,
    ) -> Dict[str, Any]:
        """
        Resolve dependencies and return them as a dict.

        This function runs all dependencies
        and calculates key word arguments required to run target function.

        :return: Dict with keyword arguments.
        """
        try:
            generator = self.traverse_deps()
            dependency = generator.send(None)
            while True:  # noqa: WPS457
                kwargs = await self.resolver(dependency, self.initial_cache)
                dependency = generator.send(kwargs)
        except StopIteration as exc:
            return exc.value  # type: ignore
