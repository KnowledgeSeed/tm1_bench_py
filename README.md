![CI Build](https://github.com/knowledgeseed/tm1_bench_py/actions/workflows/build-test.yml/badge.svg?query=branch%3Amain++)

# TM1 Benchmark Model Generator

`tm1_bench_py` is a Python library that programmatically builds TM1/Planning Analytics models from YAML configuration files. It creates reproducible benchmark models for performance testing, application testing, demo provisioning, and CI/CD model validation.

Full documentation is available in the [docs](docs/index.md) directory.

## Features

- **Schema-driven model creation** — dimensions, cubes, and datasets are defined in YAML files under `schema/`. No code changes needed to add a new component.
- **Four dimension strategies** — `elementlist` (manual), `df_template` (programmatic generation), `custom` (Python callable), and `csv` (CSV-backed via `tm1_bedrock_py`).
- **Environment-specific configuration** — each YAML file supports multiple named environment blocks (`default`, `ksAcademy`, …); `SchemaLoader` selects the matching block at runtime and falls back to `default`.
- **Pre-build schema validation** — `validate_schema()` runs before any TM1 connection and reports all errors and warnings in one pass.
- **Automatic data generation** — dataset templates generate deterministic or randomised DataFrames and load them via TM1py.
- **Model lifecycle helpers** — `build_model()` and `destroy_model()` create or remove all objects described by a schema.
- **Structured logging** — JSON logs written to `logs/` via `tm1_bench_py/logging.json`; schema validation messages prefixed `[SCHEMA]`.

## Installation

Python 3.11+ required. Install dependencies:

```bash
pip install -r requirements.txt
```

A running TM1/Planning Analytics server is required to build models. Unit tests run without a server.

## CLI Usage

After installing the package (`pip install -e .`), the `tm1-bench` command is available:

```bash
# Validate schema — no TM1 connection required (fast CI pre-check)
tm1-bench validate --schema ./schema --env default

# Build the full benchmark model
tm1-bench build --schema ./schema --env ksAcademy --connection testbench3

# Preview what would be built without connecting to TM1
tm1-bench build --schema ./schema --env default --dry-run

# Tear down a benchmark environment
tm1-bench destroy --schema ./schema --env default

# Reload data for specific datasets
tm1-bench generate-data --schema ./schema --dataset Sales --dataset Budget
```

The same commands are available via the module entrypoint (no install required):
```bash
python -m tm1_bench_py validate --schema ./schema
```

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

## Quick start

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
# tm1_bench.destroy_model(tm1=tm1, schema=schema)  # tear down
```

See `sample.py` for a complete runnable example.

## Testing

```bash
# Unit tests — no TM1 server required
pytest tests/

# Integration tests — requires TM1 Docker container
cd tests_integration && docker-compose up -d
pytest tests_integration/
```

## Documentation

| Doc | Contents |
|-----|---------|
| [User Guide](docs/user-guide.md) | Install, quick start, Python API, schema validation CLI |
| [Schema Reference](docs/schema-reference.md) | All YAML types: schema.yaml, config.yaml, variables, all 4 dimension types, cubes, datasets, built-in callables |
| [Architecture](docs/architecture.md) | Module map, data flow, validation, patterns, test architecture |
| [Best Practices](docs/best-practices.md) | Environment strategy, performance tuning, CSV tips, debugging |
| [Model Reference](docs/model-reference.md) | Default benchmark model: all dimensions and cubes documented |

## License

This project is released under the [MIT License](LICENSE).
