"""
This module defines the various contracts, i.e. types of plugins supported by
Transformer.
The term "contract" indicates that these types constrain what plugin
implementors can do in Transformer.

Transformer plugins are just functions that accept certain inputs and have
certain outputs.
Different types of plugins have different input and output types.
Not all types of plugins can be applied at the same point in Transformer's
pipeline (e.g. python.Program objects are built much later than Task objects),
hence the multiplicity of contracts.

# Plugin contracts

## OnTask

Kind of "stateless" plugins that operate independently on each task.
When implementing one, imagine their execution could be parallelized by
Transformer in the future.

Example: a plugin that injects a header in all requests.

## OnScenario

Kind of plugins that operate on scenarios.

Each scenario is the root of a tree composed of smaller scenarios and tasks
(the leaves of this tree). Therefore, in an OnScenario plugin, you have the
possibility of inspecting the subtree and making decisions based on that.
However, OnScenario plugins will be applied to all scenarios by Transformer,
so you don't need to recursively apply the plugin yourself on all subtrees.
If you do that, the plugin will be applied many times more than necessary.

Example: a plugin that keeps track of how long each scenario runs.

## OnPythonProgram

Kind of plugins that operate on the whole syntax tree.

The input and output of this kind of plugins is the complete, final locustfile
generated by Transformer, represented as a syntax tree.
OnPythonProgram plugins therefore have the most freedom compared to other
plugin kinds, because they can change anything.
Their downside is that manipulating the syntax tree is more complex than the
scenario tree or individual tasks.

Example: a plugin that injects some code in the global scope.

# Other contracts

This module also defines:

## Plugin

Any supported contract of Transformer plugin.
"""
import enum
from collections import defaultdict
from typing import Callable, NewType, Iterable, TypeVar, List, DefaultDict


class Contract(enum.Flag):
    """
    Enumeration of all supported plugin contracts. Each contract defines a way
    for plugins to be used in Transformer.

    Any function may become a Transformer plugin by announcing that
    it implements at least one contract, using the @plugin decorator.
    """

    OnTask = enum.auto()
    OnScenario = enum.auto()
    OnPythonProgram = enum.auto()

    # Historically Transformer has only one plugin contract, which transformed a
    # sequence of Task objects into another such sequence. Operating on a full list
    # of tasks (instead of task by task) offered more leeway: a plugin could e.g.
    # add a new task, or change only the first task.
    # However this OnTaskSequence model is too constraining for some use-cases,
    # e.g. when a plugin needs to inject code in the global scope, and having to
    # deal with a full, immutable list of tasks in plugins that independently
    # operate on each task implies a lot of verbosity and redundancy.
    # For these reasons, other plugin contracts were created to offer a more
    # varied choice for plugin implementers.
    # See https://github.com/zalando-incubator/Transformer/issues/10.
    OnTaskSequence = enum.auto()


Plugin = NewType("Plugin", callable)


class InvalidContractError(ValueError):
    """
    Raised for plugin functions associated with invalid contracts.

    What an "invalid contract" represents is not strictly specified,
    but this includes at least objects that are not members of the Contract
    enumeration.
    """


class InvalidPluginError(ValueError):
    """
    Raised when trying to use as plugin a function that has not been marked
    as such.
    """


def plugin(c: Contract) -> Callable[[callable], callable]:
    """
    Function decorator. Use it to associate a function to a Contract, making it
    a Transformer plugin that will be detected by resolve().

    :param c: the contract to associate to the decorated function.
    :raise InvalidContractError: if c is not a valid contract.
    """
    if not isinstance(c, Contract):
        suggestions = (f"@plugin(Contract.{x.name})" for x in Contract)
        raise InvalidContractError(
            f"{c!r} is not a {Contract.__qualname__}. "
            f"Did you mean {', '.join(suggestions)}?"
        )

    def _decorate(f: callable) -> callable:
        f._transformer_plugin_contract = c
        return f

    return _decorate


def contract(f: Plugin) -> Contract:
    """
    Returns the contract associated to a plugin function.

    :raise InvalidPluginError: if f is not a plugin.
    """
    try:
        return getattr(f, "_transformer_plugin_contract")
    except AttributeError:
        raise InvalidPluginError(f) from None


_T = TypeVar("_T")


def apply(plugins: Iterable[Plugin], init: _T) -> _T:
    """
    Applies each plugin to init in order, and returns the result.

    This just wraps a very simple but common operation.
    """
    for p in plugins:
        init = p(init)
    return init


_BASE_CONTRACTS = (
    Contract.OnTask,
    Contract.OnTaskSequence,
    Contract.OnScenario,
    Contract.OnPythonProgram,
)


def group_by_contract(plugins: Iterable[Plugin]) -> DefaultDict[Contract, List[Plugin]]:
    """
    Groups plugins in lists according to their contracts.
    Each plugin is found in as many lists as it implements base contracts.
    Lists keep the order of the original plugins iterable.
    """
    res = defaultdict(list)
    for p in plugins:
        c = contract(p)
        for bc in _BASE_CONTRACTS:
            if c & bc:  # Contract is an enum.Flag: & computes the intersection.
                res[bc].append(p)
    return res
