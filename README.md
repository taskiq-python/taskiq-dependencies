# Taskiq dependencies

This project is used to add FastAPI-like dependency injection to projects.

This project is a part of the taskiq, but it doesn't have any dependencies,
and you can easily integrate it in any project.

# Installation

```bash
pip install taskiq-dependencies
```

# Usage

Let's imagine you want to add DI in your project. What should you do?
At first we need to create a dependency graph, check if there any cycles
and compute the order of dependencies. This can be done with DependencyGraph.
It does all of those actions on create. So we can remember all graphs at the start of
our program for later use. Or we can do it when needed, but it's less optimal.

```python
from taskiq_dependencies import Depends


def dep1() -> int:
    return 1


def target_func(some_int: int = Depends(dep1)):
    print(some_int)
    return some_int + 1

```

In this example we have a function called `target_func` and as you can see, it depends on `dep1` dependency.

To create a dependnecy graph have to write this:
```python
from taskiq_dependencies import DependencyGraph

graph = DependencyGraph(target_func)
```

That's it. Now we want to resolve all dependencies and call a function. It's simple as this:

```python
with graph.sync_ctx() as ctx:
    graph.target(**ctx.resolve_kwargs())
```

Voila! We resolved all dependencies and called a function with no arguments.
The `resolve_kwargs` function will return a dict, where keys are parameter names, and values are resolved dependencies.


### Async usage

If your lib is asynchronous, you should use async context, it's similar to sync context, but instead of `with` you should use `async with`. But this way your users can use async dependencies and async generators. It's not possible in sync context.


```python
async with graph.async_ctx() as ctx:
    kwargs = await ctx.resolve_kwargs()
```

## Q&A

> Why should I use `with` or `async with` statements?

Becuase users can use generator functions as dependencies.
Everything before `yield` happens before injecting the dependency, and everything after `yield` is executed after the `with` statement is over.

> How to provide default dependencies?

It maybe useful to have default dependencies for your project.
For example, taskiq has `Context` and `State` classes that can be used as dependencies. `sync_context` and `async_context` methods have a parameter, where you can pass a dict with precalculated dependencies.


```python
from taskiq_dependencies import Depends, DependencyGraph


class DefaultDep:
    ...


def target_func(dd: DefaultDep = Depends()):
    print(dd)
    return 1


graph = DependencyGraph(target_func)

with graph.sync_ctx({DefaultDep: DefaultDep()}) as ctx:
    print(ctx.resolve_kwargs())

```

You can run this code. It will resolve dd dependency into a `DefaultDep` variable you provide.


## Getting parameters information

If you want to get the information about how this dependency was specified,
you can use special class `ParamInfo` for that.

```python
from taskiq_dependencies import Depends, DependencyGraph, ParamInfo


def dependency(info: ParamInfo = Depends()) -> str:
    assert info.name == "dd"
    return info.name

def target_func(dd: str = Depends(dependency)):
    print(dd)
    return 1


graph = DependencyGraph(target_func)

with graph.sync_ctx() as ctx:
    print(ctx.resolve_kwargs())

```

The ParamInfo has the information about name and parameters signature. It's useful if you want to create a dependency that changes based on parameter name, or signature.


## Exception propagation

By default if error happens within the context, we send this error to the dependency,
so you can close it properly. You can disable this functionality by setting `exception_propagation` parameter to `False`.

Let's imagine that you want to get a database session from pool and commit after the function is done.


```python
async def get_session():
    session = sessionmaker()

    yield session

    await session.commit()

```

But what if the error happened when the dependant function was called? In this case you want to rollback, instead of commit.
To solve this problem, you can just wrap the `yield` statement in `try except` to handle the error.

```python
async def get_session():
    session = sessionmaker()

    try:
        yield session
    except Exception:
        await session.rollback()
        return

    await session.commit()

```

**Also, as a library developer, you can disable exception propagation**. If you do so, then no exception will ever be propagated to dependencies and no such `try except` expression will ever work.


