# Best Practices

## Start small and iterate

Begin with one dimension per type, one cube, and a small dataset (100–1 000 rows). Verify that `pytest tests/` passes and `build_model()` completes without errors before scaling up. Incrementally add complexity.

---

## Environment strategy

Use environment blocks to control scale without duplicating YAML:

```yaml
default: &base
  dimension_name: "testbenchProduct"
  df_template:
    elements:
      NumberOfElements: 10000

ksAcademy:
  <<: *base
  df_template:
    elements:
      NumberOfElements: 300     # small for demos

bedrock_test_1000000:
  <<: *base
  df_template:
    elements:
      NumberOfElements: 1000000
```

- Use `default` for normal development.
- Use small-count envs for CI and quick sanity checks.
- Use large-count envs for dedicated performance benchmarking runs.

---

## Schema validation first

Run validation before every build — especially in CI. The validator needs no TM1 connection and catches typos, missing files, broken callables, and unknown dimension references in one pass:

```bash
python -c "
from pathlib import Path
from tm1_bench_py import tm1_bench, schema_validator
s = tm1_bench.SchemaLoader('schema', 'default').load_schema()
r = schema_validator.validate_schema(s, Path('.'))
r.log_report()
exit(0 if r.is_valid else 1)
"
```

A `[SCHEMA]` error means the build would fail; fix it before connecting to TM1.

---

## Controlling data volume

| Lever | Where | Effect |
|-------|-------|--------|
| `NumberOfElements` | `df_template.elements` | Dimension size |
| `number_of_rows` | `dataset.rows` | Data density; `-1` = full Cartesian product (can be massive) |
| `slice_size_of_dataframe` | `config.df_to_cube_default_kwargs` | Memory usage during upload |

Avoid `number_of_rows: -1` with large MDX scopes unless you specifically want a full population. Very large products generate coordinates slowly in Python before any data is written.

---

## TM1 performance tuning

**Dimension order in cubes matters.** List large, sparse dimensions first:

```yaml
dimensions:
  - "testbenchCustomer"    # 100 000 elements — sparse, list first
  - "testbenchProduct"     # 10 000 elements
  - "testbenchPeriod"      # ~240 elements
  - "testbenchVersion"     # 3 elements — dense, list last
  - "testbenchMeasureSales"
```

**Upload settings** (in `config.yaml`):
- `use_blob: True` — always use for production loads; fastest method.
- `async_write: True` — reduces roundtrip latency for large datasets.
- `slice_size_of_dataframe: 50000` — tune down (e.g., 10 000) if TM1 memory is constrained.

---

## CSV dimensions

- Always include the root element as an explicit row with an empty `parent_code`. `tm1_bedrock_py` enforces node integrity — every parent must also appear as a child row.
- Use `mapping_steps` to normalise placeholder values from source systems before uploading (e.g., `TOTAL → All Org Units`).
- Use `build_strategy: safe_rebuild` instead of `rebuild` when the dimension is referenced by loaded cube data — `rebuild` deletes the dimension including all cell values.
- Keep CSV source files under `schema/dimensions/csv_sources/` so relative paths in YAML always work from the project root.

---

## MDX best practices

- Prefer dynamic MDX (`DESCENDANTS`, `TM1FILTERBYLEVEL`, `TM1SUBSETALL`) over hardcoded element names. Hardcoded elements break when dimensions are rebuilt with different envs.
- Use `TM1FILTERBYLEVEL(..., 0)` to target only leaf elements — avoids loading data into consolidated cells.
- Cache MDX subsets in `_generate_from_subset_mdx` (already done internally) — don't call live MDX once per row.

---

## Realistic data generation

| Goal | Approach |
|------|---------|
| Realistic numeric distributions | `_random_number_based_on_statistic` with `distribution: normal` or `triangular` |
| Categorical attributes from controlled lists | `_random_from_variable_list` + `variables.yaml` pools |
| Derived attributes (currency from country) | `_look_up_based_on_column_value` + `variables.yaml` dict |
| Highly realistic text (names, addresses) | Write a custom callable using `Faker` or similar |
| Referential integrity across cubes | Use `_generate_from_subset_mdx` to pick valid element names from a live dimension |

---

## Custom callables

Any function in `tm1_bench_py` can be referenced as a `callable` in dimension or dataset YAML:

```yaml
callable: "my_module.my_function"
kwargs:
  param1: value1
```

- The module is resolved via `importlib.import_module("." + module_name, "tm1_bench_py")`.
- The schema validator checks the path at validation time — no silent failures at build time.
- Functions referenced in `custom` dimensions should return a pandas DataFrame with `element_id` and `element_type` columns.

---

## Debugging

- Set log level to `DEBUG` in `tm1_bench_py/logging.json` for verbose output.
- Validate YAML syntax with an IDE plugin or `python -c "import yaml; yaml.safe_load(open('schema/config.yaml'))"` before running.
- Watch the TM1 server message log for server-side errors after dimensions/cubes are created.
- Schema validation errors are prefixed `[SCHEMA]` — grep for them: `grep "\[SCHEMA\]" logs/*.log`.

---

## Version control

- Store the entire `schema/` directory in Git. This ensures full reproducibility — any commit can rebuild the exact model.
- **Never commit** `tests/config.ini` if it contains passwords. Add it to `.gitignore` and use environment variables or a secrets manager in CI.
- Tag schema versions when cutting benchmark runs so results can be correlated back to a known model definition.
