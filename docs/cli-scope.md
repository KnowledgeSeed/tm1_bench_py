# CLI Wrapper Scope — `tm1-bench`

**Status:** planned
**Owner:** core maintainers
**Author:** Architect session 2026-04-24
**Related docs:** [architecture.md](architecture.md), [schema-reference.md](schema-reference.md)

---

## 1. Feature Overview

Expose the `tm1_bench_py` library as a first-class command-line tool named `tm1-bench`. Today the only way to drive the library is by importing it from a Python script (`sample.py`). That is not usable from a CI/CD job, a Dockerfile `ENTRYPOINT`, or an AI agent tool surface without writing custom Python glue.

The CLI wrapper makes four existing orchestration functions directly invokable:

| Subcommand | Wraps |
|-|-|
| `tm1-bench validate` | `SchemaLoader.load_schema()` + `schema_validator.validate_schema()` |
| `tm1-bench build` | `tm1_bench.build_model()` |
| `tm1-bench destroy` | `tm1_bench.destroy_model()` |
| `tm1-bench generate-data` | `tm1_bench.generate_data()` |

### Goals

1. **CI/CD integration** — runnable from GitHub Actions / GitLab / Jenkins without invoking a Python wrapper script.
2. **AI agent tool surface** — deterministic subcommands + structured exit codes so an agent can call `tm1-bench validate` as a tool, parse the exit code, and decide next steps.
3. **Developer ergonomics** — faster inner-loop iteration than editing `sample.py`.
4. **Zero new runtime dependencies** — stdlib `argparse` only.

### Non-goals

- Interactive prompts, TUI, progress bars.
- A REPL or long-running server mode.
- Replacing `sample.py` (it stays as a programmatic example).
- Managing the TM1 Docker container lifecycle (tests_integration/docker-compose.yml already does that).

---

## 2. CLI Design

### Command surface

```
tm1-bench [--help] [--version] {validate,build,destroy,generate-data} ...
```

### Global flags (apply to every subcommand)

| Flag | Type | Default | Purpose |
|-|-|-|-|
| `--schema PATH` | path | `./schema` | Root of the YAML schema tree |
| `--env NAME` | string | `default` | Environment key within YAML env blocks |
| `--log-level LEVEL` | choice | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `--json-logs` | flag | off | Emit logs via `JSONLogFormatter` instead of plain |
| `-q`, `--quiet` | flag | off | Suppress non-error stdout/stderr (exit code still meaningful) |

### Connection flags (build, destroy, generate-data only)

| Flag | Type | Default | Purpose |
|-|-|-|-|
| `--config PATH` | path | `./config.ini` | Path to TM1 connection INI file |
| `--connection NAME` | string | `testbench` | Section name within the INI |

Resolution order (highest wins): CLI flag → `TM1_BENCH_CONFIG` / `TM1_BENCH_CONNECTION` env vars → built-in defaults.

### Subcommand-specific flags

**`validate`**
- `--strict` — treat warnings as errors (exit 1 if any warning present)

**`build`**
- `--dry-run` — run validation then print the build plan (dimensions, cubes, datasets that would be created); do NOT connect to TM1
- `--skip-data` — build dimensions and cubes only

**`destroy`**
- `--force` — skip confirmation log line (confirmation is a log line, not an interactive prompt — `--force` is a no-op placeholder for future interactivity)

**`generate-data`**
- `--dataset NAME` — repeatable; limit generation to specified dataset names

### Examples

```bash
# CI schema check — no TM1 needed
tm1-bench validate --schema ./schema --env default

# Full build against the testbench connection
tm1-bench build --schema ./schema --env ksAcademy --connection testbench3

# Plan-only mode for review before a destructive run
tm1-bench build --schema ./schema --env bedrock_test_1000000 --dry-run

# Tear down a benchmark environment
tm1-bench destroy --schema ./schema --env bedrock_test_100000

# Reload data for a single dataset after a rules change
tm1-bench generate-data --schema ./schema --env default --dataset Sales

# Invoke via the module (no installed script)
python -m tm1_bench_py validate --schema ./schema
```

---

## 3. Technical Approach

### 3.1 Library choice: `argparse` (stdlib)

**Decision:** use `argparse` with `add_subparsers(dest="subcommand", required=True)`.

**Rationale:**
- **Zero new dependencies.** Current runtime deps are `TM1py`, `pandas`, `numpy`, `mdxpy`, `json_logging`, `pyyaml`. Adding `click` or `typer` introduces a transitive dep tree for a 4-subcommand surface that doesn't warrant it.
- **CI Docker compatibility.** `argparse` ships with CPython; no pip install friction in the container-based integration test pipeline.
- **Testability.** `argparse.ArgumentParser.parse_args(argv)` is trivial to drive from pytest with a list of strings — no `CliRunner` fixture required.
- **Escape hatch.** If we later add auto-complete, rich help, or option groups, we can migrate to `click` without churning consumers (the `tm1-bench` command and exit codes are the public contract, not the Python argument-parsing library).

