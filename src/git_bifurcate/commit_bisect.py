"""Commit-level bisection with submodule support and cache warming.

This module provides enhanced commit-level bisection that integrates with
file/hunk-level bifurcation, handles submodules intelligently, and warms
caches for improved performance.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click

from git_bifurcate.git_ops import GitRepo
from git_bifurcate.models import CommandResult
from git_bifurcate.test_runner import CommandRunner


@dataclass
class CommitInfo:
    """Information about a commit."""

    sha: str
    parent_sha: str | None
    message: str
    author: str
    timestamp: int
    submodule_commits: dict[str, str]  # path -> commit sha


@dataclass
class BisectState:
    """State for commit-level bisection."""

    good_commit: str
    bad_commit: str
    remaining_commits: list[str]
    tested_commits: dict[str, CommandResult]
    current_iteration: int
    submodule_states: dict[str, dict[str, str]]  # commit -> {submodule_path -> sha}


class CommitBisector:
    """Performs intelligent commit-level bisection."""

    def __init__(self, git_repo: GitRepo, test_runner: CommandRunner) -> None:
        """Initialize commit bisector.

        Args:
            git_repo: Git repository wrapper.
            test_runner: Test execution wrapper.
        """
        self.git = git_repo
        self.test_runner = test_runner
        self.cache_warmed = False

    def get_commit_info(self, commit_sha: str) -> CommitInfo:
        """Get detailed information about a commit.

        Args:
            commit_sha: Commit SHA to query.

        Returns:
            CommitInfo object with commit details.
        """
        # Get commit metadata
        result = self.git.repo.git.show(commit_sha, format="%H%n%P%n%s%n%an%n%at", s=True)
        lines = result.split("\n")

        sha = lines[0]
        parent_sha = lines[1].split()[0] if lines[1] else None
        message = lines[2]
        author = lines[3]
        timestamp = int(lines[4])

        # Get submodule commits at this state
        submodule_commits = self._get_submodule_commits(commit_sha)

        return CommitInfo(
            sha=sha,
            parent_sha=parent_sha,
            message=message,
            author=author,
            timestamp=timestamp,
            submodule_commits=submodule_commits,
        )

    def _get_submodule_commits(self, commit_sha: str) -> dict[str, str]:
        """Get submodule commit SHAs at a specific commit.

        Args:
            commit_sha: Commit to query.

        Returns:
            Dictionary mapping submodule paths to their commit SHAs.
        """
        submodule_commits = {}

        try:
            # Get .gitmodules content at this commit
            gitmodules = self.git.repo.git.show(f"{commit_sha}:.gitmodules")
            # Parse submodule paths
            current_path = None
            for line in gitmodules.split("\n"):
                line = line.strip()
                if line.startswith("[submodule"):
                    current_path = None
                elif line.startswith("path ="):
                    current_path = line.split("=", 1)[1].strip()
                    if current_path:
                        # Get submodule commit at this state
                        try:
                            submodule_sha = self.git.repo.git.ls_tree(
                                commit_sha, current_path
                            ).split()[2]
                            submodule_commits[current_path] = submodule_sha
                        except Exception:
                            pass
        except Exception:
            # No submodules or error reading them
            pass

        return submodule_commits

    def bisect_commits(
        self, good_commit: str, bad_commit: str, verbose: bool = True
    ) -> str | None:
        """Perform binary search through commits to find first bad commit.

        Args:
            good_commit: Known good commit SHA.
            bad_commit: Known bad commit SHA.
            verbose: Whether to print progress messages.

        Returns:
            SHA of first bad commit, or None if not found.
        """
        # Get commit range
        commits = self._get_commit_range(good_commit, bad_commit)

        if not commits:
            if verbose:
                click.echo("No commits to bisect between good and bad.")
            return None

        if verbose:
            click.echo(f"Bisecting {len(commits)} commits between {good_commit[:8]} and {bad_commit[:8]}")

        # Warm caches if enabled
        if not self.cache_warmed:
            self._warm_caches(commits, verbose)

        # Binary search
        tested: dict[str, CommandResult] = {}
        search_space = list(range(len(commits)))
        iteration = 0

        while len(search_space) > 1:
            iteration += 1
            mid = len(search_space) // 2
            test_idx = search_space[mid]
            test_commit = commits[test_idx]

            if verbose:
                commit_info = self.get_commit_info(test_commit)
                click.echo(
                    f"\nIteration {iteration}: Testing commit {test_commit[:8]} "
                    f"({mid + 1}/{len(commits)})"
                )
                click.echo(f"  {commit_info.message}")

            # Test this commit
            result = self._test_commit(test_commit, verbose)
            tested[test_commit] = result

            if result == CommandResult.FAIL:
                # Bug is in first half (including this commit)
                search_space = search_space[:mid + 1]
                if verbose:
                    click.echo(f"  Result: FAIL - narrowing to earlier commits")
            elif result == CommandResult.PASS:
                # Bug is in second half (after this commit)
                search_space = search_space[mid + 1 :]
                if verbose:
                    click.echo(f"  Result: PASS - narrowing to later commits")
            else:
                # Skip or error - try to continue
                if verbose:
                    click.echo(f"  Result: {result.value} - skipping this commit")
                # Remove this commit and try next
                search_space.pop(mid)

        # Found the first bad commit
        if search_space:
            first_bad = commits[search_space[0]]
            if verbose:
                commit_info = self.get_commit_info(first_bad)
                click.echo(f"\nFirst bad commit found after {iteration} iterations:")
                click.echo(f"  {first_bad}")
                click.echo(f"  {commit_info.message}")
                click.echo(f"  Author: {commit_info.author}")

            return first_bad

        return None

    def _get_commit_range(self, good_commit: str, bad_commit: str) -> list[str]:
        """Get list of commits between good and bad (inclusive).

        Args:
            good_commit: Good commit SHA.
            bad_commit: Bad commit SHA.

        Returns:
            List of commit SHAs in chronological order.
        """
        try:
            # Get commits from good to bad (exclusive of good, inclusive of bad)
            result = self.git.repo.git.rev_list(
                f"{good_commit}..{bad_commit}", reverse=True
            )
            if result:
                return result.split("\n")
            return []
        except Exception:
            return []

    def _test_commit(self, commit_sha: str, verbose: bool = False) -> CommandResult:
        """Test a specific commit.

        Args:
            commit_sha: Commit to test.
            verbose: Whether to show output.

        Returns:
            Test result.
        """
        try:
            # Checkout commit
            self.git.checkout(commit_sha)

            # Update submodules if present
            self._update_submodules(commit_sha, verbose)

            # Run test
            result = self.test_runner.run()

            return result

        except Exception as e:
            if verbose:
                click.echo(f"  Error testing commit: {e}")
            return CommandResult.ERROR

    def _update_submodules(self, commit_sha: str, verbose: bool = False) -> None:
        """Update submodules to their correct state for a commit.

        Args:
            commit_sha: Commit whose submodule state to restore.
            verbose: Whether to show progress.
        """
        try:
            submodule_commits = self._get_submodule_commits(commit_sha)

            if not submodule_commits:
                return

            if verbose:
                click.echo(f"  Updating {len(submodule_commits)} submodules...")

            # Initialize submodules if needed
            self.git.repo.git.submodule("update", "--init", "--recursive")

            # Checkout correct commit in each submodule
            for path, sha in submodule_commits.items():
                try:
                    submodule_path = Path(self.git.repo.working_dir) / path
                    if submodule_path.exists():
                        subprocess.run(
                            ["git", "checkout", sha],
                            cwd=submodule_path,
                            capture_output=True,
                            check=True,
                        )
                except Exception as e:
                    if verbose:
                        click.echo(f"    Warning: Failed to update submodule {path}: {e}")

        except Exception:
            # Submodule update failed, continue anyway
            pass

    def _warm_caches(self, commits: list[str], verbose: bool = False) -> None:
        """Warm git object caches by accessing commit data.

        Args:
            commits: List of commits to warm cache for.
            verbose: Whether to show progress.
        """
        if verbose:
            click.echo("Warming caches...")

        try:
            # Access commit objects to load into cache
            for commit in commits:
                # This loads the commit object and its tree
                self.git.repo.commit(commit)

            # Pre-fetch diffs for faster access later
            for i in range(len(commits) - 1):
                try:
                    self.git.repo.git.diff(commits[i], commits[i + 1], stat=True)
                except Exception:
                    pass

            self.cache_warmed = True

            if verbose:
                click.echo(f"  Warmed cache for {len(commits)} commits")

        except Exception:
            # Cache warming failed, not critical
            pass

    def get_bisect_stats(self, good_commit: str, bad_commit: str) -> dict[str, Any]:
        """Get statistics about a potential bisect operation.

        Args:
            good_commit: Good commit SHA.
            bad_commit: Bad commit SHA.

        Returns:
            Dictionary with statistics.
        """
        commits = self._get_commit_range(good_commit, bad_commit)

        return {
            "total_commits": len(commits),
            "estimated_iterations": len(commits).bit_length(),  # log2(n)
            "has_submodules": any(self._get_submodule_commits(c) for c in commits[:10]),
        }


def warm_git_cache(repo_path: Path, commits: list[str] | None = None) -> None:
    """Warm git object cache for improved performance.

    Args:
        repo_path: Path to git repository.
        commits: Optional list of commits to warm. If None, warms recent history.
    """
    try:
        import git

        repo = git.Repo(repo_path)

        if commits is None:
            # Get recent commits
            commits = [c.hexsha for c in repo.iter_commits(max_count=100)]

        # Load commit objects
        for commit_sha in commits:
            repo.commit(commit_sha)

    except Exception:
        pass  # Cache warming is best-effort
