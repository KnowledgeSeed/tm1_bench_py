"""Tests for exit code mapping: exception type -> ExitCode."""
import pytest
from unittest.mock import patch, MagicMock
from tm1_bench_py.cli import ExitCode


def _mock_valid_report():
    report = MagicMock()
    report.is_valid = True
    report.warnings = []
    return report


def _base_schema():
    return {
        'dimensions': {'elementlist': {}, 'df_templates': {}, 'custom': {}, 'csv': {}},
        'cubes': {},
        'datasets': {},
        'config': {'df_to_cube_default_kwargs': {}},
        'env': 'default',
        'variables': {},
    }


@pytest.mark.parametrize("exc,expected_code", [
    (ValueError("schema broken"), ExitCode.VALIDATION_FAILURE),
    (FileNotFoundError("config.ini missing"), ExitCode.CONNECTION_FAILURE),
    (RuntimeError("unexpected"), ExitCode.BUILD_ERROR),
])
def test_build_exception_maps_to_exit_code(exc, expected_code, tmp_path):
    schema = _base_schema()
    with patch('tm1_bench_py.cli._load_schema', return_value=schema), \
         patch('tm1_bench_py.cli._run_validation', return_value=_mock_valid_report()), \
         patch('tm1_bench_py.cli._resolve_config_ini', return_value='config.ini'), \
         patch('tm1_bench_py.cli._resolve_connection_name', return_value='testbench'), \
         patch('tm1_bench_py.utility.tm1_connection', side_effect=exc):
        from tm1_bench_py.cli import main
        with pytest.raises(SystemExit) as exc_info:
            main(["--schema", str(tmp_path), "build"])
        assert exc_info.value.code == int(expected_code)


def test_usage_error_maps_to_exit_4():
    from tm1_bench_py.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["--bad-flag-that-does-not-exist"])
    assert exc_info.value.code == int(ExitCode.USAGE_ERROR)
