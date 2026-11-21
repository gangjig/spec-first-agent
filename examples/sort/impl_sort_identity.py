"""Broken implementation: returns the input unchanged.

The spec catches it: prop_ordered fails on unsorted inputs.
"""


def sort_numbers(xs):
    return list(xs)
