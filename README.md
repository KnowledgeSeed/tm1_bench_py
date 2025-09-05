![CI Build](https://github.com/knowledgeseed/tm1_bench_py/actions/workflows/build-test.yml/badge.svg?query=branch%3Amain++)

# TM1 Benchmark Model Generator

tm1_bench_py is a Python library that programmatically builds TM1/Planning Analytics models based on YAML configuration files. The project aims to create reproducible benchmark models for performance testing, demos and automated validation.
Full documentation is available in the [docs](docs/index.md) directory.

## Features

- **Schema-driven model creation** – Dimensions, cubes and data sets are defined in YAML files located in the `schema/` folder.
- **Environment specific configuration** – Each YAML file can contain multiple environment blocks (e.g. `dev`, `test`); `SchemaLoader` selects the appropriate block at runtime.
- **Automatic data generation** – Dataset templates create deterministic or randomised data which is written to cubes using TM1py.
- **Model lifecycle helpers** – High level functions `build_model` and `destroy_model` create or remove all objects described by a schema.
- **Structured logging** – Logging is configured through `tm1_bench_py/logging.json` and writes JSON logs to the `logs/` directory.

## Installation

The project targets Python 3.11+. Install the required packages:

```bash
pip install -r requirements.txt
```

TM1py requires a running TM1/Planning Analytics server reachable from your environment.

## Configuration

A minimal schema is provided under the `schema/` directory.

Key files:

| File | Purpose |
| --- | --- |
| `schema/schema.yaml` | Orchestrates which dimensions, cubes and datasets to load. |
| `schema/config.yaml` | Global settings such as default environment and TM1py write parameters. |
| `schema/variables.yaml` | Optional variables referenced by templates. |
| `schema/dimensions/` | Dimension definitions organised by type (`elementlist`, `df_templates`, `custom`). |
| `schema/cubes/` | Cube definitions. |
| `schema/datasets/` | Dataset templates describing how to populate cubes. |

Each definition file contains top-level keys for different environments. The active environment is passed to `SchemaLoader` or read from `config.yaml`'s `default_yaml_env`.

## Usage

```python
from tm1_bench_py import tm1_bench, utility

schema_dir = "schema"
env = "dev"                 # use "config.yaml" default if omitted
loader = tm1_bench.SchemaLoader(schema_dir, env)
schema = loader.load_schema()

tm1 = utility.tm1_connection("config.ini", "testbench")
tm1_bench.build_model(tm1=tm1, schema=schema,
                      system_defaults=schema["config"]["df_to_cube_default_kwargs"],
                      env=env)
# tm1_bench.destroy_model(tm1=tm1, schema=schema)  # tear down
```

See `sample.py` for a complete runnable example.

## Testing

Unit tests rely on a running TM1 server defined in `tests/config.ini`.

```bash
pytest
```

The tests may fail if a TM1 instance is not available.

## License

This project is released under the [MIT License](LICENSE).

