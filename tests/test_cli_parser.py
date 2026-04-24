"""Tests for tm1_bench_py.cli argument parser."""
import sys
import pytest
from unittest.mock import patch


def test_validate_subcommand_parsed():
    from tm1_bench_py.cli import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["--schema", "./my_schema", "--env", "prod", "validate"])
    assert args.subcommand == "validate"
    assert args.schema == "./my_schema"
    assert args.env == "prod"
    assert args.strict is False


def test_validate_strict_flag():
    from tm1_bench_py.cli import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["validate", "--strict"])
    assert args.strict is True


def test_build_subcommand_defaults():
    from tm1_bench_py.cli import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["build"])
    assert args.subcommand == "build"
    assert args.schema == "./schema"
    assert args.env == ""
    assert args.dry_run is False
    assert args.skip_data is False
    assert args.config is None
    assert args.connection is None


def test_build_dry_run_flag():
    from tm1_bench_py.cli import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["build", "--dry-run"])
    assert args.dry_run is True


def test_build_skip_data_flag():
    from tm1_bench_py.cli import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["build", "--skip-data"])
    assert args.skip_data is True


def test_destroy_subcommand_parsed():
    from tm1_bench_py.cli import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["destroy", "--connection", "prod_conn"])
    assert args.subcommand == "destroy"
    assert args.connection == "prod_conn"
    assert args.force is False


def test_generate_data_dataset_flag_repeatable():
    from tm1_bench_py.cli import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["generate-data", "--dataset", "Sales", "--dataset", "Budget"])
    assert args.subcommand == "generate-data"
    assert args.dataset == ["Sales", "Budget"]


def test_generate_data_no_dataset_flag_is_none():
    from tm1_bench_py.cli import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["generate-data"])
    assert args.dataset is None


def test_global_log_level_default():
    from tm1_bench_py.cli import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["validate"])
    assert args.log_level == "INFO"


def test_global_json_logs_flag():
    from tm1_bench_py.cli import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["--json-logs", "validate"])
    assert args.json_logs is True


def test_global_quiet_flag():
    from tm1_bench_py.cli import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["-q", "validate"])
    assert args.quiet is True


def test_invalid_subcommand_exits():
    from tm1_bench_py.cli import _build_parser
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["nonexistent-subcommand"])


def test_version_flag_exits(capsys):
    from tm1_bench_py.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
