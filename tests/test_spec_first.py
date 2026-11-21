"""Tests for spec-first-agent: loading, sanity checks, verification, done-gate."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from spec_first.check import check_spec
from spec_first.cli import main
from spec_first.mutants import make_mutants
from spec_first.spec import SpecError, load_impl, load_spec, run_property
from spec_first.verify import verify

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples" / "sort"
GOOD_SPEC = EXAMPLES / "spec_sort.py"
GOOD_IMPL = EXAMPLES / "impl_sort.py"
BROKEN_IMPL = EXAMPLES / "impl_sort_broken.py"  # drops duplicates
IDENTITY_IMPL = EXAMPLES / "impl_sort_identity.py"
VACUOUS_SPEC = EXAMPLES / "spec_vacuous.py"


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


GOOD_SPEC_TEXT = (GOOD_SPEC).read_text(encoding="utf-8")


# ---------------------------------------------------------------- loading

def test_load_good_spec():
    spec = load_spec(str(GOOD_SPEC))
    assert spec.target == "sort_numbers"
    assert [p.name for p in spec.properties] == [
        "prop_length_preserved",
        "prop_ordered",
        "prop_same_items",
    ]


def test_load_spec_missing_target(tmp_path):
    path = write(tmp_path, "spec.py", "def prop_x(impl, rng):\n    return True\n")
    with pytest.raises(SpecError, match="TARGET"):
        load_spec(str(path))


def test_load_spec_no_properties(tmp_path):
    path = write(tmp_path, "spec.py", 'TARGET = "f"\n')
    with pytest.raises(SpecError, match="no prop_"):
        load_spec(str(path))


def test_load_spec_wrong_arity(tmp_path):
    path = write(
        tmp_path, "spec.py",
        'TARGET = "f"\n\ndef prop_x(impl):\n    return True\n',
    )
    with pytest.raises(SpecError, match="exactly two arguments"):
        load_spec(str(path))


def test_load_impl_missing_target(tmp_path):
    impl = write(tmp_path, "impl.py", "def other(x):\n    return x\n")
    with pytest.raises(SpecError, match="does not define"):
        load_impl(str(impl), "sort_numbers")


def test_load_broken_file(tmp_path):
    path = write(tmp_path, "spec.py", "def broken(:\n")
    with pytest.raises(SpecError, match="cannot load"):
        load_spec(str(path))


# ------------------------------------------------------------ run_property

def test_run_property_counts_calls_and_passes():
    spec = load_spec(str(GOOD_SPEC))
    impl = load_impl(str(GOOD_IMPL), spec.target)
    result = run_property(spec.properties[0], impl, 1234)
    assert result.passed
    assert result.calls == 50


def test_run_property_failure_message():
    spec = load_spec(str(GOOD_SPEC))
    prop = spec.properties[1]  # prop_ordered
    impl = load_impl(str(IDENTITY_IMPL), spec.target)
    result = run_property(prop, impl, 1234)
    assert not result.passed
    assert "not ordered" in result.message


def test_run_property_bad_return_type(tmp_path):
    path = write(
        tmp_path, "spec.py",
        'TARGET = "f"\n\ndef prop_x(impl, rng):\n    impl(1)\n    return "yes"\n',
    )
    spec = load_spec(str(path))
    result = run_property(spec.properties[0], lambda x: x, 1)
    assert not result.passed
    assert "must return bool" in result.message


def test_run_property_exception_is_error(tmp_path):
    path = write(
        tmp_path, "spec.py",
        'TARGET = "f"\n\ndef prop_x(impl, rng):\n    impl(1)\n    raise ValueError("boom")\n',
    )
    spec = load_spec(str(path))
    result = run_property(spec.properties[0], lambda x: x, 1)
    assert not result.passed
    assert result.error == "ValueError: boom"


# ---------------------------------------------------------------- mutants

def test_mutants_cover_broken_behaviour():
    names = [name for name, _ in make_mutants(7)]
    assert names == ["identity", "empty", "none", "reversed", "shuffled", "raises"]


# ------------------------------------------------------------ sanity check

def test_check_good_spec_passes():
    spec = load_spec(str(GOOD_SPEC))
    report = check_spec(spec)
    assert report.passed
    assert all(p.status == "ok" for p in report.per_property)
    assert report.satisfiable is None  # no --impl: can fail, not proven to pass
    # each property catches at least one mutant
    assert all(p.mutants_caught for p in report.per_property)


def test_check_vacuous_spec_fails():
    spec = load_spec(str(VACUOUS_SPEC))
    report = check_spec(spec)
    assert not report.passed
    by_name = {p.name: p for p in report.per_property}
    assert by_name["prop_always_true"].status == "vacuous"
    assert "never calls" in by_name["prop_always_true"].reason
    assert by_name["prop_tautology"].status == "vacuous"
    assert "never returns False" in by_name["prop_tautology"].reason


def test_check_spec_never_crashes_property_is_not_vacuous(tmp_path):
    # A property that only checks "impl does not raise" returns False on
    # the raises mutant, so it genuinely can fail: weak, but not vacuous.
    path = write(
        tmp_path, "spec.py",
        'TARGET = "f"\n\n'
        "def prop_never_crashes(impl, rng):\n"
        "    for _ in range(10):\n"
        "        try:\n"
        "            impl([3, 1, 2])\n"
        "        except Exception as exc:\n"
        "            return False, f'raised: {exc}'\n"
        "    return True, ''\n",
    )
    spec = load_spec(str(path))
    report = check_spec(spec)
    assert report.passed
    assert report.per_property[0].mutants_caught == ["raises"]


def test_check_spec_crash_only_property_is_vacuous(tmp_path):
    # A property that crashes on broken implementations but never returns
    # False has not judged anything: it is vacuous, not strict.
    path = write(
        tmp_path, "spec.py",
        'TARGET = "f"\n\n'
        "def prop_first_item(impl, rng):\n"
        "    out = impl([3, 1, 2])\n"
        "    _ = out[0]\n"
        "    return True, ''\n",
    )
    spec = load_spec(str(path))
    report = check_spec(spec)
    assert not report.passed
    assert report.per_property[0].status == "vacuous"
    assert "never returns False" in report.per_property[0].reason


def test_check_spec_satisfiability_with_good_impl():
    spec = load_spec(str(GOOD_SPEC))
    impl = load_impl(str(GOOD_IMPL), spec.target)
    report = check_spec(spec, impl=impl)
    assert report.passed
    assert report.satisfiable is True


def test_check_spec_satisfiability_catches_unsatisfiable_spec(tmp_path):
    # A property no implementation can satisfy: output must be both
    # sorted ascending AND strictly descending.
    path = write(
        tmp_path, "spec.py",
        'TARGET = "f"\n\n'
        "def prop_sorted(impl, rng):\n"
        "    xs = [3, 1, 2]\n"
        "    out = impl(xs)\n"
        "    return list(out) == sorted(out), 'not sorted'\n\n"
        "def prop_reversed(impl, rng):\n"
        "    xs = [3, 1, 2]\n"
        "    out = impl(xs)\n"
        "    return list(out) == sorted(out, reverse=True), 'not reversed'\n",
    )
    spec = load_spec(str(path))
    # Plain check passes: each property CAN fail (on mutants).
    assert check_spec(spec).passed
    # With a real implementation, the contradiction shows up.
    impl_path = write(tmp_path, "impl.py", "def f(xs):\n    return sorted(xs)\n")
    impl = load_impl(str(impl_path), spec.target)
    report = check_spec(spec, impl=impl)
    assert not report.passed
    assert report.satisfiable is False
    assert [r.name for r in report.satisfiability_failures] == ["prop_reversed"]


# --------------------------------------------------------------- verification

def test_verify_good_impl_passes():
    spec = load_spec(str(GOOD_SPEC))
    impl = load_impl(str(GOOD_IMPL), spec.target)
    report = verify(spec, impl, str(GOOD_IMPL))
    assert report.passed
    assert all(r.passed for r in report.results)


def test_verify_broken_impl_fails_exactly_the_right_properties():
    spec = load_spec(str(GOOD_SPEC))
    impl = load_impl(str(BROKEN_IMPL), spec.target)
    report = verify(spec, impl, str(BROKEN_IMPL))
    assert not report.passed
    by_name = {r.name: r.passed for r in report.results}
    assert by_name["prop_ordered"] is True  # sorted(set()) is still ordered
    assert by_name["prop_same_items"] is False
    assert by_name["prop_length_preserved"] is False


def test_verify_identity_impl_fails_ordered():
    spec = load_spec(str(GOOD_SPEC))
    impl = load_impl(str(IDENTITY_IMPL), spec.target)
    report = verify(spec, impl, str(IDENTITY_IMPL))
    by_name = {r.name: r.passed for r in report.results}
    assert by_name["prop_ordered"] is False
    assert by_name["prop_same_items"] is True  # identity keeps the items


# ---------------------------------------------------------------------- CLI

def run_cli(*argv):
    return main(list(argv))


def test_cli_verify_pass_and_fail(capsys):
    assert run_cli("verify", str(GOOD_SPEC), str(GOOD_IMPL)) == 0
    out = capsys.readouterr().out
    assert "verification: PASS" in out
    assert run_cli("verify", str(GOOD_SPEC), str(BROKEN_IMPL)) == 1
    out = capsys.readouterr().out
    assert "[FAIL] prop_same_items" in out


def test_cli_check_spec_vacuous(capsys):
    assert run_cli("check-spec", str(VACUOUS_SPEC)) == 1
    out = capsys.readouterr().out
    assert "VACUOUS" in out
    assert "sanity check: FAIL" in out


def test_cli_check_spec_with_impl(capsys):
    assert run_cli("check-spec", str(GOOD_SPEC), "--impl", str(GOOD_IMPL)) == 0
    assert "satisfiability: all properties pass" in capsys.readouterr().out


def test_cli_done_gate_passes_and_refuses(capsys):
    assert run_cli("done", str(GOOD_SPEC), str(GOOD_IMPL)) == 0
    assert "DONE" in capsys.readouterr().out
    assert run_cli("done", str(GOOD_SPEC), str(BROKEN_IMPL)) == 1
    assert "NOT DONE" in capsys.readouterr().out
    # Vacuous spec: verify alone would pass (correct impl), but done refuses
    # because the spec itself failed its sanity check.
    assert run_cli("verify", str(VACUOUS_SPEC), str(GOOD_IMPL)) == 0
    assert run_cli("done", str(VACUOUS_SPEC), str(GOOD_IMPL)) == 1
    assert "NOT DONE" in capsys.readouterr().out


def test_cli_done_reruns_sanity_after_spec_change(tmp_path, capsys):
    # Start from the good spec, then weaken it to a vacuous one: done must
    # refuse the new spec even though the implementation is unchanged.
    spec_path = write(tmp_path, "spec.py", GOOD_SPEC_TEXT)
    assert run_cli("done", str(spec_path), str(GOOD_IMPL)) == 0
    spec_path.write_text(
        'TARGET = "sort_numbers"\n\n'
        "def prop_trust_me(impl, rng):\n"
        '    """Looks fine, checks nothing."""\n'
        "    return True, ''\n",
        encoding="utf-8",
    )
    assert run_cli("done", str(spec_path), str(GOOD_IMPL)) == 1
    assert "NOT DONE" in capsys.readouterr().out


def test_cli_json_output_parses(capsys):
    assert run_cli("verify", str(GOOD_SPEC), str(BROKEN_IMPL), "--format", "json") == 1
    data = json.loads(capsys.readouterr().out)
    assert data["passed"] is False
    assert {r["property"] for r in data["results"]} == {
        "prop_ordered", "prop_same_items", "prop_length_preserved",
    }


def test_cli_missing_file_is_exit_2(capsys):
    assert run_cli("verify", "no-such-spec.py", str(GOOD_IMPL)) == 2
    assert run_cli("check-spec", str(GOOD_SPEC), "--impl", "no-such-impl.py") == 2


def test_cli_init_scaffolds(tmp_path):
    assert run_cli("init", "my-task", "--directory", str(tmp_path)) == 0
    task = tmp_path / "my-task"
    assert (task / "spec.py").exists()
    assert (task / "impl.py").exists()
    spec = load_spec(str(task / "spec.py"))
    assert spec.target == "solve"
    # The scaffold's example property is a real property (identity on
    # ints), so the untouched scaffold passes its sanity check -- but
    # `done` refuses it because the impl stub is not implemented yet.
    assert run_cli("check-spec", str(task / "spec.py")) == 0
    assert run_cli("done", str(task / "spec.py"), str(task / "impl.py")) == 1


def test_cli_init_refuses_existing(tmp_path):
    (tmp_path / "my-task").mkdir()
    assert run_cli("init", "my-task", "--directory", str(tmp_path)) == 2


def test_deterministic_seeds():
    spec = load_spec(str(GOOD_SPEC))
    impl = load_impl(str(GOOD_IMPL), spec.target)
    first = verify(spec, impl, str(GOOD_IMPL), seed=99)
    second = verify(spec, impl, str(GOOD_IMPL), seed=99)
    assert [(r.name, r.passed) for r in first.results] == [
        (r.name, r.passed) for r in second.results
    ]


def test_console_script_smoke():
    env = {"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    result = subprocess.run(
        [sys.executable, "-m", "spec_first", "done",
         str(GOOD_SPEC), str(GOOD_IMPL)],
        capture_output=True, text=True, env=env, cwd=str(ROOT),
    )
    assert result.returncode == 0
    assert "DONE" in result.stdout
