# spec-first-agent

When an agent writes code first and tests it after, the tests end up
describing what the code *does*, not what it *should do*. This tool
flips the order: the agent writes a machine-checkable spec first, the
spec itself is sanity-checked, and only then does implementation begin.
A task is DONE only when every property in the spec passes — the
harness refuses to mark it complete otherwise.

The workflow:

1. **Write the spec.** A spec file is a small Python module: `TARGET`
   names the function to build, and each `prop_*` function states one
   invariant the output must satisfy, checked over generated inputs
   (e.g. for a sort: the output is ordered *and* contains exactly the
   same items as the input).
2. **Sanity-check the spec** (`spec-first check-spec`). A spec that
   cannot fail is useless, so each property is run against deliberately
   broken implementations (mutants: identity, empty, reversed,
   shuffled, always-raise, ...). A property must call the implementation
   at least once *and* fail on at least one mutant by returning False.
   A property that passes every mutant — or never calls the
   implementation at all — is flagged **vacuous** and the spec is
   rejected before any implementation work begins.
3. **Write the implementation.** Only after the spec passes its sanity
   check.
4. **Verify** (`spec-first verify`): run every property against the
   implementation, with a per-property pass/fail report.
5. **The done-gate** (`spec-first done`): runs the spec sanity check
   and the verification together. Both must pass. A vacuous spec, a
   failing property, or a spec edited after the last check all refuse
   DONE — changing the spec always re-runs the sanity check.

## Credits / motivation

Built from "The War Against Slop and an Emerging Weapon to Fight it:
Formal Verification" ([Latent Space](https://latent.space/p/formal-verification/),
2026-11-20). The article's argument: AI-written code is cheap, so
low-quality output ("slop") is the daily problem, and the emerging
answer is formal verification — proving code meets its requirements
instead of just testing it. Testing finds bugs but can never show
there are no more lurking; a proof can. The article's picture of the
future is "veri-coding": developers spend their time nailing down the
specification with the agent, the agent works with a verification tool,
and the code works the first time. This repo is a small, practical
implementation of that *shape* — spec first, machine checks it — not
the authors' code, and not a formal-verification system (see
Limitations).

## Install

```bash
pip install -e .   # from a clone; Python 3.10+, stdlib only, no runtime dependencies
```

## Quickstart

```bash
spec-first init my-task        # scaffold spec.py + impl.py
# 1. edit my-task/spec.py: replace the example property with real ones
spec-first check-spec my-task/spec.py
# 2. implement my-task/impl.py (only after step 1 passes)
spec-first done my-task/spec.py my-task/impl.py
```

## Demo: sorting

The bundled example (`examples/sort/`) specs a sort function with
three properties — ordered, same items, length preserved:

```bash
$ spec-first check-spec examples/sort/spec_sort.py
spec: examples/sort/spec_sort.py (sort a list of numbers)
target: sort_numbers

  [OK] prop_length_preserved: calls=50 caught=empty errored=none,raises
  [OK] prop_ordered: calls=50 caught=identity,reversed,shuffled errored=none,raises
  [OK] prop_same_items: calls=50 caught=empty errored=none,raises

sanity check: PASS

$ spec-first verify examples/sort/spec_sort.py examples/sort/impl_sort.py
  [PASS] prop_length_preserved
  [PASS] prop_ordered
  [PASS] prop_same_items

verification: PASS
```

The broken implementation (`impl_sort_broken.py`) sorts but silently
drops duplicates. The spec catches it — `prop_ordered` still passes
(the output *is* ordered), but the other two fail:

```bash
$ spec-first verify examples/sort/spec_sort.py examples/sort/impl_sort_broken.py
  [FAIL] prop_length_preserved: length changed: [...] -> [...]
  [PASS] prop_ordered
  [FAIL] prop_same_items: items changed: [...] -> [...]

verification: FAIL
```

And a vacuous spec (`spec_vacuous.py`) — one property that never calls
the implementation, one that calls it and ignores the result — is
rejected before anything is built against it:

