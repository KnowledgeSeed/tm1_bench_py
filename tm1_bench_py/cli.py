"""tm1-bench CLI — command-line interface for the TM1 Benchmark Model Generator.

Provides four subcommands:
  validate      — validate the schema without a TM1 connection
  build         — build the full model (dimensions, cubes, data)
  destroy       — delete all model objects from TM1
  generate-data — reload data into an existing model

All tm1_bench_py imports are kept inside functions (lazy) to avoid running the
package-level logging setup at module import time, which matters in test suites
that import cli symbols without wanting the side effects of __init__.py.
"""

import argparse
import sys
import os
from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    VALIDATION_FAILURE = 1
    CONNECTION_FAILURE = 2
    BUILD_ERROR = 3
    USAGE_ERROR = 4
    UNEXPECTED_ERROR = 10


__all__ = ["ExitCode", "main"]


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    import tm1_bench_py
    parser = argparse.ArgumentParser(
        prog="tm1-bench",
        description="TM1 Benchmark Model Generator — build, validate, and destroy TM1 OLAP models from YAML schemas.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {tm1_bench_py.__version__}")

    # Global flags
    parser.add_argument("--schema", default="./schema", metavar="PATH",
                        help="Root directory of the YAML schema tree (default: ./schema)")
    parser.add_argument("--env", default="", metavar="NAME",
                        help="Environment key within YAML env blocks (default: uses config.yaml default_yaml_env)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Log verbosity level (default: INFO)")
    parser.add_argument("--json-logs", action="store_true",
                        help="Emit structured JSON logs instead of plain text")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Suppress non-error output (exit code remains meaningful)")

    subparsers = parser.add_subparsers(dest="subcommand", required=True, title="subcommands")

    # validate
    p_validate = subparsers.add_parser(
        "validate",
        help="Validate the schema without connecting to TM1",
        description="Load and validate the YAML schema. Exits 0 if valid, 1 if errors found. No TM1 connection required.",
        epilog="Example:\n  tm1-bench validate --schema ./schema --env default",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_validate.add_argument("--strict", action="store_true",
                             help="Treat warnings as errors (exit 1 if any warning present)")

    # build
    p_build = subparsers.add_parser(
        "build",
        help="Build the full TM1 benchmark model (dimensions, cubes, data)",
        description="Validates the schema, connects to TM1, then creates dimensions, cubes, and loads data.",
        epilog="Examples:\n  tm1-bench build --schema ./schema --env default\n  tm1-bench build --schema ./schema --env staging --dry-run",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_build.add_argument("--config", default=None, metavar="PATH",
                          help="Path to config.ini TM1 connection file")
    p_build.add_argument("--connection", default=None, metavar="NAME",
                          help="Section name within config.ini (default: testbench)")
    p_build.add_argument("--dry-run", action="store_true",
                          help="Validate and print what would be built — no TM1 connection made")
    p_build.add_argument("--skip-data", action="store_true",
                          help="Build dimensions and cubes only, skip data loading")

    # destroy
    p_destroy = subparsers.add_parser(
        "destroy",
        help="Destroy the TM1 benchmark model (delete cubes and dimensions)",
        description="Connects to TM1 and deletes all cubes and dimensions defined in the schema.",
        epilog="Example:\n  tm1-bench destroy --schema ./schema --env default",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_destroy.add_argument("--config", default=None, metavar="PATH",
                            help="Path to config.ini TM1 connection file")
    p_destroy.add_argument("--connection", default=None, metavar="NAME",
                            help="Section name within config.ini (default: testbench)")
    p_destroy.add_argument("--force", action="store_true",
                            help="Suppress confirmation log line before destroying")

    # generate-data
    p_gendata = subparsers.add_parser(
        "generate-data",
        help="Load data into an existing TM1 model without rebuilding structure",
        description="Validates the schema and loads dataset(s) into an existing TM1 model.",
        epilog="Examples:\n  tm1-bench generate-data --schema ./schema --env default\n  tm1-bench generate-data --schema ./schema --dataset Sales --dataset Budget",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_gendata.add_argument("--config", default=None, metavar="PATH",
                            help="Path to config.ini TM1 connection file")
    p_gendata.add_argument("--connection", default=None, metavar="NAME",
                            help="Section name within config.ini (default: testbench)")
    p_gendata.add_argument("--dataset", action="append", metavar="NAME", dest="dataset",
                            help="Limit generation to this dataset name (repeatable)")

    return parser


# ---------------------------------------------------------------------------
# Logging wiring
# ---------------------------------------------------------------------------

def _configure_logging(args) -> None:
    """Configure log level and formatter based on CLI flags."""
    import logging
    from tm1_bench_py import basic_logger, exec_metrics_logger
    level = getattr(logging, args.log_level.upper(), logging.INFO)
    basic_logger.setLevel(level)
    exec_metrics_logger.setLevel(level)

    if args.json_logs:
        try:
            from tm1_bench_py.json_log_formatter import JSONLogFormatter
            formatter = JSONLogFormatter()
            for handler in basic_logger.handlers:
                handler.setFormatter(formatter)
        except ImportError:
            basic_logger.warning("json_log_formatter not available; using plain text logging.")

    if args.quiet:
        for handler in basic_logger.handlers[:]:
            # Remove console/stream handlers that write to stdout
            stream = getattr(handler, 'stream', None)
            if stream is not None and getattr(stream, 'name', '') in ('<stdout>',):
                basic_logger.removeHandler(handler)


def _resolve_config_ini(args) -> str:
    """Resolve config.ini path: --config flag > TM1_BENCH_CONFIG env var > ./config.ini."""
    if getattr(args, 'config', None):
        path = args.config
    else:
        path = os.environ.get('TM1_BENCH_CONFIG', 'config.ini')
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"TM1 config file not found: '{path}'. "
            "Use --config PATH or set TM1_BENCH_CONFIG environment variable."
        )
    return path


def _resolve_connection_name(args) -> str:
    """Resolve connection name: --connection flag > TM1_BENCH_CONNECTION env var > 'testbench'."""
    if getattr(args, 'connection', None):
        return args.connection
    return os.environ.get('TM1_BENCH_CONNECTION', 'testbench')


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def _load_schema(args) -> dict:
    """Load and return the schema dict using SchemaLoader."""
    from pathlib import Path
    from tm1_bench_py.tm1_bench import SchemaLoader
    schema_dir = str(Path(args.schema).resolve())
    return SchemaLoader(schema_dir, args.env).load_schema()


def _run_validation(schema: dict, args) -> "ValidationReport":
    """Run schema validation and log the report. Returns the ValidationReport."""
    from pathlib import Path
    from tm1_bench_py import schema_validator
    project_root = Path(args.schema).resolve().parent
    report = schema_validator.validate_schema(schema, project_root)
    report.log_report()
    return report


def _print_build_plan(schema: dict) -> None:
    """Print a human-readable summary of what would be built (dry-run output)."""
    dims = schema.get('dimensions', {})
    total_dims = sum(len(v) for v in dims.values())
    print(f"\nBuild plan:")
    print(f"  Dimensions ({total_dims}):")
    for dim_type, dim_dict in dims.items():
        if dim_dict:
            names = [d.get('dimension_name', k) for k, d in dim_dict.items()]
            print(f"    [{dim_type}] {', '.join(names)}")
    cubes = schema.get('cubes', {})
    print(f"  Cubes ({len(cubes)}):")
    for cube_key, cube_def in cubes.items():
        cube_name = cube_def.get('name', cube_key)
        cube_dims_list = cube_def.get('dimensions', [])
        print(f"    - {cube_name} (dims: {', '.join(cube_dims_list)})")
    datasets = schema.get('datasets', {})
    print(f"  Datasets ({len(datasets)}):")
    for ds_key, ds_def in datasets.items():
        target = ds_def.get('targetCube', '?')
        print(f"    - {ds_key} -> {target}")
    print()


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def _cmd_validate(args) -> "ExitCode":
    from tm1_bench_py import basic_logger
    schema = _load_schema(args)
    report = _run_validation(schema, args)
    if not report.is_valid:
        return ExitCode.VALIDATION_FAILURE
    if args.strict and report.warnings:
        basic_logger.warning("--strict: %d warning(s) treated as errors.", len(report.warnings))
        return ExitCode.VALIDATION_FAILURE
    return ExitCode.SUCCESS


def _cmd_build(args) -> "ExitCode":
    from tm1_bench_py import basic_logger
    from tm1_bench_py import utility
    from tm1_bench_py import tm1_bench

    schema = _load_schema(args)
    report = _run_validation(schema, args)
    if not report.is_valid:
        return ExitCode.VALIDATION_FAILURE

    if args.dry_run:
        _print_build_plan(schema)
        return ExitCode.SUCCESS

    system_defaults = schema['config'].get('df_to_cube_default_kwargs', {})
    config_path = _resolve_config_ini(args)
    connection = _resolve_connection_name(args)

    basic_logger.info("tm1-bench build · env=%s · connection=%s", args.env, connection)

    tm1 = utility.tm1_connection(config_path, connection)
    try:
        tm1_bench.create_dimensions(tm1, schema)
        tm1_bench.create_cubes(tm1, schema)
        if not args.skip_data:
            tm1_bench.generate_data(tm1, schema, system_defaults)
    finally:
        tm1.logout()

    return ExitCode.SUCCESS


def _cmd_destroy(args) -> "ExitCode":
    from tm1_bench_py import basic_logger
    from tm1_bench_py import utility
    from tm1_bench_py import tm1_bench

    schema = _load_schema(args)

    if not args.force:
        basic_logger.info(
            "tm1-bench destroy · env=%s · will delete %d cube(s) and %d dimension(s)",
            args.env,
            len(schema.get('cubes', {})),
            sum(len(v) for v in schema.get('dimensions', {}).values()),
        )

    config_path = _resolve_config_ini(args)
    connection = _resolve_connection_name(args)

    tm1 = utility.tm1_connection(config_path, connection)
    try:
        tm1_bench.delete_cubes(tm1, schema)
        tm1_bench.delete_dimensions(tm1, schema)
    finally:
        tm1.logout()

    return ExitCode.SUCCESS


def _cmd_generate_data(args) -> "ExitCode":
    from tm1_bench_py import basic_logger
    from tm1_bench_py import utility
    from tm1_bench_py import tm1_bench

    schema = _load_schema(args)
    report = _run_validation(schema, args)
    if not report.is_valid:
        return ExitCode.VALIDATION_FAILURE

    if args.dataset:
        requested = set(args.dataset)
        available = set(schema['datasets'].keys())
        missing = requested - available
        for m in sorted(missing):
            basic_logger.warning("Dataset '%s' not found in schema — skipping.", m)
        filtered = {k: v for k, v in schema['datasets'].items() if k in requested}
        schema = {**schema, 'datasets': filtered}

    system_defaults = schema['config'].get('df_to_cube_default_kwargs', {})
    config_path = _resolve_config_ini(args)
    connection = _resolve_connection_name(args)

    tm1 = utility.tm1_connection(config_path, connection)
    try:
        tm1_bench.generate_data(tm1, schema, system_defaults)
    finally:
        tm1.logout()

    return ExitCode.SUCCESS


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> None:
    """Entry point for the tm1-bench CLI tool."""
    # Intercept argparse's SystemExit(2) for usage errors before parse
    parser = _build_parser()

    # Parse — on bad args argparse calls sys.exit(2); let it propagate
    # but we remap it to USAGE_ERROR in the outer except below
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code if exc.code != 2 else int(ExitCode.USAGE_ERROR)
        sys.exit(code)

    _configure_logging(args)

    import tm1_bench_py
    from tm1_bench_py import basic_logger
    basic_logger.info(
        "tm1-bench %s · %s · env=%s · schema=%s",
        tm1_bench_py.__version__,
        args.subcommand,
        args.env,
        args.schema,
    )

    _DISPATCH = {
        'validate': _cmd_validate,
        'build': _cmd_build,
        'destroy': _cmd_destroy,
        'generate-data': _cmd_generate_data,
    }

    exit_code = ExitCode.UNEXPECTED_ERROR
    try:
        handler = _DISPATCH[args.subcommand]
        exit_code = handler(args)
    except ValueError as exc:
        basic_logger.error("Validation failure: %s", exc)
        exit_code = ExitCode.VALIDATION_FAILURE
    except FileNotFoundError as exc:
        basic_logger.error("Connection setup failure: %s", exc)
        exit_code = ExitCode.CONNECTION_FAILURE
    except Exception as exc:  # noqa: BLE001
        # Try to distinguish TM1 connection errors from build logic errors
        exc_module = type(exc).__module__ or ''
        exc_msg = str(exc).lower()
        if 'tm1py' in exc_module.lower() or 'connection' in exc_msg or 'connect' in exc_msg:
            basic_logger.error("TM1 connection error: %s", exc)
            exit_code = ExitCode.CONNECTION_FAILURE
        else:
            basic_logger.exception("Build error during '%s'", args.subcommand)
            exit_code = ExitCode.BUILD_ERROR

    sys.exit(int(exit_code))
