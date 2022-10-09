import inspect
from collections import defaultdict, deque
from graphlib import TopologicalSorter
from typing import Any, Callable, Dict, List, Optional, get_type_hints

from taskiq_dependencies.ctx import AsyncResolveContext, SyncResolveContext
from taskiq_dependencies.dependency import Dependency


class DependencyGraph:
    """Class to build dependency graph from a function."""

    dep_graph = True

    def __init__(
        self,
        target: Callable[..., Any],
    ) -> None:
        self.target = target
        # Ordinary dependencies with cache.
        self.dependencies: Dict[Any, List[Dependency]] = defaultdict(list)
        # Dependencies without cache.
        # Can be considered as sub graphs.
        self.subgraphs: Dict[Any, DependencyGraph] = {}
        self.ordered_deps: List[Dependency] = []
        self._build_graph()

    def is_empty(self) -> bool:
        """
        Checks that target function depends on at least something.

        :return: True if depends.
        """
        return len(self.ordered_deps) <= 1

    def async_ctx(
        self,
        initial_cache: Optional[Dict[Any, Any]] = None,
    ) -> AsyncResolveContext:
        """
        Create dependency resolver context.

        This context is used to actually resolve dependencies.

        :param initial_cache: initial cache dict.
        :return: new resolver context.
        """
        return AsyncResolveContext(
            self,
            initial_cache,
        )

    def sync_ctx(
        self,
        initial_cache: Optional[Dict[Any, Any]] = None,
    ) -> SyncResolveContext:
        """
        Create dependency resolver context.

        This context is used to actually resolve dependencies.

        :param initial_cache: initial cache dict.
        :return: new resolver context.
        """
        return SyncResolveContext(
            self,
            initial_cache,
        )

    def _build_graph(self) -> None:  # noqa: C901, WPS210
        """
        Builds actual graph.

        This function collects all dependencies
        and adds it the the _deps variable.

        After all dependencies are found,
        it runs topological sort, to get the
        dependency resolving order.

        :raises ValueError: if something happened.
        """
        dep_deque = deque([Dependency(self.target, use_cache=True)])

        while dep_deque:
            dep = dep_deque.popleft()
            # Skip adding dependency if it's already present.
            if dep in self.dependencies:
                continue
            if dep.dependency is None:
                continue
            # Get signature and type hints.
            sign = inspect.signature(dep.dependency)
            if inspect.isclass(dep.dependency):
                # If this is a class, we need to get signature of
                # an __init__ method.
                hints = get_type_hints(dep.dependency.__init__)  # noqa: WPS609
            else:
                # If this is function, we get it's type hints.
                hints = get_type_hints(dep.dependency)

            # Now we need to iterate over parameters, to
            # find all parameters, that have TaskiqDepends as it's
            # default vaule.
            for param_name, param in sign.parameters.items():
                # We check, that default value is an instance of
                # TaskiqDepends.
                if not isinstance(param.default, Dependency):
                    continue

                # If user haven't set the dependency,
                # using TaskiqDepends constructor,
                # we need to find variable's type hint.
                if param.default.dependency is None:
                    if hints.get(param_name) is None:
                        # In this case, we don't know anything
                        # about this dependency. And it cannot be resolved.
                        dep_mod = "unknown"
                        dep_name = "unknown"
                        if dep.dependency is not None:
                            dep_mod = dep.dependency.__module__
                            if inspect.isclass(dep.dependency):
                                dep_name = dep.dependency.__class__.__name__
                            else:
                                dep_name = dep.dependency.__name__
                        raise ValueError(
                            f"The dependency {param_name} of "
                            f"{dep_mod}:{dep_name} cannot be resolved.",
                        )
                    # We get dependency class from typehint.
                    dependency_func = hints[param_name]
                else:
                    # We can get dependency by simply using
                    # user supplied function.
                    dependency_func = param.default.dependency

                # Now we construct new TaskiqDepends instance
                # with correct dependency function and cache.
                dep_obj = Dependency(
                    dependency_func,
                    use_cache=param.default.use_cache,
                    kwargs=param.default.kwargs,
                )
                # Also we set the parameter name,
                # it will help us in future when
                # we're going to resolve all dependencies.
                dep_obj.param_name = param_name

                # We append current dependency
                # to the list of dependencies of
                # the current function.
                self.dependencies[dep].append(dep_obj)
                if dep_obj.use_cache:
                    # If this dependency uses cache, we need to resolve
                    # it's dependencies further.
                    dep_deque.append(dep_obj)
                else:
                    # If this dependency doesn't use caches,
                    # we build a subgraph for this dependency.
                    self.subgraphs[dep_obj] = DependencyGraph(
                        dependency_func,
                    )
        # Now we perform topological sort of all dependencies.
        # Now we know the order we'll be using to resolve dependencies.
        self.ordered_deps = list(TopologicalSorter(self.dependencies).static_order())
