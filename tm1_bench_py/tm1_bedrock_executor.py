import importlib
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from tm1_bench_py import basic_logger


def load_csv_template_dataframe(csv_template: Dict[str, Any], project_root: str | Path) -> pd.DataFrame:
    """Load the CSV source declared in a csv dimension template."""
    source = csv_template.get("source")
    if not source:
        raise ValueError("csv_template.source is required")

    source_path = Path(source)
    if not source_path.is_absolute():
        source_path = Path(project_root) / source_path

    if not source_path.exists():
        raise FileNotFoundError(f"CSV source file not found: {source_path}")

    return pd.read_csv(source_path)


def _apply_mapping_steps(df: pd.DataFrame, mapping_steps: List[Dict[str, Any]]) -> pd.DataFrame:
    """Apply value replacement steps declared in csv_template.mapping_steps."""
    for step in mapping_steps:
        if step.get("method") != "replace":
            basic_logger.warning("Unsupported mapping_step method '%s', skipping.", step.get("method"))
            continue
        columns = step.get("columns", [])
        values = step.get("values", {})
        for col in columns:
            if col in df.columns:
                df[col] = df[col].replace(values)
    return df


def _apply_attribute_renames(df: pd.DataFrame, attributes: List[Dict[str, str]]) -> pd.DataFrame:
    """Rename attribute columns from source names to colon-notation target names expected by tm1_bedrock_py.

    Example: {"source": "description", "target": "Description:s"} renames
    the 'description' column to 'Description:s' so the bedrock library treats
    it as a String attribute.
    """
    rename_map = {
        attr["source"]: attr["target"]
        for attr in attributes
        if "source" in attr and "target" in attr and attr["source"] in df.columns
    }
    return df.rename(columns=rename_map)


def _resolve_bedrock_kwargs(csv_template: Dict[str, Any]) -> Dict[str, Any]:
    """Translate csv_template keys to tm1_bedrock_py.bedrock.dimension_builder kwargs."""
    input_format = csv_template.get("input_format", "parent_child")
    kwargs: Dict[str, Any] = {"input_format": input_format}

    if input_format == "parent_child":
        if "parent_column" in csv_template:
            kwargs["parent_column"] = csv_template["parent_column"]
        if "element_column" in csv_template:
            kwargs["child_column"] = csv_template["element_column"]
        if "element_type_column" in csv_template:
            kwargs["type_column"] = csv_template["element_type_column"]
        if "weight_column" in csv_template:
            kwargs["weight_column"] = csv_template["weight_column"]
    else:
        # indented_levels or filled_levels — requires level_columns list
        level_columns = csv_template.get("level_columns")
        if not level_columns:
            raise ValueError(
                f"csv_template.level_columns is required for input_format='{input_format}'"
            )
        kwargs["level_columns"] = level_columns
        if "element_type_column" in csv_template:
            kwargs["type_column"] = csv_template["element_type_column"]
        if "weight_column" in csv_template:
            kwargs["weight_column"] = csv_template["weight_column"]

    return kwargs


def execute_dimension_build_with_bedrock(
    tm1,
    dimension_name: str,
    csv_template: Dict[str, Any],
    project_root: str | Path,
) -> None:
    """Build a csv-backed TM1 dimension via tm1_bedrock_py.bedrock.dimension_builder.

    Supports parent_child, indented_levels, and filled_levels input formats.
    Applies mapping_steps and attribute column renames before delegating to bedrock.
    """
    dataframe = load_csv_template_dataframe(csv_template=csv_template, project_root=project_root)

    mapping_steps = csv_template.get("mapping_steps", [])
    if mapping_steps:
        dataframe = _apply_mapping_steps(dataframe, mapping_steps)

    attributes = csv_template.get("attributes", [])
    if attributes:
        dataframe = _apply_attribute_renames(dataframe, attributes)

    try:
        bedrock = importlib.import_module("tm1_bedrock_py.bedrock")
    except ImportError as exc:
        raise ImportError(
            "tm1_bedrock_py is required for csv dimension execution. "
            "Install it before building csv-backed dimensions."
        ) from exc

    build_strategy = csv_template.get("build_strategy", "rebuild")
    bedrock_kwargs = _resolve_bedrock_kwargs(csv_template)

    basic_logger.info(
        "Building csv dimension '%s' via tm1_bedrock_py (format=%s, strategy=%s)",
        dimension_name, bedrock_kwargs["input_format"], build_strategy,
    )

    bedrock.dimension_builder(
        dimension_name=dimension_name,
        build_strategy=build_strategy,
        tm1_service=tm1,
        raw_input_df=dataframe,
        **bedrock_kwargs,
    )
