"""Tests for config.ini and connection name resolution."""
import pytest
from unittest.mock import MagicMock


def test_resolve_config_ini_uses_cli_flag(tmp_path):
    config_file = tmp_path / "my_config.ini"
    config_file.write_text("[testbench]\n")
    args = MagicMock()
    args.config = str(config_file)
    from tm1_bench_py.cli import _resolve_config_ini
    assert _resolve_config_ini(args) == str(config_file)


def test_resolve_config_ini_uses_env_var(tmp_path, monkeypatch):
    config_file = tmp_path / "env_config.ini"
    config_file.write_text("[testbench]\n")
    monkeypatch.setenv("TM1_BENCH_CONFIG", str(config_file))
    args = MagicMock()
    args.config = None
    from tm1_bench_py.cli import _resolve_config_ini
    assert _resolve_config_ini(args) == str(config_file)


def test_resolve_config_ini_falls_back_to_default(tmp_path, monkeypatch):
    config_file = tmp_path / "config.ini"
    config_file.write_text("[testbench]\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TM1_BENCH_CONFIG", raising=False)
    args = MagicMock()
    args.config = None
    from tm1_bench_py.cli import _resolve_config_ini
    assert _resolve_config_ini(args) == "config.ini"


def test_resolve_config_ini_raises_when_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TM1_BENCH_CONFIG", raising=False)
    args = MagicMock()
    args.config = None
    from tm1_bench_py.cli import _resolve_config_ini
    with pytest.raises(FileNotFoundError, match="config.ini"):
        _resolve_config_ini(args)


def test_resolve_config_ini_cli_flag_beats_env_var(tmp_path, monkeypatch):
    cli_file = tmp_path / "cli.ini"
    env_file = tmp_path / "env.ini"
    cli_file.write_text("[testbench]\n")
    env_file.write_text("[testbench]\n")
    monkeypatch.setenv("TM1_BENCH_CONFIG", str(env_file))
    args = MagicMock()
    args.config = str(cli_file)
    from tm1_bench_py.cli import _resolve_config_ini
    result = _resolve_config_ini(args)
    assert result == str(cli_file)


def test_resolve_connection_name_uses_cli_flag():
    args = MagicMock()
    args.connection = "my_server"
    from tm1_bench_py.cli import _resolve_connection_name
    assert _resolve_connection_name(args) == "my_server"


def test_resolve_connection_name_uses_env_var(monkeypatch):
    monkeypatch.setenv("TM1_BENCH_CONNECTION", "prod_server")
    args = MagicMock()
    args.connection = None
    from tm1_bench_py.cli import _resolve_connection_name
    assert _resolve_connection_name(args) == "prod_server"


def test_resolve_connection_name_falls_back_to_testbench(monkeypatch):
    monkeypatch.delenv("TM1_BENCH_CONNECTION", raising=False)
    args = MagicMock()
    args.connection = None
    from tm1_bench_py.cli import _resolve_connection_name
    assert _resolve_connection_name(args) == "testbench"


def test_resolve_connection_name_cli_flag_beats_env_var(monkeypatch):
    monkeypatch.setenv("TM1_BENCH_CONNECTION", "env_server")
    args = MagicMock()
    args.connection = "cli_server"
    from tm1_bench_py.cli import _resolve_connection_name
    assert _resolve_connection_name(args) == "cli_server"
