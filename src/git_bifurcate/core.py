"""Core bifurcation engine - binary search implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from git_bifurcate.git_ops import GitRepo
from git_bifurcate.models import CommandResult
from git_bifurcate.test_runner import CommandRunner

if TYPE_CHECKING:
    from git_bifurcate.models import FileChange, HunkChange


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
            # Run test
            result = self.test_runner.run()

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

        while len(search_space) > 1:
            iteration += 1
            mid = len(search_space) // 2
            lower_half = search_space[:mid]
            upper_half = search_space[mid:]

            if verbose:
                click.echo(
                    f"Iteration {iteration}: Testing changes {lower_half[0] + 1}-"
                    f"{lower_half[-1] + 1} of {len(changes)}..."
                )

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
            result = self.test_runner.run()

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

        while len(search_space) > 1:
            iteration += 1
            mid = len(search_space) // 2
            lower_half = search_space[:mid]
            upper_half = search_space[mid:]

            if verbose:
                click.echo(
                    f"Iteration {iteration}: Testing hunks {lower_half[0] + 1}-"
                    f"{lower_half[-1] + 1} of {len(hunks)}..."
                )

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
                "\nWarning: Isolated change doesn't fail on its own. "
                "May be an interaction effect."
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
        """

        from itertools import combinations

        total = len(changes)
        tests_run = 0

        test_func = (
            (lambda idxs: self._test_hunk_changes(changes, base_commit, bad_commit or "", idxs))
            if bad_commit is not None
            else (lambda idxs: self._test_changes(changes, base_commit, idxs))
        )

        for size in range(2, min(total, 4) + 1):
            for combo in combinations(range(total), size):
                if tests_run >= max_combinations:
                    return None

                result = test_func(list(combo))
                tests_run += 1

                if result == CommandResult.FAIL:
                    self.interaction_failure = list(combo)
                    return self.interaction_failure

        return None

    def get_stats(self) -> dict[str, int]:
        """Get statistics about bifurcation session.

        Returns:
            Dictionary with stats like number of tests run.
        """
        return {
            "tests_run": len(self.tested_combinations),
            "passed": sum(1 for r in self.tested_combinations.values() if r == CommandResult.PASS),
            "failed": sum(1 for r in self.tested_combinations.values() if r == CommandResult.FAIL),
            "skipped": sum(1 for r in self.tested_combinations.values() if r == CommandResult.SKIP),
            "errors": sum(1 for r in self.tested_combinations.values() if r == CommandResult.ERROR),
        }
