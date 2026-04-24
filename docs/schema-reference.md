# Schema Reference

All model configuration lives in YAML files under the `schema/` directory. Every definition file supports multiple named environment blocks; `SchemaLoader` extracts the block matching the active environment at load time, falling back to `default` if the requested key is absent.

---

## `schema.yaml` — Orchestrator

Lists every component to build. Edit the `import:` keys to include the base filenames (without `.yaml`) of the files you want loaded.

```yaml
import:
  cubes:
    - Sales
    - Price
  dimensions:
    elementlist:
      - version
      - measuresales
    df_templates:
      - product
      - customer
    custom:
      - period
    csv:
      - orgunit_csv
  datasets:
    - sales_data
    - product_attributes
  variables: variables    # filename of variables.yaml (no extension)
```

| Key | Type | Description |
|-----|------|-------------|
| `cubes` | List[str] | Cube definition filenames |
| `dimensions.elementlist` | List[str] | Static element-list dimension filenames |
| `dimensions.df_templates` | List[str] | DataFrame-template dimension filenames |
| `dimensions.custom` | List[str] | Custom-callable dimension filenames |
| `dimensions.csv` | List[str] | CSV-backed dimension filenames |
| `datasets` | List[str] | Dataset template filenames |
| `variables` | str | Variables filename (usually `variables`) |

---

## `config.yaml` — Global Settings

```yaml
default_yaml_env: "default"

df_to_cube_default_kwargs:
  async_write: True
  slice_size_of_dataframe: 50000
  use_blob: True
  use_ti: False

paths:
  dimensions_elementlist: 'dimensions/elementlist'
  dimensions_df_templates: 'dimensions/df_templates'
  dimensions_custom:       'dimensions/custom'
  dimensions_csv:          'dimensions/csv'
  cubes:                   'cubes'
  datasets:                'datasets'
  variables:               '.'
```

| Key | Type | Description |
|-----|------|-------------|
| `default_yaml_env` | str | Environment key used when no env is passed to `SchemaLoader` |
| `df_to_cube_default_kwargs.async_write` | bool | Use asynchronous TM1py write |
| `df_to_cube_default_kwargs.slice_size_of_dataframe` | int | Rows per upload chunk |
| `df_to_cube_default_kwargs.use_blob` | bool | Use blob upload (recommended `True`) |
| `df_to_cube_default_kwargs.use_ti` | bool | Use TurboIntegrator for loading |
| `paths.*` | str | Relative paths from the schema directory to each subdirectory |

---

## `variables.yaml` — Data Pools

Central repository of reusable lists and constants. Referenced in dataset templates via `variable_path`.

```yaml
product_size: ["S", "M", "L", "XL"]

countries:
  HU:
    name: "Hungary"
    currency: "HUF"
    region: "EMEA"
  US:
    name: "United States"
    currency: "USD"
    region: "Americas"

gender:
  M:
    first_names: ["George", "Lukas"]
  F:
    first_names: ["Ruth", "Eva"]
```

Access paths in dataset params use dot notation: `variables.product_size`, `variables.countries`, `variables.gender.M.first_names`.

---

## Dimension YAMLs — Common Structure

All dimension files are keyed by environment name. The `dimension_name` key is always required.

```yaml
default: &defaults
  dimension_name: "testbenchProduct"
  # ... type-specific keys

ksAcademy:
  <<: *defaults
  dimension_name: "Product"    # override for this env
```

### Method 1: `elementlist` — Manual Definition

**Location:** `schema/dimensions/elementlist/`
**Use when:** Small or irregular dimensions, measure dimensions, fixed hierarchies.

```yaml
default:
  dimension_name: "testbenchVersion"
  elements:
    - { name: "Actual",   element_type: "Numeric" }
    - { name: "Forecast", element_type: "Numeric" }
    - { name: "Budget",   element_type: "Numeric" }
  edges: []          # empty = flat dimension; or [[Parent, Child, Weight], ...]
  attributes:
    - { name: "ShortAlias",   attribute_type: "Alias" }
    - { name: "Description",  attribute_type: "String" }
```

| Key | Type | Description |
|-----|------|-------------|
| `elements` | List[Dict] | Each element: `name` (str), `element_type` (`Numeric`/`String`/`Consolidated`) |
| `edges` | List[List] | `[ParentName, ChildName, Weight]` triples. Empty list = flat. |
| `attributes` | List[Dict] | `name` + `attribute_type` (`String`/`Numeric`/`Alias`) |

---

### Method 2: `df_template` — Programmatic Generation

