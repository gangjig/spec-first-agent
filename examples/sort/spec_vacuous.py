"""A vacuous spec: both properties pass everything, so they check nothing.

- prop_always_true never calls the implementation at all.
- prop_tautology calls it but returns True whatever it returns.

`spec-first check-spec spec_vacuous.py` flags both, and `done` refuses
to mark anything built against this spec as complete.
"""

TARGET = "sort_numbers"
TASK = "sort a list of numbers (vacuous spec, for demonstration)"


def prop_always_true(impl, rng):
    """Never calls impl: passes every mutant, catches nothing."""
    return True, ""


def prop_tautology(impl, rng):
    """Calls impl but ignores the result: also passes every mutant."""
    for _ in range(10):
        xs = [rng.randint(-100, 100) for _ in range(rng.randint(0, 5))]
        impl(xs)
    return True, ""
