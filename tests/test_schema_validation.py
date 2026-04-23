"""Tests for schema_validator.validate_schema()."""
from pathlib import Path

import pytest

from tm1_bench_py.schema_validator import validate_schema, ValidationReport


# ---------------------------------------------------------------------------
# helpers — minimal valid schema building blocks
# ---------------------------------------------------------------------------

def _base_config():
    return {
        "default_yaml_env": "default",
        "df_to_cube_default_kwargs": {
            "async_write": True,
            "slice_size_of_dataframe": 50000,
            "use_blob": True,
            "use_ti": False,
        },
        "paths": {},
    }


def _base_schema(tmp_path: Path):
    return {
        "config": _base_config(),
        "dimensions": {"elementlist": {}, "df_templates": {}, "custom": {}, "csv": {}},
        "cubes": {},
        "datasets": {},
        "variables": {},
        "env": "default",
    }


# ---------------------------------------------------------------------------
# ValidationReport
# ---------------------------------------------------------------------------

def test_report_is_valid_when_no_errors():
    r = ValidationReport()
    assert r.is_valid

def test_report_is_invalid_when_errors_present():
    r = ValidationReport()
    r.error("something broke")
    assert not r.is_valid

def test_report_warnings_do_not_affect_validity():
    r = ValidationReport()
    r.warn("minor issue")
    assert r.is_valid


# ---------------------------------------------------------------------------
# config validation
# ---------------------------------------------------------------------------

def test_valid_config_passes(tmp_path):
    schema = _base_schema(tmp_path)
    report = validate_schema(schema, tmp_path)
    assert report.is_valid

def test_empty_config_reports_error(tmp_path):
    schema = _base_schema(tmp_path)
    schema["config"] = {}
    report = validate_schema(schema, tmp_path)
    assert not report.is_valid
    assert any("empty" in e or "loaded" in e for e in report.errors)

def test_missing_df_to_cube_kwargs_key_warns(tmp_path):
    schema = _base_schema(tmp_path)
    del schema["config"]["df_to_cube_default_kwargs"]["use_ti"]
    report = validate_schema(schema, tmp_path)
    assert any("use_ti" in w for w in report.warnings)


# ---------------------------------------------------------------------------
# elementlist dimension
# ---------------------------------------------------------------------------

def test_valid_elementlist_passes(tmp_path):
    schema = _base_schema(tmp_path)
    schema["dimensions"]["elementlist"]["currency"] = {
        "dimension_name": "Currency",
        "elements": [{"name": "USD", "element_type": "Numeric"}],
        "edges": [],
        "attributes": [],
    }
    report = validate_schema(schema, tmp_path)
    assert report.is_valid

def test_elementlist_missing_dimension_name_errors(tmp_path):
    schema = _base_schema(tmp_path)
    schema["dimensions"]["elementlist"]["currency"] = {
        "elements": [{"name": "USD"}],
        "edges": [],
        "attributes": [],
    }
    report = validate_schema(schema, tmp_path)
    assert any("dimension_name" in e for e in report.errors)

def test_elementlist_elements_not_list_errors(tmp_path):
    schema = _base_schema(tmp_path)
    schema["dimensions"]["elementlist"]["currency"] = {
        "dimension_name": "Currency",
        "elements": "USD",
        "edges": [],
    }
    report = validate_schema(schema, tmp_path)
    assert any("elements" in e and "list" in e for e in report.errors)


# ---------------------------------------------------------------------------
# df_template dimension
# ---------------------------------------------------------------------------

def test_valid_df_template_passes(tmp_path):
    schema = _base_schema(tmp_path)
    schema["dimensions"]["df_templates"]["product"] = {
        "dimension_name": "Product",
        "df_template": {
            "elements": {"NumberOfElements": 10},
            "levels": [{"name": "level000", "constant_content": "All"}],
        },
    }
    report = validate_schema(schema, tmp_path)
    assert report.is_valid

def test_df_template_missing_df_template_key_errors(tmp_path):
    schema = _base_schema(tmp_path)
    schema["dimensions"]["df_templates"]["product"] = {"dimension_name": "Product"}
    report = validate_schema(schema, tmp_path)
    assert any("df_template" in e for e in report.errors)

def test_df_template_missing_levels_errors(tmp_path):
    schema = _base_schema(tmp_path)
    schema["dimensions"]["df_templates"]["product"] = {
        "dimension_name": "Product",
        "df_template": {"elements": {"NumberOfElements": 10}},
    }
    report = validate_schema(schema, tmp_path)
    assert any("levels" in e for e in report.errors)


# ---------------------------------------------------------------------------
# custom dimension
# ---------------------------------------------------------------------------

