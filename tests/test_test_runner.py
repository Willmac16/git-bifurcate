"""Tests for test runner functionality."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from git_bifurcate.models import TestResult
from git_bifurcate.test_runner import TestRunner


def test_test_runner_creation() -> None:
    """Test creating TestRunner object."""
    runner = TestRunner("pytest tests/")

    assert runner.test_command == "pytest tests/"
    assert runner.timeout == 300


def test_test_runner_custom_timeout() -> None:
    """Test creating TestRunner with custom timeout."""
    runner = TestRunner("make test", timeout=60)

    assert runner.test_command == "make test"
    assert runner.timeout == 60


@patch("subprocess.run")
def test_test_runner_pass(mock_run: MagicMock) -> None:
    """Test runner returns PASS when test succeeds."""
    mock_run.return_value = MagicMock(returncode=0)

    runner = TestRunner("echo 'success'")
    result = runner.run()

    assert result == TestResult.PASS
    mock_run.assert_called_once()


@patch("subprocess.run")
def test_test_runner_fail(mock_run: MagicMock) -> None:
    """Test runner returns FAIL when test fails."""
    mock_run.return_value = MagicMock(returncode=1)

    runner = TestRunner("exit 1")
    result = runner.run()

    assert result == TestResult.FAIL
    mock_run.assert_called_once()


@patch("subprocess.run")
def test_test_runner_error_on_exception(mock_run: MagicMock) -> None:
    """Test runner returns ERROR when command raises exception."""
    mock_run.side_effect = FileNotFoundError("Command not found")

    runner = TestRunner("nonexistent-command")
    result = runner.run()

    assert result == TestResult.ERROR


@patch("subprocess.run")
def test_test_runner_error_on_timeout(mock_run: MagicMock) -> None:
    """Test runner returns ERROR when command times out."""
    mock_run.side_effect = subprocess.TimeoutExpired("cmd", 10)

    runner = TestRunner("sleep 100", timeout=1)
    result = runner.run()

    assert result == TestResult.ERROR


@patch("subprocess.run")
def test_test_runner_uses_shell(mock_run: MagicMock) -> None:
    """Test that runner uses shell=True."""
    mock_run.return_value = MagicMock(returncode=0)

    runner = TestRunner("echo test")
    runner.run()

    # Verify subprocess.run was called with shell=True
    call_args = mock_run.call_args
    assert call_args[1]["shell"] is True


@patch("subprocess.run")
def test_test_runner_timeout_passed(mock_run: MagicMock) -> None:
    """Test that custom timeout is passed to subprocess."""
    mock_run.return_value = MagicMock(returncode=0)

    runner = TestRunner("test command", timeout=123)
    runner.run()

    # Verify timeout was passed
    call_args = mock_run.call_args
    assert call_args[1]["timeout"] == 123


@patch("subprocess.run")
def test_test_runner_captures_output(mock_run: MagicMock) -> None:
    """Test that runner captures stdout and stderr."""
    mock_run.return_value = MagicMock(returncode=0)

    runner = TestRunner("echo test")
    runner.run()

    # Verify output capture
    call_args = mock_run.call_args
    assert call_args[1]["capture_output"] is True


@patch("subprocess.run")
def test_test_runner_handles_various_exit_codes(mock_run: MagicMock) -> None:
    """Test that different exit codes are handled correctly."""
    runner = TestRunner("test")

    # Exit code 0 = PASS
    mock_run.return_value = MagicMock(returncode=0)
    assert runner.run() == TestResult.PASS

    # Exit code 1 = FAIL
    mock_run.return_value = MagicMock(returncode=1)
    assert runner.run() == TestResult.FAIL

    # Exit code 2 = FAIL
    mock_run.return_value = MagicMock(returncode=2)
    assert runner.run() == TestResult.FAIL

    # Exit code 127 (command not found) = FAIL
    mock_run.return_value = MagicMock(returncode=127)
    assert runner.run() == TestResult.FAIL
