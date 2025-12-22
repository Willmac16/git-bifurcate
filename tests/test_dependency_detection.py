"""Comprehensive tests for dependency detection in git-bifurcate.

This test suite ensures that dependency detection is both efficient and accurate,
covering edge cases, performance scenarios, and various types of dependencies.
"""

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


class TestBasicDependencyDetection:
    """Tests for basic dependency detection scenarios."""

    def test_simple_dependency_chain(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test A depends on B - A cannot be applied without B."""
        changes = [
            FileChange("0", "module.py", "added", "diff0", ChangeStatus.UNKNOWN),  # Defines func
            FileChange("1", "caller.py", "added", "diff1", ChangeStatus.UNKNOWN),  # Imports func
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)

        # Simulate: change 1 (caller) cannot be applied without change 0 (module)
        def mock_apply(
            applied_changes: list[FileChange], base: str, use_temp_branch: bool = True
        ) -> bool:
            applied_ids = {c.id for c in applied_changes}
            # Caller alone fails (missing import)
            if applied_ids == {"1"}:
                return False
            return True

        mock_git.apply_changes.side_effect = mock_apply
        mock_test_runner.run.return_value = CommandResult.PASS

        # Test that dependency is detected via SKIP result
        result = engine._test_changes(changes, "base", [1])
        assert result == CommandResult.SKIP

        # Test that both together work
        result = engine._test_changes(changes, "base", [0, 1])
        assert result == CommandResult.PASS

    def test_no_dependency(self, mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
        """Test independent changes that can be applied separately."""
        changes = [
            FileChange("0", "file1.py", "modified", "diff0", ChangeStatus.UNKNOWN),
            FileChange("1", "file2.py", "modified", "diff1", ChangeStatus.UNKNOWN),
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)
        mock_git.apply_changes.return_value = True
        mock_test_runner.run.return_value = CommandResult.PASS

        # Both should be testable independently
        result1 = engine._test_changes(changes, "base", [0])
        assert result1 == CommandResult.PASS

        result2 = engine._test_changes(changes, "base", [1])
        assert result2 == CommandResult.PASS

    def test_mutual_dependency(self, mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
        """Test circular dependency where A and B depend on each other."""
        changes = [
            FileChange("0", "file1.py", "modified", "diff0", ChangeStatus.UNKNOWN),
            FileChange("1", "file2.py", "modified", "diff1", ChangeStatus.UNKNOWN),
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)

        # Neither can be applied alone
        def mock_apply(
            applied_changes: list[FileChange], base: str, use_temp_branch: bool = True
        ) -> bool:
            applied_ids = {c.id for c in applied_changes}
            # Only works when both are together
            return applied_ids == {"0", "1"}

        mock_git.apply_changes.side_effect = mock_apply
        mock_test_runner.run.return_value = CommandResult.PASS

        # Individual changes fail to apply
        assert engine._test_changes(changes, "base", [0]) == CommandResult.SKIP
        assert engine._test_changes(changes, "base", [1]) == CommandResult.SKIP

        # Together they work
        assert engine._test_changes(changes, "base", [0, 1]) == CommandResult.PASS

    def test_transitive_dependency(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test A->B->C dependency chain."""
        changes = [
            FileChange("0", "base.py", "added", "diff0", ChangeStatus.UNKNOWN),  # Base
            FileChange("1", "middle.py", "added", "diff1", ChangeStatus.UNKNOWN),  # Imports base
            FileChange("2", "top.py", "added", "diff2", ChangeStatus.UNKNOWN),  # Imports middle
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)

        def mock_apply(
            applied_changes: list[FileChange], base: str, use_temp_branch: bool = True
        ) -> bool:
            applied_ids = {c.id for c in applied_changes}
            # middle needs base
            if "1" in applied_ids and "0" not in applied_ids:
                return False
            # top needs middle (and transitively base)
            if "2" in applied_ids and "1" not in applied_ids:
                return False
            return True

        mock_git.apply_changes.side_effect = mock_apply
        mock_test_runner.run.return_value = CommandResult.PASS

        # Verify dependency chain
        assert engine._test_changes(changes, "base", [1]) == CommandResult.SKIP
        assert engine._test_changes(changes, "base", [2]) == CommandResult.SKIP
        assert engine._test_changes(changes, "base", [0, 1]) == CommandResult.PASS
        assert engine._test_changes(changes, "base", [0, 1, 2]) == CommandResult.PASS


class TestDependencyInBifurcation:
    """Tests for dependency handling during binary search."""

    def test_bifurcation_with_dependency_skip(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Binary search should handle SKIP results gracefully."""
        changes = [
            FileChange("0", "base.py", "added", "diff0", ChangeStatus.UNKNOWN),
            FileChange("1", "dependent.py", "added", "diff1", ChangeStatus.UNKNOWN),  # Needs 0
            FileChange("2", "bug.py", "added", "diff2", ChangeStatus.UNKNOWN),  # Has bug
            FileChange("3", "other.py", "added", "diff3", ChangeStatus.UNKNOWN),
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)

        def mock_apply(
            applied_changes: list[FileChange], base: str, use_temp_branch: bool = True
        ) -> bool:
            applied_ids = {c.id for c in applied_changes}
            # dependent needs base
            if "1" in applied_ids and "0" not in applied_ids:
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

        # Should find bug despite dependency issues
        result = engine.bifurcate_files(changes, "base", verbose=False)
        assert result is not None
        assert result.id == "2"

    def test_bifurcation_both_halves_skip(
        self, mock_git: MagicMock, mock_test_runner: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """When both halves have dependency issues, bifurcation should warn and exit."""
        changes = [
            FileChange("0", "file1.py", "modified", "diff0", ChangeStatus.UNKNOWN),
            FileChange("1", "file2.py", "modified", "diff1", ChangeStatus.UNKNOWN),
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)
        # Both halves fail to apply
        mock_git.apply_changes.return_value = False

        result = engine.bifurcate_files(changes, "base", verbose=True)
        assert result is None

        captured = capsys.readouterr()
        assert "Too many build failures" in captured.out or "dependency" in captured.out.lower()

    def test_bifurcation_recovers_from_skip(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Binary search should try upper half when lower half skips."""
        changes = [
            FileChange("0", "dep1.py", "modified", "diff0", ChangeStatus.UNKNOWN),
            FileChange("1", "dep2.py", "modified", "diff1", ChangeStatus.UNKNOWN),
            FileChange("2", "independent.py", "modified", "diff2", ChangeStatus.UNKNOWN),
            FileChange("3", "bug.py", "modified", "diff3", ChangeStatus.UNKNOWN),  # Bug
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)

        def mock_apply(
            applied_changes: list[FileChange], base: str, use_temp_branch: bool = True
        ) -> bool:
            applied_ids = {c.id for c in applied_changes}
            # Lower half (0, 1) has dependency issues
            if applied_ids == {"0", "1"}:
                return False
            return True

        mock_git.apply_changes.side_effect = mock_apply

        def mock_run() -> CommandResult:
            call_args = mock_git.apply_changes.call_args
            if call_args:
                applied_changes = call_args[0][0]
                applied_ids = {c.id for c in applied_changes}
                if "3" in applied_ids:
                    return CommandResult.FAIL
                return CommandResult.PASS
            return CommandResult.PASS

        mock_test_runner.run.side_effect = mock_run

        result = engine.bifurcate_files(changes, "base", verbose=False)
        assert result is not None
        assert result.id == "3"


class TestHunkDependencies:
    """Tests for hunk-level dependency detection."""

    def test_hunk_dependency_within_file(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test hunks that depend on each other within the same file."""
        hunks = [
            HunkChange(
                "0", "file.py", 1, 5, 1, 3, 1, 5, "def foo():\n    pass", ChangeStatus.UNKNOWN
            ),
            HunkChange(
                "1", "file.py", 10, 15, 10, 3, 10, 5, "foo()", ChangeStatus.UNKNOWN
            ),  # Calls foo
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)

        def mock_apply(
            selected_hunks: list[HunkChange],
            base_commit: str,
            bad_commit: str,
            use_temp_branch: bool = True,
        ) -> bool:
            hunk_ids = {h.id for h in selected_hunks}
            # Hunk 1 (call) needs hunk 0 (definition)
            if "1" in hunk_ids and "0" not in hunk_ids:
                return False
            return True

        mock_git.apply_hunk_changes.side_effect = mock_apply
        mock_test_runner.run.return_value = CommandResult.PASS

        # Verify dependency
        result = engine._test_hunk_changes(hunks, "base", "bad", [1])
        assert result == CommandResult.SKIP

        result = engine._test_hunk_changes(hunks, "base", "bad", [0, 1])
        assert result == CommandResult.PASS

    def test_hunk_dependency_across_files(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test hunks in different files with dependencies."""
        hunks = [
            HunkChange("0", "a.py", 1, 5, 1, 3, 1, 5, "CONSTANT = 42", ChangeStatus.UNKNOWN),
            HunkChange(
                "1", "b.py", 1, 5, 1, 3, 1, 5, "from a import CONSTANT", ChangeStatus.UNKNOWN
            ),
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)

        def mock_apply(
            selected_hunks: list[HunkChange],
            base_commit: str,
            bad_commit: str,
            use_temp_branch: bool = True,
        ) -> bool:
            hunk_ids = {h.id for h in selected_hunks}
            # Import needs definition
            if "1" in hunk_ids and "0" not in hunk_ids:
                return False
            return True

        mock_git.apply_hunk_changes.side_effect = mock_apply
        mock_test_runner.run.return_value = CommandResult.PASS

        result = engine._test_hunk_changes(hunks, "base", "bad", [1])
        assert result == CommandResult.SKIP


class TestDependencyEfficiency:
    """Tests for dependency detection efficiency."""

    def test_caching_prevents_redundant_tests(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Verify that dependency checks are cached."""
        changes = [
            FileChange("0", "file1.py", "modified", "diff0", ChangeStatus.UNKNOWN),
            FileChange("1", "file2.py", "modified", "diff1", ChangeStatus.UNKNOWN),
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)
        mock_git.apply_changes.return_value = False  # Always skip

        # First call
        result1 = engine._test_changes(changes, "base", [0, 1])
        assert result1 == CommandResult.SKIP
        call_count_1 = mock_git.apply_changes.call_count

        # Second call with same indices should use cache
        result2 = engine._test_changes(changes, "base", [0, 1])
        assert result2 == CommandResult.SKIP
        call_count_2 = mock_git.apply_changes.call_count

        # Should not have made another git call
        assert call_count_1 == call_count_2

    def test_minimal_test_execution_with_dependencies(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Binary search should minimize tests even with dependencies."""
        changes = [
            FileChange(str(i), f"file{i}.py", "modified", f"diff{i}", ChangeStatus.UNKNOWN)
            for i in range(8)
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)
        mock_git.apply_changes.return_value = True

        # Bug in change 5
        def mock_run() -> CommandResult:
            call_args = mock_git.apply_changes.call_args
            if call_args:
                applied_changes = call_args[0][0]
                applied_ids = {c.id for c in applied_changes}
                if "5" in applied_ids:
                    return CommandResult.FAIL
                return CommandResult.PASS
            return CommandResult.PASS

        mock_test_runner.run.side_effect = mock_run

        result = engine.bifurcate_files(changes, "base", verbose=False)
        assert result is not None
        assert result.id == "5"

        stats = engine.get_stats()
        # Binary search on 8 items should take ~log2(8) = 3-4 iterations
        assert stats["tests_run"] <= 5

    def test_stats_track_skip_results(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Verify that SKIP results are tracked in statistics."""
        changes = [
            FileChange("0", "file1.py", "modified", "diff0", ChangeStatus.UNKNOWN),
            FileChange("1", "file2.py", "modified", "diff1", ChangeStatus.UNKNOWN),
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)

        # First test skips
        mock_git.apply_changes.return_value = False
        engine._test_changes(changes, "base", [0])

        # Second test passes
        mock_git.apply_changes.return_value = True
        mock_test_runner.run.return_value = CommandResult.PASS
        engine._test_changes(changes, "base", [1])

        stats = engine.get_stats()
        assert stats["skipped"] == 1
        assert stats["passed"] == 1
        assert stats["tests_run"] == 2


class TestInteractionDetection:
    """Tests for detecting interacting changes."""

    def test_interaction_detection_finds_minimal_pair(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Interaction detection should find smallest failing combination."""
        changes = [
            FileChange("0", "a.py", "modified", "diff0", ChangeStatus.UNKNOWN),
            FileChange("1", "b.py", "modified", "diff1", ChangeStatus.UNKNOWN),
            FileChange("2", "c.py", "modified", "diff2", ChangeStatus.UNKNOWN),
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)
        mock_git.apply_changes.return_value = True

        # Only combination [0, 2] fails
        def mock_run() -> CommandResult:
            call_args = mock_git.apply_changes.call_args
            if call_args:
                applied_changes = call_args[0][0]
                applied_ids = {c.id for c in applied_changes}
                if applied_ids == {"0", "2"}:
                    return CommandResult.FAIL
                return CommandResult.PASS
            return CommandResult.PASS

        mock_test_runner.run.side_effect = mock_run

        result = engine._find_interaction_failure(changes, "base", None, max_combinations=64)
        assert result == [0, 2]

    def test_interaction_detection_respects_budget(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Interaction detection should stop at max_combinations."""
        changes = [
            FileChange(str(i), f"file{i}.py", "modified", f"diff{i}", ChangeStatus.UNKNOWN)
            for i in range(10)
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)
        mock_git.apply_changes.return_value = True
        mock_test_runner.run.return_value = CommandResult.PASS

        # Set very low budget
        result = engine._find_interaction_failure(changes, "base", None, max_combinations=2)
        assert result is None

        # Should have tested at most 2 combinations
        stats = engine.get_stats()
        assert stats["tests_run"] <= 2

    def test_interaction_detection_handles_skip(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Interaction detection should handle SKIP results."""
        changes = [
            FileChange("0", "a.py", "modified", "diff0", ChangeStatus.UNKNOWN),
            FileChange("1", "b.py", "modified", "diff1", ChangeStatus.UNKNOWN),
            FileChange("2", "c.py", "modified", "diff2", ChangeStatus.UNKNOWN),
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)

        # Some combinations skip, one fails
        def mock_apply(
            applied_changes: list[FileChange], base: str, use_temp_branch: bool = True
        ) -> bool:
            applied_ids = {c.id for c in applied_changes}
            # [0, 1] has dependency issues
            if applied_ids == {"0", "1"}:
                return False
            return True

        mock_git.apply_changes.side_effect = mock_apply

        def mock_run() -> CommandResult:
            call_args = mock_git.apply_changes.call_args
            if call_args:
                applied_changes = call_args[0][0]
                applied_ids = {c.id for c in applied_changes}
                if applied_ids == {"1", "2"}:
                    return CommandResult.FAIL
                return CommandResult.PASS
            return CommandResult.PASS

        mock_test_runner.run.side_effect = mock_run

        result = engine._find_interaction_failure(changes, "base", None, max_combinations=64)
        assert result == [1, 2]


class TestComplexDependencyScenarios:
    """Tests for complex dependency scenarios."""

    def test_diamond_dependency(self, mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
        """Test diamond dependency: A->B, A->C, B->D, C->D."""
        changes = [
            FileChange("0", "base.py", "added", "diff0", ChangeStatus.UNKNOWN),  # A
            FileChange("1", "left.py", "added", "diff1", ChangeStatus.UNKNOWN),  # B needs A
            FileChange("2", "right.py", "added", "diff2", ChangeStatus.UNKNOWN),  # C needs A
            FileChange("3", "top.py", "added", "diff3", ChangeStatus.UNKNOWN),  # D needs B,C
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)

        def mock_apply(
            applied_changes: list[FileChange], base: str, use_temp_branch: bool = True
        ) -> bool:
            applied_ids = {c.id for c in applied_changes}
            # B and C need A
            if ("1" in applied_ids or "2" in applied_ids) and "0" not in applied_ids:
                return False
            # D needs both B and C (and transitively A)
            if "3" in applied_ids and not ({"1", "2"}.issubset(applied_ids)):
                return False
            return True

        mock_git.apply_changes.side_effect = mock_apply
        mock_test_runner.run.return_value = CommandResult.PASS

        # Verify various combinations
        assert engine._test_changes(changes, "base", [0]) == CommandResult.PASS
        assert engine._test_changes(changes, "base", [1]) == CommandResult.SKIP
        assert engine._test_changes(changes, "base", [3]) == CommandResult.SKIP
        assert engine._test_changes(changes, "base", [0, 1]) == CommandResult.PASS
        assert engine._test_changes(changes, "base", [0, 1, 2, 3]) == CommandResult.PASS

    def test_partial_dependency_with_bug(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test scenario where some changes depend on each other and one has a bug."""
        changes = [
            FileChange("0", "lib.py", "added", "diff0", ChangeStatus.UNKNOWN),
            FileChange("1", "uses_lib.py", "added", "diff1", ChangeStatus.UNKNOWN),  # Needs 0
            FileChange("2", "bug.py", "added", "diff2", ChangeStatus.UNKNOWN),  # Has bug
            FileChange("3", "other.py", "added", "diff3", ChangeStatus.UNKNOWN),
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)

        def mock_apply(
            applied_changes: list[FileChange], base: str, use_temp_branch: bool = True
        ) -> bool:
            applied_ids = {c.id for c in applied_changes}
            # 1 needs 0
            if "1" in applied_ids and "0" not in applied_ids:
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

        # Should find the bug
        result = engine.bifurcate_files(changes, "base", verbose=False)
        assert result is not None
        assert result.id == "2"

    def test_multiple_independent_dependency_chains(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test multiple independent chains: A->B and C->D."""
        changes = [
            FileChange("0", "a.py", "added", "diff0", ChangeStatus.UNKNOWN),  # A
            FileChange("1", "b.py", "added", "diff1", ChangeStatus.UNKNOWN),  # B needs A
            FileChange("2", "c.py", "added", "diff2", ChangeStatus.UNKNOWN),  # C
            FileChange("3", "d.py", "added", "diff3", ChangeStatus.UNKNOWN),  # D needs C
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)

        def mock_apply(
            applied_changes: list[FileChange], base: str, use_temp_branch: bool = True
        ) -> bool:
            applied_ids = {c.id for c in applied_changes}
            # B needs A
            if "1" in applied_ids and "0" not in applied_ids:
                return False
            # D needs C
            if "3" in applied_ids and "2" not in applied_ids:
                return False
            return True

        mock_git.apply_changes.side_effect = mock_apply
        mock_test_runner.run.return_value = CommandResult.PASS

        # Verify chains are independent
        assert engine._test_changes(changes, "base", [0]) == CommandResult.PASS
        assert engine._test_changes(changes, "base", [2]) == CommandResult.PASS
        assert engine._test_changes(changes, "base", [1]) == CommandResult.SKIP
        assert engine._test_changes(changes, "base", [3]) == CommandResult.SKIP
        assert engine._test_changes(changes, "base", [0, 1]) == CommandResult.PASS
        assert engine._test_changes(changes, "base", [2, 3]) == CommandResult.PASS


class TestEdgeCases:
    """Tests for edge cases in dependency detection."""

    def test_all_changes_interdependent(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test when all changes depend on all others."""
        changes = [
            FileChange("0", "file1.py", "modified", "diff0", ChangeStatus.UNKNOWN),
            FileChange("1", "file2.py", "modified", "diff1", ChangeStatus.UNKNOWN),
            FileChange("2", "file3.py", "modified", "diff2", ChangeStatus.UNKNOWN),
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)

        # Only all together works
        def mock_apply(
            applied_changes: list[FileChange], base: str, use_temp_branch: bool = True
        ) -> bool:
            return len(applied_changes) == 3

        mock_git.apply_changes.side_effect = mock_apply
        mock_test_runner.run.return_value = CommandResult.PASS

        # All combinations except full set should skip
        assert engine._test_changes(changes, "base", [0]) == CommandResult.SKIP
        assert engine._test_changes(changes, "base", [0, 1]) == CommandResult.SKIP
        assert engine._test_changes(changes, "base", [0, 1, 2]) == CommandResult.PASS

    def test_single_change_with_self_dependency(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test single change that cannot be applied (malformed patch)."""
        changes = [
            FileChange("0", "broken.py", "modified", "diff0", ChangeStatus.UNKNOWN),
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)
        mock_git.apply_changes.return_value = False

        result = engine._test_changes(changes, "base", [0])
        assert result == CommandResult.SKIP

    def test_dependency_varies_by_order(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test that cache correctly handles different orderings."""
        changes = [
            FileChange("0", "file1.py", "modified", "diff0", ChangeStatus.UNKNOWN),
            FileChange("1", "file2.py", "modified", "diff1", ChangeStatus.UNKNOWN),
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)
        mock_git.apply_changes.return_value = True
        mock_test_runner.run.return_value = CommandResult.PASS

        # Test both orders - should give same result due to cache key sorting
        result1 = engine._test_changes(changes, "base", [0, 1])
        result2 = engine._test_changes(changes, "base", [1, 0])

        assert result1 == result2 == CommandResult.PASS

        # Should have only called apply once due to caching
        assert mock_git.apply_changes.call_count == 1


class TestPerformance:
    """Performance and efficiency tests."""

    def test_large_dependency_chain(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test performance with long dependency chain."""
        # Create chain: 0->1->2->...->9
        changes = [
            FileChange(str(i), f"file{i}.py", "added", f"diff{i}", ChangeStatus.UNKNOWN)
            for i in range(10)
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)

        def mock_apply(
            applied_changes: list[FileChange], base: str, use_temp_branch: bool = True
        ) -> bool:
            applied_ids = {int(c.id) for c in applied_changes}
            # Each file i needs all files < i
            for file_id in applied_ids:
                required = set(range(file_id))
                if not required.issubset(applied_ids):
                    return False
            return True

        mock_git.apply_changes.side_effect = mock_apply
        mock_test_runner.run.return_value = CommandResult.PASS

        # Test a few key combinations
        assert engine._test_changes(changes, "base", [5]) == CommandResult.SKIP
        assert engine._test_changes(changes, "base", list(range(5))) == CommandResult.PASS
        assert engine._test_changes(changes, "base", list(range(10))) == CommandResult.PASS

    def test_wide_dependency_graph(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test with many files depending on a single base file."""
        # File 0 is base, files 1-9 all depend on it
        changes = [
            FileChange(str(i), f"file{i}.py", "added", f"diff{i}", ChangeStatus.UNKNOWN)
            for i in range(10)
        ]

        engine = BifurcationEngine(mock_git, mock_test_runner)

        def mock_apply(
            applied_changes: list[FileChange], base: str, use_temp_branch: bool = True
        ) -> bool:
            applied_ids = {c.id for c in applied_changes}
            # All files except 0 need file 0
            if applied_ids - {"0"} and "0" not in applied_ids:
                return False
            return True

        mock_git.apply_changes.side_effect = mock_apply
        mock_test_runner.run.return_value = CommandResult.PASS

        # Any file alone except 0 should fail
        assert engine._test_changes(changes, "base", [0]) == CommandResult.PASS
        assert engine._test_changes(changes, "base", [5]) == CommandResult.SKIP

        # Any file with 0 should work
        assert engine._test_changes(changes, "base", [0, 5]) == CommandResult.PASS
