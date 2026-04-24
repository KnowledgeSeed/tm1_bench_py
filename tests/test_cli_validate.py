"""Tests for tm1-bench validate subcommand."""
import pytest
from unittest.mock import patch, MagicMock
from tm1_bench_py.cli import ExitCode


def _make_schema(valid=True):
    """Return a minimal schema dict."""
    return {
        'dimensions': {'elementlist': {}, 'df_templates': {}, 'custom': {}, 'csv': {}},
        'cubes': {},
        'datasets': {},
        'config': {'df_to_cube_default_kwargs': {}},
        'env': 'default',
        'variables': {},
    }


def test_validate_valid_schema_exits_0(tmp_path):
    schema = _make_schema()
    mock_report = MagicMock()
    mock_report.is_valid = True
    mock_report.warnings = []

    with patch('tm1_bench_py.cli._load_schema', return_value=schema), \
         patch('tm1_bench_py.cli._run_validation', return_value=mock_report):
        from tm1_bench_py.cli import main
        with pytest.raises(SystemExit) as exc:
            main(["--schema", str(tmp_path), "validate"])
        assert exc.value.code == int(ExitCode.SUCCESS)


def test_validate_invalid_schema_exits_1(tmp_path):
    schema = _make_schema()
    mock_report = MagicMock()
    mock_report.is_valid = False
    mock_report.warnings = []

    with patch('tm1_bench_py.cli._load_schema', return_value=schema), \
         patch('tm1_bench_py.cli._run_validation', return_value=mock_report):
        from tm1_bench_py.cli import main
        with pytest.raises(SystemExit) as exc:
            main(["--schema", str(tmp_path), "validate"])
        assert exc.value.code == int(ExitCode.VALIDATION_FAILURE)


def test_validate_strict_with_warnings_exits_1(tmp_path):
    schema = _make_schema()
    mock_report = MagicMock()
    mock_report.is_valid = True
    mock_report.warnings = ["some warning"]

    with patch('tm1_bench_py.cli._load_schema', return_value=schema), \
         patch('tm1_bench_py.cli._run_validation', return_value=mock_report):
        from tm1_bench_py.cli import main
        with pytest.raises(SystemExit) as exc:
            main(["--schema", str(tmp_path), "validate", "--strict"])
        assert exc.value.code == int(ExitCode.VALIDATION_FAILURE)


def test_validate_strict_no_warnings_exits_0(tmp_path):
    schema = _make_schema()
    mock_report = MagicMock()
    mock_report.is_valid = True
    mock_report.warnings = []

    with patch('tm1_bench_py.cli._load_schema', return_value=schema), \
         patch('tm1_bench_py.cli._run_validation', return_value=mock_report):
        from tm1_bench_py.cli import main
        with pytest.raises(SystemExit) as exc:
            main(["--schema", str(tmp_path), "validate", "--strict"])
        assert exc.value.code == int(ExitCode.SUCCESS)
