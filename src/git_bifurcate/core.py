"""Core bifurcation engine - binary search implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import click

from git_bifurcate.git_ops import GitRepo
from git_bifurcate.models import CommandResult
from git_bifurcate.test_runner import CommandRunner

if TYPE_CHECKING:
    from git_bifurcate.models import FileChange


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
                    return None

        # Found single change
        if len(search_space) == 1:
            final_index = search_space[0]
            # Verify it actually breaks
            result = self._test_changes(changes, base_commit, [final_index])

            if result == CommandResult.FAIL:
                if verbose:
                    click.echo(f"\nFound breaking change after {iteration} iterations!")
                return changes[final_index]
            else:
                if verbose:
                    click.echo(
                        "\nWarning: Isolated change doesn't fail on its own. "
                        "May be an interaction effect."
                    )
                return None

        return None

    def _test_hunk_changes(
        self, hunks: list, base_commit: str, bad_commit: str, indices: list[int]
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
        from git_bifurcate.models import HunkChange

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
        self, hunks: list, base_commit: str, bad_commit: str, verbose: bool = True
    ) -> Any | None:
        """Binary search through hunk changes to find breaking change.

        Args:
            hunks: List of HunkChange objects to search through.
            base_commit: Commit SHA to apply changes on top of.
            bad_commit: Commit SHA where hunks came from.
            verbose: Whether to print progress messages.

        Returns:
            The breaking HunkChange, a list of interacting hunks, or None if not found.
        """
        from git_bifurcate.models import HunkChange

        search_space = list(range(len(hunks)))
        iteration = 0

        # Verify that the full change set actually fails
        initial_result = self._test_hunk_changes(hunks, base_commit, bad_commit, search_space)
        failure_candidates: list[int] | None = None
        skip_candidates: list[int] | None = None

        if initial_result == CommandResult.FAIL:
            failure_candidates = search_space[:]
        elif initial_result == CommandResult.SKIP:
            skip_candidates = search_space[:]
        elif initial_result == CommandResult.PASS:
            if verbose:
                click.echo(
                    "Warning: All hunks applied cleanly and tests passed. Nothing to bisect."
                )
            return None

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
                failure_candidates = lower_half

            elif result == CommandResult.PASS:
                if verbose:
                    click.echo(f"  Result: PASS - narrowing to hunks {upper_half}")
                search_space = upper_half

            else:  # SKIP or ERROR
                if verbose:
                    click.echo(f"  Result: {result.value} - trying upper half instead")
                skip_candidates = lower_half
                # Try upper half when lower half won't build
                upper_result = self._test_hunk_changes(hunks, base_commit, bad_commit, upper_half)

                if upper_result == CommandResult.FAIL:
                    search_space = upper_half
                    failure_candidates = upper_half
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
                    return None

        # Found single hunk
        if len(search_space) == 1:
            final_index = search_space[0]
            # Verify it actually breaks
            result = self._test_hunk_changes(hunks, base_commit, bad_commit, [final_index])

            if result == CommandResult.FAIL:
                if verbose:
                    click.echo(f"\nFound breaking hunk after {iteration} iterations!")
                return hunks[final_index]

            # Look for interaction or conflict within previous failing/skip sets
            candidate_pool = failure_candidates or skip_candidates or []
            if len(candidate_pool) > 1:
                if verbose:
                    click.echo("\nSearching for interacting hunks that only fail together...")
                interaction = self._find_interacting_hunks(
                    hunks, base_commit, bad_commit, candidate_pool
                )
                if interaction:
                    indices, interaction_result = interaction
                    if verbose:
                        reason = (
                            "conflict"
                            if interaction_result == CommandResult.SKIP
                            else "interaction"
                        )
                        click.echo(f"Found hunk {reason} between: {indices}")
                    return [hunks[i] for i in indices]

            if verbose:
                click.echo(
                    "\nWarning: Isolated hunk doesn't fail on its own. "
                    "May be an interaction effect."
                )
            return None

        return None

    def _find_interacting_hunks(
        self,
        hunks: list,
        base_commit: str,
        bad_commit: str,
        candidate_pool: list[int],
    ) -> tuple[list[int], CommandResult] | None:
        """Identify hunk combinations that only fail or conflict together."""
        from itertools import combinations

        for combo in combinations(candidate_pool, 2):
            result = self._test_hunk_changes(hunks, base_commit, bad_commit, list(combo))
            if result in (CommandResult.FAIL, CommandResult.SKIP):
                return list(combo), result
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
