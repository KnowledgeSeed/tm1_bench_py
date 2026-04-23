import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from tm1_bench_py import basic_logger

_VALID_CSV_INPUT_FORMATS = {"parent_child", "indented_levels", "filled_levels"}
_VALID_BUILD_STRATEGIES = {"rebuild", "safe_rebuild", "safe_rebuild_unwind", "update"}
_REQUIRED_DF_TO_CUBE_KWARGS = {"async_write", "slice_size_of_dataframe", "use_blob", "use_ti"}


@dataclass
class ValidationReport:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def log_report(self) -> None:
        for msg in self.warnings:
            basic_logger.warning("[SCHEMA] %s", msg)
        for msg in self.errors:
            basic_logger.error("[SCHEMA] %s", msg)
        if self.is_valid:
            if self.warnings:
                basic_logger.info(
                    "[SCHEMA] Validation passed with %d warning(s).", len(self.warnings)
                )
            else:
                basic_logger.info("[SCHEMA] Validation passed — schema is ready to build.")
        else:
            basic_logger.error(
                "[SCHEMA] Validation FAILED — %d error(s), %d warning(s). Build will not proceed.",
                len(self.errors),
                len(self.warnings),
            )


def validate_schema(schema: Dict[str, Any], project_root: str | Path) -> ValidationReport:
    """Validate a fully loaded schema dict before any TM1 connection is made.

    Collects all errors and warnings rather than stopping at the first problem,
    so the user sees the complete picture in one pass.
    """
    report = ValidationReport()
    project_root = Path(project_root)

    _validate_config(schema.get("config", {}), report)

    known_dim_names = _collect_known_dimension_names(schema)
    _validate_dimensions(schema.get("dimensions", {}), project_root, report)
    _validate_cubes(schema.get("cubes", {}), known_dim_names, report)
    _validate_datasets(schema.get("datasets", {}), schema.get("cubes", {}), report)

    return report


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

def _validate_config(config: Dict[str, Any], report: ValidationReport) -> None:
    if not config:
        report.error("config.yaml could not be loaded or is empty.")
        return

    kwargs = config.get("df_to_cube_default_kwargs")
    if kwargs is None:
        report.warn("config.yaml is missing 'df_to_cube_default_kwargs' — defaults will be used.")
    else:
        missing = _REQUIRED_DF_TO_CUBE_KWARGS - set(kwargs.keys())
        for key in sorted(missing):
            report.warn(f"config.df_to_cube_default_kwargs is missing key '{key}'.")


# ---------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------

def _collect_known_dimension_names(schema: Dict[str, Any]) -> set:
    names = set()
    for dim_type, dims in schema.get("dimensions", {}).items():
        for dim_key, dim_def in dims.items():
            name = dim_def.get("dimension_name")
            if name:
                names.add(name)
    return names


def _validate_dimensions(dimensions: Dict[str, Any], project_root: Path, report: ValidationReport) -> None:
    validators = {
        "elementlist": _validate_elementlist_dim,
        "df_templates": _validate_df_template_dim,
        "custom": _validate_custom_dim,
        "csv": _validate_csv_dim,
    }
    for dim_type, dims in dimensions.items():
        validator = validators.get(dim_type)
        for dim_key, dim_def in dims.items():
            ctx = f"dimension[{dim_type}][{dim_key}]"
            if not dim_def.get("dimension_name"):
                report.error(f"{ctx}: missing required key 'dimension_name'.")
            if validator:
                validator(dim_key, dim_def, project_root, report)


def _validate_elementlist_dim(
    dim_key: str, dim_def: Dict, project_root: Path, report: ValidationReport
) -> None:
    ctx = f"dimension[elementlist][{dim_key}]"
    if not isinstance(dim_def.get("elements"), list):
        report.error(f"{ctx}: 'elements' must be a list.")
    if "edges" not in dim_def:
        report.warn(f"{ctx}: 'edges' key is missing — assuming no parent-child relationships.")
    if "attributes" not in dim_def:
        report.warn(f"{ctx}: 'attributes' key is missing — dimension will have no attributes.")


def _validate_df_template_dim(
    dim_key: str, dim_def: Dict, project_root: Path, report: ValidationReport
) -> None:
    ctx = f"dimension[df_templates][{dim_key}]"
    df_template = dim_def.get("df_template")
    if not df_template:
        report.error(f"{ctx}: missing required key 'df_template'.")
        return
    if "elements" not in df_template:
        report.error(f"{ctx}: df_template is missing 'elements'.")
    if "levels" not in df_template:
        report.error(f"{ctx}: df_template is missing 'levels'.")


def _validate_custom_dim(
    dim_key: str, dim_def: Dict, project_root: Path, report: ValidationReport
) -> None:
    ctx = f"dimension[custom][{dim_key}]"
    callable_str = dim_def.get("callable")
    if not callable_str:
        report.error(f"{ctx}: missing required key 'callable'.")
        return
    _validate_callable(callable_str, ctx, report)
    if "kwargs" not in dim_def:
        report.warn(f"{ctx}: 'kwargs' key is missing — callable will be invoked with no arguments.")


