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
