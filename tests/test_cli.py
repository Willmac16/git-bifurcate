"""Tests for CLI interface."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from git_bifurcate.cli import main
from git_bifurcate.models import BifurcationState, ChangeStatus


@pytest.fixture
def runner() -> CliRunner:
    """Get Click CLI runner."""
    return CliRunner()


@pytest.fixture
def cli_test_repo(tmp_path: Path) -> Path:
    """Create a test git repository with a breaking change."""
    repo = tmp_path / "test-repo"
    repo.mkdir()

    # Initialize git
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True, capture_output=True
    )

    # Create initial version
    (repo / "module.py").write_text("value = 1\n")
    (repo / "test.sh").write_text("#!/bin/bash\npython3 -c 'from module import value; assert value == 1'\n")
    (repo / "test.sh").chmod(0o755)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo, check=True, capture_output=True)

    # Get parent SHA
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    )
    parent_sha = result.stdout.strip()

    # Create breaking version
    (repo / "module.py").write_text("value = 2\n")
    subprocess.run(["git", "add", "module.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Break test"], cwd=repo, check=True, capture_output=True
    )

    return repo


def test_cli_version(runner: CliRunner) -> None:
    """Test --version flag."""
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_help(runner: CliRunner) -> None:
    """Test --help flag."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "git-bifurcate" in result.output


def test_cli_start_help(runner: CliRunner) -> None:
    """Test start command help."""
    result = runner.invoke(main, ["start", "--help"])
    assert result.exit_code == 0
    assert "Start bifurcating" in result.output


def test_cli_start_no_test_command(runner: CliRunner, cli_test_repo: Path) -> None:
    """Test start without --test flag."""
    with runner.isolated_filesystem(temp_dir=cli_test_repo):
        result = runner.invoke(main, ["start"])
        assert result.exit_code != 0


def test_cli_start_already_in_progress(runner: CliRunner, cli_test_repo: Path, change_to_original_dir: None) -> None:
    """Test start when bifurcation already in progress."""
    os.chdir(cli_test_repo)

    # Create fake state file
    from git_bifurcate.models import FileChange, Strategy
    changes = [FileChange("0", "module.py", "modified", "diff", status=ChangeStatus.UNKNOWN)]
    state = BifurcationState(
        commit_sha="abc123",
        parent_sha="def456",
        test_command="bash test.sh",
        strategy=Strategy.FILE,
        changes=changes,
        search_space=[0],
    )
    state.save()

    result = runner.invoke(main, ["start", "--test", "bash test.sh"])
    assert result.exit_code != 0
    assert "already in progress" in result.output.lower()


def test_cli_status_no_bifurcation(runner: CliRunner, cli_test_repo: Path, change_to_original_dir: None) -> None:
    """Test status when no bifurcation in progress."""
    os.chdir(cli_test_repo)
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "No bifurcation in progress" in result.output


def test_cli_status_with_bifurcation(runner: CliRunner, cli_test_repo: Path, change_to_original_dir: None) -> None:
    """Test status when bifurcation in progress."""
    from git_bifurcate.models import FileChange, Strategy

    os.chdir(cli_test_repo)

    # Create fake state
    changes = [FileChange("0", "module.py", "modified", "diff", status=ChangeStatus.UNKNOWN)]
    state = BifurcationState(
        commit_sha="abc123",
        parent_sha="def456",
        test_command="bash test.sh",
        strategy=Strategy.FILE,
        changes=changes,
        search_space=[0],
    )
    state.save()

    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "Bifurcation in progress" in result.output or "abc123" in result.output


def test_cli_reset_no_bifurcation(runner: CliRunner, cli_test_repo: Path, change_to_original_dir: None) -> None:
    """Test reset when no bifurcation in progress."""
    os.chdir(cli_test_repo)
    result = runner.invoke(main, ["reset"])
    assert result.exit_code == 0
    assert "No bifurcation in progress" in result.output


def test_cli_reset_with_bifurcation(runner: CliRunner, cli_test_repo: Path, change_to_original_dir: None) -> None:
    """Test reset when bifurcation in progress."""
    from git_bifurcate.models import FileChange, Strategy
    import subprocess

    os.chdir(cli_test_repo)

    # Get a valid commit SHA
    result_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=cli_test_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    valid_sha = result_sha.stdout.strip()

    # Create fake state with valid SHA
    changes = [FileChange("0", "module.py", "modified", "diff", status=ChangeStatus.UNKNOWN)]
    state = BifurcationState(
        commit_sha=valid_sha,
        parent_sha=valid_sha,
        test_command="bash test.sh",
        strategy=Strategy.FILE,
        changes=changes,
        search_space=[0],
    )
    state.save()

    result = runner.invoke(main, ["reset"])
    assert result.exit_code == 0
    assert "abort" in result.output.lower() or "complete" in result.output.lower()

    # Verify state file is gone
    assert not BifurcationState.exists()

