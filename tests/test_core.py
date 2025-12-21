"""Tests for bifurcation engine."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from git_bifurcate.core import BifurcationEngine
from git_bifurcate.git_ops import GitRepo
from git_bifurcate.models import ChangeStatus, FileChange, CommandResult
from git_bifurcate.test_runner import CommandRunner


@pytest.fixture
def mock_git() -> MagicMock:
    """Create mock GitRepo."""
    return MagicMock(spec=GitRepo)


@pytest.fixture
def mock_test_runner() -> MagicMock:
    """Create mock CommandRunner."""
    return MagicMock(spec=CommandRunner)


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
    mock_test_runner.run.return_value = CommandResult.PASS

    # First call
    result1 = engine._test_changes(sample_changes, "base", [0, 1])
    assert result1 == CommandResult.PASS
    assert mock_test_runner.run.call_count == 1

    # Second call with same indices should use cache
    result2 = engine._test_changes(sample_changes, "base", [0, 1])
    assert result2 == CommandResult.PASS
    assert mock_test_runner.run.call_count == 1  # Still 1, not 2

    # Call with different order should use cache (keys are sorted)
    result3 = engine._test_changes(sample_changes, "base", [1, 0])
    assert result3 == CommandResult.PASS
    assert mock_test_runner.run.call_count == 1  # Still 1


def test_test_changes_apply_failure(
    mock_git: MagicMock, mock_test_runner: MagicMock, sample_changes: list[FileChange]
) -> None:
    """Test handling of patch application failure."""
    engine = BifurcationEngine(mock_git, mock_test_runner)

    mock_git.apply_changes.return_value = False

    result = engine._test_changes(sample_changes, "base", [0, 1])

    assert result == CommandResult.SKIP
    assert mock_test_runner.run.call_count == 0  # Test should not run


def test_test_changes_test_execution(
    mock_git: MagicMock, mock_test_runner: MagicMock, sample_changes: list[FileChange]
) -> None:
    """Test that changes are properly applied and tested."""
    engine = BifurcationEngine(mock_git, mock_test_runner)

    mock_git.apply_changes.return_value = True
    mock_test_runner.run.return_value = CommandResult.FAIL

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
    assert result == CommandResult.FAIL


def test_bifurcate_files_single_breaking_change(
    mock_git: MagicMock, mock_test_runner: MagicMock, sample_changes: list[FileChange]
) -> None:
    """Test bifurcation finding single breaking change."""
    engine = BifurcationEngine(mock_git, mock_test_runner)

    mock_git.apply_changes.return_value = True

    # Simulate: changes[1] is the breaking change
    def mock_run() -> CommandResult:
        # Get the indices being tested from the last apply_changes call
        call_args = mock_git.apply_changes.call_args
        if call_args:
            applied_changes = call_args[0][0]
            applied_ids = {c.id for c in applied_changes}

            # If change "1" is included, test fails
            if "1" in applied_ids:
                return CommandResult.FAIL
            return CommandResult.PASS
        return CommandResult.PASS

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
    mock_test_runner.run.return_value = CommandResult.PASS  # All tests pass

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
    def mock_run() -> CommandResult:
        call_args = mock_git.apply_changes.call_args
        if call_args:
            applied_changes = call_args[0][0]
            if len(applied_changes) == 2:
                return CommandResult.FAIL
            return CommandResult.PASS
        return CommandResult.PASS

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

    def mock_run() -> CommandResult:
        call_args = mock_git.apply_changes.call_args
        if call_args:
            applied_changes = call_args[0][0]
            applied_ids = {c.id for c in applied_changes}
            if "1" in applied_ids:
                return CommandResult.FAIL
            return CommandResult.PASS
        return CommandResult.PASS

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

    def mock_run() -> CommandResult:
        call_args = mock_git.apply_changes.call_args
        if call_args:
            applied_changes = call_args[0][0]
            applied_ids = {c.id for c in applied_changes}
            if "2" in applied_ids:
                return CommandResult.FAIL
            return CommandResult.PASS
        return CommandResult.PASS

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

    def mock_run() -> CommandResult:
        call_args = mock_git.apply_changes.call_args
        if call_args:
            applied_changes = call_args[0][0]
            applied_ids = {c.id for c in applied_changes}
            if "2" in applied_ids:
                return CommandResult.FAIL
            return CommandResult.PASS
        return CommandResult.PASS

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
        "0,1": CommandResult.PASS,
        "2,3": CommandResult.FAIL,
        "0": CommandResult.PASS,
        "1": CommandResult.SKIP,
        "2": CommandResult.ERROR,
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
    mock_test_runner.run.return_value = CommandResult.PASS

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
    mock_test_runner.run.return_value = CommandResult.FAIL

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


def test_bifurcate_files_verbose_output(
    mock_git: MagicMock, mock_test_runner: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test verbose output during bifurcation."""
    changes = [
        FileChange("0", "file1.py", "modified", "diff1", ChangeStatus.UNKNOWN),
        FileChange("1", "file2.py", "modified", "diff2", ChangeStatus.UNKNOWN),
        FileChange("2", "file3.py", "modified", "diff3", ChangeStatus.UNKNOWN),
        FileChange("3", "file4.py", "modified", "diff4", ChangeStatus.UNKNOWN),
    ]

    engine = BifurcationEngine(mock_git, mock_test_runner)
    mock_git.apply_changes.return_value = True

    def mock_run() -> CommandResult:
        call_args = mock_git.apply_changes.call_args
        if call_args:
            applied_changes = call_args[0][0]
            applied_ids = {c.id for c in applied_changes}
            if "2" in applied_ids:
                return CommandResult.FAIL
            return CommandResult.PASS
        return CommandResult.PASS

    mock_test_runner.run.side_effect = mock_run

    # Run with verbose=True
    result = engine.bifurcate_files(changes, "base", verbose=True)

    assert result is not None
    assert result.id == "2"

    # Check verbose output
    captured = capsys.readouterr()
    assert "Iteration" in captured.out
    assert "Testing changes" in captured.out
    assert "Found breaking change" in captured.out


