# User Guide

## Installation

Python 3.11+ is required. Install all dependencies:

```bash
pip install -r requirements.txt
```

A running TM1/Planning Analytics server reachable from your environment is needed to build models. The unit test suite runs without a TM1 server.

---

## Project layout

```
tm1_bench_py/        ← Python library
schema/              ← Your model definition (YAML files)
  schema.yaml        ← Orchestrator: lists what to build
  config.yaml        ← Global settings (env, paths, write params)
  variables.yaml     ← Shared data pools
  dimensions/        ← One YAML per dimension
  cubes/             ← One YAML per cube
  datasets/          ← One YAML per dataset
sample.py            ← Runnable example
tests/               ← Unit tests (no TM1 required)
tests_integration/   ← Full end-to-end tests (TM1 Docker)
```

---

## Quick start

### 1. Configure TM1 connection

Edit `tests/config.ini` (INI format, one section per environment):

```ini
[testbench]
address = localhost
port    = 5360
user    = Admin
password = apple
ssl     = True
```

### 2. Set the active environment

In `schema/config.yaml`, set `default_yaml_env` to the environment key you want to build:

```yaml
default_yaml_env: "default"
```

Every dimension, cube, and dataset YAML has blocks keyed by environment name. `SchemaLoader` extracts the matching block at load time and falls back to `default` if the requested key is not found.

### 3. Run the sample script

```bash
python sample.py
```

`sample.py` loads the schema, validates it, connects to TM1, and builds the full model. Check the console output and `logs/` for structured JSON logs.

### 4. Python API

```python
from tm1_bench_py import tm1_bench, utility

loader = tm1_bench.SchemaLoader(schema_dir="schema", env="default")
schema = loader.load_schema()

tm1 = utility.tm1_connection("tests/config.ini", "testbench")
tm1_bench.build_model(
    tm1=tm1,
    schema=schema,
    system_defaults=schema["config"]["df_to_cube_default_kwargs"],
    env="default",
)

# To tear everything down:
# tm1_bench.destroy_model(tm1=tm1, schema=schema)
```

`build_model()` validates the schema before making any TM1 connection. If errors are found they are logged with a `[SCHEMA]` prefix and the build is aborted. Warnings are logged but do not block the build.

---

## Running tests

Unit and integration tests use `pytest`:

```bash
# Unit tests — no TM1 server required
pytest tests/

# Single test
pytest tests/test_schema_validation.py -k "test_valid_config_passes"

# Integration tests — requires TM1 Docker container
cd tests_integration && docker-compose up -d
pytest tests_integration/
```

---

## Adding a new dimension

1. Create a YAML file in the appropriate `schema/dimensions/<type>/` subdirectory.
2. Add env blocks (`default:`, `ksAcademy:`, …) with at minimum a `dimension_name` key.
3. Add the filename (without `.yaml`) to the matching list in `schema/schema.yaml` under `import.dimensions.<type>`.
4. Run `pytest tests/` to validate — the schema validator will report any structural issues without needing a TM1 connection.

See [Schema Reference](schema-reference.md) for the full YAML specification for each dimension type.

---

## Adding a new cube

1. Create `schema/cubes/<CubeName>.yaml`.
2. Add the filename to `import.cubes` in `schema/schema.yaml`.
3. Reference only dimension names that are already defined in the schema.

---

## Adding a new dataset

1. Create `schema/datasets/<dataset_name>.yaml`.
2. Add the filename to `import.datasets` in `schema/schema.yaml`.
3. Set `targetCube` to a cube defined in the schema (or a `}ElementAttributes_*` system cube).

---

## Using the CLI

After installing the package (`pip install -e .`), the `tm1-bench` command is available from any terminal:

```bash
# Validate schema — no TM1 connection required (fast CI pre-check)
tm1-bench validate --schema ./schema --env default

# Build the full benchmark model
tm1-bench build --schema ./schema --env ksAcademy --connection testbench3

# Preview what would be built without connecting to TM1
tm1-bench build --schema ./schema --env default --dry-run

# Tear down a benchmark environment
tm1-bench destroy --schema ./schema --env default

# Reload data for specific datasets only
tm1-bench generate-data --schema ./schema --dataset Sales --dataset Budget
```

The same commands are available via the Python module entrypoint (no install required):

```bash
python -m tm1_bench_py validate --schema ./schema
```

### Config and connection resolution

The CLI resolves the TM1 connection config file and section name with the following priority order:

| Setting | Priority |
|---------|---------|
| `--config PATH` flag | highest |
| `TM1_BENCH_CONFIG` environment variable | |
| `./config.ini` (current directory) | fallback |

| Setting | Priority |
|---------|---------|
| `--connection NAME` flag | highest |
| `TM1_BENCH_CONNECTION` environment variable | |
| `testbench` | fallback |

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Schema validation failure |
| 2 | TM1 connection failure |
| 3 | Build/pipeline error |
| 4 | Invalid usage (bad arguments) |
| 10 | Unexpected error |

---

## Schema validation

Before building, run a validation-only check by loading the schema and calling the validator directly:

```python
from pathlib import Path
from tm1_bench_py import tm1_bench, schema_validator

loader = tm1_bench.SchemaLoader("schema", "default")
schema = loader.load_schema()

report = schema_validator.validate_schema(schema, project_root=Path("."))
report.log_report()

if not report.is_valid:
    print(f"Fix {len(report.errors)} error(s) before building.")
```

This is useful as a CI pre-flight check — no TM1 connection required.
