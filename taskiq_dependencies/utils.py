import inspect
import sys
from contextlib import _AsyncGeneratorContextManager, _GeneratorContextManager
from typing import TYPE_CHECKING, Any, AsyncContextManager, ContextManager, Optional

if sys.version_info >= (3, 10):
    from typing import TypeGuard
else:
    from typing_extensions import TypeGuard

if TYPE_CHECKING:
    from taskiq_dependencies.graph import DependencyGraph


class ParamInfo:
    """
    Parameter information.

    This class helps you to get information,
    about how the current dependency was specified.

    If there's no dependant function, the name will be an empty string
    and the definition will be None.
    """

    def __init__(
        self,
        name: str,
        graph: "DependencyGraph",
        signature: Optional[inspect.Parameter] = None,
    ) -> None:
        self.name = name
        self.graph = graph
        self.definition = signature

    def __repr__(self) -> str:
        return f"ParamInfo<name={self.name}>"


def iscontextmanager(obj: Any) -> TypeGuard[ContextManager[Any]]:
    """
    Return true if the object is a sync context manager.

    :param obj: object to check.
    :return: bool that indicates whether the object is a context manager or not.
    """
    return issubclass(obj.__class__, _GeneratorContextManager)


def isasynccontextmanager(obj: Any) -> TypeGuard[AsyncContextManager[Any]]:
    """
    Return true if the object is a async context manager.

    :param obj: object to check.
    :return: bool that indicates whether the object is a async context manager or not.
    """
    return issubclass(obj.__class__, _AsyncGeneratorContextManager)