**Location:** `schema/dimensions/df_templates/`
**Use when:** Large dimensions with regular structures (10 000+ elements).

```yaml
default:
  dimension_name: "testbenchProduct"
  df_template:
    elements:
      NumberOfElements: 10000
      ElementPrefix: "P"
      ElementLength: 8
      Method: "enumerate"
    levels:
      - name: "level000"
        constant_content: "All Products"
      - name: "level001"
        content_template:
          Prefix: "ProductGroup"
          Length: 2
          Method: "enumerate"
    attributes:
      - "Size:s"
      - "Color:s"
      - "CostType:a"
```

| Key | Type | Description |
|-----|------|-------------|
| `df_template.elements.NumberOfElements` | int | Number of leaf elements to generate |
| `df_template.elements.ElementPrefix` | str | Prefix for element names |
| `df_template.elements.ElementLength` | int | Zero-padded numeric suffix length |
| `df_template.elements.Method` | str | Generation method (`enumerate`) |
| `df_template.levels` | List[Dict] | Hierarchy levels top-down; `constant_content` = single top node; `content_template` = procedural intermediate nodes |
| `df_template.attributes` | List[str] | Attribute names with type suffix: `:s` String, `:n` Numeric, `:a` Alias |

---

### Method 3: `custom` — Python Callable

**Location:** `schema/dimensions/custom/`
**Use when:** Complex bespoke logic (e.g., fiscal time dimensions with offsets, calculated hierarchies).

```yaml
default:
  dimension_name: "testbenchPeriod"
  callable: "dimension_period_builder.generate_time_dimension"
  kwargs:
    year_start: 2024
    year_end: 2028
    monthly: 1
    daily: 0
    quarterly: 1
    ytd: 1
    ytg: 0
    attributes:
      - name: "PREV_PERIOD:s"
        method: "time_reference"
        referenced_period_distance: -1
      - name: "MonthName:s"
        method: "format"
        format: "MMMM"
```

| Key | Type | Description |
|-----|------|-------------|
| `callable` | str | `module.function` path (resolved via `importlib` inside `tm1_bench_py`) |
| `kwargs` | Dict | Passed directly to the callable; structure depends on the target function |

The callable must return a pandas DataFrame that `TM1py.hierarchies.update_or_create_hierarchy_from_dataframe()` can consume (columns: `element_id`, `element_type`, parent columns as needed).

---

### Method 4: `csv` — CSV-backed via tm1_bedrock_py

**Location:** `schema/dimensions/csv/`
**Use when:** Dimension structure is maintained in a CSV file (org charts, account structures, cost centre hierarchies).

```yaml
default:
  dimension_name: "testbenchOrgUnit"
  csv_template:
    source: "schema/dimensions/csv_sources/orgunit.csv"  # relative to project root, or absolute
    input_format: "parent_child"      # parent_child | indented_levels | filled_levels
    build_strategy: "rebuild"         # rebuild | safe_rebuild | safe_rebuild_unwind | update
    element_column: "code"            # column holding the child/element name
    parent_column: "parent_code"      # column holding the parent name (parent_child only)
    element_type_column: "element_type"  # optional: Numeric / Consolidated
    mapping_steps:                    # optional: value replacements before upload
      - method: "replace"
        columns: ["parent_code"]
        values: { "TOTAL": "All Org Units" }
    attributes:                       # optional: rename CSV columns to bedrock attribute notation
      - source: "description"
        target: "Description:s"
      - source: "country"
        target: "Country:s"
```

**`input_format` values:**

| Value | Description | Required columns |
|-------|-------------|-----------------|
| `parent_child` | Each row is a child with its parent | `element_column`, `parent_column` |
| `indented_levels` | Column per hierarchy level, filled from left | `level_columns: [L1, L2, L3, ...]` |
| `filled_levels` | Same as indented_levels but levels are always populated | `level_columns: [L1, L2, L3, ...]` |

**`build_strategy` values:**

| Value | Description |
|-------|-------------|
| `rebuild` | Delete dimension and rebuild from scratch |
| `safe_rebuild` | Rebuild, preserving any values in cells that reference this dimension |
| `safe_rebuild_unwind` | Same as safe_rebuild but unwinds consolidations first |
| `update` | Add/update elements without deleting existing ones |

**CSV requirements for `parent_child` format:**
- Every element that acts as a parent must also appear as a child row (with its own parent or an empty parent column for the root).
- Root element: empty `parent_column` value.
- All rows must be included — no implicit TOTAL placeholders.

