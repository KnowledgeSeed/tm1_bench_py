"""Tests for tm1-bench build --dry-run."""
import pytest
from unittest.mock import patch, MagicMock
from tm1_bench_py.cli import ExitCode


def _make_schema():
    return {
        'dimensions': {
            'elementlist': {
                'Currency': {'dimension_name': 'Currency'},
                'Version': {'dimension_name': 'Version'},
            },
            'df_templates': {},
            'custom': {},
            'csv': {},
        },
        'cubes': {
            'Sales': {'name': 'Sales', 'dimensions': ['Currency', 'Version'], 'rules': []},
        },
        'datasets': {
            'SalesData': {'targetCube': 'Sales', 'rows': 100},
        },
        'config': {'df_to_cube_default_kwargs': {}},
        'env': 'default',
        'variables': {},
    }


def test_dry_run_valid_schema_exits_0_and_prints_plan(tmp_path, capsys):
    schema = _make_schema()
    mock_report = MagicMock()
    mock_report.is_valid = True
    mock_report.warnings = []

    with patch('tm1_bench_py.cli._load_schema', return_value=schema), \
         patch('tm1_bench_py.cli._run_validation', return_value=mock_report):
        from tm1_bench_py.cli import main
        with pytest.raises(SystemExit) as exc:
            main(["--schema", str(tmp_path), "build", "--dry-run"])
        assert exc.value.code == int(ExitCode.SUCCESS)

    captured = capsys.readouterr()
    assert "Build plan" in captured.out
    assert "Currency" in captured.out
    assert "Sales" in captured.out
    assert "SalesData" in captured.out


def test_dry_run_counts_match_schema(tmp_path, capsys):
    schema = _make_schema()
    mock_report = MagicMock()
    mock_report.is_valid = True
    mock_report.warnings = []

    with patch('tm1_bench_py.cli._load_schema', return_value=schema), \
         patch('tm1_bench_py.cli._run_validation', return_value=mock_report):
        from tm1_bench_py.cli import main
        with pytest.raises(SystemExit):
            main(["--schema", str(tmp_path), "build", "--dry-run"])

    captured = capsys.readouterr()
    # 2 elementlist dims
    assert "Dimensions (2)" in captured.out
    # 1 cube
    assert "Cubes (1)" in captured.out
    # 1 dataset
    assert "Datasets (1)" in captured.out


def test_dry_run_invalid_schema_exits_1(tmp_path):
    schema = _make_schema()
    mock_report = MagicMock()
    mock_report.is_valid = False
    mock_report.warnings = []

    with patch('tm1_bench_py.cli._load_schema', return_value=schema), \
         patch('tm1_bench_py.cli._run_validation', return_value=mock_report):
        from tm1_bench_py.cli import main
        with pytest.raises(SystemExit) as exc:
            main(["--schema", str(tmp_path), "build", "--dry-run"])
        assert exc.value.code == int(ExitCode.VALIDATION_FAILURE)


def test_dry_run_does_not_connect_to_tm1(tmp_path):
    schema = _make_schema()
    mock_report = MagicMock()
    mock_report.is_valid = True
    mock_report.warnings = []

    with patch('tm1_bench_py.cli._load_schema', return_value=schema), \
         patch('tm1_bench_py.cli._run_validation', return_value=mock_report), \
         patch('tm1_bench_py.utility.tm1_connection') as mock_conn:
        from tm1_bench_py.cli import main
        with pytest.raises(SystemExit):
            main(["--schema", str(tmp_path), "build", "--dry-run"])
        mock_conn.assert_not_called()
