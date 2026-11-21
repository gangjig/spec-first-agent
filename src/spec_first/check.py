"""Sanity-check a spec before any implementation work begins.

A spec passes the sanity check only if every property:

1. actually calls the implementation at least once (a property that
   never calls ``impl`` checks nothing), and
2. fails on at least one built-in mutant *by returning False*. Merely
   crashing on a mutant does not count: a property that calls ``impl``
   and ignores the result still crashes when the mutant raises, so a
   crash proves nothing about what the property checks. A property
   that passes every mutant it can judge is vacuous: it would bless
   broken code, so it cannot catch a real mistake.

Optionally, when an implementation is supplied (``check-spec --impl``
or the ``done`` gate), each property must also pass against it. That
leg proves the spec is *satisfiable*: a spec no implementation could
ever satisfy (for example, one property demanding the output sorted
and another demanding it reversed) fails here. Without an
implementation the check can only prove the spec can fail, not that it
can pass, and the report says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from spec_first.mutants import make_mutants
from spec_first.spec import PropertyResult, Spec, run_property


@dataclass
class PropertySanity:
    name: str
    status: str  # "ok" | "vacuous"
    calls: int
    mutants_caught: list[str] = field(default_factory=list)
    mutants_missed: list[str] = field(default_factory=list)
    mutants_errored: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class SanityReport:
    spec_path: str
    per_property: list[PropertySanity] = field(default_factory=list)
    satisfiable: bool | None = None  # None when no implementation was supplied
    satisfiability_failures: list[PropertyResult] = field(default_factory=list)
    passed: bool = False


def check_spec(spec: Spec, *, seed: int = 1234, impl=None) -> SanityReport:
    """Run the sanity check on a loaded spec."""
    mutants = make_mutants(seed)
    report = SanityReport(spec_path=spec.path)
    for index, prop in enumerate(spec.properties):
        prop_seed = seed + index
        calls = 0
        caught: list[str] = []
        missed: list[str] = []
        errored: list[str] = []
        for mutant_name, mutant_fn in mutants:
            result = run_property(prop, mutant_fn, prop_seed)
            calls = max(calls, result.calls)
            if result.error:
                # The property crashed instead of judging: a tautology
                # that ignores impl's result crashes on the raises
                # mutant too, so a crash is not evidence it can fail.
                errored.append(mutant_name)
            elif result.passed:
                missed.append(mutant_name)
            else:
                caught.append(mutant_name)
        if calls == 0:
            status = "vacuous"
            reason = "property never calls the implementation"
        elif not caught:
            status = "vacuous"
            reason = "property never returns False on any mutant (cannot fail)"
        else:
            status = "ok"
            reason = ""
        report.per_property.append(
            PropertySanity(
                name=prop.name, status=status, calls=calls,
                mutants_caught=caught, mutants_missed=missed,
                mutants_errored=errored, reason=reason,
            )
        )
    if impl is not None:
        report.satisfiable = True
        for index, prop in enumerate(spec.properties):
            result = run_property(prop, impl, seed + index)
            if not result.passed:
                report.satisfiable = False
                report.satisfiability_failures.append(result)
    report.passed = all(p.status == "ok" for p in report.per_property) and (
        report.satisfiable is not False
    )
    return report
