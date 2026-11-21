"""Broken implementation: sorts, but silently drops duplicate items.

The spec catches it: prop_ordered passes (the output IS ordered),
but prop_same_items and prop_length_preserved fail.
"""


def sort_numbers(xs):
    return sorted(set(xs))
