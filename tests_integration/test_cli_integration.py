"""Integration test: run tm1-bench build via subprocess against the Docker TM1."""
import subprocess
import sys
import pytest


@pytest.mark.integration
def test_cli_build_exits_0():
    """tm1-bench build should exit 0 against the running TM1 Docker container."""
    result = subprocess.run(
        [sys.executable, "-m", "tm1_bench_py", "build",
         "--schema", "schema",
         "--env", "default",
         "--config", "tests/config.ini",
         "--connection", "testbench"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"tm1-bench build exited {result.returncode}\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )


@pytest.mark.integration
def test_cli_validate_exits_0_without_tm1():
    """tm1-bench validate should exit 0 with no TM1 connection required."""
    result = subprocess.run(
        [sys.executable, "-m", "tm1_bench_py", "validate",
         "--schema", "schema",
         "--env", "default"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"tm1-bench validate exited {result.returncode}\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
