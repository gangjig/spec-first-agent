"""Verify an implementation against a spec: every property must pass."""

from __future__ import annotations

from dataclasses import dataclass, field

from spec_first.spec import PropertyResult, Spec, run_property


@dataclass
class VerifyReport:
    spec_path: str
    impl_path: str
    results: list[PropertyResult] = field(default_factory=list)
    passed: bool = False


def verify(spec: Spec, impl, impl_path: str, *, seed: int = 1234) -> VerifyReport:
    """Run every property in the spec against the implementation."""
    report = VerifyReport(spec_path=spec.path, impl_path=impl_path)
    for index, prop in enumerate(spec.properties):
        report.results.append(run_property(prop, impl, seed + index))
    report.passed = all(r.passed for r in report.results)
    return report
