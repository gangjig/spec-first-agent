# Changelog

## v0.1.0 — 2026-11-21

- First release. Spec-first harness for coding agents: write a
  machine-checkable spec (`TARGET` + `prop_*` properties) before any
  implementation, sanity-check the spec against built-in mutants
  (vacuous specs rejected), verify the implementation per property,
  and a `done` gate that requires both the spec sanity check and full
  verification to pass. CLI: `init`, `check-spec`, `verify`, `done`
  (text/JSON output, fixed seeds). Worked sort demo including a broken
  implementation the spec catches and a vacuous spec the gate rejects.
  Stdlib only, 31 tests.
