import shutil
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tm1_bench_py.tm1_bedrock_executor import (
    load_csv_template_dataframe,
    execute_dimension_build_with_bedrock,
    _apply_mapping_steps,
    _apply_attribute_renames,
    _resolve_bedrock_kwargs,
)
from tm1_bench_py.tm1_bench import SchemaLoader


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _tmp() -> Path:
    base = Path(__file__).parent / "_runtime_tmp"
    base.mkdir(exist_ok=True)
    d = base / str(uuid.uuid4())
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# load_csv_template_dataframe
# ---------------------------------------------------------------------------

def test_load_csv_uses_project_root_for_relative_source():
    tmp = _tmp()
    csv_dir = tmp / "schema" / "dimensions" / "csv_sources"
    csv_dir.mkdir(parents=True)
    csv_path = csv_dir / "org.csv"
    csv_path.write_text("code,parent_code\nA,\n", encoding="utf-8")

    df = load_csv_template_dataframe(
        csv_template={"source": "schema/dimensions/csv_sources/org.csv"},
        project_root=tmp,
    )

    assert list(df.columns) == ["code", "parent_code"]
    assert df.iloc[0]["code"] == "A"
    shutil.rmtree(tmp)


def test_load_csv_raises_for_missing_source_key():
    with pytest.raises(ValueError, match="csv_template.source is required"):
        load_csv_template_dataframe(csv_template={}, project_root="/any")


def test_load_csv_raises_for_missing_file():
    with pytest.raises(FileNotFoundError):
        load_csv_template_dataframe(
            csv_template={"source": "nonexistent.csv"},
            project_root="/tmp",
        )


# ---------------------------------------------------------------------------
# _apply_mapping_steps
# ---------------------------------------------------------------------------

def test_mapping_steps_replace_values():
    df = pd.DataFrame({"parent": ["TOTAL", "A", "TOTAL"]})
    result = _apply_mapping_steps(df, [{"method": "replace", "columns": ["parent"], "values": {"TOTAL": "Root"}}])
    assert list(result["parent"]) == ["Root", "A", "Root"]


def test_mapping_steps_unknown_method_skips():
    df = pd.DataFrame({"col": ["x"]})
    result = _apply_mapping_steps(df, [{"method": "unknown_op", "columns": ["col"], "values": {}}])
    assert list(result["col"]) == ["x"]


# ---------------------------------------------------------------------------
# _apply_attribute_renames
# ---------------------------------------------------------------------------

def test_attribute_renames_applied():
    df = pd.DataFrame({"description": ["x"], "country": ["DE"]})
    result = _apply_attribute_renames(
        df,
        [{"source": "description", "target": "Description:s"}, {"source": "country", "target": "Country:s"}],
    )
    assert "Description:s" in result.columns
    assert "Country:s" in result.columns
    assert "description" not in result.columns


def test_attribute_renames_skips_missing_source_column():
    df = pd.DataFrame({"other": [1]})
    result = _apply_attribute_renames(df, [{"source": "description", "target": "Description:s"}])
    assert "Description:s" not in result.columns
    assert "other" in result.columns


# ---------------------------------------------------------------------------
# _resolve_bedrock_kwargs
# ---------------------------------------------------------------------------

def test_resolve_kwargs_parent_child():
    template = {
        "input_format": "parent_child",
        "element_column": "code",
        "parent_column": "parent_code",
        "element_type_column": "element_type",
    }
    kwargs = _resolve_bedrock_kwargs(template)
    assert kwargs["input_format"] == "parent_child"
    assert kwargs["child_column"] == "code"
    assert kwargs["parent_column"] == "parent_code"
    assert kwargs["type_column"] == "element_type"


def test_resolve_kwargs_indented_levels():
    template = {
        "input_format": "indented_levels",
        "level_columns": ["L1", "L2", "L3"],
    }
    kwargs = _resolve_bedrock_kwargs(template)
    assert kwargs["input_format"] == "indented_levels"
    assert kwargs["level_columns"] == ["L1", "L2", "L3"]


def test_resolve_kwargs_level_format_requires_level_columns():
    with pytest.raises(ValueError, match="level_columns is required"):
        _resolve_bedrock_kwargs({"input_format": "indented_levels"})


def test_resolve_kwargs_defaults_to_parent_child():
    kwargs = _resolve_bedrock_kwargs({})
    assert kwargs["input_format"] == "parent_child"


# ---------------------------------------------------------------------------
# execute_dimension_build_with_bedrock — import error
# ---------------------------------------------------------------------------