def test_valid_custom_dim_passes(tmp_path):
    schema = _base_schema(tmp_path)
    schema["dimensions"]["custom"]["period"] = {
        "dimension_name": "Period",
        "callable": "dimension_period_builder.generate_time_dimension",
        "kwargs": {"year_start": 2024, "year_end": 2025, "monthly": 1},
    }
    report = validate_schema(schema, tmp_path)
    assert report.is_valid

def test_custom_dim_missing_callable_errors(tmp_path):
    schema = _base_schema(tmp_path)
    schema["dimensions"]["custom"]["period"] = {
        "dimension_name": "Period",
        "kwargs": {},
    }
    report = validate_schema(schema, tmp_path)
    assert any("callable" in e for e in report.errors)

def test_custom_dim_unresolvable_callable_errors(tmp_path):
    schema = _base_schema(tmp_path)
    schema["dimensions"]["custom"]["period"] = {
        "dimension_name": "Period",
        "callable": "nonexistent_module.nonexistent_func",
        "kwargs": {},
    }
    report = validate_schema(schema, tmp_path)
    assert any("nonexistent_module" in e for e in report.errors)

def test_custom_dim_missing_function_in_module_errors(tmp_path):
    schema = _base_schema(tmp_path)
    schema["dimensions"]["custom"]["period"] = {
        "dimension_name": "Period",
        "callable": "dimension_period_builder.this_function_does_not_exist",
        "kwargs": {},
    }
    report = validate_schema(schema, tmp_path)
    assert any("this_function_does_not_exist" in e for e in report.errors)


# ---------------------------------------------------------------------------
# csv dimension
# ---------------------------------------------------------------------------

def test_valid_csv_dim_passes(tmp_path):
    csv_file = tmp_path / "org.csv"
    csv_file.write_text("code,parent_code\nRoot,\n", encoding="utf-8")

    schema = _base_schema(tmp_path)
    schema["dimensions"]["csv"]["orgunit"] = {
        "dimension_name": "OrgUnit",
        "csv_template": {
            "source": str(csv_file),
            "input_format": "parent_child",
            "build_strategy": "rebuild",
            "element_column": "code",
            "parent_column": "parent_code",
        },
    }
    report = validate_schema(schema, tmp_path)
    assert report.is_valid

def test_csv_dim_missing_source_errors(tmp_path):
    schema = _base_schema(tmp_path)
    schema["dimensions"]["csv"]["orgunit"] = {
        "dimension_name": "OrgUnit",
        "csv_template": {"input_format": "parent_child"},
    }
    report = validate_schema(schema, tmp_path)
    assert any("source" in e for e in report.errors)

def test_csv_dim_source_file_not_found_errors(tmp_path):
    schema = _base_schema(tmp_path)
    schema["dimensions"]["csv"]["orgunit"] = {
        "dimension_name": "OrgUnit",
        "csv_template": {
            "source": "does_not_exist.csv",
            "input_format": "parent_child",
        },
    }
    report = validate_schema(schema, tmp_path)
    assert any("not found" in e for e in report.errors)

def test_csv_dim_invalid_input_format_errors(tmp_path):
    csv_file = tmp_path / "org.csv"
    csv_file.write_text("code\n", encoding="utf-8")
    schema = _base_schema(tmp_path)
    schema["dimensions"]["csv"]["orgunit"] = {
        "dimension_name": "OrgUnit",
        "csv_template": {"source": str(csv_file), "input_format": "bad_format"},
    }
    report = validate_schema(schema, tmp_path)
    assert any("input_format" in e for e in report.errors)

def test_csv_dim_level_format_missing_level_columns_errors(tmp_path):
    csv_file = tmp_path / "org.csv"
    csv_file.write_text("L1,L2\n", encoding="utf-8")
    schema = _base_schema(tmp_path)
    schema["dimensions"]["csv"]["orgunit"] = {
        "dimension_name": "OrgUnit",
        "csv_template": {"source": str(csv_file), "input_format": "indented_levels"},
    }
    report = validate_schema(schema, tmp_path)
    assert any("level_columns" in e for e in report.errors)


# ---------------------------------------------------------------------------
# cube validation
# ---------------------------------------------------------------------------

def _schema_with_dim(tmp_path, dim_name="Currency"):
    schema = _base_schema(tmp_path)
    schema["dimensions"]["elementlist"]["currency"] = {
        "dimension_name": dim_name,
        "elements": [],
        "edges": [],
        "attributes": [],
    }
    return schema

def test_valid_cube_passes(tmp_path):
    schema = _schema_with_dim(tmp_path)
    schema["cubes"]["Sales"] = {
        "name": "Sales",
        "dimensions": ["Currency"],
        "rules": ["SKIPCHECK;"],
    }
    report = validate_schema(schema, tmp_path)
    assert report.is_valid

