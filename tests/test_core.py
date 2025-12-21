"""Tests for bifurcation engine."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from git_bifurcate.core import BifurcationEngine
from git_bifurcate.git_ops import GitRepo
from git_bifurcate.models import ChangeStatus, FileChange, TestResult
from git_bifurcate.test_runner import TestRunner


@pytest.fixture
def mock_git() -> MagicMock:
    """Create mock GitRepo."""
    return MagicMock(spec=GitRepo)


@pytest.fixture
def mock_test_runner() -> MagicMock:
    """Create mock TestRunner."""
    return MagicMock(spec=TestRunner)


@pytest.fixture
def sample_changes() -> list[FileChange]:
    """Create sample FileChanges for testing."""
    return [
        FileChange("0", "file1.py", "modified", "diff1", ChangeStatus.UNKNOWN),
        FileChange("1", "file2.py", "added", "diff2", ChangeStatus.UNKNOWN),
        FileChange("2", "file3.py", "modified", "diff3", ChangeStatus.UNKNOWN),
        FileChange("3", "file4.py", "deleted", "diff4", ChangeStatus.UNKNOWN),
    ]


def test_bifurcation_engine_creation(mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
    """Test creating BifurcationEngine."""
    engine = BifurcationEngine(mock_git, mock_test_runner)

    assert engine.git == mock_git
    assert engine.test_runner == mock_test_runner
    assert len(engine.tested_combinations) == 0


def test_get_combination_key(mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
    """Test combination key generation."""
    engine = BifurcationEngine(mock_git, mock_test_runner)

    # Keys should be sorted
    assert engine._get_combination_key([0, 1, 2]) == "0,1,2"
    assert engine._get_combination_key([2, 0, 1]) == "0,1,2"
    assert engine._get_combination_key([1]) == "1"
    assert engine._get_combination_key([]) == ""


def test_test_changes_caching(
    mock_git: MagicMock, mock_test_runner: MagicMock, sample_changes: list[FileChange]
) -> None:
    """Test that test results are cached."""
    engine = BifurcationEngine(mock_git, mock_test_runner)

    mock_git.apply_changes.return_value = True
    mock_test_runner.run.return_value = TestResult.PASS

    # First call
    result1 = engine._test_changes(sample_changes, "base", [0, 1])
    assert result1 == TestResult.PASS
    assert mock_test_runner.run.call_count == 1

    # Second call with same indices should use cache
    result2 = engine._test_changes(sample_changes, "base", [0, 1])
    assert result2 == TestResult.PASS
    assert mock_test_runner.run.call_count == 1  # Still 1, not 2

    # Call with different order should use cache (keys are sorted)
    result3 = engine._test_changes(sample_changes, "base", [1, 0])
    assert result3 == TestResult.PASS
    assert mock_test_runner.run.call_count == 1  # Still 1


def test_test_changes_apply_failure(
    mock_git: MagicMock, mock_test_runner: MagicMock, sample_changes: list[FileChange]
) -> None:
    """Test handling of patch application failure."""
    engine = BifurcationEngine(mock_git, mock_test_runner)

    mock_git.apply_changes.return_value = False

    result = engine._test_changes(sample_changes, "base", [0, 1])

    assert result == TestResult.SKIP
    assert mock_test_runner.run.call_count == 0  # Test should not run


def test_test_changes_test_execution(
    mock_git: MagicMock, mock_test_runner: MagicMock, sample_changes: list[FileChange]
) -> None:
    """Test that changes are properly applied and tested."""
    engine = BifurcationEngine(mock_git, mock_test_runner)

    mock_git.apply_changes.return_value = True
    mock_test_runner.run.return_value = TestResult.FAIL

    result = engine._test_changes(sample_changes, "base_sha", [0, 2])

    # Verify apply_changes was called with correct arguments
    mock_git.apply_changes.assert_called_once()
    call_args = mock_git.apply_changes.call_args
    applied_changes = call_args[0][0]
    assert len(applied_changes) == 2
    assert applied_changes[0].id == "0"
    assert applied_changes[1].id == "2"
    assert call_args[0][1] == "base_sha"

    # Verify test was run
    mock_test_runner.run.assert_called_once()
    assert result == TestResult.FAIL


def test_bifurcate_files_single_breaking_change(
    mock_git: MagicMock, mock_test_runner: MagicMock, sample_changes: list[FileChange]
) -> None:
    """Test bifurcation finding single breaking change."""
    engine = BifurcationEngine(mock_git, mock_test_runner)

    mock_git.apply_changes.return_value = True

    # Simulate: changes[1] is the breaking change
    def mock_run() -> TestResult:
        # Get the indices being tested from the last apply_changes call
        call_args = mock_git.apply_changes.call_args
        if call_args:
            applied_changes = call_args[0][0]
            applied_ids = {c.id for c in applied_changes}

            # If change "1" is included, test fails
            if "1" in applied_ids:
                return TestResult.FAIL
            return TestResult.PASS
        return TestResult.PASS

    mock_test_runner.run.side_effect = mock_run

    result = engine.bifurcate_files(sample_changes, "base", verbose=False)

    assert result is not None
    assert result.id == "1"
    assert result.file_path == "file2.py"


def test_bifurcate_files_no_breaking_change(
    mock_git: MagicMock, mock_test_runner: MagicMock, sample_changes: list[FileChange]
) -> None:
    """Test bifurcation when no single breaking change exists."""
    engine = BifurcationEngine(mock_git, mock_test_runner)

    mock_git.apply_changes.return_value = True
    mock_test_runner.run.return_value = TestResult.PASS  # All tests pass

    result = engine.bifurcate_files(sample_changes, "base", verbose=False)

    assert result is None


def test_bifurcate_files_interaction_effect(
    mock_git: MagicMock, mock_test_runner: MagicMock
) -> None:
    """Test bifurcation when multiple changes interact."""
    changes = [
        FileChange("0", "file1.py", "modified", "diff1", ChangeStatus.UNKNOWN),
        FileChange("1", "file2.py", "modified", "diff2", ChangeStatus.UNKNOWN),
    ]

    engine = BifurcationEngine(mock_git, mock_test_runner)
    mock_git.apply_changes.return_value = True

    # Simulate interaction: both pass individually but fail together
    def mock_run() -> TestResult:
        call_args = mock_git.apply_changes.call_args
        if call_args:
            applied_changes = call_args[0][0]
            if len(applied_changes) == 2:
                return TestResult.FAIL
            return TestResult.PASS
        return TestResult.PASS

    mock_test_runner.run.side_effect = mock_run

    result = engine.bifurcate_files(changes, "base", verbose=False)

    # Should detect interaction and return None
    assert result is None


def test_bifurcate_files_first_half_fails(
    mock_git: MagicMock, mock_test_runner: MagicMock
) -> None:
    """Test binary search when first half contains bug."""
    changes = [
        FileChange("0", "file1.py", "modified", "diff1", ChangeStatus.UNKNOWN),
        FileChange("1", "file2.py", "modified", "diff2", ChangeStatus.UNKNOWN),  # Bug here
        FileChange("2", "file3.py", "modified", "diff3", ChangeStatus.UNKNOWN),
        FileChange("3", "file4.py", "modified", "diff4", ChangeStatus.UNKNOWN),
    ]

    engine = BifurcationEngine(mock_git, mock_test_runner)
    mock_git.apply_changes.return_value = True

    def mock_run() -> TestResult:
        call_args = mock_git.apply_changes.call_args
        if call_args:
            applied_changes = call_args[0][0]
            applied_ids = {c.id for c in applied_changes}
            if "1" in applied_ids:
                return TestResult.FAIL
            return TestResult.PASS
        return TestResult.PASS

    mock_test_runner.run.side_effect = mock_run

    result = engine.bifurcate_files(changes, "base", verbose=False)

    assert result is not None
    assert result.id == "1"


def test_bifurcate_files_second_half_fails(
    mock_git: MagicMock, mock_test_runner: MagicMock
) -> None:
    """Test binary search when second half contains bug."""
    changes = [
        FileChange("0", "file1.py", "modified", "diff1", ChangeStatus.UNKNOWN),
        FileChange("1", "file2.py", "modified", "diff2", ChangeStatus.UNKNOWN),
        FileChange("2", "file3.py", "modified", "diff3", ChangeStatus.UNKNOWN),  # Bug here
        FileChange("3", "file4.py", "modified", "diff4", ChangeStatus.UNKNOWN),
    ]

    engine = BifurcationEngine(mock_git, mock_test_runner)
    mock_git.apply_changes.return_value = True

    def mock_run() -> TestResult:
        call_args = mock_git.apply_changes.call_args
        if call_args:
            applied_changes = call_args[0][0]
            applied_ids = {c.id for c in applied_changes}
            if "2" in applied_ids:
                return TestResult.FAIL
            return TestResult.PASS
        return TestResult.PASS

    mock_test_runner.run.side_effect = mock_run

    result = engine.bifurcate_files(changes, "base", verbose=False)

    assert result is not None
    assert result.id == "2"


def test_bifurcate_files_handles_skip(
    mock_git: MagicMock, mock_test_runner: MagicMock
) -> None:
    """Test handling of SKIP results from dependency issues."""
    changes = [
        FileChange("0", "file1.py", "modified", "diff1", ChangeStatus.UNKNOWN),
        FileChange("1", "file2.py", "modified", "diff2", ChangeStatus.UNKNOWN),
        FileChange("2", "file3.py", "modified", "diff3", ChangeStatus.UNKNOWN),  # Bug
        FileChange("3", "file4.py", "modified", "diff4", ChangeStatus.UNKNOWN),
    ]

    engine = BifurcationEngine(mock_git, mock_test_runner)

    # Simulate: first half can't be applied (dependencies), second half has bug
    def mock_apply(applied_changes: list[FileChange], base: str, use_temp_branch: bool = True) -> bool:
        applied_ids = {c.id for c in applied_changes}
        # First half (0, 1) can't be applied
        if applied_ids == {"0", "1"}:
            return False
        return True

    mock_git.apply_changes.side_effect = mock_apply

    def mock_run() -> TestResult:
        call_args = mock_git.apply_changes.call_args
        if call_args:
            applied_changes = call_args[0][0]
            applied_ids = {c.id for c in applied_changes}
            if "2" in applied_ids:
                return TestResult.FAIL
            return TestResult.PASS
        return TestResult.PASS

    mock_test_runner.run.side_effect = mock_run

    result = engine.bifurcate_files(changes, "base", verbose=False)

    # Should find bug in second half despite first half failing to apply
    assert result is not None
    assert result.id == "2"


def test_get_stats(mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
    """Test statistics gathering."""
    engine = BifurcationEngine(mock_git, mock_test_runner)

    # Manually populate tested_combinations
    engine.tested_combinations = {
        "0,1": TestResult.PASS,
        "2,3": TestResult.FAIL,
        "0": TestResult.PASS,
        "1": TestResult.SKIP,
        "2": TestResult.ERROR,
    }

    stats = engine.get_stats()

    assert stats["tests_run"] == 5
    assert stats["passed"] == 2
    assert stats["failed"] == 1
    assert stats["skipped"] == 1
    assert stats["errors"] == 1


def test_bifurcate_files_verbose_output(
    mock_git: MagicMock, mock_test_runner: MagicMock, sample_changes: list[FileChange]
) -> None:
    """Test that verbose mode produces output."""
    engine = BifurcationEngine(mock_git, mock_test_runner)

    mock_git.apply_changes.return_value = True
    mock_test_runner.run.return_value = TestResult.PASS

    # Capture output
    with patch("click.echo") as mock_echo:
        engine.bifurcate_files(sample_changes, "base", verbose=True)

        # Verify some output was produced
        assert mock_echo.call_count > 0


def test_bifurcate_files_single_change(
    mock_git: MagicMock, mock_test_runner: MagicMock
) -> None:
    """Test bifurcation with single change."""
    changes = [
        FileChange("0", "file1.py", "modified", "diff1", ChangeStatus.UNKNOWN),
    ]

    engine = BifurcationEngine(mock_git, mock_test_runner)
    mock_git.apply_changes.return_value = True
    mock_test_runner.run.return_value = TestResult.FAIL

    result = engine.bifurcate_files(changes, "base", verbose=False)

    assert result is not None
    assert result.id == "0"


def test_bifurcate_files_empty_changes(
    mock_git: MagicMock, mock_test_runner: MagicMock
) -> None:
    """Test bifurcation with no changes."""
    changes: list[FileChange] = []

    engine = BifurcationEngine(mock_git, mock_test_runner)

    result = engine.bifurcate_files(changes, "base", verbose=False)

    assert result is None
