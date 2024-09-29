import asyncio
import inspect
from collections import defaultdict
from copy import copy
from logging import getLogger
from typing import TYPE_CHECKING, Any, DefaultDict, Dict, Generator, List, Optional

from taskiq_dependencies.utils import ParamInfo, isasynccontextmanager, iscontextmanager

if TYPE_CHECKING:
    from taskiq_dependencies.graph import DependencyGraph  # pragma: no cover


logger = getLogger("taskiq.dependencies.ctx")


class BaseResolveContext:
    """Base resolver context."""

    def __init__(
        self,
        graph: "DependencyGraph",
        main_graph: "DependencyGraph",
        initial_cache: Optional[Dict[Any, Any]] = None,
        exception_propagation: bool = True,
    ) -> None:
        self.graph = graph
        # Main graph that contains all the subgraphs.
        self.main_graph = main_graph
        self.opened_dependencies: List[Any] = []
        self.sub_contexts: "List[Any]" = []
        self.initial_cache = initial_cache or {}
        self.propagate_excs = exception_propagation

    def traverse_deps(  # noqa: C901
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
        # Cache for all dependencies with kwargs.
        kwargs_cache: "DefaultDict[Any, List[Any]]" = defaultdict(list)
        # We iterate over topologicaly sorted list of dependencies.
        for index, dep in enumerate(self.graph.ordered_deps):
            # If this dependency doesn't use cache,
            # we don't need to calculate it, since it may be met
            # later.
            if not dep.use_cache:
                continue
            # If somehow we have dependency with unknown function.
            if dep.dependency is None:
                continue
            # If dependency is already calculated.
            if dep.dependency in cache:
                continue
            # For dependencies with kwargs we check kwarged cache.
            elif dep.kwargs and dep.dependency in kwargs_cache:
                cache_hit = False
                # We have to iterate over all cached dependencies with
                # kwargs, because users may pass unhashable objects as kwargs.
                # That's why we cannot use them as dict keys.
                for cached_kwargs, _ in kwargs_cache[dep.dependency]:
                    if cached_kwargs == dep.kwargs:
                        cache_hit = True
                        break
                if cache_hit:
                    continue

            kwargs = {}
            # Now we get list of dependencies for current top-level dependency
            # and iterate over it.
            for subdep in self.graph.dependencies[dep]:
                # If we don't have known dependency function,
                # we skip it.
                if subdep.dependency is None:
                    continue
                # If the user want to get ParamInfo,
                # we get declaration of the current dependency.
                if subdep.dependency == ParamInfo:
                    kwargs[subdep.param_name] = ParamInfo(
                        dep.param_name,
                        self.main_graph,
                        dep.signature,
                    )
                    continue
                if subdep.use_cache:
                    # If this dependency can be calculated, using cache,
                    # we try to get it from cache.
                    if subdep.kwargs and subdep.dependency in kwargs_cache:
                        for cached_kwargs, kw_cache in kwargs_cache[subdep.dependency]:
                            if cached_kwargs == subdep.kwargs:
                                kwargs[subdep.param_name] = kw_cache
                                break
                    else:
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
            if (
                index < len(self.graph.ordered_deps) - 1
                # We skip all ParamInfo dependencies,
                # because we calculate them when needed.
                and dep.dependency != ParamInfo
            ):
                user_kwargs = copy(dep.kwargs)
                user_kwargs.update(kwargs)
                resolved = yield dep.dependency(**user_kwargs)
                if dep.kwargs:
                    kwargs_cache[dep.dependency].append((dep.kwargs, resolved))
                else:
                    cache[dep.dependency] = resolved
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

    def __exit__(self, *args: object) -> None:
        self.close(*args)

    def close(self, *args: Any) -> None:
        """
        Close all opened dependencies.

        This function runs teardown of all dependencies.

        :param args: exception info if any.
        """
        exception_found = False
        if self.propagate_excs and len(args) > 1 and args[1] is not None:
            exception_found = True
        for ctx in self.sub_contexts:
            ctx.close(*args)
        for dep in reversed(self.opened_dependencies):
            if inspect.isgenerator(dep):
                if exception_found:
                    try:
                        dep.throw(*args)
                    except StopIteration:
                        continue
                    except BaseException as exc:
                        logger.warning(
                            "Exception found on dependency teardown %s",
                            exc,
                            exc_info=True,
                        )
                        continue
                    continue
                for _ in dep:
                    pass
            elif iscontextmanager(dep):
                dep.__exit__(*args)

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
            ctx = SyncResolveContext(executed_func, self.main_graph, initial_cache)
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
        elif iscontextmanager(executed_func):
            sub_result = executed_func.__enter__()
            self.opened_dependencies.append(executed_func)
        elif inspect.isasyncgen(executed_func) or isasynccontextmanager(executed_func):
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
            while True:
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

    async def __aexit__(self, *args: object) -> None:
        await self.close(*args)

    async def close(self, *args: Any) -> None:  # noqa: C901
        """
        Close all opened dependencies.

        This function runs teardown of all dependencies.

        :param args: exception info if any.
        """
        exception_found = False
        if self.propagate_excs and len(args) > 1 and args[1] is not None:
            exception_found = True
        for ctx in self.sub_contexts:
            await ctx.close(*args)  # type: ignore
        for dep in reversed(self.opened_dependencies):
            if inspect.isgenerator(dep):
                if exception_found:
                    try:
                        dep.throw(*args)
                    except StopIteration:
                        continue
                    except BaseException as exc:
                        logger.warning(
                            "Exception found on dependency teardown %s",
                            exc,
                            exc_info=True,
                        )
                        continue
                    continue
                for _ in dep:
                    pass
            elif inspect.isasyncgen(dep):
                if exception_found:
                    try:
                        await dep.athrow(*args)
                    except StopAsyncIteration:
                        continue
                    except BaseException as exc:
                        logger.warning(
                            "Exception found on dependency teardown %s",
                            exc,
                            exc_info=True,
                        )
                        continue
                    continue
                async for _ in dep:
                    pass
            elif iscontextmanager(dep):
                dep.__exit__(*args)
            elif isasynccontextmanager(dep):
                await dep.__aexit__(*args)

    async def resolver(
        self,
        executed_func: Any,
        initial_cache: Dict[Any, Any],
    ) -> Any:
        """
        Async resolver.

        This function is used to execute functions
        to resolve dependencies.

        :param executed_func: function to resolve.
        :param initial_cache: cache to build a context if graph was passed.
        :return: dict with resolved kwargs.
        """
        if getattr(executed_func, "dep_graph", False):
            ctx = AsyncResolveContext(executed_func, self.main_graph, initial_cache)  # type: ignore
            self.sub_contexts.append(ctx)
            sub_result = await ctx.resolve_kwargs()
        elif inspect.isgenerator(executed_func):
            sub_result = next(executed_func)
            self.opened_dependencies.append(executed_func)
        elif asyncio.iscoroutine(executed_func):
            sub_result = await executed_func
        elif inspect.isasyncgen(executed_func):
            sub_result = await executed_func.__anext__()
            self.opened_dependencies.append(executed_func)
        elif iscontextmanager(executed_func):
            sub_result = executed_func.__enter__()
            self.opened_dependencies.append(executed_func)
        elif isasynccontextmanager(executed_func):
            sub_result = await executed_func.__aenter__()
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
            while True:
                kwargs = await self.resolver(dependency, self.initial_cache)
                dependency = generator.send(kwargs)
        except StopIteration as exc:
            return exc.value  # type: ignore