def test_cube_missing_name_errors(tmp_path):
    schema = _base_schema(tmp_path)
    schema["cubes"]["Sales"] = {"dimensions": ["Currency"], "rules": []}
    report = validate_schema(schema, tmp_path)
    assert any("name" in e and "cube" in e.lower() for e in report.errors)

def test_cube_unknown_dimension_errors(tmp_path):
    schema = _base_schema(tmp_path)
    schema["cubes"]["Sales"] = {
        "name": "Sales",
        "dimensions": ["NonExistentDim"],
        "rules": [],
    }
    report = validate_schema(schema, tmp_path)
    assert any("NonExistentDim" in e for e in report.errors)

def test_cube_with_all_known_dimensions_passes(tmp_path):
    schema = _schema_with_dim(tmp_path, "Currency")
    schema["dimensions"]["elementlist"]["version"] = {
        "dimension_name": "Version",
        "elements": [],
        "edges": [],
        "attributes": [],
    }
    schema["cubes"]["FXRates"] = {
        "name": "FXRates",
        "dimensions": ["Currency", "Version"],
        "rules": [],
    }
    report = validate_schema(schema, tmp_path)
    assert report.is_valid


# ---------------------------------------------------------------------------
# dataset validation
# ---------------------------------------------------------------------------

def _schema_with_cube(tmp_path, cube_name="Sales"):
    schema = _base_schema(tmp_path)
    schema["cubes"][cube_name] = {
        "name": cube_name,
        "dimensions": [],
        "rules": [],
    }
    return schema

def test_valid_dataset_with_rows_passes(tmp_path):
    schema = _schema_with_cube(tmp_path)
    schema["datasets"]["sales_data"] = {
        "targetCube": "Sales",
        "rows": {"mdx": "{[Version].[Version].[Actual]}", "number_of_rows": 100},
        "data": {
            "Value": {
                "method": "function",
                "callable": "df_generator_for_dataset._random_number_based_on_statistic",
                "params": {"min_val": 0, "max_val": 100, "num_type": "int", "distribution": "uniform"},
            }
        },
    }
    report = validate_schema(schema, tmp_path)
    assert report.is_valid

def test_dataset_missing_target_cube_errors(tmp_path):
    schema = _base_schema(tmp_path)
    schema["datasets"]["sales_data"] = {
        "rows": {"mdx": "...", "number_of_rows": 1},
    }
    report = validate_schema(schema, tmp_path)
    assert any("targetCube" in e for e in report.errors)

def test_dataset_unknown_target_cube_errors(tmp_path):
    schema = _base_schema(tmp_path)
    schema["datasets"]["sales_data"] = {
        "targetCube": "NonExistentCube",
        "rows": {"mdx": "...", "number_of_rows": 1},
    }
    report = validate_schema(schema, tmp_path)
    assert any("NonExistentCube" in e for e in report.errors)

def test_dataset_element_attributes_cube_skips_cube_check(tmp_path):
    schema = _base_schema(tmp_path)
    schema["datasets"]["attr_data"] = {
        "targetCube": "}ElementAttributes_Currency",
        "rows": {"mdx": "...", "number_of_rows": 1},
    }
    report = validate_schema(schema, tmp_path)
    assert not any("}ElementAttributes" in e for e in report.errors)

def test_dataset_missing_rows_and_mdx_errors(tmp_path):
    schema = _schema_with_cube(tmp_path)
    schema["datasets"]["sales_data"] = {"targetCube": "Sales"}
    report = validate_schema(schema, tmp_path)
    assert any("rows" in e or "df_from_mdx" in e for e in report.errors)

def test_dataset_unresolvable_data_callable_errors(tmp_path):
    schema = _schema_with_cube(tmp_path)
    schema["datasets"]["sales_data"] = {
        "targetCube": "Sales",
        "rows": {"mdx": "...", "number_of_rows": 1},
        "data": {
            "Value": {
                "callable": "df_generator_for_dataset.this_does_not_exist",
            }
        },
    }
    report = validate_schema(schema, tmp_path)
    assert any("this_does_not_exist" in e for e in report.errors)


# ---------------------------------------------------------------------------
# full schema integration — multiple errors collected in one pass
# ---------------------------------------------------------------------------

def test_multiple_errors_collected_in_single_pass(tmp_path):
    schema = _base_schema(tmp_path)
    # bad dimension (no dimension_name)
    schema["dimensions"]["elementlist"]["bad_dim"] = {"elements": "not_a_list"}
    # bad cube (unknown dimension)
    schema["cubes"]["BadCube"] = {"name": "BadCube", "dimensions": ["Ghost"], "rules": []}
    # bad dataset (no targetCube, no rows)
    schema["datasets"]["bad_ds"] = {}

    report = validate_schema(schema, tmp_path)
    assert not report.is_valid
    assert len(report.errors) >= 3
