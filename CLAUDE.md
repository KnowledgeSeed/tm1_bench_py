# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`tm1_bench_py` is a TM1 Benchmark Model Generator — a Python library that reads YAML configuration files and uses the TM1py REST API to create reproducible TM1 OLAP models for performance testing, application testing, and demo creation.

## Commands

### Install dependencies
```bash
pip install -r requirements.txt
```

### Build the package
```bash
python -m pip install --upgrade pip build
python -m build
```

### Run unit tests
```bash
pytest tests/
```

### Run a single test
```bash
pytest tests/test_unit.py::test_name
pytest tests/test_csv_dimension_integration.py -k "test_name"
```

### Run the main sample script
```bash
python sample.py
```

### Integration tests (requires running TM1 Docker container)
```bash
cd tests_integration && docker-compose up -d
pytest tests_integration/
```

## Architecture

### Data flow

The library is YAML-driven. `schema/schema.yaml` is the top-level orchestrator that imports dimension, cube, and dataset definition files. `schema/config.yaml` holds global settings (environment name, paths, data loader defaults). `schema/variables.yaml` holds reusable constants and data pools referenced by other YAMLs.

`sample.py` → `tm1_bench.SchemaLoader` (parses all YAMLs) → `tm1_bench.build_model()` (calls TM1py to create dimensions, cubes, and load data).

### Core modules

- **`tm1_bench.py`** — Orchestrator. `SchemaLoader` deserializes all YAML configs. `build_model()` and `destroy_model()` are the main entry points. Drives dimension and cube creation in order.
- **`dimension_builder.py`** — Handles two dimension definition methods: `elementlist` (manually listed elements) and `df_template` (generates elements from a pandas DataFrame template with leaf/consolidation rules).
- **`dimension_period_builder.py`** — Custom time/period dimension builder with fiscal year support (separate from the generic builder because of its complexity).
- **`df_generator_for_dataset.py`** — Generates pandas DataFrames to populate cube cells. Each dataset YAML references a generator function here.
- **`utility.py`** — TM1 connection factory (reads `config.ini`), logging helpers, and DataFrame-to-cube loaders that call TM1py.
- **`tm1_bedrock_executor.py`** — Runs TM1 Bedrock (server-side) processes, used for advanced dimension operations.

### Schema directory layout

```
schema/
├── schema.yaml          # Top-level orchestrator — lists all dimensions, cubes, datasets to build
├── config.yaml          # Global settings: environment name, file paths, df_to_cube defaults
├── variables.yaml       # Shared data pools (lists of values reused across dimension YAMLs)
├── dimensions/
│   ├── elementlist/     # Dimensions defined by manually listing elements
│   ├── df_templates/    # Dimensions generated from a DataFrame template
│   ├── custom/          # period.yaml — drives dimension_period_builder.py
│   └── csv/             # CSV-import-based dimensions (newer feature)
├── cubes/               # One YAML per cube: defines dimensions, rules files, etc.
└── datasets/            # One YAML per dataset: maps to a generator function + target cube
```

### Three dimension definition strategies

1. **`elementlist`** — Static list of elements and consolidations directly in YAML.
2. **`df_template`** — A template row is expanded into many elements by combining values from `variables.yaml` pools; supports leaf/consolidation hierarchy rules.
3. **`custom`** — References a specific Python builder function (e.g., the period dimension).
4. **`csv`** — Imports dimension structure from a CSV file (newer, see `schema/dimensions/csv/`).

### TM1 connection

Connection parameters live in `tests/config.ini` (or a path configured in `config.yaml`). The file follows `configparser` INI format with a section per environment (e.g., `[default]`, `[ksAcademy]`). `utility.py:get_tm1_service()` reads this file to instantiate a `TM1Service` from TM1py.

### CI/CD

`.github/workflows/build-test.yml` sets up a WireGuard VPN, pulls a private TM1 Docker image (`kseed-docker1.knowledgeseed.local:3000/tm1-docker:2.1.4-rocky9`), starts the container via `tests_integration/docker-compose.yml`, then runs `sample.py` as the integration smoke test.

---

## Project Assistant Protocol

### Files (git-ignored, local only)
- `project_memory.md` — central living memory: goals, decisions, patterns, tech debt, improvement log
- `work_logs/YYYY-MM-DD.md` — one file per working day

### During a session
- At the start of a session, read `project_memory.md` and today's log (if it exists) to restore context.
- Append notable findings, decisions, and blockers to today's `work_logs/YYYY-MM-DD.md` as work progresses.
- Create today's log file if it doesn't exist yet.

### Wrap-up trigger
When the user says **"review"**, **"wrap up"**, or **"wrap up the day"**:
1. Read `work_logs/YYYY-MM-DD.md` for today.
2. Distill key decisions, patterns discovered, and open items.
3. Append a dated summary to the **Continuous Improvement Log** section of `project_memory.md`.
4. Update **Active Goals**, **Open Items**, and **Patterns** sections in `project_memory.md` if anything changed.
5. Confirm to the user what was updated.

### Skills to use
- `/review` — review a PR or branch before wrapping up
- `/simplify` — check changed code for quality and reuse
- `/security-review` — flag security concerns on current branch changes
- `/init` — regenerate or update `CLAUDE.md` if architecture changes significantly

### Suggested tool permissions to add (via `/update-config`)
- `Bash: git log`, `git diff`, `git status` — always safe, used for context building
- `Read` on `project_memory.md` and `work_logs/**` — auto-allow, no side effects
- `Write` on `work_logs/**` — auto-allow for log append operations
