import inspect
from typing import Optional


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