```bash
$ spec-first check-spec examples/sort/spec_vacuous.py
  [VACUOUS] prop_always_true: calls=0 caught=- -- property never calls the implementation
  [VACUOUS] prop_tautology: calls=10 caught=- errored=raises -- property never returns False on any mutant (cannot fail)

sanity check: FAIL
```

## The spec format

A spec file is a plain Python module:

```python
TARGET = "sort_numbers"          # function name in the implementation module
TASK = "sort a list of numbers"  # optional one-line description

def prop_ordered(impl, rng):
    """The output must be in non-decreasing order."""
    for _ in range(50):
        xs = [rng.randint(-100, 100) for _ in range(rng.randint(0, 20))]
        out = impl(xs)
        if list(out) != sorted(out):
            return False, f"not ordered: {xs} -> {out}"
    return True, ""
```

- Each `prop_*` function takes exactly two arguments: `impl` (the
  target callable, or a mutant during sanity checks) and `rng` (a
  seeded `random.Random` — use it to generate inputs so runs are
  reproducible).
- Return `True`/`False`, or `(bool, message)`. Returning `False` or
  raising `AssertionError` fails the property; any other exception is
  recorded as an error (also a failure).
- The implementation module just defines the `TARGET` function.

## Commands

| Command | What it does | Exit codes |
|---|---|---|
| `spec-first init NAME [--directory DIR]` | Scaffold a task directory with `spec.py` + `impl.py` | 0 ok, 2 already exists |
| `spec-first check-spec SPEC [--impl IMPL] [--seed N] [--format text\|json]` | Sanity-check the spec. With `--impl`, also proves the spec *can* pass (satisfiability): a spec no implementation could satisfy fails here | 0 sane, 1 vacuous/unsatisfiable, 2 load error |
| `spec-first verify SPEC IMPL [--seed N] [--format text\|json]` | Run every property against the implementation | 0 all pass, 1 any fail, 2 load error |
| `spec-first done SPEC IMPL [--seed N] [--format text\|json]` | The done-gate: spec sanity + verification, both must pass | 0 done, 1 not done, 2 load error |

Notes on the checks:

- **Vacuity is judged by returning False, not by crashing.** A
  property that calls the implementation and ignores the result still
  crashes when the `raises` mutant raises — so a crash proves nothing
  about what the property checks. Only a `False` return counts as
  catching a mutant. (A genuine "impl must not raise" property *does*
  pass: it catches the `raises` mutant by returning False.)
- **A plain `check-spec` proves the spec can fail, not that it can
  pass.** Use `check-spec --impl` (or `done`, which always runs the
  satisfiability leg through verification) to catch unsatisfiable
  specs — e.g. one property demanding the output sorted and another
  demanding it reversed. Without an implementation the check says so
  explicitly.
- **Seeds are fixed** (`--seed 1234` by default) and each property
  gets its own derived seed, so the same inputs are used across
  mutants and runs are reproducible.

## Limitations

- **This is the lightweight version of the article's idea, not formal
  verification.** Properties are property tests and invariants, not
  Lean proofs. Nothing here proves the absence of bugs; it proves the
  implementation satisfies the properties the author wrote, on the
  inputs the properties generate. A missing property is still a hole,
  and a wrong property still blesses wrong code.
- The built-in mutants are generic (identity, empty, reversed,
  shuffled, always-raise, ...). They catch sloppy specs well for
  sequence-transforming functions and less well for other shapes; a
  property can pass the sanity check and still be weak.
- Properties run in-process against the implementation module, in the
  same Python process as the harness. There is no sandboxing: only run
  specs and implementations you trust.
- Python only; the spec format is Python modules.
- The `done` gate judges the current files. It cannot tell whether
  the implementation was verified against a *different* spec, or
  whether the properties were weakened after the fact — it re-runs
  everything from the files you hand it, every time.

## Build your own

Build a small harness that forces spec-first development for coding
agents: the agent must write machine-checkable properties before any
implementation, the harness sanity-checks the spec itself by requiring
each property to fail on deliberately broken implementations, and the
task only counts as done when every property passes against the real
implementation. Include a worked demo showing the full loop and a
vacuous spec being rejected, and state plainly where the lightweight
property approach stops short of real formal verification.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