def test_execute_raises_import_error_when_bedrock_missing(tmp_path):
    csv_path = tmp_path / "dim.csv"
    csv_path.write_text("code,parent_code\nA,\n", encoding="utf-8")

    with patch("tm1_bench_py.tm1_bedrock_executor.importlib.import_module", side_effect=ImportError("no module")):
        with pytest.raises(ImportError, match="tm1_bedrock_py is required"):
            execute_dimension_build_with_bedrock(
                tm1=MagicMock(),
                dimension_name="Test",
                csv_template={"source": str(csv_path)},
                project_root=tmp_path,
            )


# ---------------------------------------------------------------------------
# execute_dimension_build_with_bedrock — happy path, parent_child
# ---------------------------------------------------------------------------

def test_execute_calls_bedrock_dimension_builder_parent_child(tmp_path):
    csv_path = tmp_path / "dim.csv"
    csv_path.write_text("code,parent_code,element_type\nRoot,,Consolidated\nA,Root,Numeric\n", encoding="utf-8")

    captured = {}

    class FakeBedrock:
        @staticmethod
        def dimension_builder(**kwargs):
            captured.update(kwargs)

    with patch("tm1_bench_py.tm1_bedrock_executor.importlib.import_module", return_value=FakeBedrock()):
        execute_dimension_build_with_bedrock(
            tm1=MagicMock(),
            dimension_name="MyDim",
            csv_template={
                "source": str(csv_path),
                "input_format": "parent_child",
                "element_column": "code",
                "parent_column": "parent_code",
                "element_type_column": "element_type",
                "build_strategy": "rebuild",
            },
            project_root=tmp_path,
        )

    assert captured["dimension_name"] == "MyDim"
    assert captured["input_format"] == "parent_child"
    assert captured["build_strategy"] == "rebuild"
    assert captured["child_column"] == "code"
    assert isinstance(captured["raw_input_df"], pd.DataFrame)


# ---------------------------------------------------------------------------
# execute_dimension_build_with_bedrock — happy path, indented_levels
# ---------------------------------------------------------------------------

def test_execute_calls_bedrock_dimension_builder_indented_levels(tmp_path):
    csv_path = tmp_path / "dim.csv"
    csv_path.write_text("L1,L2\nRoot,\n,Child1\n", encoding="utf-8")

    captured = {}

    class FakeBedrock:
        @staticmethod
        def dimension_builder(**kwargs):
            captured.update(kwargs)

    with patch("tm1_bench_py.tm1_bedrock_executor.importlib.import_module", return_value=FakeBedrock()):
        execute_dimension_build_with_bedrock(
            tm1=MagicMock(),
            dimension_name="LevelDim",
            csv_template={
                "source": str(csv_path),
                "input_format": "indented_levels",
                "level_columns": ["L1", "L2"],
            },
            project_root=tmp_path,
        )

    assert captured["input_format"] == "indented_levels"
    assert captured["level_columns"] == ["L1", "L2"]


# ---------------------------------------------------------------------------
# execute_dimension_build_with_bedrock — mapping_steps and attribute renames applied
# ---------------------------------------------------------------------------

def test_execute_applies_mapping_and_renames_before_bedrock(tmp_path):
    csv_path = tmp_path / "dim.csv"
    csv_path.write_text("code,parent_code,element_type,description\nRoot,TOTAL,Consolidated,Root desc\n", encoding="utf-8")

    captured = {}

    class FakeBedrock:
        @staticmethod
        def dimension_builder(**kwargs):
            captured.update(kwargs)

    with patch("tm1_bench_py.tm1_bedrock_executor.importlib.import_module", return_value=FakeBedrock()):
        execute_dimension_build_with_bedrock(
            tm1=MagicMock(),
            dimension_name="MappedDim",
            csv_template={
                "source": str(csv_path),
                "input_format": "parent_child",
                "element_column": "code",
                "parent_column": "parent_code",
                "mapping_steps": [{"method": "replace", "columns": ["parent_code"], "values": {"TOTAL": "All"}}],
                "attributes": [{"source": "description", "target": "Description:s"}],
            },
            project_root=tmp_path,
        )

    df: pd.DataFrame = captured["raw_input_df"]
    assert df.iloc[0]["parent_code"] == "All"
    assert "Description:s" in df.columns
    assert "description" not in df.columns


# ---------------------------------------------------------------------------
# SchemaLoader — reads csv dimension type
# ---------------------------------------------------------------------------

