# CLI Wrapper Tasks — `tm1-bench`

Flat, ordered task list for implementing the CLI wrapper feature. See [cli-scope.md](cli-scope.md) for design rationale.

Each task is atomic (1–2 hours), self-contained, and tagged with a phase. Tasks are ordered so that dependencies always appear before dependents.

**Phase tags:**
- `[SETUP]` — scaffolding, no behaviour change
- `[CORE]` — business logic
- `[UX]` — user-facing polish, flags, help text
- `[TEST]` — unit and integration tests
- `[DOCS]` — documentation updates
- `[CI]` — pipeline integration

---

## Phase 1 — Scaffolding

- [x] **[SETUP]** Create `tm1_bench_py/cli.py` skeleton with empty `main()` function, `ExitCode` IntEnum (SUCCESS=0, VALIDATION_FAILURE=1, CONNECTION_FAILURE=2, BUILD_ERROR=3, USAGE_ERROR=4, UNEXPECTED_ERROR=10), and module-level `__all__`. No argparse yet.
- [x] **[SETUP]** Create `tm1_bench_py/__main__.py` with a 2-line shim that imports `cli.main` and calls it under `if __name__ == "__main__"`.
- [x] **[SETUP]** Add `[project.scripts]` table to `pyproject.toml` mapping `tm1-bench = "tm1_bench_py.cli:main"`. Verify `pip install -e .` places `tm1-bench` on `$PATH`.
- [x] **[SETUP]** Extract `_derive_project_root()` and `_ensure_schema_loaded(schema, schema_dir, env)` helpers from `tm1_bench.build_model()`. `build_model()` must still pass its existing unit test unchanged.

## Phase 2 — Argument parsing

- [x] **[CORE]** In `cli.py`, implement `_build_parser()` returning the top-level `ArgumentParser` with global flags (`--schema`, `--env`, `--log-level`, `--json-logs`, `--quiet`, `--version`) and an empty subparsers group (`dest="subcommand"`, `required=True`).
- [x] **[CORE]** Add `validate` subparser with `--strict` flag. Wire to placeholder `_cmd_validate(args)` that returns `ExitCode.SUCCESS`.
- [x] **[CORE]** Add `build` subparser with `--config`, `--connection`, `--dry-run`, `--skip-data` flags. Wire to placeholder `_cmd_build(args)`.
- [x] **[CORE]** Add `destroy` subparser with `--config`, `--connection`, `--force` flags. Wire to placeholder `_cmd_destroy(args)`.
- [x] **[CORE]** Add `generate-data` subparser with `--config`, `--connection`, `--dataset NAME` (action=append) flags. Wire to placeholder `_cmd_generate_data(args)`.
- [x] **[CORE]** Implement `main(argv=None)`: call `_build_parser()`, `parse_args(argv)`, dispatch by `args.subcommand` to the right `_cmd_*` handler, `sys.exit(handler_return_value)`.

## Phase 3 — Logging wiring

- [x] **[CORE]** Implement `_configure_logging(log_level, json_logs, quiet)` in `cli.py`. Sets level on `basic_logger` + `exec_metrics_logger`, swaps formatter to `JSONLogFormatter` when `--json-logs`, silences stdout handler when `--quiet`. Called once at the start of `main()` after argv parsing.
- [x] **[CORE]** Implement `_resolve_config_ini(args)` helper: precedence is `--config` → `TM1_BENCH_CONFIG` env var → `./config.ini`. Raises `FileNotFoundError` with a clear message if none found. Likewise `_resolve_connection_name(args)` for the INI section.

## Phase 4 — Subcommand implementation

- [x] **[CORE]** Implement `_cmd_validate(args)`: load schema via `SchemaLoader`, call `schema_validator.validate_schema(schema, project_root)`, `report.log_report()`. Return `VALIDATION_FAILURE` if `not report.is_valid`, or if `--strict` and `report.warnings`. Else `SUCCESS`.
- [x] **[CORE]** Implement `_print_build_plan(schema)` helper: emits the dimensions-to-create, cubes-to-create, datasets-to-load summary described in cli-scope §3.6. Pure function, no side effects on TM1.
- [x] **[CORE]** Implement `_cmd_build(args)`: validate first; if failure return early with `VALIDATION_FAILURE`. If `--dry-run`, call `_print_build_plan` and return SUCCESS. Otherwise open TM1 connection via `utility.tm1_connection(_resolve_config_ini(args), _resolve_connection_name(args))` and call `tm1_bench.build_model(tm1, schema, system_defaults, env)`. If `--skip-data`, build dims + cubes but skip `generate_data` — this requires a small hook in `tm1_bench.build_model()` (add `skip_data=False` kwarg). 
- [x] **[CORE]** Implement `_cmd_destroy(args)`: load schema → open connection → call `tm1_bench.destroy_model(tm1, schema)`. No validation needed (destroying against a stale schema is still valid if dimensions exist).
- [x] **[CORE]** Implement `_cmd_generate_data(args)`: validate first; open connection; if `args.dataset` is non-empty, filter `schema['datasets']` to just those keys before calling `tm1_bench.generate_data(tm1, schema, system_defaults)`. Warn if a requested dataset name is not in the schema.
- [x] **[CORE]** Add exception-to-exit-code mapping around each `_cmd_*` call in `main()`: `ValueError` → VALIDATION_FAILURE, `FileNotFoundError`/`TM1pyException`/connection errors → CONNECTION_FAILURE, other exceptions → BUILD_ERROR with `basic_logger.exception()` so traceback is logged. `SystemExit` from argparse stays as-is but is intercepted to remap code 2 → USAGE_ERROR (4).

