"""Command-line interface for git-bifurcate."""

from __future__ import annotations

import sys
from typing import cast

import click

from git_bifurcate.commit_bisect import CommitBisector
from git_bifurcate.core import BifurcationEngine
from git_bifurcate.dependency_analyzer import (
    apply_dependency_analysis,
    apply_hunk_dependency_analysis,
)
from git_bifurcate.git_ops import GitRepo
from git_bifurcate.models import BifurcationState, CommandResult, FileChange, HunkChange, Strategy
from git_bifurcate.parser import parse_file_changes, parse_hunk_changes
from git_bifurcate.test_runner import CommandRunner


def _matches_path_filter(file_path: str, filter_paths: tuple[str, ...]) -> bool:
    """Check if a file path matches any of the filter paths.

    Args:
        file_path: The file path to check.
        filter_paths: Tuple of paths to match against (files or directories).

    Returns:
        True if the file matches any filter path, False otherwise.
    """
    if not filter_paths:
        return True  # No filter means include everything

    for filter_path in filter_paths:
        # Normalize paths for comparison
        filter_path_normalized = filter_path.rstrip("/")

        # Exact file match
        if file_path == filter_path_normalized:
            return True

        # Directory match (file is under the directory)
        if file_path.startswith(filter_path_normalized + "/"):
            return True

    return False


