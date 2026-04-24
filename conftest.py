"""Root conftest.py — project-wide pytest configuration."""
import pathlib
import pytest


def pytest_configure(config):
    """Set tmp_path base to a local directory to avoid Windows permission issues."""
    local_tmp = pathlib.Path(__file__).parent / ".pytest_tmp"
    local_tmp.mkdir(exist_ok=True)
    config.option.basetemp = local_tmp
