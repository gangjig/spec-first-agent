"""spec-first-agent: write the spec first, then the code.

A task is DONE only when every machine-checkable property in its spec
passes against the implementation. The spec itself is sanity-checked
first: a spec that cannot fail (vacuous, tautological, or never calling
the implementation) is rejected before any implementation work begins.
"""

__version__ = "0.1.0"
