"""Core bifurcation engine - binary search implementation."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import cast

import click

from git_bifurcate.git_ops import GitRepo
from git_bifurcate.models import CommandResult, FileChange, HunkChange
from git_bifurcate.test_runner import CommandRunner


class BifurcationEngine:
    """Implements binary search for finding breaking changes."""

    def __init__(self, git_repo: GitRepo, test_runner: CommandRunner) -> None:
        """Initialize bifurcation engine.

        Args:
            git_repo: Git repository wrapper.
            test_runner: Test execution wrapper.
        """
        self.git = git_repo
        self.test_runner = test_runner
        self.tested_combinations: dict[str, CommandResult] = {}
        self.interaction_failure: list[int] | None = None
        self.test_times: list[float] = []  # Track test execution times
        self.start_time: float | None = None

    def _get_combination_key(self, indices: list[int]) -> str:
        """Get cache key for a combination of changes."""
        return ",".join(map(str, sorted(indices)))

    def _test_changes(
        self, changes: list[FileChange], base_commit: str, indices: list[int]
    ) -> CommandResult:
        """Test a specific combination of changes.

        Args:
            changes: All available changes.
            base_commit: Commit to apply changes on top of.
            indices: Indices of changes to test.

        Returns:
            CommandResult from running tests.
        """
        # Check cache
        cache_key = self._get_combination_key(indices)
        if cache_key in self.tested_combinations:
            return self.tested_combinations[cache_key]

        # Select changes to test
        selected_changes = [changes[i] for i in indices]

        # Apply changes (don't use temp branches to avoid state issues)
        success = self.git.apply_changes(selected_changes, base_commit, use_temp_branch=False)

        if not success:
            # Failed to apply - likely dependency issues
            result = CommandResult.SKIP
        else:
            # Run test and track time
            test_start = time.time()
            result = self.test_runner.run()
            test_duration = time.time() - test_start
            self.test_times.append(test_duration)

        # Cache result
        self.tested_combinations[cache_key] = result

        # Always checkout base commit for next iteration (non-destructive)
        try:
            self.git.checkout(base_commit)
        except Exception:
            pass

        return result

    def bifurcate_files(
        self, changes: list[FileChange], base_commit: str, verbose: bool = True
    ) -> FileChange | None:
        """Binary search through file changes to find breaking change.

        Args:
            changes: List of FileChange objects to search through.
            base_commit: Commit SHA to apply changes on top of.
            verbose: Whether to print progress messages.

        Returns:
            The breaking FileChange, or None if not found.
        """
        search_space = list(range(len(changes)))
        iteration = 0
        self.start_time = time.time()

        while len(search_space) > 1:
            iteration += 1
            mid = len(search_space) // 2
            lower_half = search_space[:mid]
            upper_half = search_space[mid:]

            if verbose:
                # Calculate estimates
                remaining_iters = self.estimate_remaining_iterations(len(search_space))
                remaining_time = self.estimate_remaining_time(len(search_space))
                avg_time = self.get_average_test_time()

                progress_msg = (
                    f"Iteration {iteration}: Testing changes {lower_half[0] + 1}-"
                    f"{lower_half[-1] + 1} of {len(changes)}"
                )

                if avg_time > 0:
                    progress_msg += (
                        f" | Est. {remaining_iters} iterations remaining"
                        f" (~{self.format_time(remaining_time)})"
                    )

                click.echo(progress_msg)

            # Test lower half
            result = self._test_changes(changes, base_commit, lower_half)

            if result == CommandResult.FAIL:
                if verbose:
                    click.echo(f"  Result: FAIL - narrowing to changes {lower_half}")
                search_space = lower_half

            elif result == CommandResult.PASS:
                if verbose:
                    click.echo(f"  Result: PASS - narrowing to changes {upper_half}")
                search_space = upper_half

            else:  # SKIP or ERROR
                if verbose:
                    click.echo(f"  Result: {result.value} - trying upper half instead")
                # Try upper half when lower half won't build
                upper_result = self._test_changes(changes, base_commit, upper_half)

                if upper_result == CommandResult.FAIL:
                    search_space = upper_half
                elif upper_result == CommandResult.PASS:
                    # Complex case - might need to handle dependencies
                    click.echo(
                        "Warning: Lower half won't build but upper half passes. "
                        "This suggests dependency issues."
                    )
                    # For MVP, just continue with upper half
                    search_space = upper_half
                else:
                    # Both halves skip - complex dependency issue
                    click.echo("Error: Too many build failures. Possible dependency issues.")
                    break

        # Found single change
        if len(search_space) == 1:
            final_index = search_space[0]
            # Verify it actually breaks
            result = self._test_changes(changes, base_commit, [final_index])

            if result == CommandResult.FAIL:
                if verbose:
                    click.echo(f"\nFound breaking change after {iteration} iterations!")
                return changes[final_index]

            self._report_interaction(changes, base_commit, verbose)
            return None

        return None

    def _test_hunk_changes(
        self, hunks: list[HunkChange], base_commit: str, bad_commit: str, indices: list[int]
    ) -> CommandResult:
        """Test a specific combination of hunk changes.

        Args:
            hunks: List of all HunkChange objects.
            base_commit: Base commit SHA to apply on top of.
            bad_commit: Bad commit SHA (for diff reconstruction).
            indices: Indices of hunks to test.

        Returns:
            CommandResult from running tests.
        """
        # Check cache
        cache_key = self._get_combination_key(indices)
        if cache_key in self.tested_combinations:
            return self.tested_combinations[cache_key]

        # Select hunks to test
        selected_hunks: list[HunkChange] = [hunks[i] for i in indices]

        # Apply hunks (don't use temp branches to avoid state issues)
        success = self.git.apply_hunk_changes(
            selected_hunks, base_commit, bad_commit, use_temp_branch=False
        )

        if not success:
            # Failed to apply - likely dependency issues
            result = CommandResult.SKIP
        else:
            # Run test and track time
            test_start = time.time()
            result = self.test_runner.run()
            test_duration = time.time() - test_start
            self.test_times.append(test_duration)

        # Cache result
        self.tested_combinations[cache_key] = result

        # Always checkout base commit for next iteration (non-destructive)
        try:
            self.git.checkout(base_commit)
        except Exception:
            pass

        return result

    def bifurcate_hunks(
        self, hunks: list[HunkChange], base_commit: str, bad_commit: str, verbose: bool = True
    ) -> HunkChange | None:
        """Binary search through hunk changes to find breaking change.

        Args:
            hunks: List of HunkChange objects to search through.
            base_commit: Commit SHA to apply changes on top of.
            bad_commit: Commit SHA where hunks came from.
            verbose: Whether to print progress messages.

        Returns:
            The breaking HunkChange, or None if not found.
        """
        search_space = list(range(len(hunks)))
        iteration = 0
        if self.start_time is None:
            self.start_time = time.time()

        while len(search_space) > 1:
            iteration += 1
            mid = len(search_space) // 2
            lower_half = search_space[:mid]
            upper_half = search_space[mid:]

            if verbose:
                # Calculate estimates
                remaining_iters = self.estimate_remaining_iterations(len(search_space))
                remaining_time = self.estimate_remaining_time(len(search_space))
                avg_time = self.get_average_test_time()

                progress_msg = (
                    f"Iteration {iteration}: Testing hunks {lower_half[0] + 1}-"
                    f"{lower_half[-1] + 1} of {len(hunks)}"
                )

                if avg_time > 0:
                    progress_msg += (
                        f" | Est. {remaining_iters} iterations remaining"
                        f" (~{self.format_time(remaining_time)})"
                    )

                click.echo(progress_msg)

            # Test lower half
            result = self._test_hunk_changes(hunks, base_commit, bad_commit, lower_half)

            if result == CommandResult.FAIL:
                if verbose:
                    click.echo(f"  Result: FAIL - narrowing to hunks {lower_half}")
                search_space = lower_half

            elif result == CommandResult.PASS:
                if verbose:
                    click.echo(f"  Result: PASS - narrowing to hunks {upper_half}")
                search_space = upper_half

            else:  # SKIP or ERROR
                if verbose:
                    click.echo(f"  Result: {result.value} - trying upper half instead")
                # Try upper half when lower half won't build
                upper_result = self._test_hunk_changes(hunks, base_commit, bad_commit, upper_half)

                if upper_result == CommandResult.FAIL:
                    search_space = upper_half
                elif upper_result == CommandResult.PASS:
                    # Complex case - might need to handle dependencies
                    click.echo(
                        "Warning: Lower half won't build but upper half passes. "
                        "This suggests dependency issues."
                    )
                    # For MVP, just continue with upper half
                    search_space = upper_half
                else:
                    # Both halves skip - complex dependency issue
                    click.echo("Error: Too many build failures. Possible dependency issues.")
                    break

        # Found single hunk
        if len(search_space) == 1:
            final_index = search_space[0]
            # Verify it actually breaks
            result = self._test_hunk_changes(hunks, base_commit, bad_commit, [final_index])

            if result == CommandResult.FAIL:
                if verbose:
                    click.echo(f"\nFound breaking hunk after {iteration} iterations!")
                return hunks[final_index]

            self._report_interaction(hunks, base_commit, verbose, bad_commit=bad_commit)
            return None

        return None

    def _report_interaction(
        self,
        changes: list[FileChange] | list[HunkChange],
        base_commit: str,
        verbose: bool,
        bad_commit: str | None = None,
    ) -> None:
        """Attempt to identify interacting changes when no single culprit is found."""

        self.interaction_failure = None
        interaction = self._find_interaction_failure(
            changes, base_commit, bad_commit, max_combinations=64
        )

        if verbose:
            click.echo(
                "\nWarning: Isolated change doesn't fail on its own. May be an interaction effect."
            )

            if interaction:
                click.echo("Identified failing combination:")
                for idx in interaction:
                    change = changes[idx]
                    if isinstance(change, HunkChange):
                        click.echo(
                            f"  - [{idx}] {change.file_path}:{change.start_line}-{change.end_line}"
                        )
                    else:
                        click.echo(f"  - [{idx}] {change.file_path}")
                click.echo(
                    "Consider re-running with these changes applied together to confirm the interaction."
                )
            else:
                click.echo("No minimal failing combination found within search budget.")

    def _find_interaction_failure(
        self,
        changes: list[FileChange] | list[HunkChange],
        base_commit: str,
        bad_commit: str | None,
        max_combinations: int,
    ) -> list[int] | None:
        """Search for the smallest combination of changes that fails tests.

        This is a bounded search intended for diagnostic use when binary
        search doesn't yield a single culprit. It will reuse cached test
        results where possible.

        Optimization: Use dependency information to prioritize likely combinations.
        """

        from itertools import combinations

        total = len(changes)
        tests_run = 0

        test_func: Callable[[list[int]], CommandResult]

        if bad_commit is not None:
            hunk_changes = cast(list[HunkChange], changes)

            def test_func(idxs: list[int]) -> CommandResult:
                return self._test_hunk_changes(hunk_changes, base_commit, bad_commit, idxs)

        else:
            file_changes = cast(list[FileChange], changes)

            def test_func(idxs: list[int]) -> CommandResult:
                return self._test_changes(file_changes, base_commit, idxs)

        # Optimization: Try pairs with known dependencies first
        dependent_pairs = self._get_dependent_pairs(changes)
        for pair in dependent_pairs:
            if tests_run >= max_combinations:
                return None

            result = test_func(list(pair))
            tests_run += 1

            if result == CommandResult.FAIL:
                self.interaction_failure = list(pair)
                return self.interaction_failure

        # Then try all combinations systematically
        for size in range(2, min(total, 4) + 1):
            for combo in combinations(range(total), size):
                if tests_run >= max_combinations:
                    return None

                # Skip if already tested
                cache_key = self._get_combination_key(list(combo))
                if cache_key in self.tested_combinations:
                    continue

                result = test_func(list(combo))
                tests_run += 1

                if result == CommandResult.FAIL:
                    self.interaction_failure = list(combo)
                    return self.interaction_failure

        return None

    def _get_dependent_pairs(
        self, changes: list[FileChange] | list[HunkChange]
    ) -> list[tuple[int, int]]:
        """Get pairs of changes that have dependencies.

        Args:
            changes: List of changes to analyze.

        Returns:
            List of (index1, index2) tuples for dependent pairs.
        """
        pairs = []
        id_to_idx = {change.id: i for i, change in enumerate(changes)}

        for i, change in enumerate(changes):
            for dep_id in change.dependencies:
                if dep_id in id_to_idx:
                    dep_idx = id_to_idx[dep_id]
                    if dep_idx < i:  # Ensure consistent ordering
                        pairs.append((dep_idx, i))
                    else:
                        pairs.append((i, dep_idx))

        # Remove duplicates
        return list(set(pairs))

    def get_stats(self) -> dict[str, int | float]:
        """Get statistics about bifurcation session.

        Returns:
            Dictionary with stats like number of tests run.
        """
        stats = {
            "tests_run": len(self.tested_combinations),
            "passed": sum(1 for r in self.tested_combinations.values() if r == CommandResult.PASS),
            "failed": sum(1 for r in self.tested_combinations.values() if r == CommandResult.FAIL),
            "skipped": sum(1 for r in self.tested_combinations.values() if r == CommandResult.SKIP),
            "errors": sum(1 for r in self.tested_combinations.values() if r == CommandResult.ERROR),
        }

        # Add timing statistics
        if self.test_times:
            stats["avg_test_time"] = sum(self.test_times) / len(self.test_times)
            stats["total_test_time"] = sum(self.test_times)

        return stats

    def get_average_test_time(self) -> float:
        """Get average test execution time.

        Returns:
            Average time in seconds, or 0 if no tests run yet.
        """
        if not self.test_times:
            return 0.0
        return sum(self.test_times) / len(self.test_times)

    def estimate_remaining_iterations(self, search_space_size: int) -> int:
        """Estimate remaining iterations in binary search.

        Args:
            search_space_size: Current size of search space.

        Returns:
            Estimated number of remaining iterations.
        """
        if search_space_size <= 1:
            return 0
        # Binary search takes log2(n) iterations
        return math.ceil(math.log2(search_space_size))

    def estimate_remaining_time(self, search_space_size: int) -> float:
        """Estimate remaining time to complete bifurcation.

        Args:
            search_space_size: Current size of search space.

        Returns:
            Estimated time in seconds, or 0 if not enough data.
        """
        avg_time = self.get_average_test_time()
        if avg_time == 0:
            return 0.0

        remaining_iterations = self.estimate_remaining_iterations(search_space_size)
        # Each iteration typically runs 1-2 tests (lower half, maybe upper half)
        # Conservative estimate: 2 tests per iteration
        return remaining_iterations * avg_time * 2

    @staticmethod
    def format_time(seconds: float) -> str:
        """Format time duration in a human-readable way.

        Args:
            seconds: Time duration in seconds.

        Returns:
            Formatted time string (e.g., "2m 30s", "45s", "1h 5m").
        """
        if seconds < 1:
            return "< 1s"

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 or not parts:
            parts.append(f"{secs}s")

        return " ".join(parts)
