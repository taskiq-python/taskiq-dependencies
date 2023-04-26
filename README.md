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