## Phase 5 — User experience polish

- [x] **[UX]** Write a quality top-level `--help` description + per-subcommand `--help`, including at least one example per subcommand in the epilog.
- [x] **[UX]** Add `--version` flag that prints `tm1_bench_py.__version__` from `__init__.py` and exits 0.
- [x] **[UX]** Verify `tm1-bench` with no args prints help and exits 4 (USAGE_ERROR), not 0.
- [x] **[UX]** Add a single-line startup log message: `basic_logger.info("tm1-bench %s · %s · env=%s · schema=%s", __version__, args.subcommand, args.env, args.schema)` — helps CI log triage.

## Phase 6 — Tests

- [x] **[TEST]** Add `tests/test_cli_parser.py` — unit tests for `_build_parser()`: parses all subcommands, all flags, defaults are correct, invalid subcommand raises `SystemExit`. No TM1 or filesystem side effects.
- [x] **[TEST]** Add `tests/test_cli_validate.py` — drives `main(["validate", "--schema", str(tmp_path), "--env", "default"])` against a good schema fixture (exit 0), a bad one (exit 1), and `--strict` on a warnings-only schema (exit 1). Uses `monkeypatch` on `sys.exit` or captures via `pytest.raises(SystemExit)`.
- [x] **[TEST]** Add `tests/test_cli_dry_run.py` — drives `main(["build", "--schema", ..., "--dry-run"])`, captures stdout via `capsys`, asserts plan contains dimension/cube/dataset sections and counts match the fixture schema. No TM1 mock needed (dry-run never connects).
- [x] **[TEST]** Add `tests/test_cli_exit_codes.py` — parametrized test that injects each exception type (`ValueError`, `FileNotFoundError`, `RuntimeError`) into a mocked `_cmd_build` and asserts the right exit code is returned.
- [x] **[TEST]** Add `tests/test_cli_config_resolution.py` — covers `_resolve_config_ini` precedence: CLI flag > env var > default. Uses `monkeypatch.setenv` and `tmp_path`.
- [x] **[TEST]** Add an integration entry in `tests_integration/` that runs `tm1-bench build --env default` as a subprocess against the Docker TM1 and asserts exit code 0. Proves the console script is really wired.

## Phase 7 — Documentation

- [x] **[DOCS]** Update `README.md`: add a "CLI usage" section with the four subcommand examples and exit-code table. Replace the `python sample.py` reference with `tm1-bench build`.
- [x] **[DOCS]** Update `docs/user-guide.md`: add a "Using the CLI" section after the Python-library example. Link to `docs/cli-scope.md` for the full reference.
- [x] **[DOCS]** Update `docs/index.md` toctree to include `cli-scope.md`.
- [x] **[DOCS]** Update `CLAUDE.md`: in the "Commands" section add `tm1-bench {build,destroy,validate,generate-data}` alongside `python sample.py`.
- [x] **[DOCS]** Update `blueprint.md`: mark the CLI module as implemented (was "planned"), update module map, update data-flow diagram to show the CLI as a second entry point next to `sample.py`.

## Phase 8 — CI integration

- [x] **[CI]** Update `.github/workflows/build-test.yml`: after the `python -m build` step, run `pip install dist/*.whl` to exercise the console-script install path, then replace `python sample.py` with `tm1-bench build --env default --connection testbench`.
- [x] **[CI]** Add a pre-TM1-container CI step `tm1-bench validate --schema ./schema --env default` that runs without Docker — catches schema regressions in <10 seconds before the slow integration leg.
- [x] **[CI]** Verify the `tm1-bench --version` output appears in the CI logs near the top (useful for debugging which wheel was installed).

---

## Effort Estimate

| Phase | Tasks | Hours |
|-|-|-|
| 1 — Scaffolding | 4 | 3 |
| 2 — Argument parsing | 6 | 5 |
| 3 — Logging wiring | 2 | 2 |
| 4 — Subcommand implementation | 6 | 9 |
| 5 — UX polish | 4 | 2 |
| 6 — Tests | 6 | 7 |
| 7 — Documentation | 5 | 3 |
| 8 — CI integration | 3 | 2 |
| **Total** | **36** | **~33 hours** |

Realistic calendar estimate for one developer: **5–6 working days**, including review and iteration.

Recommended split point for a first merge: complete phases 1–4 and tests for `validate` + `dry-run` (most of phase 6) in a first PR. Land that, then do phases 5, 7, 8 in a follow-up. This keeps PR size reviewable and gives the CI pipeline something real to exercise early.