**For `indented_levels` / `filled_levels`, add `level_columns`:**
```yaml
csv_template:
  source: "schema/dimensions/csv_sources/account.csv"
  input_format: "indented_levels"
  level_columns: ["L1", "L2", "L3"]
```

---

## Cube YAMLs

**Location:** `schema/cubes/`

```yaml
default:
  name: "testbenchSales"
  dimensions:            # order affects TM1 performance — list large sparse dims first
    - "testbenchVersion"
    - "testbenchPeriod"
    - "testbenchProduct"
    - "testbenchCustomer"
    - "testbenchMeasureSales"
  rules:
    - "SKIPCHECK;"
    - "FEEDERS;"
    - "['Revenue'] = N: ['Quantity'] * DB('testbenchPrice', !testbenchVersion, !testbenchPeriod, !testbenchProduct, 'Price');"
    - "['Quantity'] => ['Revenue'];"
```

| Key | Type | Description |
|-----|------|-------------|
| `name` | str | Cube name in TM1 |
| `dimensions` | List[str] | Dimension names — must match `dimension_name` values in loaded dimension definitions |
| `rules` | List[str] | TM1 rule lines. Empty list = no rules. |

---

## Dataset YAMLs

**Location:** `schema/datasets/`

### Rows-based dataset (most common)

```yaml
default:
  targetCube: "testbenchSales"
  rows:
    mdx: >
      {[testbenchVersion].[Actual]} *
      {DESCENDANTS([testbenchPeriod].[All Periods], 99, LEAVES)} *
      {TM1FILTERBYLEVEL({TM1SUBSETALL([testbenchProduct])}, 0)} *
      {TM1FILTERBYLEVEL({TM1SUBSETALL([testbenchCustomer])}, 0)}
    number_of_rows: 1500000   # positive = random sample; -1 = full Cartesian product
  data:
    Quantity:
      method: "function"
      callable: "df_generator_for_dataset._random_number_based_on_statistic"
      params:
        min_val: 0
        max_val: 100
        num_type: "int"
        distribution: "normal"
        mean: 65
        std_dev: 20
```

### MDX-sourced dataset

```yaml
default:
  targetCube: "testbenchSales"
  df_from_mdx: "SELECT ... ON ROWS FROM [testbenchSales]"   # full MDX query
  data:
    callable: "df_generator_for_dataset._random_number_based_on_statistic"
    params: { min_val: 0, max_val: 100, num_type: "int", distribution: "uniform" }
```

### Attribute cube dataset

```yaml
default:
  targetCube: "}ElementAttributes_testbenchProduct"   # system cube, skips cube cross-reference check
  rows:
    mdx: "{TM1FILTERBYLEVEL({TM1SUBSETALL([testbenchProduct])}, 0)}"
    number_of_rows: -1
  data:
    Size:
      callable: "df_generator_for_dataset._random_from_variable_list"
      params:
        variable_path: "variables.product_size"
```

| Key | Type | Description |
|-----|------|-------------|
| `targetCube` | str | Cube to load data into. `}ElementAttributes_*` cubes skip the cross-reference check. |
| `rows.mdx` | str | MDX set expressions joined with `*` — one per non-measure dimension |
| `rows.number_of_rows` | int | `-1` = full product; positive = random sample of that size |
| `df_from_mdx` | str | Full MDX query (alternative to `rows`); data column callable transforms the result |
| `data` | Dict | Measure/attribute name → callable config |
| `data.<col>.callable` | str | `module.function` path inside `tm1_bench_py` |
| `data.<col>.params` | Dict | Passed to the callable |

---

## Built-in Data Generator Callables

All callables live in `tm1_bench_py.df_generator_for_dataset`.

| Callable | Purpose | Key params |
|----------|---------|-----------|
| `_random_number_based_on_statistic` | Random numbers from a statistical distribution | `min_val`, `max_val`, `num_type` (`int`/`float`), `distribution` (`uniform`/`normal`/`exponential`/`triangular`), `mean`, `std_dev`, `rate`, `mode` |
| `_random_from_variable_list` | Random pick from a `variables.yaml` list or dict keys | `variable_path` |
| `_index_from_variable_list` | Deterministic index into a `variables.yaml` list | `variable_path` |
| `_look_up_based_on_column_value` | Lookup in `variables.yaml` keyed by another column's value | `referred_column`, `variable_path`, `variable_key`, `prefix`, `postfix` |
| `_generate_from_subset_mdx` | Random element from a live MDX subset (result cached per run) | `dimension_name`, `subsetMDX`, `hierarchy_name` |
| `_getCapitalLetters` | Extract capital letters from another column's value in the same row | `apply_on_column` |
