"""Command-line interface for git-bifurcate."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from git_bifurcate.core import BifurcationEngine
from git_bifurcate.git_ops import GitRepo
from git_bifurcate.models import BifurcationState, Strategy, TestResult
from git_bifurcate.parser import parse_file_changes, parse_hunk_changes
from git_bifurcate.test_runner import TestRunner


@click.group(invoke_without_command=True)
@click.option("--version", is_flag=True, help="Show version and exit")
@click.pass_context
def main(ctx: click.Context, version: bool) -> None:
    """git-bifurcate: Find the exact change that broke your tests.

    Extends git bisect to find bugs at the file and hunk level within a single commit.
    """
    if version:
        click.echo("git-bifurcate version 0.1.0")
        ctx.exit(0)

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command()
@click.argument("commit", required=False)
@click.option(
    "--test",
    "-t",
    required=True,
    help="Test command to run (e.g., 'pytest tests/test_feature.py')",
)
@click.option(
    "--strategy",
    "-s",
    type=click.Choice(["file", "hunk", "hybrid"], case_sensitive=False),
    default="file",
    help="Bifurcation strategy: file (default), hunk, or hybrid",
)
@click.option(
    "--parent",
    "-p",
    help="Parent commit SHA (defaults to commit^)",
)
def start(commit: str | None, test: str, strategy: str, parent: str | None) -> None:
    """Start bifurcating a commit to find breaking changes.

    COMMIT is the commit SHA to bifurcate (defaults to HEAD).

    Example:
        git bifurcate start abc123 --test "pytest tests/test_feature.py"
    """
    # Check if bifurcation already in progress
    if BifurcationState.exists():
        click.echo("Error: Bifurcation already in progress.")
        click.echo("Use 'git bifurcate status' to see current state,")
        click.echo("or 'git bifurcate reset' to abort and start fresh.")
        sys.exit(1)

    try:
        # Initialize git repo
        git = GitRepo()

        # Default to HEAD if no commit specified
        if commit is None:
            commit = "HEAD"

        # Get commit SHA
        commit_sha = git.get_commit(commit)

        # Get parent commit
        if parent is None:
            parent_sha = git.get_parent_commit(commit_sha)
        else:
            parent_sha = git.get_commit(parent)

        click.echo(f"Starting bifurcation of commit {commit_sha[:8]}")
        click.echo(f"Parent commit: {parent_sha[:8]}")
        click.echo(f"Strategy: {strategy}")
        click.echo(f"Test command: {test}")
        click.echo()

        # Get diff
        diff_text = git.get_diff(parent_sha, commit_sha)

        # Parse changes based on strategy
        strategy_enum = Strategy(strategy.lower())

        if strategy_enum == Strategy.FILE:
            changes = parse_file_changes(diff_text)
            click.echo(f"Found {len(changes)} file-level changes")
        elif strategy_enum == Strategy.HUNK:
            changes = parse_hunk_changes(diff_text)
            click.echo(f"Found {len(changes)} hunk-level changes")
        else:  # HYBRID
            click.echo("Error: Hybrid strategy not yet implemented")
            click.echo("Please use --strategy=file or --strategy=hunk")
            sys.exit(1)

        if not changes:
            click.echo("Error: No changes found in commit")
            sys.exit(1)

        # Display changes
        click.echo("\nChanges to bifurcate:")
        for i, change in enumerate(changes):
            if hasattr(change, "start_line"):
                # HunkChange
                click.echo(
                    f"  [{i}] {change.file_path}:{change.start_line}-{change.end_line}"
                )
            else:
                # FileChange
                click.echo(f"  [{i}] {change.file_path} ({change.change_type})")
        click.echo()

        # First, verify that all changes together reproduce the failure
        click.echo("Verifying that all changes together fail the test...")
        test_runner = TestRunner(test)
        engine = BifurcationEngine(git, test_runner)

        all_indices = list(range(len(changes)))
        result = engine._test_changes(changes, parent_sha, all_indices)

        if result != TestResult.FAIL:
            click.echo(f"\nError: Expected test to FAIL with all changes, but got {result.value}")
            click.echo("The commit you're bifurcating should fail tests.")
            click.echo("Please verify:")
            click.echo(f"  1. Tests pass at parent commit: {parent_sha[:8]}")
            click.echo(f"  2. Tests fail at target commit: {commit_sha[:8]}")
            click.echo(f"  3. Test command is correct: {test}")
            sys.exit(1)

        click.echo("✓ Confirmed: All changes together fail the test")
        click.echo()

        # Verify that no changes passes
        click.echo("Verifying that parent commit passes the test...")
        result = engine._test_changes(changes, parent_sha, [])

        if result != TestResult.PASS:
            click.echo(f"\nError: Expected test to PASS with no changes, but got {result.value}")
            click.echo("The parent commit should pass tests.")
            sys.exit(1)

        click.echo("✓ Confirmed: No changes (parent commit) passes the test")
        click.echo()

        # Create initial state
        state = BifurcationState(
            commit_sha=commit_sha,
            parent_sha=parent_sha,
            test_command=test,
            strategy=strategy_enum,
            changes=changes,
            search_space=list(range(len(changes))),
        )
        state.save()

        # Start bifurcation
        click.echo("=" * 60)
        click.echo("Starting binary search...")
        click.echo("=" * 60)
        click.echo()

        breaking_change = engine.bifurcate_files(changes, parent_sha, verbose=True)

        if breaking_change:
            click.echo()
            click.echo("=" * 60)
            click.echo("BREAKING CHANGE FOUND!")
            click.echo("=" * 60)
            click.echo()

            if hasattr(breaking_change, "start_line"):
                # HunkChange
                click.echo(f"File: {breaking_change.file_path}")
                click.echo(f"Lines: {breaking_change.start_line}-{breaking_change.end_line}")
            else:
                # FileChange
                click.echo(f"File: {breaking_change.file_path}")
                click.echo(f"Type: {breaking_change.change_type}")

            click.echo()
            click.echo("Diff content:")
            click.echo("-" * 60)
            click.echo(breaking_change.diff_content)
            click.echo("-" * 60)
            click.echo()

            # Show stats
            stats = engine.get_stats()
            click.echo(f"Statistics:")
            click.echo(f"  Total tests run: {stats['tests_run']}")
            click.echo(f"  Passed: {stats['passed']}")
            click.echo(f"  Failed: {stats['failed']}")
            click.echo(f"  Skipped: {stats['skipped']}")
            click.echo(f"  Errors: {stats['errors']}")

            # Clean up
            click.echo()
            click.echo("Cleaning up...")
            git.reset_hard(commit_sha)
            BifurcationState.delete()
            click.echo("✓ Done")
        else:
            click.echo()
            click.echo("=" * 60)
            click.echo("NO SINGLE BREAKING CHANGE FOUND")
            click.echo("=" * 60)
            click.echo()
            click.echo("This could mean:")
            click.echo("  1. Multiple changes interact to cause the failure")
            click.echo("  2. Dependency issues between changes")
            click.echo("  3. The test is nondeterministic")
            click.echo()
            click.echo("Try:")
            click.echo("  - Using --strategy=hunk for finer granularity")
            click.echo("  - Running the test multiple times to check for flakiness")
            click.echo("  - Manually reviewing the changes")

            # Clean up
            click.echo()
            click.echo("Cleaning up...")
            git.reset_hard(commit_sha)
            BifurcationState.delete()

    except FileNotFoundError as e:
        click.echo(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}")
        click.echo()
        click.echo("Attempting cleanup...")
        try:
            git = GitRepo()
            state = BifurcationState.load()
            git.reset_hard(state.commit_sha)
            BifurcationState.delete()
            click.echo("✓ Cleanup successful")
        except Exception:
            click.echo("⚠ Cleanup failed - you may need to manually reset your repository")
        sys.exit(1)


@main.command()
def status() -> None:
    """Show current bifurcation status."""
    if not BifurcationState.exists():
        click.echo("No bifurcation in progress.")
        click.echo()
        click.echo("To start bifurcating a commit:")
        click.echo("  git bifurcate start <commit> --test <command>")
        return

    try:
        state = BifurcationState.load()

        click.echo("=" * 60)
        click.echo("BIFURCATION IN PROGRESS")
        click.echo("=" * 60)
        click.echo()
        click.echo(f"Commit: {state.commit_sha[:8]}")
        click.echo(f"Parent: {state.parent_sha[:8]}")
        click.echo(f"Strategy: {state.strategy.value}")
        click.echo(f"Test command: {state.test_command}")
        click.echo()
        click.echo(f"Total changes: {len(state.changes)}")
        click.echo(f"Search space: {len(state.search_space)} changes remaining")
        click.echo(f"Iteration: {state.current_iteration}")
        click.echo()

        if state.found_breaking:
            click.echo("Breaking changes found:")
            for idx in state.found_breaking:
                change = state.changes[idx]
                if hasattr(change, "start_line"):
                    click.echo(f"  [{idx}] {change.file_path}:{change.start_line}-{change.end_line}")
                else:
                    click.echo(f"  [{idx}] {change.file_path}")

        click.echo()
        click.echo(f"Tests run so far: {len(state.tested_combinations)}")
        click.echo()
        click.echo("To abort and clean up:")
        click.echo("  git bifurcate reset")

    except Exception as e:
        click.echo(f"Error loading state: {e}")
        sys.exit(1)


@main.command()
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Force reset even if state file is corrupted",
)
def reset(force: bool) -> None:
    """Abort bifurcation and clean up."""
    if not BifurcationState.exists() and not force:
        click.echo("No bifurcation in progress.")
        return

    try:
        # Load state to get commit SHA
        state = BifurcationState.load()
        commit_sha = state.commit_sha

        click.echo("Aborting bifurcation...")
        click.echo(f"Resetting to commit {commit_sha[:8]}...")

        # Reset repository
        git = GitRepo()
        git.reset_hard(commit_sha)

        # Delete state file
        BifurcationState.delete()

        # Clean up temp branch if it exists
        try:
            git.delete_branch("bifurcate-temp")
        except Exception:
            pass  # Branch might not exist

        click.echo("✓ Bifurcation aborted and cleaned up")

    except FileNotFoundError:
        if force:
            click.echo("State file not found, removing if exists...")
            BifurcationState.delete()
            click.echo("✓ Cleanup attempted")
        else:
            click.echo("Error: State file not found")
            click.echo("Use --force to force cleanup")
            sys.exit(1)
    except Exception as e:
        click.echo(f"Error during reset: {e}")
        click.echo()
        click.echo("You may need to manually:")
        click.echo("  1. git reset --hard to desired commit")
        click.echo("  2. rm .git/bifurcate-state.json")
        click.echo("  3. git branch -D bifurcate-temp (if exists)")
        sys.exit(1)


if __name__ == "__main__":
    main()
