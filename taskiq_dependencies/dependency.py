import inspect
import uuid
from collections.abc import Coroutine
from contextlib import _AsyncGeneratorContextManager, _GeneratorContextManager
from types import CoroutineType
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    Generator,
    Optional,
    Type,
    TypeVar,
    Union,
    overload,
)

_T = TypeVar("_T")


@overload
def Depends(
    dependency: Optional[Callable[..., "_GeneratorContextManager[_T]"]] = None,
    *,
    use_cache: bool = True,
    kwargs: Optional[Dict[str, Any]] = None,
) -> _T:  # pragma: no cover
    ...


@overload
def Depends(
    dependency: Optional[Callable[..., "_AsyncGeneratorContextManager[_T]"]] = None,
    *,
    use_cache: bool = True,
    kwargs: Optional[Dict[str, Any]] = None,
) -> _T:  # pragma: no cover
    ...


@overload
def Depends(
    dependency: Optional[Callable[..., AsyncGenerator[_T, None]]] = None,
    *,
    use_cache: bool = True,
    kwargs: Optional[Dict[str, Any]] = None,
) -> _T:  # pragma: no cover
    ...


@overload
def Depends(
    dependency: Optional[Callable[..., Generator[_T, None, None]]] = None,
    *,
    use_cache: bool = True,
    kwargs: Optional[Dict[str, Any]] = None,
) -> _T:  # pragma: no cover
    ...


@overload
def Depends(
    dependency: Optional[Type[_T]] = None,
    *,
    use_cache: bool = True,
    kwargs: Optional[Dict[str, Any]] = None,
) -> _T:  # pragma: no cover
    ...


@overload
def Depends(
    dependency: Optional[Callable[..., "CoroutineType[Any, Any, _T]"]] = None,
    *,
    use_cache: bool = True,
    kwargs: Optional[Dict[str, Any]] = None,
) -> _T:  # pragma: no cover
    ...


@overload
def Depends(
    dependency: Optional[Callable[..., Coroutine[Any, Any, _T]]] = None,
    *,
    use_cache: bool = True,
    kwargs: Optional[Dict[str, Any]] = None,
) -> _T:  # pragma: no cover
    ...


@overload
def Depends(
    dependency: Optional[Callable[..., _T]] = None,
    *,
    use_cache: bool = True,
    kwargs: Optional[Dict[str, Any]] = None,
) -> _T:  # pragma: no cover
    ...


def Depends(
    dependency: Optional[Any] = None,
    *,
    use_cache: bool = True,
    kwargs: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Constructs a dependency.

    This function returns TaskiqDepends
    and needed for typehinting.

    :param dependency: function to run as a dependency.
    :param use_cache: whether the dependency
        can use previously calculated dependencies.
    :param kwargs: optional keyword arguments to the dependency.
        May be used to parametrize dependencies.
    :return: TaskiqDepends instance.
    """
    return Dependency(
        dependency=dependency,
        use_cache=use_cache,
        kwargs=kwargs,
    )


class Dependency:
    """
    Class to mark parameter as a dependency.

    This class is used to mark parameters of a function,
    or a class as injectables, so taskiq can resolve it
    and calculate before execution.
    """

    def __init__(
        self,
        dependency: Optional[Union[Type[Any], Callable[..., Any]]] = None,
        *,
        use_cache: bool = True,
        kwargs: Optional[Dict[str, Any]] = None,
        signature: Optional[inspect.Parameter] = None,
        parent: "Optional[Dependency]" = None,
    ) -> None:
        self._id = uuid.uuid4()
        self.dependency = dependency
        self.use_cache = use_cache
        self.param_name = ""
        self.kwargs = kwargs or {}
        self.signature = signature
        self.parent = parent

    def __hash__(self) -> int:
        return hash(self._id)

    def __eq__(self, rhs: object) -> bool:
        """
        Overriden eq operation.

        This is required to perform correct topological
        sort after building dependency graph.

        :param rhs: object to compare.
        :return: True if objects are equal.
        """
        if not isinstance(rhs, Dependency):
            return False
        return self._id == rhs._id

    def __repr__(self) -> str:
        func_name = str(self.dependency)
        if self.dependency is not None and hasattr(self.dependency, "__name__"):
            func_name = self.dependency.__name__
        return (
            f"Dependency({func_name}, "
            f"use_cache={self.use_cache}, "
            f"kwargs={self.kwargs}, "
            f"parent={self.parent}"
            ")"
        )
