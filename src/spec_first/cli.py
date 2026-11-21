"""Command-line interface for spec-first-agent.

Commands:
  init NAME              scaffold a new task directory (spec + impl stub)
  check-spec SPEC        sanity-check a spec (vacuity + optional satisfiability)
  verify SPEC IMPL       run every property against an implementation
  done SPEC IMPL         the done-gate: spec sanity + verification, both must pass

Exit codes: 0 pass / done, 1 check failed / not done, 2 usage or load error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from spec_first import __version__
from spec_first.check import check_spec
from spec_first.spec import SpecError, load_impl, load_spec
from spec_first.verify import verify

DEFAULT_SEED = 1234

SPEC_TEMPLATE = '''"""Spec for {task}.

Write properties BEFORE writing any implementation. Each property
takes (impl, rng): call impl with generated inputs and return True
(or (True, "")) when the property holds, False (or (False, "why"))
when it does not.
"""

TARGET = "{target}"
TASK = "{task}"


def prop_example(impl, rng):
    """Example: the output must satisfy <state the invariant here>."""
    for _ in range(50):
        value = rng.randint(0, 100)
        out = impl(value)
        if out != value:  # replace with the real invariant
            return False, f"expected {{value}}, got {{out}}"
    return True, ""
'''

IMPL_TEMPLATE = '''"""Implementation for {task}.

