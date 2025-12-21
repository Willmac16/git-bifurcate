"""Core bifurcation engine - binary search implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from git_bifurcate.git_ops import GitRepo
from git_bifurcate.models import TestResult
from git_bifurcate.test_runner import TestRunner

if TYPE_CHECKING:
    from git_bifurcate.models import FileChange


class BifurcationEngine:
    """Implements binary search for finding breaking changes."""

    def __init__(self, git_repo: GitRepo, test_runner: TestRunner) -> None:
        """Initialize bifurcation engine.

        Args:
            git_repo: Git repository wrapper.
            test_runner: Test execution wrapper.
        """
        self.git = git_repo
        self.test_runner = test_runner
        self.tested_combinations: dict[str, TestResult] = {}

    def _get_combination_key(self, indices: list[int]) -> str:
        """Get cache key for a combination of changes."""
        return ",".join(map(str, sorted(indices)))

    def _test_changes(
        self, changes: list[FileChange], base_commit: str, indices: list[int]
    ) -> TestResult:
        """Test a specific combination of changes.

        Args:
            changes: All available changes.
            base_commit: Commit to apply changes on top of.
            indices: Indices of changes to test.

        Returns:
            TestResult from running tests.
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
            result = TestResult.SKIP
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

            if result == TestResult.FAIL:
                if verbose:
                    click.echo(f"  Result: FAIL - narrowing to changes {lower_half}")
                search_space = lower_half

            elif result == TestResult.PASS:
                if verbose:
                    click.echo(f"  Result: PASS - narrowing to changes {upper_half}")
                search_space = upper_half

            else:  # SKIP or ERROR
                if verbose:
                    click.echo(
                        f"  Result: {result.value} - trying upper half instead"
                    )
                # Try upper half when lower half won't build
                upper_result = self._test_changes(changes, base_commit, upper_half)

                if upper_result == TestResult.FAIL:
                    search_space = upper_half
                elif upper_result == TestResult.PASS:
                    # Complex case - might need to handle dependencies
                    click.echo(
                        "Warning: Lower half won't build but upper half passes. "
                        "This suggests dependency issues."
                    )
                    # For MVP, just continue with upper half
                    search_space = upper_half
                else:
                    # Both halves skip - complex dependency issue
                    click.echo(
                        "Error: Too many build failures. Possible dependency issues."
                    )
                    return None

        # Found single change
        if len(search_space) == 1:
            final_index = search_space[0]
            # Verify it actually breaks
            result = self._test_changes(changes, base_commit, [final_index])

            if result == TestResult.FAIL:
                if verbose:
                    click.echo(
                        f"\nFound breaking change after {iteration} iterations!"
                    )
                return changes[final_index]
            else:
                if verbose:
                    click.echo(
                        "\nWarning: Isolated change doesn't fail on its own. "
                        "May be an interaction effect."
                    )
                return None

        return None

    def get_stats(self) -> dict[str, int]:
        """Get statistics about bifurcation session.

        Returns:
            Dictionary with stats like number of tests run.
        """
        return {
            "tests_run": len(self.tested_combinations),
            "passed": sum(
                1 for r in self.tested_combinations.values() if r == TestResult.PASS
            ),
            "failed": sum(
                1 for r in self.tested_combinations.values() if r == TestResult.FAIL
            ),
            "skipped": sum(
                1 for r in self.tested_combinations.values() if r == TestResult.SKIP
            ),
            "errors": sum(
                1 for r in self.tested_combinations.values() if r == TestResult.ERROR
            ),
        }
