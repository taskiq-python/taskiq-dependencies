import inspect
from collections import defaultdict, deque
from graphlib import TopologicalSorter
from typing import Any, Callable, Dict, List, Optional, TypeVar, get_type_hints

from taskiq_dependencies.ctx import AsyncResolveContext, SyncResolveContext
from taskiq_dependencies.dependency import Dependency

try:
    from fastapi.params import Depends as FastapiDepends  # noqa: WPS433
except ImportError:
    FastapiDepends = None


class DependencyGraph:
    """Class to build dependency graph from a function."""

    dep_graph = True

    def __init__(
        self,
        target: Callable[..., Any],
        replaced_deps: Optional[Dict[Any, Any]] = None,
    ) -> None:
        self.target = target
        # Ordinary dependencies with cache.
        self.dependencies: Dict[Any, List[Dependency]] = defaultdict(list)
        # Dependencies without cache.
        # Can be considered as sub graphs.
        self.subgraphs: Dict[Any, DependencyGraph] = {}
        self.ordered_deps: List[Dependency] = []
        self.replaced_deps = replaced_deps
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
        replaced_deps: Optional[Dict[Any, Any]] = None,
        exception_propagation: bool = True,
    ) -> AsyncResolveContext:
        """
        Create dependency resolver context.

        This context is used to actually resolve dependencies.

        :param initial_cache: initial cache dict.
        :param exception_propagation: If true, all found errors within
            context will be propagated to dependencies.
        :param replaced_deps: Dependencies to replace during runtime.
        :return: new resolver context.
        """
        graph = self
        if replaced_deps:
            graph = DependencyGraph(self.target, replaced_deps)
        return AsyncResolveContext(
            graph,
            initial_cache,
            exception_propagation,
        )

    def sync_ctx(
        self,
        initial_cache: Optional[Dict[Any, Any]] = None,
        replaced_deps: Optional[Dict[Any, Any]] = None,
        exception_propagation: bool = True,
    ) -> SyncResolveContext:
        """
        Create dependency resolver context.

        This context is used to actually resolve dependencies.

        :param initial_cache: initial cache dict.
        :param exception_propagation: If true, all found errors within
            context will be propagated to dependencies.
        :param replaced_deps: Dependencies to replace during runtime.
        :return: new resolver context.
        """
        graph = self
        if replaced_deps:
            graph = DependencyGraph(self.target, replaced_deps)
        return SyncResolveContext(
            graph,
            initial_cache,
            exception_propagation,
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
            if self.replaced_deps and dep.dependency in self.replaced_deps:
                dep.dependency = self.replaced_deps[dep.dependency]
            # Get signature and type hints.
            origin = getattr(dep.dependency, "__origin__", None)
            if origin is None:
                origin = dep.dependency

            # If we found the typevar.
            # It means, that somebody depend on generic type.
            if isinstance(origin, TypeVar):
                if dep.parent is None:
                    raise ValueError(f"Cannot resolve generic {dep.dependency}")
                parent_cls = dep.parent.dependency
                parent_cls_origin = getattr(parent_cls, "__origin__", None)
                # If we cannot find origin, than means, that we cannot resolve
                # generic parameters. So exiting.
                if parent_cls_origin is None:
                    raise ValueError(
                        f"Unknown generic argument {origin}. "
                        + f"Please provide a type in param `{dep.parent.param_name}`"
                        + f" of `{dep.parent.dependency}`",
                    )
                # We zip together names of parameters and the substituted values
                # for generics.
                generics = zip(
                    parent_cls_origin.__parameters__,
                    parent_cls.__args__,  # type: ignore
                )
                for tvar, type_param in generics:
                    # If we found the typevar we're currently try to resolve,
                    # we need to find origin of the substituted class.
                    if tvar == origin:
                        dep.dependency = type_param
                        origin = getattr(type_param, "__origin__", None)
                        if origin is None:
                            origin = type_param

            if inspect.isclass(origin):
                # If this is a class, we need to get signature of
                # an __init__ method.
                hints = get_type_hints(origin.__init__)  # noqa: WPS609
                sign = inspect.signature(origin.__init__)  # noqa: WPS609
            elif inspect.isfunction(dep.dependency):
                # If this is function or an instance of a class, we get it's type hints.
                hints = get_type_hints(dep.dependency)
                sign = inspect.signature(origin)  # type: ignore
            else:
                hints = get_type_hints(
                    dep.dependency.__call__,  # type: ignore # noqa: WPS609
                )
                sign = inspect.signature(origin)  # type: ignore

            # Now we need to iterate over parameters, to
            # find all parameters, that have TaskiqDepends as it's
            # default vaule.
            for param_name, param in sign.parameters.items():
                default_value = param.default
                if hasattr(param.annotation, "__metadata__"):  # noqa: WPS421
                    # We go backwards,
                    # because you may want to override your annotation
                    # and the overriden value will appear to be after
                    # the original `Depends` annotation.
                    for meta in reversed(param.annotation.__metadata__):
                        if isinstance(meta, Dependency):
                            default_value = meta
                            break
                        if FastapiDepends is not None and isinstance(  # noqa: WPS337
                            meta,
                            FastapiDepends,
                        ):
                            default_value = meta
                            break

                # This is for FastAPI integration. So you can
                # use Depends from taskiq mixed with fastapi's dependencies.
                if FastapiDepends is not None and isinstance(  # noqa: WPS337
                    default_value,
                    FastapiDepends,
                ):
                    default_value = Dependency(
                        dependency=default_value.dependency,
                        use_cache=default_value.use_cache,
                        signature=param,
                    )

                # We check, that default value is an instance of
                # TaskiqDepends.
                if not isinstance(default_value, Dependency):
                    continue
                # If user haven't set the dependency,
                # using TaskiqDepends constructor,
                # we need to find variable's type hint.
                if default_value.dependency is None:
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
                    dependency_func = default_value.dependency

                # Now we construct new TaskiqDepends instance
                # with correct dependency function and cache.
                dep_obj = Dependency(
                    dependency_func,
                    use_cache=default_value.use_cache,
                    kwargs=default_value.kwargs,
                    signature=param,
                    parent=dep,
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
