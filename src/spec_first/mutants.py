"""Built-in adversarial implementations (mutants) for spec sanity checks.

A spec is only worth anything if it can fail. The sanity check runs
each property against these deliberately broken stand-ins for the
implementation and requires the property to *fail* on at least one of
them. A property that passes every mutant is vacuous: it blesses broken
code, so it cannot catch a real mistake either.

Mutants operate on the first positional argument when it is a sequence;
mutants that cannot apply to the given arguments raise, which also
counts as the property not passing (it did not bless the mutant).
"""

from __future__ import annotations

import random


def _first_sequence(args, kwargs):
    for value in args:
        if isinstance(value, (list, tuple)) and not isinstance(value, (str, bytes)):
            return value
    return None


def _identity(*args, **kwargs):
    return args[0] if args else None


def _empty(*args, **kwargs):
    return []


def _none(*args, **kwargs):
    return None


def _reversed_seq(*args, **kwargs):
    seq = _first_sequence(args, kwargs)
    if seq is None:
        raise TypeError("mutant reversed: no sequence argument")
    return list(reversed(seq))


def _raises(*args, **kwargs):
    raise RuntimeError("mutant failure")


def make_mutants(seed: int):
    """Return the list of (name, callable) mutants for one sanity run."""
    shuffle_rng = random.Random(seed)

    def _shuffled(*args, **kwargs):
        seq = _first_sequence(args, kwargs)
        if seq is None:
            raise TypeError("mutant shuffled: no sequence argument")
        out = list(seq)
        shuffle_rng.shuffle(out)
        return out

    return [
        ("identity", _identity),
        ("empty", _empty),
        ("none", _none),
        ("reversed", _reversed_seq),
        ("shuffled", _shuffled),
        ("raises", _raises),
    ]