def _validate_csv_dim(
    dim_key: str, dim_def: Dict, project_root: Path, report: ValidationReport
) -> None:
    ctx = f"dimension[csv][{dim_key}]"
    csv_template = dim_def.get("csv_template")
    if not csv_template:
        report.error(f"{ctx}: missing required key 'csv_template'.")
        return

    source = csv_template.get("source")
    if not source:
        report.error(f"{ctx}: csv_template is missing 'source'.")
    else:
        source_path = Path(source) if Path(source).is_absolute() else project_root / source
        if not source_path.exists():
            report.error(f"{ctx}: CSV source file not found: {source_path}")

    input_format = csv_template.get("input_format", "parent_child")
    if input_format not in _VALID_CSV_INPUT_FORMATS:
        report.error(
            f"{ctx}: invalid csv_template.input_format '{input_format}'. "
            f"Must be one of {sorted(_VALID_CSV_INPUT_FORMATS)}."
        )

    build_strategy = csv_template.get("build_strategy", "rebuild")
    if build_strategy not in _VALID_BUILD_STRATEGIES:
        report.error(
            f"{ctx}: invalid csv_template.build_strategy '{build_strategy}'. "
            f"Must be one of {sorted(_VALID_BUILD_STRATEGIES)}."
        )

    if input_format == "parent_child":
        if not csv_template.get("element_column"):
            report.warn(f"{ctx}: csv_template.element_column not set — bedrock will use default child column mapping.")
        if not csv_template.get("parent_column"):
            report.warn(f"{ctx}: csv_template.parent_column not set — bedrock will use default parent column mapping.")
    else:
        if not csv_template.get("level_columns"):
            report.error(
                f"{ctx}: csv_template.level_columns is required for input_format='{input_format}'."
            )


# ---------------------------------------------------------------------------
# cubes
# ---------------------------------------------------------------------------

def _validate_cubes(
    cubes: Dict[str, Any], known_dim_names: set, report: ValidationReport
) -> None:
    for cube_key, cube_def in cubes.items():
        ctx = f"cube[{cube_key}]"
        if not cube_def.get("name"):
            report.error(f"{ctx}: missing required key 'name'.")
        if not isinstance(cube_def.get("dimensions"), list):
            report.error(f"{ctx}: 'dimensions' must be a list.")
        else:
            for dim_name in cube_def["dimensions"]:
                if dim_name not in known_dim_names:
                    report.error(
                        f"{ctx}: dimension '{dim_name}' is not defined in any loaded dimension. "
                        "Check spelling or environment."
                    )
        if not isinstance(cube_def.get("rules"), list):
            report.warn(f"{ctx}: 'rules' key is missing or not a list — cube will have no rules.")


# ---------------------------------------------------------------------------
# datasets
# ---------------------------------------------------------------------------

def _validate_datasets(
    datasets: Dict[str, Any], cubes: Dict[str, Any], report: ValidationReport
) -> None:
    known_cube_names = {cube_def.get("name") for cube_def in cubes.values() if cube_def.get("name")}

    for dataset_key, dataset_def in datasets.items():
        ctx = f"dataset[{dataset_key}]"
        target_cube = dataset_def.get("targetCube")
        if not target_cube:
            report.error(f"{ctx}: missing required key 'targetCube'.")
        elif not target_cube.startswith("}") and target_cube not in known_cube_names:
            report.error(
                f"{ctx}: targetCube '{target_cube}' is not defined in loaded cubes. "
                "Check spelling or environment."
            )

        has_rows = bool(dataset_def.get("rows"))
        has_mdx = bool(dataset_def.get("df_from_mdx"))
        if not has_rows and not has_mdx:
            report.error(f"{ctx}: must define either 'rows' or 'df_from_mdx'.")

        data = dataset_def.get("data")
        if data and isinstance(data, dict):
            if has_mdx:
                callable_str = data.get("callable")
                if callable_str:
                    _validate_callable(callable_str, f"{ctx}.data.callable", report)
            else:
                for col_name, col_def in data.items():
                    if not isinstance(col_def, dict):
                        continue
                    callable_str = col_def.get("callable")
                    if callable_str:
                        _validate_callable(callable_str, f"{ctx}.data[{col_name}].callable", report)


# ---------------------------------------------------------------------------
# callable resolution
# ---------------------------------------------------------------------------

def _validate_callable(callable_str: str, ctx: str, report: ValidationReport) -> None:
    try:
        module_name, func_name = callable_str.rsplit(".", 1)
        module = importlib.import_module("." + module_name, "tm1_bench_py")
        if not hasattr(module, func_name):
            report.error(f"{ctx}: callable '{callable_str}' — function '{func_name}' not found in module '{module_name}'.")
    except (ImportError, ModuleNotFoundError) as exc:
        report.error(f"{ctx}: callable '{callable_str}' — module could not be imported: {exc}")
    except ValueError:
        report.error(f"{ctx}: callable '{callable_str}' — expected format 'module.function'.")
