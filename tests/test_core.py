"""Tests for bifurcation engine."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from git_bifurcate.core import BifurcationEngine
from git_bifurcate.git_ops import GitRepo
from git_bifurcate.models import ChangeStatus, CommandResult, FileChange, HunkChange
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


def test_test_changes_checkout_failure(
    mock_git: MagicMock, mock_test_runner: MagicMock, sample_changes: list[FileChange]
) -> None:
    """Checkout errors are swallowed after running tests."""
    engine = BifurcationEngine(mock_git, mock_test_runner)

    mock_git.apply_changes.return_value = True
    mock_test_runner.run.return_value = CommandResult.PASS
    mock_git.checkout.side_effect = RuntimeError("boom")

    result = engine._test_changes(sample_changes, "base", [0])
    assert result == CommandResult.PASS
    mock_git.checkout.assert_called_once_with("base")


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


def test_bifurcate_files_first_half_fails(mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
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


def test_bifurcate_files_reports_interaction(
    mock_git: MagicMock, mock_test_runner: MagicMock
) -> None:
    """Test that interaction detection surfaces minimal failing combo."""
    changes = [
        FileChange("0", "file1.py", "modified", "diff1", ChangeStatus.UNKNOWN),
        FileChange("1", "file2.py", "modified", "diff2", ChangeStatus.UNKNOWN),
    ]

    engine = BifurcationEngine(mock_git, mock_test_runner)
    mock_git.apply_changes.return_value = True

    def mock_run() -> CommandResult:
        call_args = mock_git.apply_changes.call_args
        if call_args:
            applied_changes = call_args[0][0]
            applied_ids = {c.id for c in applied_changes}
            if applied_ids == {"0", "1"}:
                return CommandResult.FAIL
            return CommandResult.PASS
        return CommandResult.PASS

    mock_test_runner.run.side_effect = mock_run

    result = engine.bifurcate_files(changes, "base", verbose=False)

    assert result is None
    assert engine.interaction_failure == [0, 1]


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


def test_bifurcate_files_handles_skip(mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
    """Test handling of SKIP results from dependency issues."""
    changes = [
        FileChange("0", "file1.py", "modified", "diff1", ChangeStatus.UNKNOWN),
        FileChange("1", "file2.py", "modified", "diff2", ChangeStatus.UNKNOWN),
        FileChange("2", "file3.py", "modified", "diff3", ChangeStatus.UNKNOWN),  # Bug
        FileChange("3", "file4.py", "modified", "diff4", ChangeStatus.UNKNOWN),
    ]

    engine = BifurcationEngine(mock_git, mock_test_runner)

    # Simulate: first half can't be applied (dependencies), second half has bug
    def mock_apply(
        applied_changes: list[FileChange], base: str, use_temp_branch: bool = True
    ) -> bool:
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


def test_bifurcate_files_verbose_mode_basic(
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


def test_bifurcate_files_single_change(mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
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


def test_bifurcate_files_empty_changes(mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
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

    def mock_apply(
        applied_changes: list[FileChange], base: str, use_temp_branch: bool = True
    ) -> bool:
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


def test_bifurcate_files_upper_half_pass_warning(
    mock_git: MagicMock, mock_test_runner: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """When lower half fails but upper half passes, a warning is emitted."""
    changes = [
        FileChange("0", "file1.py", "modified", "diff1", ChangeStatus.UNKNOWN),
        FileChange("1", "file2.py", "modified", "diff2", ChangeStatus.UNKNOWN),
        FileChange("2", "file3.py", "modified", "diff3", ChangeStatus.UNKNOWN),
        FileChange("3", "file4.py", "modified", "diff4", ChangeStatus.UNKNOWN),
    ]

    engine = BifurcationEngine(mock_git, mock_test_runner)

    def mock_apply(applied_changes: list[FileChange], *_: object, **__: object) -> bool:
        ids = {c.id for c in applied_changes}
        return ids != {"0", "1"}

    mock_git.apply_changes.side_effect = mock_apply
    mock_test_runner.run.return_value = CommandResult.PASS

    result = engine.bifurcate_files(changes, "base", verbose=True)

    assert result is None
    captured = capsys.readouterr()
    assert "Upper half" in captured.out or "Warning: Lower half won't build" in captured.out


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

    _result = engine.bifurcate_hunks(hunks, "base", "bad", verbose=True)

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


def test_bifurcate_hunks_upper_half_pass_warning(
    mock_git: MagicMock, mock_test_runner: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """When lower hunks fail but upper hunks pass, dependency warning is printed."""
    from git_bifurcate.models import HunkChange

    hunks = [
        HunkChange("0", "file.py", 1, 1, 1, 1, 1, 1, "@@", ChangeStatus.UNKNOWN),
        HunkChange("1", "file.py", 2, 2, 2, 1, 2, 1, "@@", ChangeStatus.UNKNOWN),
        HunkChange("2", "file.py", 3, 3, 3, 1, 3, 1, "@@", ChangeStatus.UNKNOWN),
        HunkChange("3", "file.py", 4, 4, 4, 1, 4, 1, "@@", ChangeStatus.UNKNOWN),
    ]

    engine = BifurcationEngine(mock_git, mock_test_runner)

    def apply_hunks(selected: list[HunkChange], *_: object, **__: object) -> bool:
        ids = {h.id for h in selected}
        return ids != {"0", "1"}

    mock_git.apply_hunk_changes.side_effect = apply_hunks
    mock_test_runner.run.return_value = CommandResult.PASS

    result = engine.bifurcate_hunks(hunks, "base", "bad", verbose=True)

    assert result is None
    captured = capsys.readouterr()
    assert "Warning: Lower half won't build" in captured.out


def test_bifurcate_hunks_upper_half_fail_path(
    mock_git: MagicMock, mock_test_runner: MagicMock
) -> None:
    """Upper-half failure path is used when lower half cannot be applied."""
    from git_bifurcate.models import HunkChange

    hunks = [
        HunkChange("0", "file.py", 1, 1, 1, 1, 1, 1, "@@", ChangeStatus.UNKNOWN),
        HunkChange("1", "file.py", 2, 2, 2, 1, 2, 1, "@@", ChangeStatus.UNKNOWN),
        HunkChange("2", "file.py", 3, 3, 3, 1, 3, 1, "@@", ChangeStatus.UNKNOWN),
    ]

    def apply(selected: list[HunkChange], *_: object, **__: object) -> bool:
        ids = {h.id for h in selected}
        return ids != {"0"}

    def run() -> CommandResult:
        call_args = mock_git.apply_hunk_changes.call_args
        applied = call_args[0][0]
        return CommandResult.FAIL if any(h.id == "1" for h in applied) else CommandResult.PASS

    mock_git.apply_hunk_changes.side_effect = apply
    mock_test_runner.run.side_effect = run

    engine = BifurcationEngine(mock_git, mock_test_runner)
    result = engine.bifurcate_hunks(hunks, "base", "bad", verbose=False)

    assert result is not None
    assert result.id == "1"


def test_test_hunk_changes_checkout_failure(
    mock_git: MagicMock, mock_test_runner: MagicMock
) -> None:
    """Checkout errors after hunk testing are ignored."""
    from git_bifurcate.models import HunkChange

    engine = BifurcationEngine(mock_git, mock_test_runner)
    hunk = HunkChange("0", "file.py", 1, 1, 1, 1, 1, 1, "@@", ChangeStatus.UNKNOWN)
    mock_git.apply_hunk_changes.return_value = True
    mock_test_runner.run.return_value = CommandResult.PASS
    mock_git.checkout.side_effect = RuntimeError("fail")

    result = engine._test_hunk_changes([hunk], "base", "bad", [0])
    assert result == CommandResult.PASS
    mock_git.checkout.assert_called_once_with("base")


def test_find_interaction_failure_files(mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
    """_find_interaction_failure returns minimal combo for file changes."""
    changes = [
        FileChange("0", "f1", "modified", "d1", ChangeStatus.UNKNOWN),
        FileChange("1", "f2", "modified", "d2", ChangeStatus.UNKNOWN),
    ]
    engine = BifurcationEngine(mock_git, mock_test_runner)

    def test_func(applied: list[FileChange], *_: object, **__: object) -> CommandResult:
        ids = {c.id for c in applied}
        return CommandResult.FAIL if ids == {"0", "1"} else CommandResult.PASS

    mock_git.apply_changes.side_effect = lambda applied, *_args, **_kwargs: True
    mock_test_runner.run.side_effect = lambda: test_func(mock_git.apply_changes.call_args[0][0])

    combo = engine._find_interaction_failure(changes, "base", None, max_combinations=10)
    assert combo == [0, 1]
    assert engine.interaction_failure == [0, 1]


def test_find_interaction_failure_hunks(mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
    """_find_interaction_failure exercises hunk testing branch."""
    from git_bifurcate.models import HunkChange

    hunks = [
        HunkChange("0", "f.py", 1, 1, 1, 1, 1, 1, "@@", ChangeStatus.UNKNOWN),
        HunkChange("1", "f.py", 2, 2, 2, 1, 2, 1, "@@", ChangeStatus.UNKNOWN),
    ]
    engine = BifurcationEngine(mock_git, mock_test_runner)

    def hunk_result(selected: list[HunkChange]) -> CommandResult:
        ids = {h.id for h in selected}
        return CommandResult.FAIL if ids == {"0", "1"} else CommandResult.PASS

    mock_git.apply_hunk_changes.side_effect = (
        lambda selected, *_args, **_kwargs: hunk_result(selected) != CommandResult.SKIP
    )
    mock_test_runner.run.side_effect = lambda: hunk_result(
        mock_git.apply_hunk_changes.call_args[0][0]
    )

    combo = engine._find_interaction_failure(hunks, "base", "bad", max_combinations=10)
    assert combo == [0, 1]
    assert engine.interaction_failure == [0, 1]


def test_find_interaction_failure_respects_limit(
    mock_git: MagicMock, mock_test_runner: MagicMock
) -> None:
    """Max combination budget returns None early."""
    changes = [
        FileChange("0", "f1", "modified", "d1", ChangeStatus.UNKNOWN),
        FileChange("1", "f2", "modified", "d2", ChangeStatus.UNKNOWN),
        FileChange("2", "f3", "modified", "d3", ChangeStatus.UNKNOWN),
    ]
    engine = BifurcationEngine(mock_git, mock_test_runner)

    mock_git.apply_changes.return_value = True
    mock_test_runner.run.return_value = CommandResult.PASS

    combo = engine._find_interaction_failure(changes, "base", None, max_combinations=0)
    assert combo is None
    assert engine.interaction_failure is None


def test_find_interaction_failure_with_dependencies(
    mock_git: MagicMock, mock_test_runner: MagicMock
) -> None:
    """_find_interaction_failure tries dependent pairs first."""
    changes = [
        FileChange("0", "f1", "modified", "d1", ChangeStatus.UNKNOWN, dependencies=[]),
        FileChange("1", "f2", "modified", "d2", ChangeStatus.UNKNOWN, dependencies=["0"]),
        FileChange("2", "f3", "modified", "d3", ChangeStatus.UNKNOWN, dependencies=[]),
    ]
    engine = BifurcationEngine(mock_git, mock_test_runner)

    def test_func(applied: list[FileChange], *_: object, **__: object) -> CommandResult:
        ids = {c.id for c in applied}
        # Only the dependent pair (0, 1) fails
        return CommandResult.FAIL if ids == {"0", "1"} else CommandResult.PASS

    mock_git.apply_changes.side_effect = lambda applied, *_args, **_kwargs: True
    mock_test_runner.run.side_effect = lambda: test_func(mock_git.apply_changes.call_args[0][0])

    combo = engine._find_interaction_failure(changes, "base", None, max_combinations=10)
    # Should find the dependent pair first
    assert combo == [0, 1]
    assert engine.interaction_failure == [0, 1]


def test_find_interaction_failure_dependent_pairs_max_limit(
    mock_git: MagicMock, mock_test_runner: MagicMock
) -> None:
    """_find_interaction_failure respects max_combinations during dependent pairs."""
    changes = [
        FileChange("0", "f1", "modified", "d1", ChangeStatus.UNKNOWN, dependencies=[]),
        FileChange("1", "f2", "modified", "d2", ChangeStatus.UNKNOWN, dependencies=["0"]),
        FileChange("2", "f3", "modified", "d3", ChangeStatus.UNKNOWN, dependencies=["0"]),
    ]
    engine = BifurcationEngine(mock_git, mock_test_runner)

    mock_git.apply_changes.return_value = True
    mock_test_runner.run.return_value = CommandResult.PASS

    # Max 1 combination, should return None even with dependent pairs to check
    combo = engine._find_interaction_failure(changes, "base", None, max_combinations=1)
    assert combo is None


def test_find_interaction_failure_forward_dependency(
    mock_git: MagicMock, mock_test_runner: MagicMock
) -> None:
    """_find_interaction_failure handles forward dependencies (dep comes later)."""
    changes = [
        FileChange("0", "f1", "modified", "d1", ChangeStatus.UNKNOWN, dependencies=["1"]),
        FileChange("1", "f2", "modified", "d2", ChangeStatus.UNKNOWN, dependencies=[]),
        FileChange("2", "f3", "modified", "d3", ChangeStatus.UNKNOWN, dependencies=[]),
    ]
    engine = BifurcationEngine(mock_git, mock_test_runner)

    def test_func(applied: list[FileChange], *_: object, **__: object) -> CommandResult:
        ids = {c.id for c in applied}
        # The forward dependency pair (0, 1) fails
        return CommandResult.FAIL if ids == {"0", "1"} else CommandResult.PASS

    mock_git.apply_changes.side_effect = lambda applied, *_args, **_kwargs: True
    mock_test_runner.run.side_effect = lambda: test_func(mock_git.apply_changes.call_args[0][0])

    combo = engine._find_interaction_failure(changes, "base", None, max_combinations=10)
    # Should find the forward dependency pair
    assert set(combo) == {0, 1}
    assert engine.interaction_failure == combo


def test_report_interaction_outputs(monkeypatch: pytest.MonkeyPatch) -> None:
    """_report_interaction prints identified failing combos and handles no results."""
    engine = BifurcationEngine(MagicMock(spec=GitRepo), MagicMock(spec=CommandRunner))
    file_changes = [
        FileChange("0", "f1", "modified", "d1", ChangeStatus.UNKNOWN),
        FileChange("1", "f2", "modified", "d2", ChangeStatus.UNKNOWN),
    ]
    hunk_changes = [
        HunkChange("0", "f.py", 1, 1, 1, 1, 1, 1, "@@", ChangeStatus.UNKNOWN),
        HunkChange("1", "f.py", 2, 2, 2, 1, 2, 1, "@@", ChangeStatus.UNKNOWN),
    ]

    # Case: interaction found
    monkeypatch.setattr(
        engine,
        "_find_interaction_failure",
        lambda *args, **kwargs: engine.__setattr__("interaction_failure", [0, 1]) or [0, 1],
    )
    with patch("click.echo") as echo:
        engine._report_interaction(file_changes, "base", verbose=True)
        assert engine.interaction_failure == [0, 1]
        assert any("f1" in call.args[0] or "f2" in call.args[0] for call in echo.call_args_list)

    # Case: no interaction found
    monkeypatch.setattr(engine, "_find_interaction_failure", lambda *args, **kwargs: None)
    with patch("click.echo") as echo:
        engine._report_interaction(file_changes, "base", verbose=True)
        assert engine.interaction_failure is None
        assert any("No minimal failing combination" in call.args[0] for call in echo.call_args_list)

    # Case: hunk combo prints hunk-specific details
    monkeypatch.setattr(
        engine,
        "_find_interaction_failure",
        lambda *args, **kwargs: engine.__setattr__("interaction_failure", [0]) or [0],
    )
    with patch("click.echo") as echo:
        engine._report_interaction(hunk_changes, "base", verbose=True, bad_commit="bad")
        assert any("f.py" in call.args[0] for call in echo.call_args_list)