def test_bifurcate_files_skip_warning(
    mock_git: MagicMock, mock_test_runner: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test warning message when lower half can't build."""
    changes = [
        FileChange("0", "file1.py", "modified", "diff1", ChangeStatus.UNKNOWN),
        FileChange("1", "file2.py", "modified", "diff2", ChangeStatus.UNKNOWN),
        FileChange("2", "file3.py", "modified", "diff3", ChangeStatus.UNKNOWN),
        FileChange("3", "file4.py", "modified", "diff4", ChangeStatus.UNKNOWN),
    ]

    engine = BifurcationEngine(mock_git, mock_test_runner)

    def mock_apply(applied_changes: list[FileChange], base: str, use_temp_branch: bool = True) -> bool:
        applied_ids = {c.id for c in applied_changes}
        # Lower half can't be applied
        if applied_ids == {"0", "1"}:
            return False
        return True

    mock_git.apply_changes.side_effect = mock_apply

    def mock_run() -> CommandResult:
        call_args = mock_git.apply_changes.call_args
        if call_args:
            applied_changes = call_args[0][0]
            applied_ids = {c.id for c in applied_changes}
            if "2" in applied_ids:
                return CommandResult.FAIL
            return CommandResult.PASS
        return CommandResult.PASS

    mock_test_runner.run.side_effect = mock_run

    result = engine.bifurcate_files(changes, "base", verbose=True)

    assert result is not None

    # Check warning output
    captured = capsys.readouterr()
    assert "skip" in captured.out.lower() or "trying upper half" in captured.out.lower()


def test_bifurcate_files_dependency_warning(
    mock_git: MagicMock, mock_test_runner: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test dependency warning when both halves fail to build."""
    changes = [
        FileChange("0", "file1.py", "modified", "diff1", ChangeStatus.UNKNOWN),
        FileChange("1", "file2.py", "modified", "diff2", ChangeStatus.UNKNOWN),
    ]

    engine = BifurcationEngine(mock_git, mock_test_runner)

    # Both halves fail to apply
    mock_git.apply_changes.return_value = False

    result = engine.bifurcate_files(changes, "base", verbose=True)

    assert result is None

    # Check error message
    captured = capsys.readouterr()
    assert "Too many build failures" in captured.out or "dependency" in captured.out.lower()


def test_bifurcate_files_interaction_warning(
    mock_git: MagicMock, mock_test_runner: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test warning when isolated change doesn't fail on its own."""
    changes = [
        FileChange("0", "file1.py", "modified", "diff1", ChangeStatus.UNKNOWN),
    ]

    engine = BifurcationEngine(mock_git, mock_test_runner)
    mock_git.apply_changes.return_value = True

    # Single change passes but shouldn't
    mock_test_runner.run.return_value = CommandResult.PASS

    result = engine.bifurcate_files(changes, "base", verbose=True)

    assert result is None

    # Check warning about interaction effect
    captured = capsys.readouterr()
    assert "doesn't fail on its own" in captured.out or "interaction" in captured.out.lower()


def test_bifurcate_hunks_verbose_output(
    mock_git: MagicMock, mock_test_runner: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test verbose output during hunk bifurcation."""
    from git_bifurcate.models import HunkChange

    hunks = [
        HunkChange("0", "file.py", 1, 5, 1, 3, 1, 5, "@@ -1,3 +1,5 @@", ChangeStatus.UNKNOWN),
        HunkChange("1", "file.py", 6, 10, 4, 3, 6, 5, "@@ -4,3 +6,5 @@", ChangeStatus.UNKNOWN),
    ]

    engine = BifurcationEngine(mock_git, mock_test_runner)
    mock_git.apply_hunk_changes.return_value = True

    def mock_run() -> CommandResult:
        # Second hunk fails
        return CommandResult.FAIL

    mock_test_runner.run.side_effect = mock_run

    result = engine.bifurcate_hunks(hunks, "base", "bad", verbose=True)

    # Check verbose output
    captured = capsys.readouterr()
    assert "Testing hunks" in captured.out or "hunk" in captured.out.lower()


def test_bifurcate_hunks_dependency_error(
    mock_git: MagicMock, mock_test_runner: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test dependency error during hunk bifurcation."""
    from git_bifurcate.models import HunkChange

    hunks = [
        HunkChange("0", "file.py", 1, 5, 1, 3, 1, 5, "@@ -1,3 +1,5 @@", ChangeStatus.UNKNOWN),
        HunkChange("1", "file.py", 6, 10, 4, 3, 6, 5, "@@ -4,3 +6,5 @@", ChangeStatus.UNKNOWN),
    ]

    engine = BifurcationEngine(mock_git, mock_test_runner)

    # Both halves fail to apply
    mock_git.apply_hunk_changes.return_value = False

    result = engine.bifurcate_hunks(hunks, "base", "bad", verbose=True)

    assert result is None

    # Check error message
    captured = capsys.readouterr()
    assert "build failures" in captured.out.lower() or "dependency" in captured.out.lower()
