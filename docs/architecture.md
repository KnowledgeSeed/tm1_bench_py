# Architecture

## Data flow

```
sample.py  (or your own script)
  │
  ├─ SchemaLoader(schema_dir, env).load_schema()
  │    ├─ Reads schema.yaml  → list of component files to load
  │    ├─ Reads config.yaml  → global settings + env default
  │    ├─ Reads variables.yaml
  │    ├─ Reads dimension YAMLs  (elementlist / df_templates / custom / csv)
  │    ├─ Reads cube YAMLs
  │    └─ Reads dataset YAMLs
  │         └─ Returns: { dimensions, cubes, datasets, variables, config, env }
  │
  └─ build_model(tm1=None, schema=None, system_defaults=None, env="")
       │
       ├─ [1] schema_validator.validate_schema(schema, project_root)
       │         Collects ALL errors + warnings in one pass.
       │         Aborts with ValueError if errors > 0.
       │         No TM1 connection required.
       │
       ├─ [2] utility.tm1_connection()   ← only reached if schema is valid
       │
       ├─ [3] create_dimensions(tm1, schema)
       │         for each dim type → matching builder
       │
       ├─ [4] create_cubes(tm1, schema)
       │         TM1py Cube object + rules upload
       │
       └─ [5] generate_data(tm1, schema)
                DataFrame generation → TM1py cell write
```

**Critical ordering guarantee:** schema validation always runs before any TM1 connection is opened. A bad schema surfaces all errors in one pass without wasting server resources.

---

## Module map

| Module | Role | Key public API |
|--------|------|----------------|
| `tm1_bench.py` | Orchestrator: YAML loading + pipeline driver | `SchemaLoader`, `build_model()`, `destroy_model()` |
| `schema_validator.py` | Pre-build validation; collects all issues before stopping | `validate_schema()`, `ValidationReport` |
| `dimension_builder.py` | Dimension creation for `elementlist` and `df_template` strategies | `create_dimension_from_element_list()`, `create_dimension_from_dataframe_template()` |
| `dimension_period_builder.py` | Time/fiscal dimension specialist | `generate_time_dimension()` |
| `df_generator_for_dataset.py` | Synthetic data engine | `generate_dataframe()` |
| `tm1_bedrock_executor.py` | Adapter to `tm1_bedrock_py` for CSV-backed dimensions | `execute_dimension_build_with_bedrock()` |
| `utility.py` | TM1 connection factory, logging decorator, DataFrame↔cube I/O | `tm1_connection()`, `@log_exec_metrics`, `_dataframe_to_cube_default()` |
| `json_log_formatter.py` | Structured JSON log output | `JSONLogFormatter` |
| `__init__.py` | Package boot — exposes `basic_logger`, `exec_metrics_logger` | — |

---

## Four dimension strategies

| Strategy | YAML key | Builder | When to use |
|----------|---------|---------|-------------|
| `elementlist` | `dimensions.elementlist` | `dimension_builder.create_dimension_from_element_list()` | Small/irregular dimensions, measure dims |
| `df_template` | `dimensions.df_templates` | `dimension_builder.create_dimension_from_dataframe_template()` | Large regular hierarchies (1 000–10 M+ elements) |
| `custom` | `dimensions.custom` | any `importlib`-resolved callable returning a DataFrame | Complex bespoke logic (fiscal time, calculated hierarchies) |
| `csv` | `dimensions.csv` | `tm1_bedrock_executor.execute_dimension_build_with_bedrock()` | Structure lives in a CSV file (org charts, account lists) |

---

## Schema validation

`schema_validator.validate_schema(schema, project_root)` returns a `ValidationReport`:

```python
@dataclass
class ValidationReport:
    errors:   List[str]   # blocking — build will not proceed
    warnings: List[str]   # informational — build continues

    @property
    def is_valid(self) -> bool: ...
    def log_report(self) -> None: ...   # prefixes all messages with [SCHEMA]
```

**What is validated (all in one pass):**

| Scope | Checks |
|-------|--------|
| `config` | Not empty; `df_to_cube_default_kwargs` has all 4 required keys |
| `elementlist` dim | `dimension_name` present; `elements` is a list |
| `df_template` dim | `df_template` key, `elements` sub-key, `levels` sub-key present |
| `custom` dim | `callable` present; resolved via `importlib` at validate time |
| `csv` dim | `csv_template.source` present and file exists; `input_format` valid; `level_columns` present for non-parent_child formats |
| Cubes | `name` present; `dimensions` is a list; every dimension name cross-referenced against loaded dimension definitions |
| Datasets | `targetCube` present; cube cross-referenced (skipped for `}ElementAttributes_*`); `rows` or `df_from_mdx` present; callable paths resolvable |