**Trade-off accepted:** `argparse` has uglier help output and no built-in shell completion. Both are cosmetic; addressable later.

### 3.2 Module layout

```
tm1_bench_py/
├── __init__.py
├── __main__.py          ← NEW: 2-line shim → cli.main()
├── cli.py               ← NEW: all parsing + subcommand dispatch
├── tm1_bench.py         ← EDITED: extract _derive_project_root() helper
├── schema_validator.py  ← unchanged
├── dimension_builder.py ← unchanged
├── dimension_period_builder.py
├── df_generator_for_dataset.py
├── tm1_bedrock_executor.py
├── utility.py
├── json_log_formatter.py
└── logging.json
```

**`cli.py` responsibilities:**
1. Build the top-level parser + subparsers.
2. Parse argv into a `Namespace`.
3. Configure logging level / formatter based on `--log-level` / `--json-logs`.
4. Dispatch to per-subcommand handler (`_cmd_validate`, `_cmd_build`, `_cmd_destroy`, `_cmd_generate_data`).
5. Map handler return / raised exception to an `ExitCode` IntEnum.
6. Call `sys.exit(exit_code)`.

**`__main__.py` responsibilities:**
```python
from tm1_bench_py.cli import main
if __name__ == "__main__":
    main()
```

### 3.3 Console script wiring

Add to `pyproject.toml`:
```toml
[project.scripts]
tm1-bench = "tm1_bench_py.cli:main"
```

After `pip install -e .`, the user's `$PATH` contains `tm1-bench` resolving to the main function. Both `tm1-bench ...` and `python -m tm1_bench_py ...` behave identically.

### 3.4 Config.ini connection resolution

Precedence (first match wins):
1. `--config PATH` CLI flag
2. `TM1_BENCH_CONFIG` environment variable
3. `./config.ini` relative to CWD (where the user invoked `tm1-bench`)
4. Error: exit code 2 ("TM1 connection failure — config.ini not found")

Same pattern for `--connection` / `TM1_BENCH_CONNECTION` / default `testbench`.

Why env-var support: GitHub Actions and Docker `ENV` directives make env vars the ergonomic way to pass secrets. Putting path to the INI in an env var also lets pipelines mount the config outside the repo.

### 3.5 Error surface to the user

Two layers:
1. **Human-readable stderr** — one line per error / warning, `[SCHEMA]`-prefixed as today. Re-use existing `basic_logger` wiring. This is the default.
2. **Machine-readable exit code** — always. Every subcommand returns an `ExitCode` (see table below).

Optional future: `--output json` to emit a structured JSON summary to stdout. Not in scope for v1 but the code layout reserves the hook.

### 3.6 `--dry-run` semantics

When `build --dry-run` is specified, after validation passes print:
```
Would create 14 dimensions:
  - elementlist: Currency, Version, MeasureAccount, ...
  - df_templates: Product, Customer, Account, ...
  - custom: Period
  - csv: Department
Would create 3 cubes:
  - Sales (dims: Period, Version, Customer, Product, MeasureSales)
  - ...
Would load 3 datasets:
  - Sales → Sales (80M rows)
  - ...
```

No TM1 connection is attempted. Exit code 0 if validation passed, 1 otherwise. This is essentially `validate` with extra printing; implementation shares the validation path.

### 3.7 Refactor to `tm1_bench.py`

`build_model()` currently owns path derivation (`project_root = os.path.dirname(script_dir)`), schema loading, validation, connection, and pipeline. To reuse its components cleanly from the CLI, extract two helpers:

```python
def _derive_project_root() -> str: ...
def _ensure_schema_loaded(schema, schema_dir, env) -> dict: ...
```

The existing `build_model()` signature does not change — it just delegates to the new helpers. This keeps existing callers (`sample.py`, any downstream library users) working.

---

## 4. Exit Code Table

Defined in `cli.py` as `class ExitCode(IntEnum)`.

| Code | Name | When returned |
|-|-|-|
| 0 | `SUCCESS` | Subcommand completed without errors |
| 1 | `VALIDATION_FAILURE` | `ValidationReport.is_valid` is False, or `--strict` with warnings |
| 2 | `CONNECTION_FAILURE` | `config.ini` missing, unreadable, or TM1py fails to connect |
| 3 | `BUILD_ERROR` | Dimension/cube/data pipeline raised an unhandled exception |
| 4 | `USAGE_ERROR` | Bad argv (argparse default; surfaces naturally via `SystemExit(2)`, remapped to 4) |
| 10 | `UNEXPECTED_ERROR` | Any other uncaught exception |

