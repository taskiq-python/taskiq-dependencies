import inspect
import sys
from typing import Any, AsyncContextManager, ContextManager, Optional

if sys.version_info < (3, 10):
    from typing_extensions import TypeGuard  # noqa: WPS433
else:
    from typing import TypeGuard  # noqa: WPS433


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
        signature: Optional[inspect.Parameter] = None,
    ) -> None:
        self.name = name
        self.definition = signature

    def __repr__(self) -> str:
        return f"ParamInfo<name={self.name}>"


def iscontextmanager(obj: Any) -> TypeGuard[ContextManager[Any]]:
    """
    Return true if the object is a sync context manager.

    :param obj: object to check.
    :return: bool that indicates whether the object is a context manager or not.
    """
    if not hasattr(obj, "__enter__"):  # noqa: WPS421
        return False
    elif not hasattr(obj, "__exit__"):  # noqa: WPS421
        return False
    return True


def isasynccontextmanager(obj: Any) -> TypeGuard[AsyncContextManager[Any]]:
    """
    Return true if the object is a async context manager.

    :param obj: object to check.
    :return: bool that indicates whether the object is a async context manager or not.
    """
    if not hasattr(obj, "__aenter__"):  # noqa: WPS421
        return False
    elif not hasattr(obj, "__aexit__"):  # noqa: WPS421
        return False
    return True