Write this only after `spec-first check-spec spec.py` passes.
The task is DONE only when `spec-first done spec.py impl.py` passes.
"""


def {target}(value):
    """TODO: implement."""
    raise NotImplementedError
'''


def _emit_text(lines: list[str]) -> None:
    for line in lines:
        print(line)


def _property_result_dict(result) -> dict:
    return {
        "property": result.name,
        "passed": result.passed,
        "message": result.message,
        "calls": result.calls,
        "error": result.error,
    }


def _cmd_init(args: argparse.Namespace) -> int:
    target_dir = Path(args.directory) / args.name if args.directory else Path(args.name)
    if target_dir.exists():
        print(f"error: {target_dir} already exists", file=sys.stderr)
        return 2
    target_dir.mkdir(parents=True)
    task = args.name.replace("-", " ").replace("_", " ")
    target = "solve"
    (target_dir / "spec.py").write_text(
        SPEC_TEMPLATE.format(task=task, target=target), encoding="utf-8"
    )
    (target_dir / "impl.py").write_text(
        IMPL_TEMPLATE.format(task=task, target=target), encoding="utf-8"
    )
    print(f"created {target_dir}/spec.py and {target_dir}/impl.py")
    print("next steps:")
    print(f"  1. edit {target_dir}/spec.py: replace the example property with real ones")
    print(f"  2. spec-first check-spec {target_dir}/spec.py")
    print(f"  3. implement {target_dir}/impl.py (only after step 2 passes)")
    print(f"  4. spec-first done {target_dir}/spec.py {target_dir}/impl.py")
    return 0


def _cmd_check_spec(args: argparse.Namespace) -> int:
    try:
        spec = load_spec(args.spec)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    impl = None
    if args.impl:
        try:
            impl = load_impl(args.impl, spec.target)
        except SpecError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    report = check_spec(spec, seed=args.seed, impl=impl)
    if args.format == "json":
        print(json.dumps({
            "command": "check-spec",
            "spec": report.spec_path,
            "passed": report.passed,
            "satisfiable": report.satisfiable,
            "properties": [
                {
                    "property": p.name,
                    "status": p.status,
                    "calls": p.calls,
                    "mutants_caught": p.mutants_caught,
                    "mutants_missed": p.mutants_missed,
                    "mutants_errored": p.mutants_errored,
                    "reason": p.reason,
                }
                for p in report.per_property
            ],
            "satisfiability_failures": [
                _property_result_dict(r) for r in report.satisfiability_failures
            ],
        }, indent=2))
    else:
        task = f" ({spec.task})" if spec.task else ""
        _emit_text([f"spec: {spec.path}{task}", f"target: {spec.target}", ""])
        for p in report.per_property:
            status = "OK" if p.status == "ok" else "VACUOUS"
            detail = (
                f"calls={p.calls} caught={','.join(p.mutants_caught) or '-'}"
                + (f" errored={','.join(p.mutants_errored)}" if p.mutants_errored else "")
                + (f" -- {p.reason}" if p.reason else "")
            )
            _emit_text([f"  [{status}] {p.name}: {detail}"])
        if report.satisfiable is None:
            _emit_text(["", "satisfiability: not checked (no --impl given);",
                        "  run `done` or `check-spec --impl` to prove the spec can pass."])
        elif report.satisfiable:
            _emit_text(["", "satisfiability: all properties pass on the supplied implementation"])
        else:
            _emit_text(["", "satisfiability: FAILED -- properties failing on the supplied",
                        "  implementation (spec or implementation is wrong):"])
            for r in report.satisfiability_failures:
                _emit_text([f"  [FAIL] {r.name}: {r.message}"])
        _emit_text(["", "sanity check: " + ("PASS" if report.passed else "FAIL")])
    return 0 if report.passed else 1


def _cmd_verify(args: argparse.Namespace) -> int:
    try:
        spec = load_spec(args.spec)
        impl = load_impl(args.impl, spec.target)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report = verify(spec, impl, args.impl, seed=args.seed)
    if args.format == "json":
        print(json.dumps({
            "command": "verify",
            "spec": report.spec_path,
            "impl": report.impl_path,
            "passed": report.passed,
            "results": [_property_result_dict(r) for r in report.results],
        }, indent=2))
    else:
        _emit_text([f"spec: {spec.path}", f"impl: {args.impl}", ""])
        for r in report.results:
            status = "PASS" if r.passed else "FAIL"
            detail = f": {r.message}" if r.message else ""
            _emit_text([f"  [{status}] {r.name}{detail}"])
        _emit_text(["", "verification: " + ("PASS" if report.passed else "FAIL")])
    return 0 if report.passed else 1


def _cmd_done(args: argparse.Namespace) -> int:
    try:
        spec = load_spec(args.spec)
        impl = load_impl(args.impl, spec.target)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    # Gate 1: the spec itself must be sane (non-vacuous). Satisfiability
    # is NOT part of this gate: a property failing on the candidate
    # implementation is an implementation failure, reported per property
    # by the verification step below -- not a spec failure.
    sanity = check_spec(spec, seed=args.seed)
    if not sanity.passed:
        if args.format == "json":
            print(json.dumps({
                "command": "done", "done": False,
                "reason": "spec failed its sanity check",
                "vacuous": [p.name for p in sanity.per_property if p.status != "ok"],
            }, indent=2))
        else:
            bad = [p.name for p in sanity.per_property if p.status != "ok"]
            _emit_text(["NOT DONE: the spec failed its sanity check."])
            if bad:
                _emit_text([f"  vacuous properties: {', '.join(bad)}"])
            _emit_text(["Fix the spec (and re-run the sanity check) before anything counts as done."])
        return 1
    report = verify(spec, impl, args.impl, seed=args.seed)
    if args.format == "json":
        print(json.dumps({
            "command": "done", "done": report.passed,
            "results": [_property_result_dict(r) for r in report.results],
        }, indent=2))
    else:
        for r in report.results:
            status = "PASS" if r.passed else "FAIL"
            detail = f": {r.message}" if r.message else ""
            _emit_text([f"  [{status}] {r.name}{detail}"])
        if report.passed:
            _emit_text(["", "DONE: spec is sane and every property passes."])
        else:
            failed = [r.name for r in report.results if not r.passed]
            _emit_text(["", "NOT DONE: failing properties: " + ", ".join(failed)])
            _emit_text(["Fix the implementation (or the spec, then re-run the sanity check)."])
    return 0 if report.passed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spec-first",
        description="Write the spec first: machine-checkable properties gate "
        "the implementation, and a task is DONE only when every property passes.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="scaffold a new task directory (spec + impl stub)")
    p_init.add_argument("name", help="task directory name, e.g. my-task")
    p_init.add_argument("--directory", help="parent directory for the new task")
    p_init.set_defaults(func=_cmd_init)

    p_check = sub.add_parser(
        "check-spec", help="sanity-check a spec: reject vacuous specs before coding starts"
    )
    p_check.add_argument("spec", help="spec file, e.g. spec.py")
    p_check.add_argument("--impl", help="implementation file; also proves the spec can pass")
    p_check.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p_check.add_argument("--format", choices=["text", "json"], default="text")
    p_check.set_defaults(func=_cmd_check_spec)

    p_verify = sub.add_parser("verify", help="run every property against an implementation")
    p_verify.add_argument("spec", help="spec file, e.g. spec.py")
    p_verify.add_argument("impl", help="implementation file, e.g. impl.py")
    p_verify.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p_verify.add_argument("--format", choices=["text", "json"], default="text")
    p_verify.set_defaults(func=_cmd_verify)

    p_done = sub.add_parser(
        "done", help="the done-gate: spec sanity + verification, both must pass"
    )
    p_done.add_argument("spec", help="spec file, e.g. spec.py")
    p_done.add_argument("impl", help="implementation file, e.g. impl.py")
    p_done.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p_done.add_argument("--format", choices=["text", "json"], default="text")
    p_done.set_defaults(func=_cmd_done)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