def test_schema_loader_reads_csv_dimension_type():
    tmp = _tmp()
    schema_dir = tmp / "schema"
    (schema_dir / "dimensions" / "csv").mkdir(parents=True)
    (schema_dir / "cubes").mkdir()
    (schema_dir / "datasets").mkdir()

    (schema_dir / "config.yaml").write_text(
        "default_yaml_env: \"default\"\npaths:\n"
        "  dimensions_elementlist: 'dimensions/elementlist'\n"
        "  dimensions_df_templates: 'dimensions/df_templates'\n"
        "  dimensions_custom: 'dimensions/custom'\n"
        "  dimensions_csv: 'dimensions/csv'\n"
        "  cubes: 'cubes'\n"
        "  datasets: 'datasets'\n"
        "  variables: '.'\n",
        encoding="utf-8",
    )
    (schema_dir / "variables.yaml").write_text("{}", encoding="utf-8")
    (schema_dir / "schema.yaml").write_text(
        "import:\n  dimensions:\n    csv:\n      - orgunit_csv\n  cubes: []\n  datasets: []\n  variables: variables\n",
        encoding="utf-8",
    )
    (schema_dir / "dimensions" / "csv" / "orgunit_csv.yaml").write_text(
        "default:\n  dimension_name: \"OrgUnit\"\n  csv_template:\n    source: \"schema/dimensions/csv_sources/org.csv\"\n    element_column: \"code\"\n",
        encoding="utf-8",
    )

    loader = SchemaLoader(str(schema_dir), "default")
    schema = loader.load_schema()

    assert "orgunit_csv" in schema["dimensions"]["csv"]
    assert schema["dimensions"]["csv"]["orgunit_csv"]["dimension_name"] == "OrgUnit"
    shutil.rmtree(tmp)


def test_schema_loader_falls_back_to_default_env_with_warning():
    tmp = _tmp()
    schema_dir = tmp / "schema"
    (schema_dir / "dimensions" / "csv").mkdir(parents=True)
    (schema_dir / "cubes").mkdir()
    (schema_dir / "datasets").mkdir()

    (schema_dir / "config.yaml").write_text(
        "default_yaml_env: \"default\"\npaths:\n"
        "  dimensions_csv: 'dimensions/csv'\n"
        "  dimensions_elementlist: 'dimensions/elementlist'\n"
        "  dimensions_df_templates: 'dimensions/df_templates'\n"
        "  dimensions_custom: 'dimensions/custom'\n"
        "  cubes: 'cubes'\n  datasets: 'datasets'\n  variables: '.'\n",
        encoding="utf-8",
    )
    (schema_dir / "variables.yaml").write_text("{}", encoding="utf-8")
    (schema_dir / "schema.yaml").write_text(
        "import:\n  dimensions:\n    csv:\n      - orgunit_csv\n  cubes: []\n  datasets: []\n  variables: variables\n",
        encoding="utf-8",
    )
    # YAML has only 'default' block — no 'ksAcademy' block
    (schema_dir / "dimensions" / "csv" / "orgunit_csv.yaml").write_text(
        "default:\n  dimension_name: \"OrgUnit\"\n  csv_template:\n    source: \"org.csv\"\n    element_column: \"code\"\n",
        encoding="utf-8",
    )

    loader = SchemaLoader(str(schema_dir), "ksAcademy")
    schema = loader.load_schema()

    # Falls back to default — dimension is present, not skipped
    assert "orgunit_csv" in schema["dimensions"]["csv"]
    assert schema["dimensions"]["csv"]["orgunit_csv"]["dimension_name"] == "OrgUnit"
    shutil.rmtree(tmp)


def test_schema_loader_skips_when_env_and_default_both_missing():
    tmp = _tmp()
    schema_dir = tmp / "schema"
    (schema_dir / "dimensions" / "csv").mkdir(parents=True)
    (schema_dir / "cubes").mkdir()
    (schema_dir / "datasets").mkdir()

    (schema_dir / "config.yaml").write_text(
        "default_yaml_env: \"default\"\npaths:\n"
        "  dimensions_csv: 'dimensions/csv'\n"
        "  dimensions_elementlist: 'dimensions/elementlist'\n"
        "  dimensions_df_templates: 'dimensions/df_templates'\n"
        "  dimensions_custom: 'dimensions/custom'\n"
        "  cubes: 'cubes'\n  datasets: 'datasets'\n  variables: '.'\n",
        encoding="utf-8",
    )
    (schema_dir / "variables.yaml").write_text("{}", encoding="utf-8")
    (schema_dir / "schema.yaml").write_text(
        "import:\n  dimensions:\n    csv:\n      - orgunit_csv\n  cubes: []\n  datasets: []\n  variables: variables\n",
        encoding="utf-8",
    )
    # YAML has only 'production' block — neither requested env nor 'default' exists
    (schema_dir / "dimensions" / "csv" / "orgunit_csv.yaml").write_text(
        "production:\n  dimension_name: \"OrgUnit\"\n  csv_template:\n    source: \"org.csv\"\n    element_column: \"code\"\n",
        encoding="utf-8",
    )

    loader = SchemaLoader(str(schema_dir), "ksAcademy")
    schema = loader.load_schema()

    # No default to fall back to — dimension is skipped
    assert "orgunit_csv" not in schema["dimensions"]["csv"]
    shutil.rmtree(tmp)