Example of disabled propogation.

```python

graph = DependencyGraph(target_func)

with graph.sync_ctx(exception_propagation=False) as ctx:
    print(ctx.resolve_kwargs())


```


## Generics support

We support generics substitution for class-based dependencies.
For example, let's define an interface and a class. This class can be
parameterized with some type and we consider this type a dependency.

```python
import abc
from typing import Any, Generic, TypeVar

class MyInterface(abc.ABC):
    @abc.abstractmethod
    def getval(self) -> Any:
        ...


_T = TypeVar("_T", bound=MyInterface)


class MyClass(Generic[_T]):
    # We don't know exact type, but we assume
    # that it can be used as a dependency.
    def __init__(self, resource: _T = Depends()):
        self.resource = resource

    @property
    def my_value(self) -> Any:
        return self.resource.getval()

```

Now let's create several implementation of defined interface:

```python

def getstr() -> str:
    return "strstr"


def getint() -> int:
    return 100


class MyDep1(MyInterface):
    def __init__(self, s: str = Depends(getstr)) -> None:
        self.s = s

    def getval(self) -> str:
        return self.s


class MyDep2(MyInterface):
    def __init__(self, i: int = Depends(getint)) -> None:
        self.i = i

    def getval(self) -> int:
        return self.i

```

Now you can use these dependencies by just setting proper type hints.

```python
def my_target(
    d1: MyClass[MyDep1] = Depends(),
    d2: MyClass[MyDep2] = Depends(),
) -> None:
    print(d1.my_value)
    print(d2.my_value)


with DependencyGraph(my_target).sync_ctx() as ctx:
    my_target(**ctx.resolve_kwargs())

```

This code will is going to print:

```
strstr
100
```

## Dependencies replacement

You can replace dependencies in runtime, it will recalculate graph
and will execute your function with updated dependencies.

**!!! This functionality tremendously slows down dependency resolution.**

Use this functionality only for tests. Otherwise, you will end up building dependency graphs on every resolution request. Which is very slow.

But for tests it may be a game changer, since you don't want to change your code, but some dependencies instead.

Here's an example. Imagine you have a built graph for a specific function, like this:

```python
from taskiq_dependencies import DependencyGraph, Depends


def dependency() -> int:
    return 1


def target(dep_value: int = Depends(dependency)) -> None:
    assert dep_value == 1

graph = DependencyGraph(target)
```

Normally, you would call the target, by writing something like this:

```python
with graph.sync_ctx() as ctx:
    target(**ctx.resolve_kwargs())
```

But what if you want to replace dependency in runtime, just
before resolving kwargs? The solution is to add `replaced_deps`
parameter to the context method. For example:

```python
def replaced() -> int:
    return 2


with graph.sync_ctx(replaced_deps={dependency: replaced}) as ctx:
    target(**ctx.resolve_kwargs())
```

Furthermore, the new dependency can depend on other dependencies. Or you can change type of your dependency, like generator instead of plain return. Everything should work as you would expect it.

## Annotated types

Taskiq dependenices also support dependency injection through Annotated types.

```python
from typing import Annotated

async def my_function(dependency: Annotated[int, Depends(my_func)]):
    pass
```

Or you can specify classes


```python
from typing import Annotated

class MyClass:
    pass

async def my_function(dependency: Annotated[MyClass, Depends(my_func)]):
    pass
```

And, of course you can easily save such type aliases in variables.

```python
from typing import Annotated

DepType = Annotated[int, Depends(my_func)]

def my_function(dependency: DepType):
    pass

```

Also we support overrides for annotated types.

For example:

```python
from typing import Annotated

DepType = Annotated[int, Depends(my_func)]

def my_function(
    dependency: DepType,
    no_cache_dep: Annotated[DepType, Depends(my_func, use_cache=False)],
) -> None:
    pass

```

Also, please note that if you're using `from __future__ import annotations` it won't work for python <= 3.9. Because the `inspect.signature` function doesn't support it. In all future versions it will work as expected.
