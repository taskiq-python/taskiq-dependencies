import inspect
import sys
import warnings
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar, get_type_hints

from graphlib import TopologicalSorter

from taskiq_dependencies.ctx import AsyncResolveContext, SyncResolveContext
from taskiq_dependencies.dependency import Dependency
from taskiq_dependencies.utils import ParamInfo

try:
    from fastapi.params import Depends as FastapiDepends
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
            graph,
            initial_cache,
            exception_propagation,
        )

    def _build_graph(self) -> None:  # noqa: C901
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
        # This is for `from __future__ import annotations` support.
        # We need to use `eval_str` argument, because
        # signature of the function is a string, not an object.
        signature_kwargs: Dict[str, Any] = {}
        if sys.version_info >= (3, 10):
            signature_kwargs["eval_str"] = True

        while dep_deque:
            dep = dep_deque.popleft()
            # Skip adding dependency if it's already present.
            if dep in self.dependencies:
                continue
            if dep.dependency is None:
                continue
            # If we have replaced dependencies, we need to replace
            # them in the current dependency.
            if self.replaced_deps and dep.dependency in self.replaced_deps:
                dep.dependency = self.replaced_deps[dep.dependency]
            # We can say for sure that ParamInfo doesn't have any dependencies,
            # so we skip it.
            if dep.dependency == ParamInfo:
                continue
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
                        f"Please provide a type in param `{dep.parent.param_name}`"
                        f" of `{dep.parent.dependency}`",
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
                try:
                    hints = get_type_hints(origin.__init__)
                except NameError:
                    _, src_lineno = inspect.getsourcelines(origin)
                    src_file = Path(inspect.getfile(origin))
                    cwd = Path.cwd()
                    if src_file.is_relative_to(cwd):
                        src_file = src_file.relative_to(cwd)
                    warnings.warn(
                        "Cannot resolve type hints for "
                        f"a class {origin.__name__} defined "
                        f"at {src_file}:{src_lineno}.",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    continue
                sign = inspect.signature(
                    origin.__init__,
                    **signature_kwargs,
                )
            elif inspect.isfunction(dep.dependency):
                # If this is function or an instance of a class, we get it's type hints.
                try:
                    hints = get_type_hints(dep.dependency)
                except NameError:
                    _, src_lineno = inspect.getsourcelines(dep.dependency)  # type: ignore
                    src_file = Path(inspect.getfile(dep.dependency))
                    cwd = Path.cwd()
                    if src_file.is_relative_to(cwd):
                        src_file = src_file.relative_to(cwd)
                    warnings.warn(
                        "Cannot resolve type hints for "
                        f"a function {dep.dependency.__name__} defined "
                        f"at {src_file}:{src_lineno}.",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    continue
                sign = inspect.signature(origin, **signature_kwargs)  # type: ignore
            else:
                try:
                    hints = get_type_hints(
                        dep.dependency.__call__,  # type: ignore
                    )
                except NameError:
                    _, src_lineno = inspect.getsourcelines(dep.dependency.__class__)
                    src_file = Path(inspect.getfile(dep.dependency.__class__))
                    cwd = Path.cwd()
                    if src_file.is_relative_to(cwd):
                        src_file = src_file.relative_to(cwd)
                    cls_name = dep.dependency.__class__.__name__
                    warnings.warn(
                        "Cannot resolve type hints for "
                        f"an object of class {cls_name} defined "
                        f"at {src_file}:{src_lineno}.",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    continue
                sign = inspect.signature(origin, **signature_kwargs)  # type: ignore

            # Now we need to iterate over parameters, to
            # find all parameters, that have TaskiqDepends as it's
            # default vaule.
            for param_name, param in sign.parameters.items():
                default_value = param.default
                if hasattr(param.annotation, "__metadata__"):
                    # We go backwards,
                    # because you may want to override your annotation
                    # and the overriden value will appear to be after
                    # the original `Depends` annotation.
                    for meta in reversed(param.annotation.__metadata__):
                        if isinstance(meta, Dependency):
                            default_value = meta
                            break
                        if FastapiDepends is not None and isinstance(
                            meta,
                            FastapiDepends,
                        ):
                            default_value = meta
                            break

                # This is for FastAPI integration. So you can
                # use Depends from taskiq mixed with fastapi's dependencies.
                if FastapiDepends is not None and isinstance(
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
