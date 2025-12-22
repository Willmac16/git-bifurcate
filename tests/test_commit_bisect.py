"""Tests for commit-level bisection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from git_bifurcate.commit_bisect import CommitBisector, CommitInfo, warm_git_cache
from git_bifurcate.models import CommandResult
from git_bifurcate.test_runner import CommandRunner


@pytest.fixture
def mock_git() -> MagicMock:
    """Create mock GitRepo."""
    mock = MagicMock()
    mock.repo = MagicMock()
    return mock


@pytest.fixture
def mock_test_runner() -> MagicMock:
    """Create mock CommandRunner."""
    return MagicMock(spec=CommandRunner)


class TestCommitInfo:
    """Tests for CommitInfo dataclass."""

    def test_commit_info_creation(self) -> None:
        """Test creating CommitInfo."""
        info = CommitInfo(
            sha="abc123",
            parent_sha="def456",
            message="Test commit",
            author="Test Author",
            timestamp=1234567890,
            submodule_commits={"sub/path": "ghi789"},
        )

        assert info.sha == "abc123"
        assert info.parent_sha == "def456"
        assert info.message == "Test commit"
        assert info.author == "Test Author"
        assert info.timestamp == 1234567890
        assert info.submodule_commits == {"sub/path": "ghi789"}


class TestCommitBisector:
    """Tests for CommitBisector class."""

    def test_commit_bisector_creation(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test creating CommitBisector."""
        bisector = CommitBisector(mock_git, mock_test_runner)

        assert bisector.git == mock_git
        assert bisector.test_runner == mock_test_runner
        assert bisector.cache_warmed is False

    def test_get_commit_info(self, mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
        """Test getting commit information."""
        mock_git.repo.git.show.return_value = (
            "abc123\ndef456\nTest commit\nJohn Doe\n1234567890"
        )

        bisector = CommitBisector(mock_git, mock_test_runner)
        info = bisector.get_commit_info("abc123")

        assert info.sha == "abc123"
        assert info.parent_sha == "def456"
        assert info.message == "Test commit"
        assert info.author == "John Doe"
        assert info.timestamp == 1234567890

    def test_get_commit_info_no_parent(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test getting info for initial commit (no parent)."""
        mock_git.repo.git.show.return_value = "abc123\n\nInitial commit\nJohn Doe\n1234567890"

        bisector = CommitBisector(mock_git, mock_test_runner)
        info = bisector.get_commit_info("abc123")

        assert info.sha == "abc123"
        assert info.parent_sha is None

    def test_get_submodule_commits(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test getting submodule commits."""
        mock_git.repo.git.show.return_value = "[submodule test]\n\tpath = sub/path"
        mock_git.repo.git.ls_tree.return_value = "160000 commit ghi789\tsub/path"

        bisector = CommitBisector(mock_git, mock_test_runner)
        submodules = bisector._get_submodule_commits("abc123")

        assert submodules == {"sub/path": "ghi789"}

    def test_get_submodule_commits_no_submodules(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test getting submodule commits when there are none."""
        mock_git.repo.git.show.side_effect = Exception("No .gitmodules")

        bisector = CommitBisector(mock_git, mock_test_runner)
        submodules = bisector._get_submodule_commits("abc123")

        assert submodules == {}

    def test_get_commit_range(self, mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
        """Test getting commit range."""
        mock_git.repo.git.rev_list.return_value = "commit1\ncommit2\ncommit3"

        bisector = CommitBisector(mock_git, mock_test_runner)
        commits = bisector._get_commit_range("good", "bad")

        assert commits == ["commit1", "commit2", "commit3"]
        mock_git.repo.git.rev_list.assert_called_once_with("good..bad", reverse=True)

    def test_get_commit_range_empty(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test getting empty commit range."""
        mock_git.repo.git.rev_list.return_value = ""

        bisector = CommitBisector(mock_git, mock_test_runner)
        commits = bisector._get_commit_range("good", "bad")

        assert commits == []

    def test_get_commit_range_error(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test error getting commit range."""
        mock_git.repo.git.rev_list.side_effect = Exception("Error")

        bisector = CommitBisector(mock_git, mock_test_runner)
        commits = bisector._get_commit_range("good", "bad")

        assert commits == []

    def test_test_commit_success(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test testing a commit successfully."""
        mock_test_runner.run.return_value = CommandResult.PASS

        bisector = CommitBisector(mock_git, mock_test_runner)
        result = bisector._test_commit("abc123", verbose=False)

        assert result == CommandResult.PASS
        mock_git.checkout.assert_called_once_with("abc123")
        mock_test_runner.run.assert_called_once()

    def test_test_commit_failure(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test testing a commit that fails."""
        mock_test_runner.run.return_value = CommandResult.FAIL

        bisector = CommitBisector(mock_git, mock_test_runner)
        result = bisector._test_commit("abc123", verbose=False)

        assert result == CommandResult.FAIL

    def test_test_commit_error(self, mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
        """Test error during commit testing."""
        mock_git.checkout.side_effect = Exception("Checkout error")

        bisector = CommitBisector(mock_git, mock_test_runner)
        result = bisector._test_commit("abc123", verbose=False)

        assert result == CommandResult.ERROR

    def test_update_submodules(self, mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
        """Test updating submodules."""
        mock_git.repo.git.show.return_value = "[submodule test]\n\tpath = sub/path"
        mock_git.repo.git.ls_tree.return_value = "160000 commit ghi789\tsub/path"
        mock_git.repo.working_dir = "/fake/path"

        bisector = CommitBisector(mock_git, mock_test_runner)

        with patch("subprocess.run"), patch("pathlib.Path.exists", return_value=True):
            bisector._update_submodules("abc123", verbose=False)

            mock_git.repo.git.submodule.assert_called_once_with(
                "update", "--init", "--recursive"
            )

    def test_update_submodules_error(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test error updating submodules."""
        mock_git.repo.git.show.side_effect = Exception("Error")

        bisector = CommitBisector(mock_git, mock_test_runner)
        # Should not raise
        bisector._update_submodules("abc123", verbose=False)

    def test_warm_caches(self, mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
        """Test warming git caches."""
        commits = ["commit1", "commit2", "commit3"]

        bisector = CommitBisector(mock_git, mock_test_runner)
        bisector._warm_caches(commits, verbose=False)

        assert bisector.cache_warmed is True

    def test_warm_caches_error(self, mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
        """Test error during cache warming."""
        commits = ["commit1"]
        mock_git.repo.commit.side_effect = Exception("Error")

        bisector = CommitBisector(mock_git, mock_test_runner)
        # Should not raise
        bisector._warm_caches(commits, verbose=False)

    def test_bisect_commits_no_commits(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test bisecting with no commits."""
        mock_git.repo.git.rev_list.return_value = ""

        bisector = CommitBisector(mock_git, mock_test_runner)
        result = bisector.bisect_commits("good", "bad", verbose=False)

        assert result is None

    def test_bisect_commits_single_bad(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test bisecting to find single bad commit."""
        mock_git.repo.git.rev_list.return_value = "commit1"
        mock_git.repo.git.show.return_value = (
            "commit1\ncommit0\nBad commit\nJohn Doe\n1234567890"
        )
        mock_test_runner.run.return_value = CommandResult.FAIL

        bisector = CommitBisector(mock_git, mock_test_runner)
        result = bisector.bisect_commits("good", "bad", verbose=False)

        assert result == "commit1"

    def test_bisect_commits_with_skip(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test bisecting when some commits are skipped."""
        commits = ["commit1", "commit2", "commit3"]
        mock_git.repo.git.rev_list.return_value = "\n".join(commits)
        mock_git.repo.git.show.return_value = (
            "commit3\ncommit2\nFinal commit\nJohn Doe\n1234567890"
        )

        results = [CommandResult.SKIP, CommandResult.FAIL]
        mock_test_runner.run.side_effect = results

        bisector = CommitBisector(mock_git, mock_test_runner)
        result = bisector.bisect_commits("good", "bad", verbose=False)

        assert result in commits or result is None

    def test_get_bisect_stats(self, mock_git: MagicMock, mock_test_runner: MagicMock) -> None:
        """Test getting bisect statistics."""
        commits = ["commit1", "commit2", "commit3", "commit4"]
        mock_git.repo.git.rev_list.return_value = "\n".join(commits)
        mock_git.repo.git.show.return_value = ""

        bisector = CommitBisector(mock_git, mock_test_runner)
        stats = bisector.get_bisect_stats("good", "bad")

        assert stats["total_commits"] == 4
        assert stats["estimated_iterations"] == 3  # log2(4) + 1


    def test_bisect_commits_verbose_output(
        self, mock_git: MagicMock, mock_test_runner: MagicMock, capsys: pytest.CaptureFixture
    ) -> None:
        """Test bisecting with verbose output enabled."""
        commits = ["commit1", "commit2", "commit3"]
        mock_git.repo.git.rev_list.return_value = "\n".join(commits)
        mock_git.repo.git.show.return_value = (
            "commit2\ncommit1\nMiddle commit\nJohn Doe\n1234567890"
        )

        # First test returns PASS, then FAIL
        results = [CommandResult.PASS, CommandResult.FAIL]
        mock_test_runner.run.side_effect = results

        bisector = CommitBisector(mock_git, mock_test_runner)
        _ = bisector.bisect_commits("good", "bad", verbose=True)

        captured = capsys.readouterr()
        assert "Bisecting 3 commits" in captured.out
        assert "Iteration" in captured.out
        assert "First bad commit found" in captured.out

    def test_bisect_commits_verbose_skip_result(
        self, mock_git: MagicMock, mock_test_runner: MagicMock, capsys: pytest.CaptureFixture
    ) -> None:
        """Test bisecting with SKIP result and verbose output."""
        commits = ["commit1", "commit2", "commit3"]
        mock_git.repo.git.rev_list.return_value = "\n".join(commits)
        mock_git.repo.git.show.return_value = (
            "commit2\ncommit1\nMiddle commit\nJohn Doe\n1234567890"
        )

        # First test returns SKIP, then FAIL
        results = [CommandResult.SKIP, CommandResult.FAIL]
        mock_test_runner.run.side_effect = results

        bisector = CommitBisector(mock_git, mock_test_runner)
        _ = bisector.bisect_commits("good", "bad", verbose=True)

        captured = capsys.readouterr()
        assert "skipping this commit" in captured.out

    def test_bisect_commits_verbose_pass_result(
        self, mock_git: MagicMock, mock_test_runner: MagicMock, capsys: pytest.CaptureFixture
    ) -> None:
        """Test bisecting with PASS result and verbose output."""
        commits = ["commit1", "commit2", "commit3"]
        mock_git.repo.git.rev_list.return_value = "\n".join(commits)
        mock_git.repo.git.show.return_value = (
            "commit3\ncommit2\nLast commit\nJohn Doe\n1234567890"
        )

        # First test PASS, second FAIL
        results = [CommandResult.PASS, CommandResult.FAIL]
        mock_test_runner.run.side_effect = results

        bisector = CommitBisector(mock_git, mock_test_runner)
        _ = bisector.bisect_commits("good", "bad", verbose=True)

        captured = capsys.readouterr()
        assert "PASS" in captured.out

    def test_test_commit_verbose_error(
        self, mock_git: MagicMock, mock_test_runner: MagicMock, capsys: pytest.CaptureFixture
    ) -> None:
        """Test error during commit testing with verbose output."""
        mock_git.checkout.side_effect = Exception("Checkout error")

        bisector = CommitBisector(mock_git, mock_test_runner)
        result = bisector._test_commit("abc123", verbose=True)

        assert result == CommandResult.ERROR
        captured = capsys.readouterr()
        assert "Error testing commit" in captured.out

    def test_update_submodules_verbose(
        self, mock_git: MagicMock, mock_test_runner: MagicMock, capsys: pytest.CaptureFixture
    ) -> None:
        """Test updating submodules with verbose output."""
        mock_git.repo.git.show.return_value = "[submodule test]\n\tpath = sub/path"
        mock_git.repo.git.ls_tree.return_value = "160000 commit ghi789\tsub/path"
        mock_git.repo.working_dir = "/fake/path"

        bisector = CommitBisector(mock_git, mock_test_runner)

        with patch("subprocess.run"), patch("pathlib.Path.exists", return_value=True):
            bisector._update_submodules("abc123", verbose=True)

            captured = capsys.readouterr()
            assert "Updating 1 submodules" in captured.out

    def test_update_submodules_checkout_error(
        self, mock_git: MagicMock, mock_test_runner: MagicMock, capsys: pytest.CaptureFixture
    ) -> None:
        """Test error during submodule checkout with verbose output."""
        mock_git.repo.git.show.return_value = "[submodule test]\n\tpath = sub/path"
        mock_git.repo.git.ls_tree.return_value = "160000 commit ghi789\tsub/path"
        mock_git.repo.working_dir = "/fake/path"

        bisector = CommitBisector(mock_git, mock_test_runner)

        with patch("subprocess.run", side_effect=Exception("Checkout failed")), \
             patch("pathlib.Path.exists", return_value=True):
            bisector._update_submodules("abc123", verbose=True)

            captured = capsys.readouterr()
            assert "Warning: Failed to update submodule" in captured.out

    def test_warm_caches_verbose(
        self, mock_git: MagicMock, mock_test_runner: MagicMock, capsys: pytest.CaptureFixture
    ) -> None:
        """Test cache warming with verbose output."""
        commits = ["commit1", "commit2", "commit3"]

        bisector = CommitBisector(mock_git, mock_test_runner)
        bisector._warm_caches(commits, verbose=True)

        captured = capsys.readouterr()
        assert "Warming caches" in captured.out
        assert "Warmed cache for 3 commits" in captured.out

    def test_warm_caches_diff_error(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test cache warming with diff errors (should not raise)."""
        commits = ["commit1", "commit2"]
        mock_git.repo.git.diff.side_effect = Exception("Diff error")

        bisector = CommitBisector(mock_git, mock_test_runner)
        bisector._warm_caches(commits, verbose=False)

        # Should complete without raising
        assert bisector.cache_warmed is True

    def test_get_submodule_commits_parse_error(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test getting submodule commits with ls-tree error."""
        mock_git.repo.git.show.return_value = "[submodule test]\n\tpath = sub/path"
        mock_git.repo.git.ls_tree.side_effect = Exception("ls-tree error")

        bisector = CommitBisector(mock_git, mock_test_runner)
        submodules = bisector._get_submodule_commits("abc123")

        # Should handle error gracefully
        assert submodules == {}

    def test_bisect_commits_no_commits_verbose(
        self, mock_git: MagicMock, mock_test_runner: MagicMock, capsys: pytest.CaptureFixture
    ) -> None:
        """Test bisecting with no commits and verbose output."""
        mock_git.repo.git.rev_list.return_value = ""

        bisector = CommitBisector(mock_git, mock_test_runner)
        result = bisector.bisect_commits("good", "bad", verbose=True)

        assert result is None
        captured = capsys.readouterr()
        assert "No commits to bisect" in captured.out

    def test_bisect_commits_returns_none_verbose(
        self, mock_git: MagicMock, mock_test_runner: MagicMock, capsys: pytest.CaptureFixture
    ) -> None:
        """Test bisecting when search space becomes empty with verbose output."""
        commits = ["commit1", "commit2"]
        mock_git.repo.git.rev_list.return_value = "\n".join(commits)
        mock_git.repo.git.show.return_value = (
            "commit1\ncommit0\nCommit\nJohn Doe\n1234567890"
        )

        # Return PASS to narrow to second half, which will be empty
        # search_space = [0, 1], mid = 1, PASS -> search_space = [1+1:] = []
        mock_test_runner.run.return_value = CommandResult.PASS

        bisector = CommitBisector(mock_git, mock_test_runner)
        result = bisector.bisect_commits("good", "bad", verbose=True)

        # Should return None when search space empties
        assert result is None
        captured = capsys.readouterr()
        assert "Bisecting" in captured.out

    def test_update_submodules_general_error(
        self, mock_git: MagicMock, mock_test_runner: MagicMock
    ) -> None:
        """Test general error during submodule update."""
        mock_git.repo.git.show.return_value = "[submodule test]\n\tpath = sub/path"
        mock_git.repo.git.ls_tree.return_value = "160000 commit ghi789\tsub/path"
        mock_git.repo.git.submodule.side_effect = Exception("Submodule init error")

        bisector = CommitBisector(mock_git, mock_test_runner)
        # Should not raise, outer exception handler should catch
        bisector._update_submodules("abc123", verbose=False)


class TestWarmGitCache:
    """Tests for warm_git_cache function."""

    def test_warm_git_cache_with_commits(self) -> None:
        """Test warming cache with specific commits."""
        with patch("git.Repo") as mock_repo:
            repo_instance = MagicMock()
            mock_repo.return_value = repo_instance

            warm_git_cache(Path("/fake/path"), ["commit1", "commit2"])

            assert repo_instance.commit.call_count == 2

    def test_warm_git_cache_without_commits(self) -> None:
        """Test warming cache with recent history."""
        with patch("git.Repo") as mock_repo:
            repo_instance = MagicMock()
            mock_repo.return_value = repo_instance

            # Mock iter_commits to return some commits
            commit_mock = MagicMock()
            commit_mock.hexsha = "abc123"
            repo_instance.iter_commits.return_value = [commit_mock] * 10

            warm_git_cache(Path("/fake/path"), None)

            assert repo_instance.commit.call_count == 10

    def test_warm_git_cache_error(self) -> None:
        """Test error during cache warming."""
        with patch("git.Repo", side_effect=Exception("Error")):
            # Should not raise
            warm_git_cache(Path("/fake/path"), ["commit1"])