Mapping logic (simplified):
```python
try:
    return _cmd_dispatch(args)
except ValueError as e:          # raised by build_model on validation failure
    basic_logger.error("%s", e)
    return ExitCode.VALIDATION_FAILURE
except (TM1pyException, ConnectionError, FileNotFoundError) as e:
    basic_logger.error("TM1 connection failure: %s", e)
    return ExitCode.CONNECTION_FAILURE
except Exception as e:
    basic_logger.exception("Build error")
    return ExitCode.BUILD_ERROR
```

---

## 5. Integration Points

| Subcommand | Existing functions reached (in order) | New code needed |
|-|-|-|
| `validate` | `SchemaLoader(schema_dir, env).load_schema()` → `schema_validator.validate_schema(schema, project_root)` → `report.log_report()` | `_cmd_validate()` wrapper + `--strict` handling |
| `build` | all of validate + `utility.tm1_connection(config, conn)` → `tm1_bench.build_model(tm1, schema, system_defaults, env)` | `_cmd_build()` wrapper + `--dry-run` plan printer + `--skip-data` branch |
| `destroy` | `SchemaLoader.load_schema()` → `utility.tm1_connection()` → `tm1_bench.destroy_model(tm1, schema)` | `_cmd_destroy()` wrapper |
| `generate-data` | validate + `utility.tm1_connection()` → `tm1_bench.generate_data(tm1, schema, system_defaults)` | `_cmd_generate_data()` wrapper + `--dataset NAME` filter (filters `schema['datasets']` before calling `generate_data`) |

**No changes needed to:** `dimension_builder.py`, `dimension_period_builder.py`, `df_generator_for_dataset.py`, `tm1_bedrock_executor.py`, `schema_validator.py`.

---

## 6. Open Questions and Risks

### Open questions

1. **Should `--dataset NAME` exist on `build` too?** Today `build` is all-or-nothing. A `--dataset` filter there would help incremental builds but has complex semantics (do we still build all dims/cubes?). Propose: defer to v2.
2. **Exit code on partial success?** If 3 of 10 datasets succeed and 7 fail, is that exit 3 or exit 0? Propose: exit 3 — any pipeline failure is a failure. Existing `generate_data` swallows per-dataset callable errors; we may want to tighten that in a separate issue.
3. **Should `--json-logs` also emit a machine-readable summary to stdout?** Nice for agents but adds surface area. Propose: defer; today's JSON log lines to file plus exit code are sufficient.
4. **Naming: `tm1-bench` vs `tm1bench` vs `tm1_bench`?** Hyphenated is standard for console scripts (compare `pip-compile`, `docker-compose`). Going with `tm1-bench`.
5. **Should the console script auto-discover `pyproject.toml` to find the project root?** Simpler: require `--schema` to be explicit, default `./schema`.

### Risks

| Risk | Likelihood | Mitigation |
|-|-|-|
| Existing `sample.py` path-derivation logic breaks when invoked from a different CWD via the CLI | Medium | Extract `_derive_project_root()` helper that respects `--schema` absolute path; test from both repo root and arbitrary CWD |
| `config.ini` schema drift between connections (e.g. `testbench` vs `testbench3` sections) silently fails | Medium | `cli.py` validates the INI section exists and raises clear `CONNECTION_FAILURE` before TM1Service instantiation |
| Logging double-configures when `cli.main()` is called from tests back-to-back | Low | Guard `basicConfig` call; or have tests not touch the logging setup — they should invoke handlers directly |
| `--dry-run` diverges from actual build behaviour over time | Medium | Same code path for validation; dry-run is "validate + print plan," not a parallel simulator. Covered by a CLI integration test that confirms plan output matches dimension/cube counts in the schema. |
| `argparse` help strings go stale as features grow | Low | Single source of truth: this doc. Periodic review by Architect. |

---

## 7. Success Criteria

All acceptance criteria from the product backlog story:

- [x] `tm1-bench validate --schema schema/ --env default` exits 0/1 without TM1
- [x] `tm1-bench build --schema schema/ --env default` runs full pipeline
- [x] `tm1-bench destroy --schema schema/ --env default` tears down the model
- [x] `tm1-bench generate-data --schema schema/ --env default` loads data only
- [x] Exit codes: 0 success, 1 validation, 2 connection, 3 build, plus 4 usage and 10 unexpected
- [x] `--dry-run` on `build` validates and prints the plan
- [x] Usable as GitHub Actions step (any executable with exit code) and as AI agent tool (deterministic subcommand + exit-code contract)

Measurable: CI pipeline replaces `python sample.py` with `tm1-bench build --env default --connection testbench`.
