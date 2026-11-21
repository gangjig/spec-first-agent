"""Loading spec files and implementation modules.

A spec file is a plain Python module that defines:

- ``TARGET``: the name of the function in the implementation module that
  the properties check (a string, e.g. ``"sort_numbers"``).
- ``TASK`` (optional): a one-line human description of the task.
- one or more ``prop_*`` functions. Each property takes exactly two
  arguments, ``(impl, rng)``:

  - ``impl`` is the target callable (or a stand-in for it during
    sanity checks). Call it with generated inputs.
  - ``rng`` is a seeded ``random.Random``; use it to generate inputs so
    runs are reproducible.

  A property returns ``True`` / ``False``, or ``(bool, message)``.
  Returning ``False`` or raising ``AssertionError`` fails the property;
  any other exception is recorded as an error (also a failure).

An implementation module is a plain Python module that defines the
``TARGET`` function.
"""

from __future__ import annotations

import importlib.util
import inspect
import random
from dataclasses import dataclass, field


class SpecError(Exception):
    """The spec file or implementation module is unusable."""


@dataclass
class Property:
    name: str
    func: object
    doc: str = ""


@dataclass
class Spec:
    path: str
    target: str
    task: str
    properties: list[Property] = field(default_factory=list)


def load_module(path: str, module_name: str):
    """Import a Python file by path, raising SpecError on failure."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise SpecError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - report the load failure plainly
        raise SpecError(f"cannot load {path}: {type(exc).__name__}: {exc}") from exc
    return module


def load_spec(path: str) -> Spec:
    """Load and validate a spec file (well-formedness only)."""
    module = load_module(path, "_spec_first_spec")
    target = getattr(module, "TARGET", None)
    if not isinstance(target, str) or not target:
        raise SpecError("spec must define TARGET as the name of the function to check")
    properties = []
    for name in dir(module):
        if not name.startswith("prop_"):
            continue
        func = getattr(module, name)
        if not callable(func):
            raise SpecError(f"{name} is not callable")
        params = [
            p
            for p in inspect.signature(func).parameters.values()
            if p.kind
            in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        if len(params) != 2:
            raise SpecError(f"{name} must take exactly two arguments (impl, rng)")
        doc = (inspect.getdoc(func) or "").strip().splitlines()
        properties.append(Property(name=name, func=func, doc=doc[0] if doc else ""))
    if not properties:
        raise SpecError("spec defines no prop_* properties")
    properties.sort(key=lambda p: p.name)
    task = getattr(module, "TASK", "")
    if not isinstance(task, str):
        raise SpecError("TASK must be a string when present")
    return Spec(path=path, target=target, task=task, properties=properties)


def load_impl(path: str, target: str):
    """Load the TARGET callable from an implementation module."""
    module = load_module(path, "_spec_first_impl")
    func = getattr(module, target, None)
    if func is None:
        raise SpecError(f"implementation {path} does not define {target!r}")
    if not callable(func):
        raise SpecError(f"{target!r} in {path} is not callable")
    return func


@dataclass
class PropertyResult:
    name: str
    passed: bool
    message: str = ""
    calls: int = 0
    error: str = ""


class _CallCounter:
    """Wrap a callable and count how many times it is invoked."""

    def __init__(self, func):
        self._func = func
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self._func(*args, **kwargs)


def run_property(prop: Property, impl, seed: int) -> PropertyResult:
    """Run one property against one implementation with a fixed seed.

    Returns a PropertyResult. A property that raises AssertionError
    fails with the assertion message; any other exception is an error
    (also a failure). A return value that is not a bool or a
    (bool, message) pair is an error.
    """
    counter = _CallCounter(impl)
    rng = random.Random(seed)
    try:
        outcome = prop.func(counter, rng)
    except AssertionError as exc:
        return PropertyResult(
            name=prop.name, passed=False,
            message=str(exc) or "assertion failed", calls=counter.calls,
        )
    except Exception as exc:  # noqa: BLE001 - a crashing property is a failed property
        return PropertyResult(
            name=prop.name, passed=False,
            message=f"{type(exc).__name__}: {exc}", calls=counter.calls,
            error=f"{type(exc).__name__}: {exc}",
        )
    if isinstance(outcome, tuple):
        if len(outcome) != 2:
            return PropertyResult(
                name=prop.name, passed=False,
                message="property must return bool or (bool, message)",
                calls=counter.calls, error="bad return arity",
            )
        ok, message = outcome
    else:
        ok, message = outcome, ""
    if not isinstance(ok, bool):
        return PropertyResult(
            name=prop.name, passed=False,
            message="property must return bool or (bool, message)",
            calls=counter.calls, error="bad return type",
        )
    return PropertyResult(
        name=prop.name, passed=bool(ok), message=str(message), calls=counter.calls
    )