def _filter_changes_by_paths[ChangeT: (FileChange, HunkChange)](
    changes: list[ChangeT], paths: tuple[str, ...]
) -> list[ChangeT]:
    """Filter changes to only include those matching the specified paths.

    Args:
        changes: List of FileChange or HunkChange objects.
        paths: Tuple of paths to filter by (files or directories).

    Returns:
        Filtered list of changes.
    """
    if not paths:
        return changes  # No filter means return all changes

    return [change for change in changes if _matches_path_filter(change.file_path, paths)]


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
@click.argument("paths", nargs=-1, type=click.Path())
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
@click.option(
    "--analyze-deps",
    "-d",
    is_flag=True,
    help="Analyze and detect dependencies between changes",
)
@click.option(
    "--find-more",
    "-m",
    is_flag=True,
    help="Continue searching for more breaking changes after finding the first",
)
def start(
    commit: str | None,
    paths: tuple[str, ...],
    test: str,
    strategy: str,
    parent: str | None,
    analyze_deps: bool,
    find_more: bool,
) -> None:
    """Start bifurcating a commit to find breaking changes.

    COMMIT is the commit SHA to bifurcate (defaults to HEAD).
    PATHS restricts the search to specific files or directories (optional).
    Use -- to separate commit from paths if needed.

    Examples:
        git bifurcate start abc123 --test "pytest tests/test_feature.py"
        git bifurcate start abc123 --test "pytest" -- src/module.py
        git bifurcate start --test "pytest" -- src/problematic/
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
        commit_obj = git.get_commit(commit)
        commit_sha = commit_obj.hexsha

        # Get parent commit
        if parent is None:
            parent_sha = git.get_parent_commit(commit_sha)
        else:
            parent_obj = git.get_commit(parent)
            parent_sha = parent_obj.hexsha

        click.echo(f"Starting bifurcation of commit {commit_sha[:8]}")
        click.echo(f"Parent commit: {parent_sha[:8]}")
        click.echo(f"Strategy: {strategy}")
        click.echo(f"Test command: {test}")
        click.echo()

        # Get diff
        diff_text = git.get_diff(commit_sha, parent_sha)

        # Parse changes based on strategy
        strategy_enum = Strategy(strategy.lower())

        if strategy_enum == Strategy.FILE:
            file_changes = parse_file_changes(diff_text)
            click.echo(f"Found {len(file_changes)} file-level changes")

            # Apply path filtering if specified
            if paths:
                file_changes = _filter_changes_by_paths(file_changes, paths)
                click.echo(f"Filtered to {len(file_changes)} changes matching: {', '.join(paths)}")

            if not file_changes:
                click.echo("Error: No changes found in commit")
                sys.exit(1)

            # Analyze dependencies if requested
            if analyze_deps:
                click.echo("Analyzing dependencies between changes...")
                apply_dependency_analysis(file_changes)
                dep_count = sum(len(c.dependencies) for c in file_changes)
                click.echo(f"Found {dep_count} dependencies")

            # Display changes
            click.echo("\nChanges to bifurcate:")
            for i, file_change in enumerate(file_changes):
                deps_info = (
                    f" (depends on: {file_change.dependencies})" if file_change.dependencies else ""
                )
                click.echo(
                    f"  [{i}] {file_change.file_path} ({file_change.change_type}){deps_info}"
                )
            click.echo()

            # First, verify that all changes together reproduce the failure
            click.echo("Verifying that all changes together fail the test...")
            test_runner = CommandRunner(test)
            engine = BifurcationEngine(git, test_runner)

            all_indices = list(range(len(file_changes)))
            result = engine._test_changes(file_changes, parent_sha, all_indices)

            if result != CommandResult.FAIL:
                click.echo(
                    f"\nError: Expected test to FAIL with all changes, but got {result.value}"
                )
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
            result = engine._test_changes(file_changes, parent_sha, [])

            if result != CommandResult.PASS:
                click.echo(
                    f"\nError: Expected test to PASS with no changes, but got {result.value}"
                )
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
                changes=cast(list[FileChange | HunkChange], file_changes),
                search_space=list(range(len(file_changes))),
            )
            state.save()

            # Start bifurcation
            click.echo("=" * 60)
            click.echo("Starting binary search...")
            click.echo("=" * 60)
            click.echo()

            breaking_files = []
            search_indices = list(range(len(file_changes)))

            while True:
                # Create new engine for each search to reset state
                engine = BifurcationEngine(git, test_runner)

                # Filter to only search remaining indices
                remaining_changes = [file_changes[i] for i in search_indices]

                breaking_file = engine.bifurcate_files(remaining_changes, parent_sha, verbose=True)

                if breaking_file:
                    # Find the original index
                    original_idx = next(
                        i for i in search_indices if file_changes[i].id == breaking_file.id
                    )
                    breaking_files.append((original_idx, breaking_file))

                    click.echo()
                    click.echo("=" * 60)
                    if find_more:
                        click.echo(f"BREAKING CHANGE #{len(breaking_files)} FOUND!")
                    else:
                        click.echo("BREAKING CHANGE FOUND!")
                    click.echo("=" * 60)
                    click.echo()
                    click.echo(f"File: {breaking_file.file_path}")
                    click.echo(f"Type: {breaking_file.change_type}")
                    click.echo()
                    click.echo("Diff content:")
                    click.echo("-" * 60)
                    click.echo(breaking_file.diff_content)
                    click.echo("-" * 60)
                    click.echo()

                    if breaking_file.change_type == "submodule":
                        _analyze_submodule_drift(
                            git, test_runner, parent_sha, file_changes, breaking_file, commit_sha
                        )

                    # Remove this change from search space
                    search_indices.remove(original_idx)

                    # Ask if user wants to find more (if flag is set and there are more changes)
                    if find_more and search_indices:
                        if not click.confirm("\nContinue searching for more breaking changes?"):
                            break
                    else:
                        break
                else:
                    # No more single breaking changes found
                    break

            # Show summary (only if find_more was used and multiple were found)
            if breaking_files:
                if find_more and len(breaking_files) > 1:
                    click.echo()
                    click.echo("=" * 60)
                    click.echo(f"FOUND {len(breaking_files)} BREAKING CHANGE(S)")
                    click.echo("=" * 60)
                    for idx, (orig_idx, bf) in enumerate(breaking_files, 1):
                        click.echo(f"\n{idx}. [{orig_idx}] {bf.file_path} ({bf.change_type})")

                click.echo()
                # Show stats
                click.echo()
                stats = engine.get_stats()
                click.echo("Statistics:")
                click.echo(f"  Total tests run: {stats['tests_run']}")
                click.echo(f"  Passed: {stats['passed']}")
                click.echo(f"  Failed: {stats['failed']}")
                click.echo(f"  Skipped: {stats['skipped']}")
                click.echo(f"  Errors: {stats['errors']}")
                if "avg_test_time" in stats:
                    click.echo(
                        f"  Average test time: {BifurcationEngine.format_time(stats['avg_test_time'])}"
                    )
                    click.echo(
                        f"  Total time: {BifurcationEngine.format_time(stats['total_test_time'])}"
                    )

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

                _analyze_submodule_interactions(
                    git, test_runner, parent_sha, file_changes, commit_sha
                )

                # Show stats
                stats = engine.get_stats()
                click.echo("Statistics:")
                click.echo(f"  Total tests run: {stats['tests_run']}")

                # Clean up
                git.reset_hard(commit_sha)
                BifurcationState.delete()
        elif strategy_enum == Strategy.HUNK:
            hunk_changes = parse_hunk_changes(diff_text)
            click.echo(f"Found {len(hunk_changes)} hunk-level changes")

            # Apply path filtering if specified
            if paths:
                hunk_changes = _filter_changes_by_paths(hunk_changes, paths)
                click.echo(f"Filtered to {len(hunk_changes)} changes matching: {', '.join(paths)}")

            if not hunk_changes:
                click.echo("Error: No changes found in commit")
                sys.exit(1)

            # Analyze dependencies if requested
            if analyze_deps:
                click.echo("Analyzing dependencies between hunks...")
                apply_hunk_dependency_analysis(hunk_changes)
                dep_count = sum(len(h.dependencies) for h in hunk_changes)
                click.echo(f"Found {dep_count} dependencies")

            # Display changes
            click.echo("\nChanges to bifurcate:")
            for i, hunk_change in enumerate(hunk_changes):
                deps_info = (
                    f" (depends on: {hunk_change.dependencies})" if hunk_change.dependencies else ""
                )
                click.echo(
                    f"  [{i}] {hunk_change.file_path}:{hunk_change.start_line}-{hunk_change.end_line}{deps_info}"
                )
            click.echo()

            # First, verify that all changes together reproduce the failure
            click.echo("Verifying that all changes together fail the test...")
            test_runner = CommandRunner(test)
            engine = BifurcationEngine(git, test_runner)

            all_indices = list(range(len(hunk_changes)))
            result = engine._test_hunk_changes(hunk_changes, parent_sha, commit_sha, all_indices)

            if result != CommandResult.FAIL:
                click.echo(
                    f"\nError: Expected test to FAIL with all changes, but got {result.value}"
                )
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
            result = engine._test_hunk_changes(hunk_changes, parent_sha, commit_sha, [])

            if result != CommandResult.PASS:
                click.echo(
                    f"\nError: Expected test to PASS with no changes, but got {result.value}"
                )
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
                changes=cast(list[FileChange | HunkChange], hunk_changes),
                search_space=list(range(len(hunk_changes))),
            )
            state.save()

            # Start bifurcation
            click.echo("=" * 60)
            click.echo("Starting binary search...")
            click.echo("=" * 60)
            click.echo()

            breaking_hunks = []
            search_indices = list(range(len(hunk_changes)))

            while True:
                # Create new engine for each search to reset state
                engine = BifurcationEngine(git, test_runner)

                # Filter to only search remaining indices
                remaining_hunks = [hunk_changes[i] for i in search_indices]

                breaking_hunk = engine.bifurcate_hunks(
                    remaining_hunks, parent_sha, commit_sha, verbose=True
                )

                if breaking_hunk:
                    # Find the original index
                    original_idx = next(
                        i for i in search_indices if hunk_changes[i].id == breaking_hunk.id
                    )
                    breaking_hunks.append((original_idx, breaking_hunk))

                    click.echo()
                    click.echo("=" * 60)
                    if find_more:
                        click.echo(f"BREAKING CHANGE #{len(breaking_hunks)} FOUND!")
                    else:
                        click.echo("BREAKING CHANGE FOUND!")
                    click.echo("=" * 60)
                    click.echo()
                    click.echo(f"File: {breaking_hunk.file_path}")
                    click.echo(f"Lines: {breaking_hunk.start_line}-{breaking_hunk.end_line}")
                    click.echo()
                    click.echo("Diff content:")
                    click.echo("-" * 60)
                    click.echo(breaking_hunk.diff_content)
                    click.echo("-" * 60)
                    click.echo()

                    # Remove this hunk from search space
                    search_indices.remove(original_idx)

                    # Ask if user wants to find more (if flag is set and there are more hunks)
                    if find_more and search_indices:
                        if not click.confirm("\nContinue searching for more breaking changes?"):
                            break
                    else:
                        break
                else:
                    # No more single breaking changes found
                    break

            # Show summary (only if find_more was used and multiple were found)
            if breaking_hunks:
                if find_more and len(breaking_hunks) > 1:
                    click.echo()
                    click.echo("=" * 60)
                    click.echo(f"FOUND {len(breaking_hunks)} BREAKING CHANGE(S)")
                    click.echo("=" * 60)
                    for idx, (orig_idx, bh) in enumerate(breaking_hunks, 1):
                        click.echo(
                            f"\n{idx}. [{orig_idx}] {bh.file_path}:{bh.start_line}-{bh.end_line}"
                        )

                click.echo()
                # Show stats
                click.echo()
                stats = engine.get_stats()
                click.echo("Statistics:")
                click.echo(f"  Total tests run: {stats['tests_run']}")
                click.echo(f"  Passed: {stats['passed']}")
                click.echo(f"  Failed: {stats['failed']}")
                click.echo(f"  Skipped: {stats['skipped']}")
                click.echo(f"  Errors: {stats['errors']}")
                if "avg_test_time" in stats:
                    click.echo(
                        f"  Average test time: {BifurcationEngine.format_time(stats['avg_test_time'])}"
                    )
                    click.echo(
                        f"  Total time: {BifurcationEngine.format_time(stats['total_test_time'])}"
                    )

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

                # Show stats
                stats = engine.get_stats()
                click.echo("Statistics:")
                click.echo(f"  Total tests run: {stats['tests_run']}")

                # Clean up
                git.reset_hard(commit_sha)
                BifurcationState.delete()
        else:  # HYBRID
            file_changes = parse_file_changes(diff_text)
            click.echo(f"Found {len(file_changes)} file-level changes")

            # Apply path filtering if specified
            if paths:
                file_changes = _filter_changes_by_paths(file_changes, paths)
                click.echo(f"Filtered to {len(file_changes)} changes matching: {', '.join(paths)}")

            if not file_changes:
                click.echo("Error: No changes found in commit")
                sys.exit(1)

            # Analyze dependencies if requested
            if analyze_deps:
                click.echo("Analyzing dependencies between changes...")
                apply_dependency_analysis(file_changes)
                dep_count = sum(len(c.dependencies) for c in file_changes)
                click.echo(f"Found {dep_count} dependencies")

            # Display changes
            click.echo("\nChanges to bifurcate:")
            for i, file_change in enumerate(file_changes):
                deps_info = (
                    f" (depends on: {file_change.dependencies})" if file_change.dependencies else ""
                )
                click.echo(
                    f"  [{i}] {file_change.file_path} ({file_change.change_type}){deps_info}"
                )
            click.echo()

            # First, verify that all changes together reproduce the failure
            click.echo("Verifying that all changes together fail the test...")
            test_runner = CommandRunner(test)
            engine = BifurcationEngine(git, test_runner)

            all_indices = list(range(len(file_changes)))
            result = engine._test_changes(file_changes, parent_sha, all_indices)

            if result != CommandResult.FAIL:
                click.echo(
                    f"\nError: Expected test to FAIL with all changes, but got {result.value}"
                )
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
            result = engine._test_changes(file_changes, parent_sha, [])

            if result != CommandResult.PASS:
                click.echo(
                    f"\nError: Expected test to PASS with no changes, but got {result.value}"
                )
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
                changes=cast(list[FileChange | HunkChange], file_changes),
                search_space=list(range(len(file_changes))),
            )
            state.save()

            # Start hybrid bifurcation
            click.echo()
            click.echo("=" * 60)
            click.echo("HYBRID STRATEGY: File-level → Hunk-level")
            click.echo("=" * 60)
            click.echo()

            breaking_results = []
            search_indices = list(range(len(file_changes)))

            while True:
                # Create new engine for each search to reset state
                engine = BifurcationEngine(git, test_runner)

                # Filter to only search remaining indices
                remaining_changes = [file_changes[i] for i in search_indices]

                result = engine.bifurcate_hybrid(
                    remaining_changes, parent_sha, commit_sha, diff_text, verbose=True
                )

                if result:
                    # Result can be FileChange or tuple[FileChange, HunkChange]
                    if isinstance(result, tuple):
                        breaking_file, breaking_hunk = result
                        breaking_file = cast(FileChange, breaking_file)
                        breaking_hunk = cast(HunkChange, breaking_hunk)
                        # Find original index
                        original_idx = next(
                            i for i in search_indices if file_changes[i].id == breaking_file.id
                        )
                        breaking_results.append((original_idx, breaking_file, breaking_hunk))

                        click.echo()
                        click.echo("=" * 60)
                        if find_more:
                            click.echo(f"BREAKING CHANGE #{len(breaking_results)} FOUND!")
                        else:
                            click.echo("BREAKING CHANGE FOUND!")
                        click.echo("=" * 60)
                        click.echo()
                        click.echo(f"File: {breaking_file.file_path}")
                        click.echo(f"Type: {breaking_file.change_type}")
                        click.echo(f"Hunk: Lines {breaking_hunk.start_line}-{breaking_hunk.end_line}")
                        click.echo()
                        click.echo("Diff content:")
                        click.echo("-" * 60)
                        click.echo(breaking_hunk.diff_content)
                        click.echo("-" * 60)
                        click.echo()

                        # Remove from search space
                        search_indices.remove(original_idx)
                    else:
                        # Only file-level result
                        breaking_file = cast(FileChange, result)
                        original_idx = next(
                            i for i in search_indices if file_changes[i].id == breaking_file.id
                        )
                        breaking_results.append((original_idx, breaking_file, None))

                        click.echo()
                        click.echo("=" * 60)
                        if find_more:
                            click.echo(f"BREAKING CHANGE #{len(breaking_results)} FOUND!")
                        else:
                            click.echo("BREAKING CHANGE FOUND!")
                        click.echo("=" * 60)
                        click.echo()
                        click.echo(f"File: {breaking_file.file_path}")
                        click.echo(f"Type: {breaking_file.change_type}")
                        click.echo()
                        click.echo("Diff content:")
                        click.echo("-" * 60)
                        click.echo(breaking_file.diff_content)
                        click.echo("-" * 60)
                        click.echo()

                        if breaking_file.change_type == "submodule":
                            _analyze_submodule_drift(
                                git, test_runner, parent_sha, file_changes, breaking_file, commit_sha
                            )

                        # Remove from search space
                        search_indices.remove(original_idx)

                    # Ask if user wants to find more
                    if find_more and search_indices:
                        if not click.confirm("\nContinue searching for more breaking changes?"):
                            break
                    else:
                        break
                else:
                    # No more breaking changes found
                    break

            # Show summary
            if breaking_results:
                if find_more and len(breaking_results) > 1:
                    click.echo()
                    click.echo("=" * 60)
                    click.echo(f"FOUND {len(breaking_results)} BREAKING CHANGE(S)")
                    click.echo("=" * 60)
                    for idx, (orig_idx, bf, bh) in enumerate(breaking_results, 1):
                        if bh:
                            click.echo(
                                f"\n{idx}. [{orig_idx}] {bf.file_path}:{bh.start_line}-{bh.end_line}"
                            )
                        else:
                            click.echo(f"\n{idx}. [{orig_idx}] {bf.file_path} ({bf.change_type})")

                click.echo()
                # Show stats
                click.echo()
                stats = engine.get_stats()
                click.echo("Statistics:")
                click.echo(f"  Total tests run: {stats['tests_run']}")
                click.echo(f"  Passed: {stats['passed']}")
                click.echo(f"  Failed: {stats['failed']}")
                click.echo(f"  Skipped: {stats['skipped']}")
                click.echo(f"  Errors: {stats['errors']}")
                if "avg_test_time" in stats:
                    click.echo(
                        f"  Average test time: {BifurcationEngine.format_time(stats['avg_test_time'])}"
                    )
                    click.echo(
                        f"  Total time: {BifurcationEngine.format_time(stats['total_test_time'])}"
                    )

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

                _analyze_submodule_interactions(
                    git, test_runner, parent_sha, file_changes, commit_sha
                )

                # Show stats
                stats = engine.get_stats()
                click.echo("Statistics:")
                click.echo(f"  Total tests run: {stats['tests_run']}")

                # Clean up
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
                if isinstance(change, HunkChange):
                    click.echo(
                        f"  [{idx}] {change.file_path}:{change.start_line}-{change.end_line}"
                    )
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


@main.command()
@click.argument("good_commit")
@click.argument("bad_commit")
@click.option(
    "--test",
    "-t",
    required=True,
    help="Test command to run (e.g., 'pytest tests/test_feature.py')",
)
def bisect(good_commit: str, bad_commit: str, test: str) -> None:
    """Bisect commits to find the first bad commit.

    GOOD_COMMIT is the known good commit SHA.
    BAD_COMMIT is the known bad commit SHA.

    Example:
        git bifurcate bisect v1.0.0 HEAD --test "npm test"
    """
    try:
        git = GitRepo()
        test_runner = CommandRunner(test)

        click.echo(f"Bisecting commits from {good_commit[:8]} to {bad_commit[:8]}")
        click.echo(f"Test command: {test}")
        click.echo()

        bisector = CommitBisector(git, test_runner)

        # Get stats first
        stats = bisector.get_bisect_stats(good_commit, bad_commit)
        click.echo(f"Total commits to search: {stats['total_commits']}")
        click.echo(f"Estimated iterations: {stats['estimated_iterations']}")
        if stats["has_submodules"]:
            click.echo("Note: Repository contains submodules")
        click.echo()

        # Run bisection
        first_bad = bisector.bisect_commits(good_commit, bad_commit, verbose=True)

        if first_bad:
            click.echo()
            click.echo("=" * 60)
            click.echo("FIRST BAD COMMIT FOUND!")
            click.echo("=" * 60)
            click.echo()
            click.echo(f"Commit: {first_bad}")
            click.echo()
            click.echo("You can now run:")
            click.echo(f'  git bifurcate start {first_bad} --test "{test}"')
            click.echo("to find the exact change that broke the tests.")
        else:
            click.echo()
            click.echo("No bad commit found in the range.")

    except Exception as e:
        click.echo(f"Error during commit bisection: {e}")
        sys.exit(1)


@main.command(name="continue")
def continue_bifurcation() -> None:
    """Resume an interrupted bifurcation session.

    Loads the saved state and continues the bisection process.
    """
    if not BifurcationState.exists():
        click.echo("No bifurcation in progress to resume.")
        click.echo()
        click.echo("To start a new bifurcation:")
        click.echo("  git bifurcate start <commit> --test <command>")
        sys.exit(1)

    try:
        state = BifurcationState.load()

        click.echo("=" * 60)
        click.echo("RESUMING BIFURCATION")
        click.echo("=" * 60)
        click.echo()
        click.echo(f"Commit: {state.commit_sha[:8]}")
        click.echo(f"Parent: {state.parent_sha[:8]}")
        click.echo(f"Strategy: {state.strategy.value}")
        click.echo(f"Test command: {state.test_command}")
        click.echo(f"Iteration: {state.current_iteration}")
        click.echo(f"Search space: {len(state.search_space)} changes remaining")
        click.echo()

        git = GitRepo()
        test_runner = CommandRunner(state.test_command)
        engine = BifurcationEngine(git, test_runner)

        # Continue from where we left off
        if state.strategy == Strategy.FILE:
            file_changes = cast(list[FileChange], state.changes)
            remaining_changes = [file_changes[i] for i in state.search_space]

            if not remaining_changes:
                click.echo("Search space is empty. Bifurcation may be complete.")
                sys.exit(0)

            breaking_file = engine.bifurcate_files(
                remaining_changes, state.parent_sha, verbose=True
            )

            if breaking_file:
                click.echo()
                click.echo("=" * 60)
                click.echo("BREAKING CHANGE FOUND!")
                click.echo("=" * 60)
                click.echo()
                click.echo(f"File: {breaking_file.file_path}")
                click.echo(f"Type: {breaking_file.change_type}")
                click.echo()
                click.echo("Diff content:")
                click.echo("-" * 60)
                click.echo(breaking_file.diff_content)
                click.echo("-" * 60)
            else:
                click.echo()
                click.echo("No single breaking change found.")

        elif state.strategy == Strategy.HUNK:
            hunk_changes = cast(list[HunkChange], state.changes)
            remaining_hunks = [hunk_changes[i] for i in state.search_space]

            if not remaining_hunks:
                click.echo("Search space is empty. Bifurcation may be complete.")
                sys.exit(0)

            breaking_hunk = engine.bifurcate_hunks(
                remaining_hunks, state.parent_sha, state.commit_sha, verbose=True
            )

            if breaking_hunk:
                click.echo()
                click.echo("=" * 60)
                click.echo("BREAKING CHANGE FOUND!")
                click.echo("=" * 60)
                click.echo()
                click.echo(f"File: {breaking_hunk.file_path}")
                click.echo(f"Lines: {breaking_hunk.start_line}-{breaking_hunk.end_line}")
                click.echo()
                click.echo("Diff content:")
                click.echo("-" * 60)
                click.echo(breaking_hunk.diff_content)
                click.echo("-" * 60)
            else:
                click.echo()
                click.echo("No single breaking change found.")

        # Show stats
        stats = engine.get_stats()
        click.echo()
        click.echo("Statistics:")
        click.echo(f"  Total tests run: {stats['tests_run']}")
        click.echo(f"  Passed: {stats['passed']}")
        click.echo(f"  Failed: {stats['failed']}")
        click.echo(f"  Skipped: {stats['skipped']}")
        click.echo(f"  Errors: {stats['errors']}")

        # Clean up
        click.echo()
        click.echo("Cleaning up...")
        git.reset_hard(state.commit_sha)
        BifurcationState.delete()
        click.echo("✓ Done")

    except Exception as e:
        click.echo(f"Error resuming bifurcation: {e}")
        sys.exit(1)


def _analyze_submodule_drift(
    git: GitRepo,
    test_runner: CommandRunner,
    parent_sha: str,
    file_changes: list[FileChange],
    breaking_submodule: FileChange,
    commit_sha: str,
) -> None:
    """Dive into a breaking submodule change to pinpoint the inner culprit."""

    click.echo("Submodule update detected; drilling down to locate offending change...")
    inner_changes = git.get_submodule_changes(breaking_submodule)

    if not inner_changes:
        click.echo("  Unable to inspect submodule contents (no diff available).")
        return

    click.echo(f"  Found {len(inner_changes)} changes inside {breaking_submodule.file_path}")
    inner_engine = BifurcationEngine(git, test_runner)
    breaking_inner = inner_engine.bifurcate_files(inner_changes, parent_sha, verbose=True)

    if breaking_inner:
        click.echo("\nSubmodule-level breaking change identified:")
        click.echo(f"  Path: {breaking_inner.file_path}")
        click.echo(f"  Type: {breaking_inner.change_type}")
    else:
        click.echo("  No single submodule change isolated; interaction analysis may be required.")

    # Always return the working tree to the commit under investigation to avoid surprises
    git.reset_hard(commit_sha)


def _analyze_submodule_interactions(
    git: GitRepo,
    test_runner: CommandRunner,
    parent_sha: str,
    file_changes: list[FileChange],
    commit_sha: str,
) -> None:
    """Expand submodule updates into granular changes to search for interactions."""

    submodule_changes = [c for c in file_changes if c.change_type == "submodule"]
    if not submodule_changes:
        return

    nested_changes: list[FileChange] = []
    for sub_change in submodule_changes:
        nested_changes.extend(git.get_submodule_changes(sub_change))

    if not nested_changes:
        click.echo("No deeper submodule diffs available; skipping nested analysis.")
        return

    click.echo("Re-running search across supermodule changes and submodule internals...")
    combined_changes = [c for c in file_changes if c.change_type != "submodule"] + nested_changes
    inner_engine = BifurcationEngine(git, test_runner)
    breaking = inner_engine.bifurcate_files(combined_changes, parent_sha, verbose=True)

    if breaking:
        click.echo("\nInteraction candidate detected:")
        click.echo(f"  Path: {breaking.file_path}")
        click.echo(f"  Type: {breaking.change_type}")
    elif inner_engine.interaction_failure:
        click.echo(
            "  Possible interaction identified. Retry with the reported combination to confirm."
        )
    else:
        click.echo("  No interaction found within search budget.")

    git.reset_hard(commit_sha)


if __name__ == "__main__":
    main()