---

## CSV dimension adapter

`tm1_bedrock_executor` is a thin adapter that translates the project's YAML config into `tm1_bedrock_py`'s API:

```
csv_template (YAML)
  │
  ├─ load_csv_template_dataframe()       → resolves relative paths against project_root
  ├─ _apply_mapping_steps()             → column value replacements
  ├─ _apply_attribute_renames()         → column renames to bedrock notation (Description:s)
  └─ _resolve_bedrock_kwargs()          → translates YAML field names to bedrock API names
       element_column     → child_column
       element_type_column → type_column
       level_columns (required for non-parent_child formats)

bedrock.dimension_builder(
    dimension_name, build_strategy, tm1_service, raw_input_df,
    input_format, child_column, parent_column, ...
)
```

`tm1_bedrock_py` is an optional dependency — `execute_dimension_build_with_bedrock()` raises `ImportError` with a clear message if it is not installed.

---

## Data write path

```
DataFrame (generated by df_generator_for_dataset)
  └─ utility._dataframe_to_cube_default()
       ├─ Reorders columns to match cube dimension order
       ├─ Path A: tm1.cells.write_dataframe()          (synchronous)
       ├─ Path B: tm1.cells.write_dataframe_async()    (async_write=True)
       └─ Path C: TurboIntegrator blob                 (use_blob=True)
```

Default parameters (from `config.yaml`):

| Param | Default | Effect |
|-------|---------|--------|
| `async_write` | `True` | Parallel async write |
| `use_blob` | `True` | Fastest upload method for large datasets |
| `use_ti` | `False` | TI-based loading (rarely needed) |
| `slice_size_of_dataframe` | `50000` | Rows per chunk |

---

## Logging

Two loggers initialised in `__init__.py`:

- **`basic_logger`** — general application messages
- **`exec_metrics_logger`** — timing per function (written by `@log_exec_metrics` decorator)

Both write JSON via `JSONLogFormatter` when `tm1_bench_py/logging.json` is present; otherwise fall back to `basicConfig`. Logs go to `logs/`. Schema validation messages are always prefixed `[SCHEMA]` for easy filtering.

---

## TM1 connection

Connection parameters are read from an INI file (default: `tests/config.ini`) with one section per environment:

```ini
[testbench]
address  = localhost
port     = 5360
user     = Admin
password = apple
ssl      = True
```

`utility.tm1_connection(file_path, object_name)` instantiates `TM1Service(**config[object_name])`.

---

## Test architecture

| Suite | Location | TM1 required |
|-------|----------|-------------|
| Unit | `tests/test_unit.py` | No |
| Schema validation | `tests/test_schema_validation.py` | No |
| CSV integration | `tests/test_csv_dimension_integration.py` | No (bedrock mocked) |
| Integration smoke | `sample.py` (run in CI) | Yes — Docker |
| Integration suite | `tests_integration/` | Yes — Docker |

---

## CI/CD pipeline

`.github/workflows/build-test.yml`:

1. WireGuard VPN → `kseed-docker1.knowledgeseed.local:3000`
2. `pip install` + `python -m build`
3. `docker compose up` (TM1 on port 5360, image `tm1-docker:2.1.4-rocky9`)
4. `python sample.py` — integration smoke test
5. Teardown

---

## Key patterns

### Dynamic callable resolution
Both `custom` dimensions and dataset `data` callables are resolved at runtime:
```python
module = importlib.import_module("." + module_name, "tm1_bench_py")
func   = getattr(module, func_name)
```
Schema validation resolves all callables before the build starts, so a bad path surfaces without a TM1 connection.

### Environment override
Every YAML file supports named env blocks. `SchemaLoader` applies a two-level fallback: requested env → `default` → skip with error log. YAML anchors (`&anchor` / `<<: *merge`) keep env-specific overrides DRY.

### Sequential pipeline, no rollback
`build_model()` runs dimensions → cubes → data sequentially. There is no transactional rollback. `destroy_model()` exists for manual cleanup.
