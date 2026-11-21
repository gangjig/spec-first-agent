"""Spec for sorting a list of numbers.

The spec is written BEFORE any implementation. Each property states one
invariant the output must satisfy, as a check over generated inputs.
"""

TARGET = "sort_numbers"
TASK = "sort a list of numbers"


def prop_ordered(impl, rng):
    """The output must be in non-decreasing order."""
    for _ in range(50):
        xs = [rng.randint(-100, 100) for _ in range(rng.randint(0, 20))]
        out = impl(xs)
        if list(out) != sorted(out):
            return False, f"not ordered: {xs} -> {out}"
    return True, ""


def prop_same_items(impl, rng):
    """The output must contain exactly the same items as the input."""
    for _ in range(50):
        xs = [rng.randint(-100, 100) for _ in range(rng.randint(0, 20))]
        out = impl(xs)
        if sorted(out) != sorted(xs):
            return False, f"items changed: {xs} -> {out}"
    return True, ""


def prop_length_preserved(impl, rng):
    """The output must have the same length as the input."""
    for _ in range(50):
        xs = [rng.randint(-100, 100) for _ in range(rng.randint(0, 20))]
        out = impl(xs)
        if len(out) != len(xs):
            return False, f"length changed: {xs} -> {out}"
    return True, ""
