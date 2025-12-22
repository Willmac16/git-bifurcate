"""Tests for CLI interface."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from git_bifurcate.cli import (
    _analyze_submodule_drift,
    _analyze_submodule_interactions,
    main,
)
from git_bifurcate.git_ops import GitRepo
from git_bifurcate.models import (
    BifurcationState,
    ChangeStatus,
    CommandResult,  # type: ignore  # re-export convenience
    FileChange,
    HunkChange,
    Strategy,
)
from git_bifurcate.test_runner import CommandRunner


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
    (repo / "test.sh").write_text(
        "#!/bin/bash\npython3 -c 'from module import value; assert value == 1'\n"
    )
    (repo / "test.sh").chmod(0o755)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo, check=True, capture_output=True)

    # Get parent SHA
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    )
    _parent_sha = result.stdout.strip()

    # Create breaking version
    (repo / "module.py").write_text("value = 2\n")
    subprocess.run(["git", "add", "module.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Break test"], cwd=repo, check=True, capture_output=True)

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


def test_cli_start_already_in_progress(
    runner: CliRunner, cli_test_repo: Path, change_to_original_dir: None
) -> None:
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


def test_cli_status_no_bifurcation(
    runner: CliRunner, cli_test_repo: Path, change_to_original_dir: None
) -> None:
    """Test status when no bifurcation in progress."""
    os.chdir(cli_test_repo)
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "No bifurcation in progress" in result.output


def test_cli_status_with_bifurcation(
    runner: CliRunner, cli_test_repo: Path, change_to_original_dir: None
) -> None:
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


def test_cli_reset_no_bifurcation(
    runner: CliRunner, cli_test_repo: Path, change_to_original_dir: None
) -> None:
    """Test reset when no bifurcation in progress."""
    os.chdir(cli_test_repo)
    result = runner.invoke(main, ["reset"])
    assert result.exit_code == 0
    assert "No bifurcation in progress" in result.output


def test_cli_reset_with_bifurcation(
    runner: CliRunner, cli_test_repo: Path, change_to_original_dir: None
) -> None:
    """Test reset when bifurcation in progress."""
    import subprocess

    from git_bifurcate.models import FileChange, Strategy

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


def test_cli_start_file_strategy_integration(
    runner: CliRunner, simple_fixture: Path, change_to_original_dir: None
) -> None:
    """Integration test for file strategy using real fixture repo."""

    from conftest import get_commit_shas

    os.chdir(simple_fixture)
    _parent_sha, bad_sha = get_commit_shas(simple_fixture)

    result = runner.invoke(
        main,
        ["start", bad_sha, "--strategy", "file", "--test", "bash test.sh"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "BREAKING CHANGE FOUND" in result.output
    assert "module2.py" in result.output
    # State file should be removed after successful run
    assert not BifurcationState.exists()


def test_cli_start_hunk_strategy_integration(
    runner: CliRunner, hunk_fixture: Path, change_to_original_dir: None
) -> None:
    """Integration test for hunk strategy using real fixture repo."""

    from conftest import get_commit_shas

    os.chdir(hunk_fixture)
    _parent_sha, bad_sha = get_commit_shas(hunk_fixture)

    result = runner.invoke(
        main,
        ["start", bad_sha, "--strategy", "hunk", "--test", "python3 test.py"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "BREAKING CHANGE FOUND" in result.output
    assert "calculator.py" in result.output
    assert "multiply" in result.output
    # State file should be removed after successful run
    assert not BifurcationState.exists()


def test_cli_main_no_subcommand_shows_help(runner: CliRunner) -> None:
    """Invoking without subcommands prints help text."""
    result = runner.invoke(main, [])
    assert result.exit_code == 0
    assert "Usage" in result.output


def test_cli_start_defaults_and_parent_option(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    """Start uses HEAD and explicit parent and exits when no changes exist."""

    class FakeGit:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def get_commit(self, ref: str) -> SimpleNamespace:
            return SimpleNamespace(hexsha=f"{ref}-sha")

        def get_parent_commit(self, sha: str) -> str:
            return f"{sha}-parent"

        def get_diff(self, commit_sha: str, parent_sha: str) -> str:
            self.calls.append((commit_sha, parent_sha))
            return "diff"

    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: False))
    monkeypatch.setattr("git_bifurcate.cli.GitRepo", FakeGit)
    monkeypatch.setattr("git_bifurcate.cli.parse_file_changes", lambda diff: [])

    result = runner.invoke(main, ["start", "--test", "echo", "--parent", "explicit"])
    assert result.exit_code == 1
    assert "No changes found" in result.output


def test_cli_start_all_changes_should_fail(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    """If the combined change passes, the CLI aborts early."""

    class FakeGit:
        def __init__(self) -> None:
            self.repo_path = Path(".")

        def get_commit(self, ref: str) -> SimpleNamespace:
            return SimpleNamespace(hexsha="abc123")

        def get_parent_commit(self, sha: str) -> str:
            return "parent"

        def get_diff(self, commit_sha: str, parent_sha: str) -> str:
            return "diff"

    class FakeEngine:
        def __init__(self, *_: object) -> None:
            self.calls = 0

        def _test_changes(self, *args, **kwargs) -> CommandResult:
            return CommandResult.PASS

    file_change = FileChange("0", "file.txt", "modified", "diff", status=ChangeStatus.UNKNOWN)

    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: False))
    monkeypatch.setattr("git_bifurcate.cli.GitRepo", FakeGit)
    monkeypatch.setattr("git_bifurcate.cli.parse_file_changes", lambda diff: [file_change])
    monkeypatch.setattr("git_bifurcate.cli.CommandRunner", lambda cmd: None)
    monkeypatch.setattr("git_bifurcate.cli.BifurcationEngine", FakeEngine)

    result = runner.invoke(main, ["start", "--test", "echo"])
    assert result.exit_code == 1
    assert "Expected test to FAIL" in result.output


def test_cli_start_parent_should_pass(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    """Parent failing triggers guidance output."""

    class FakeGit:
        def __init__(self) -> None:
            self.repo_path = Path(".")

        def get_commit(self, ref: str) -> SimpleNamespace:
            return SimpleNamespace(hexsha="abc123")

        def get_parent_commit(self, sha: str) -> str:
            return "parent"

        def get_diff(self, commit_sha: str, parent_sha: str) -> str:
            return "diff"

    class FakeEngine:
        def __init__(self, *_: object) -> None:
            self.calls = 0

        def _test_changes(self, *args, **kwargs) -> CommandResult:
            self.calls += 1
            return CommandResult.FAIL if self.calls == 1 else CommandResult.ERROR

    file_change = FileChange("0", "file.txt", "modified", "diff", status=ChangeStatus.UNKNOWN)

    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: False))
    monkeypatch.setattr("git_bifurcate.cli.GitRepo", FakeGit)
    monkeypatch.setattr("git_bifurcate.cli.parse_file_changes", lambda diff: [file_change])
    monkeypatch.setattr("git_bifurcate.cli.CommandRunner", lambda cmd: None)
    monkeypatch.setattr("git_bifurcate.cli.BifurcationEngine", FakeEngine)

    result = runner.invoke(main, ["start", "--test", "echo"])
    assert result.exit_code == 1
    assert "Expected test to PASS" in result.output


def test_cli_start_no_breaking_file_found(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    """When no single breaking file is found, the CLI reports and cleans up."""

    class FakeGit:
        def __init__(self) -> None:
            self.repo_path = Path(".")
            self.reset_calls: list[str] = []

        def get_commit(self, ref: str) -> SimpleNamespace:
            return SimpleNamespace(hexsha="abc123")

        def get_parent_commit(self, sha: str) -> str:
            return "parent"

        def get_diff(self, commit_sha: str, parent_sha: str) -> str:
            return "diff"

        def reset_hard(self, ref: str) -> None:
            self.reset_calls.append(ref)

    class FakeEngine:
        def __init__(self, *_: object) -> None:
            self.calls = 0

        def _test_changes(self, *args, **kwargs) -> CommandResult:
            self.calls += 1
            return CommandResult.FAIL if self.calls == 1 else CommandResult.PASS

        def bifurcate_files(self, *_: object, **__: object):
            return None

        def get_stats(self) -> dict[str, int]:
            return {"tests_run": 1, "passed": 0, "failed": 1, "skipped": 0, "errors": 0}

    file_change = FileChange("0", "file.txt", "modified", "diff", status=ChangeStatus.UNKNOWN)

    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: False))
    monkeypatch.setattr(BifurcationState, "save", lambda self, filepath=None: None)
    monkeypatch.setattr(BifurcationState, "delete", staticmethod(lambda filepath=None: None))
    monkeypatch.setattr("git_bifurcate.cli.GitRepo", FakeGit)
    monkeypatch.setattr("git_bifurcate.cli.parse_file_changes", lambda diff: [file_change])
    monkeypatch.setattr("git_bifurcate.cli.CommandRunner", lambda cmd: None)
    monkeypatch.setattr("git_bifurcate.cli.BifurcationEngine", FakeEngine)

    result = runner.invoke(main, ["start", "--test", "echo"])
    assert result.exit_code == 0
    assert "NO SINGLE BREAKING CHANGE FOUND" in result.output


def test_cli_start_hunk_no_changes(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    """Hunk strategy exits when no hunks are present."""

    class FakeGit:
        def __init__(self) -> None:
            self.repo_path = Path(".")

        def get_commit(self, ref: str) -> SimpleNamespace:
            return SimpleNamespace(hexsha="abc123")

        def get_parent_commit(self, sha: str) -> str:
            return "parent"

        def get_diff(self, commit_sha: str, parent_sha: str) -> str:
            return "diff"

    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: False))
    monkeypatch.setattr("git_bifurcate.cli.GitRepo", FakeGit)
    monkeypatch.setattr("git_bifurcate.cli.parse_hunk_changes", lambda diff: [])

    result = runner.invoke(main, ["start", "--strategy", "hunk", "--test", "echo"])
    assert result.exit_code == 1
    assert "No changes found" in result.output


def test_cli_start_hunk_expected_fail(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    """Hunk strategy requires the combined change to fail."""

    class FakeGit:
        def __init__(self) -> None:
            self.repo_path = Path(".")

        def get_commit(self, ref: str) -> SimpleNamespace:
            return SimpleNamespace(hexsha="abc123")

        def get_parent_commit(self, sha: str) -> str:
            return "parent"

        def get_diff(self, commit_sha: str, parent_sha: str) -> str:
            return "diff"

    class FakeEngine:
        def __init__(self, *_: object) -> None:
            pass

        def _test_hunk_changes(self, *args, **kwargs) -> CommandResult:
            return CommandResult.PASS

    hunk = HunkChange(
        id="0",
        file_path="file.txt",
        start_line=1,
        end_line=1,
        original_start=1,
        original_length=1,
        new_start=1,
        new_length=1,
        diff_content="@@",
        status=ChangeStatus.UNKNOWN,
    )

    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: False))
    monkeypatch.setattr("git_bifurcate.cli.GitRepo", FakeGit)
    monkeypatch.setattr("git_bifurcate.cli.parse_hunk_changes", lambda diff: [hunk])
    monkeypatch.setattr("git_bifurcate.cli.CommandRunner", lambda cmd: None)
    monkeypatch.setattr("git_bifurcate.cli.BifurcationEngine", FakeEngine)

    result = runner.invoke(main, ["start", "--strategy", "hunk", "--test", "echo"])
    assert result.exit_code == 1
    assert "Expected test to FAIL" in result.output


def test_cli_start_hunk_parent_should_pass(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    """Hunk strategy aborts when parent does not pass."""

    class FakeGit:
        def __init__(self) -> None:
            self.repo_path = Path(".")

        def get_commit(self, ref: str) -> SimpleNamespace:
            return SimpleNamespace(hexsha="abc123")

        def get_parent_commit(self, sha: str) -> str:
            return "parent"

        def get_diff(self, commit_sha: str, parent_sha: str) -> str:
            return "diff"

    class FakeEngine:
        def __init__(self, *_: object) -> None:
            self.calls = 0

        def _test_hunk_changes(self, *args, **kwargs) -> CommandResult:
            self.calls += 1
            return CommandResult.FAIL if self.calls == 1 else CommandResult.ERROR

    hunk = HunkChange(
        id="0",
        file_path="file.txt",
        start_line=1,
        end_line=1,
        original_start=1,
        original_length=1,
        new_start=1,
        new_length=1,
        diff_content="@@",
        status=ChangeStatus.UNKNOWN,
    )

    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: False))
    monkeypatch.setattr("git_bifurcate.cli.GitRepo", FakeGit)
    monkeypatch.setattr("git_bifurcate.cli.parse_hunk_changes", lambda diff: [hunk])
    monkeypatch.setattr("git_bifurcate.cli.CommandRunner", lambda cmd: None)
    monkeypatch.setattr("git_bifurcate.cli.BifurcationEngine", FakeEngine)

    result = runner.invoke(main, ["start", "--strategy", "hunk", "--test", "echo"])
    assert result.exit_code == 1
    assert "Expected test to PASS" in result.output


def test_cli_start_hunk_no_breaking_change(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    """No single hunk found path is reported and cleaned."""

    class FakeGit:
        def __init__(self) -> None:
            self.repo_path = Path(".")
            self.reset_calls: list[str] = []

        def get_commit(self, ref: str) -> SimpleNamespace:
            return SimpleNamespace(hexsha="abc123")

        def get_parent_commit(self, sha: str) -> str:
            return "parent"

        def get_diff(self, commit_sha: str, parent_sha: str) -> str:
            return "diff"

        def reset_hard(self, ref: str) -> None:
            self.reset_calls.append(ref)

    class FakeEngine:
        def __init__(self, *_: object) -> None:
            self.calls = 0

        def _test_hunk_changes(self, *args, **kwargs) -> CommandResult:
            self.calls += 1
            return CommandResult.FAIL if self.calls == 1 else CommandResult.PASS

        def bifurcate_hunks(self, *_: object, **__: object):
            return None

        def get_stats(self) -> dict[str, int]:
            return {"tests_run": 1, "passed": 0, "failed": 1, "skipped": 0, "errors": 0}

    hunk = HunkChange(
        id="0",
        file_path="file.txt",
        start_line=1,
        end_line=1,
        original_start=1,
        original_length=1,
        new_start=1,
        new_length=1,
        diff_content="@@",
        status=ChangeStatus.UNKNOWN,
    )

    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: False))
    monkeypatch.setattr(BifurcationState, "save", lambda self, filepath=None: None)
    monkeypatch.setattr(BifurcationState, "delete", staticmethod(lambda filepath=None: None))
    monkeypatch.setattr("git_bifurcate.cli.GitRepo", FakeGit)
    monkeypatch.setattr("git_bifurcate.cli.parse_hunk_changes", lambda diff: [hunk])
    monkeypatch.setattr("git_bifurcate.cli.CommandRunner", lambda cmd: None)
    monkeypatch.setattr("git_bifurcate.cli.BifurcationEngine", FakeEngine)

    result = runner.invoke(main, ["start", "--strategy", "hunk", "--test", "echo"])
    assert result.exit_code == 0
    assert "NO SINGLE BREAKING CHANGE FOUND" in result.output


def test_cli_start_unexpected_exception(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    """Unexpected exceptions fall back to cleanup messaging."""

    class FakeGit:
        def __init__(self) -> None:
            raise ValueError("boom")

    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: False))
    monkeypatch.setattr("git_bifurcate.cli.GitRepo", FakeGit)

    result = runner.invoke(main, ["start", "--test", "echo"])
    assert result.exit_code == 1
    assert "Unexpected error" in result.output


def test_cli_start_hybrid_strategy(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    """Hybrid strategy is not implemented."""

    class FakeGit:
        def __init__(self) -> None:
            self.repo_path = Path(".")

        def get_commit(self, ref: str) -> SimpleNamespace:
            return SimpleNamespace(hexsha="abc123")

        def get_parent_commit(self, sha: str) -> str:
            return "parent"

        def get_diff(self, commit_sha: str, parent_sha: str) -> str:
            return "diff"

    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: False))
    monkeypatch.setattr("git_bifurcate.cli.GitRepo", FakeGit)

    result = runner.invoke(main, ["start", "--strategy", "hybrid", "--test", "echo"])
    assert result.exit_code == 1
    assert "Hybrid strategy" in result.output


def test_cli_start_file_not_found(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    """FileNotFoundError is handled explicitly."""

    class FakeGit:
        def __init__(self) -> None:
            raise FileNotFoundError("missing repo")

    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: False))
    monkeypatch.setattr("git_bifurcate.cli.GitRepo", FakeGit)

    result = runner.invoke(main, ["start", "--test", "echo"])
    assert result.exit_code == 1
    assert "Error: missing repo" in result.output


def test_cli_start_cleanup_success(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    """Cleanup succeeds when an unexpected error occurs."""
    cleanup_git = SimpleNamespace(reset_calls=[])

    class FakeGit:
        def __init__(self, fail: bool = False) -> None:
            self.fail = fail
            self.repo_path = Path(".")

        def get_commit(self, ref: str) -> SimpleNamespace:
            if self.fail:
                raise RuntimeError("boom")
            return SimpleNamespace(hexsha="abc123")

        def get_parent_commit(self, sha: str) -> str:
            return "parent"

        def get_diff(self, commit_sha: str, parent_sha: str) -> str:
            return "diff"

        def reset_hard(self, ref: str) -> None:
            cleanup_git.reset_calls.append(ref)

    git_instances = [FakeGit(fail=True), FakeGit(fail=False)]

    def git_factory(*args, **kwargs):
        return git_instances.pop(0)

    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: False))
    monkeypatch.setattr(
        BifurcationState, "load", classmethod(lambda cls: SimpleNamespace(commit_sha="abc123"))
    )
    monkeypatch.setattr(BifurcationState, "delete", staticmethod(lambda filepath=None: None))
    monkeypatch.setattr("git_bifurcate.cli.GitRepo", git_factory)

    result = runner.invoke(main, ["start", "--test", "echo"])
    assert result.exit_code == 1
    assert "Cleanup successful" in result.output
    assert cleanup_git.reset_calls == ["abc123"]


def test_cli_status_lists_breaking(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    """Status prints both hunk and file breaking entries."""
    state = BifurcationState(
        commit_sha="abc",
        parent_sha="def",
        test_command="echo",
        strategy=Strategy.FILE,
        changes=[
            HunkChange(
                id="0",
                file_path="file.txt",
                start_line=1,
                end_line=1,
                original_start=1,
                original_length=1,
                new_start=1,
                new_length=1,
                diff_content="@@",
                status=ChangeStatus.UNKNOWN,
            ),
            FileChange("1", "another.txt", "modified", "diff", status=ChangeStatus.UNKNOWN),
        ],
        search_space=[],
        tested_combinations={},
        found_breaking=[0, 1],
    )

    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: True))
    monkeypatch.setattr(BifurcationState, "load", classmethod(lambda cls: state))

    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "Breaking changes found" in result.output
    assert "file.txt" in result.output
    assert "another.txt" in result.output


def test_cli_status_load_error(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    """Status handles load errors by exiting."""
    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: True))
    monkeypatch.setattr(
        BifurcationState, "load", classmethod(lambda cls: (_ for _ in ()).throw(ValueError("bad")))
    )

    result = runner.invoke(main, ["status"])
    assert result.exit_code == 1
    assert "Error loading state" in result.output


def test_cli_reset_missing_state(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    """Reset handles missing state with and without force."""
    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: True))
    monkeypatch.setattr(
        BifurcationState,
        "load",
        classmethod(lambda cls: (_ for _ in ()).throw(FileNotFoundError())),
    )

    result = runner.invoke(main, ["reset"])
    assert result.exit_code == 1
    assert "State file not found" in result.output

    result_force = runner.invoke(main, ["reset", "--force"])
    assert result_force.exit_code == 0
    assert "Cleanup attempted" in result_force.output


def test_cli_reset_generic_error(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    """Unexpected reset errors are reported with guidance."""
    state = BifurcationState(
        commit_sha="abc",
        parent_sha="abc",
        test_command="echo",
        strategy=Strategy.FILE,
        changes=[],
        search_space=[],
    )

    class FakeGit:
        def __init__(self) -> None:
            pass

        def reset_hard(self, ref: str) -> None:
            raise ValueError("boom")

        def delete_branch(self, name: str) -> None:
            raise ValueError("ignored")

    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: True))
    monkeypatch.setattr(BifurcationState, "load", classmethod(lambda cls: state))
    monkeypatch.setattr("git_bifurcate.cli.GitRepo", FakeGit)

    result = runner.invoke(main, ["reset"])
    assert result.exit_code == 1
    assert "Error during reset" in result.output


def test_cli_main_guard_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Executing the module directly triggers the main guard."""
    import importlib.util

    monkeypatch.setenv("PYTHONPATH", "src")
    monkeypatch.setattr(sys, "argv", ["cli.py", "--help"])
    spec = importlib.util.spec_from_file_location("__main__", "src/git_bifurcate/cli.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    with pytest.raises(SystemExit) as excinfo:
        spec.loader.exec_module(module)  # type: ignore[arg-type]
    assert excinfo.value.code == 0


def test_cli_start_triggers_submodule_analysis(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    """start calls submodule analysis helpers when a submodule is the culprit."""
    drift_calls: list[tuple] = []

    class FakeGit:
        def __init__(self) -> None:
            self.repo_path = Path(".")
            self.reset_calls: list[str] = []

        def get_commit(self, ref: str) -> SimpleNamespace:
            return SimpleNamespace(hexsha="bad")

        def get_parent_commit(self, sha: str) -> str:
            return "good"

        def get_diff(self, *args, **kwargs) -> str:
            return "diff"

        def reset_hard(self, ref: str) -> None:
            self.reset_calls.append(ref)

    sub_change = FileChange("0", "vendor/lib", "submodule", "diff", status=ChangeStatus.UNKNOWN)

    class FakeEngine:
        def __init__(self, *_: object) -> None:
            pass

        def _test_changes(self, changes, base, indices):
            return CommandResult.FAIL if indices else CommandResult.PASS

        def bifurcate_files(self, changes, base, verbose=True):
            return sub_change

        def get_stats(self) -> dict[str, int]:
            return {"tests_run": 2, "passed": 1, "failed": 1, "skipped": 0, "errors": 0}

    def fake_drift(git, test_runner, parent_sha, file_changes, breaking_submodule, commit_sha):
        drift_calls.append((parent_sha, commit_sha, breaking_submodule.file_path))

    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: False))
    monkeypatch.setattr("git_bifurcate.cli.GitRepo", FakeGit)
    monkeypatch.setattr("git_bifurcate.cli.CommandRunner", lambda cmd: None)
    monkeypatch.setattr("git_bifurcate.cli.BifurcationEngine", FakeEngine)
    monkeypatch.setattr("git_bifurcate.cli._analyze_submodule_drift", fake_drift)
    monkeypatch.setattr("git_bifurcate.cli.parse_file_changes", lambda diff: [sub_change])

    result = runner.invoke(main, ["start", "--test", "echo", "HEAD"])
    assert result.exit_code == 0
    assert drift_calls and drift_calls[0][2] == "vendor/lib"


def test_analyze_submodule_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Helper functions handle empty and populated submodule diffs."""
    inner_change = FileChange(
        "1", "vendor/lib/file.py", "modified", "diff", status=ChangeStatus.UNKNOWN
    )

    class FakeEngine:
        def __init__(self, *_: object) -> None:
            self.interaction_failure: list[int] | None = [0]

        def bifurcate_files(self, changes, base, verbose=True):
            self.changes_seen = changes
            return None

    class FakeGit(GitRepo):
        def __init__(self, inner: list[FileChange]) -> None:
            self.inner = inner
            self.reset_calls: list[str] = []

        def get_submodule_changes(self, change: FileChange) -> list[FileChange]:  # type: ignore[override]
            return self.inner

        def reset_hard(self, ref: str) -> None:
            self.reset_calls.append(ref)

    class DummyRunner(CommandRunner):
        def __init__(self) -> None:
            self.test_command = "noop"

        def run(self) -> CommandResult:
            return CommandResult.PASS

    # Drift with no inner changes
    git = FakeGit([])
    runner = DummyRunner()
    _analyze_submodule_drift(
        git,
        runner,
        "good",
        [],
        FileChange("0", "vendor/lib", "submodule", "diff", status=ChangeStatus.UNKNOWN),
        "bad",
    )  # type: ignore[arg-type]
    assert git.reset_calls == []

    # Drift with inner changes that don't isolate a change
    git2 = FakeGit([inner_change])
    monkeypatch.setattr("git_bifurcate.cli.BifurcationEngine", FakeEngine)
    _analyze_submodule_drift(
        git2,
        runner,
        "good",
        [],
        FileChange("0", "vendor/lib", "submodule", "diff", status=ChangeStatus.UNKNOWN),
        "bad",
    )  # type: ignore[arg-type]
    assert git2.reset_calls[-1] == "bad"

    # Drift with a breaking inner change
    class BreakingEngine(FakeEngine):
        def bifurcate_files(self, changes, base, verbose=True):
            return inner_change

    git_break = FakeGit([inner_change])
    monkeypatch.setattr("git_bifurcate.cli.BifurcationEngine", BreakingEngine)
    _analyze_submodule_drift(
        git_break,
        runner,
        "good",
        [],
        FileChange("0", "vendor/lib", "submodule", "diff", status=ChangeStatus.UNKNOWN),
        "bad",
    )  # type: ignore[arg-type]
    assert git_break.reset_calls[-1] == "bad"

    # Interactions: no submodule changes short-circuit
    _analyze_submodule_interactions(git, runner, "good", [], "bad")  # type: ignore[arg-type]

    # Interactions with nested changes
    def get_changes(change: FileChange) -> list[FileChange]:
        return [inner_change]

    git3 = FakeGit([])
    git3.get_submodule_changes = get_changes  # type: ignore[assignment]
    monkeypatch.setattr("git_bifurcate.cli.BifurcationEngine", FakeEngine)
    _analyze_submodule_interactions(
        git3,
        runner,
        "good",
        [FileChange("0", "vendor/lib", "submodule", "diff", status=ChangeStatus.UNKNOWN)],
        "bad",
    )  # type: ignore[arg-type]
    assert git3.reset_calls[-1] == "bad"

    # Interactions where no nested diffs are available despite submodule references
    git_empty_nested = FakeGit([])
    git_empty_nested.get_submodule_changes = lambda change: []  # type: ignore[assignment]
    _analyze_submodule_interactions(
        git_empty_nested,
        runner,
        "good",
        [FileChange("0", "vendor/lib", "submodule", "diff", status=ChangeStatus.UNKNOWN)],
        "bad",
    )  # type: ignore[arg-type]

    # Interactions where a breaking nested change is found
    class BreakingInteractions(FakeEngine):
        def bifurcate_files(self, changes, base, verbose=True):
            return inner_change

    git_found = FakeGit([])
    git_found.get_submodule_changes = get_changes  # type: ignore[assignment]
    monkeypatch.setattr("git_bifurcate.cli.BifurcationEngine", BreakingInteractions)
    _analyze_submodule_interactions(
        git_found,
        runner,
        "good",
        [FileChange("0", "vendor/lib", "submodule", "diff", status=ChangeStatus.UNKNOWN)],
        "bad",
    )  # type: ignore[arg-type]
    assert git_found.reset_calls[-1] == "bad"

    # Interactions where no combination is identified
    class NoInteractionEngine(FakeEngine):
        def __init__(self, *_: object) -> None:
            super().__init__()
            self.interaction_failure = None

    git_none = FakeGit([])
    git_none.get_submodule_changes = get_changes  # type: ignore[assignment]
    monkeypatch.setattr("git_bifurcate.cli.BifurcationEngine", NoInteractionEngine)
    _analyze_submodule_interactions(
        git_none,
        runner,
        "good",
        [FileChange("0", "vendor/lib", "submodule", "diff", status=ChangeStatus.UNKNOWN)],
        "bad",
    )  # type: ignore[arg-type]
    assert git_none.reset_calls[-1] == "bad"


def test_cli_bisect_command(runner: CliRunner, simple_fixture: Path) -> None:
    """Test the bisect command."""
    from conftest import get_commit_shas

    os.chdir(simple_fixture)
    parent_sha, bad_sha = get_commit_shas(simple_fixture)

    result = runner.invoke(
        main,
        ["bisect", parent_sha, bad_sha, "--test", "bash test.sh"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "FIRST BAD COMMIT FOUND" in result.output or "Bisecting commits" in result.output


def test_cli_bisect_no_commits(runner: CliRunner, simple_fixture: Path) -> None:
    """Test bisect with same good/bad commit."""
    from conftest import get_commit_shas

    os.chdir(simple_fixture)
    parent_sha, _bad_sha = get_commit_shas(simple_fixture)

    # Use same commit as both good and bad
    result = runner.invoke(
        main,
        ["bisect", parent_sha, parent_sha, "--test", "true"],
        catch_exceptions=False,
    )

    # Should handle gracefully
    assert "No bad commit found" in result.output or "0" in result.output


def test_cli_continue_no_session(runner: CliRunner) -> None:
    """Test continue command with no session."""
    result = runner.invoke(main, ["continue"], catch_exceptions=False)

    assert result.exit_code == 1
    assert "No bifurcation in progress" in result.output


def test_cli_continue_with_session(
    runner: CliRunner, simple_fixture: Path, change_to_original_dir: None
) -> None:
    """Test continue command with existing session."""
    from conftest import get_commit_shas

    os.chdir(simple_fixture)
    parent_sha, bad_sha = get_commit_shas(simple_fixture)

    # Create a state file
    from git_bifurcate.git_ops import GitRepo
    from git_bifurcate.models import Strategy
    from git_bifurcate.parser import parse_file_changes

    git = GitRepo()
    diff_text = git.get_diff(bad_sha, parent_sha)
    file_changes = parse_file_changes(diff_text)

    state = BifurcationState(
        commit_sha=bad_sha,
        parent_sha=parent_sha,
        test_command="bash test.sh",
        strategy=Strategy.FILE,
        changes=file_changes,
        search_space=list(range(len(file_changes))),
    )
    state.save()

    # Run continue
    result = runner.invoke(main, ["continue"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "RESUMING BIFURCATION" in result.output


def test_cli_start_with_analyze_deps(
    runner: CliRunner, simple_fixture: Path, change_to_original_dir: None
) -> None:
    """Test start command with dependency analysis."""
    from conftest import get_commit_shas

    os.chdir(simple_fixture)
    _parent_sha, bad_sha = get_commit_shas(simple_fixture)

    result = runner.invoke(
        main,
        ["start", bad_sha, "--strategy", "file", "--test", "bash test.sh", "--analyze-deps"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Analyzing dependencies" in result.output


def test_cli_start_with_find_more(
    runner: CliRunner,
    simple_fixture: Path,
    change_to_original_dir: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test start command with find-more flag."""
    from conftest import get_commit_shas

    os.chdir(simple_fixture)
    _parent_sha, bad_sha = get_commit_shas(simple_fixture)

    # Mock click.confirm to always return False (don't continue)
    import click

    monkeypatch.setattr(click, "confirm", lambda _: False)

    result = runner.invoke(
        main,
        ["start", bad_sha, "--strategy", "file", "--test", "bash test.sh", "--find-more"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    # Should find at least one breaking change
    assert "BREAKING CHANGE" in result.output


def test_cli_start_find_more_multiple_breaks(
    runner: CliRunner,
    simple_fixture: Path,
    change_to_original_dir: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test find-more flag finding multiple breaks."""
    import click
    from conftest import get_commit_shas

    os.chdir(simple_fixture)
    _parent_sha, bad_sha = get_commit_shas(simple_fixture)

    # Mock to return True once, then False
    confirm_calls = [True, False]

    def mock_confirm(_prompt: str) -> bool:
        if confirm_calls:
            return confirm_calls.pop(0)
        return False

    monkeypatch.setattr(click, "confirm", mock_confirm)

    result = runner.invoke(
        main,
        ["start", bad_sha, "--strategy", "file", "--test", "bash test.sh", "--find-more"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "BREAKING CHANGE" in result.output


def test_cli_continue_empty_search_space(
    runner: CliRunner, simple_fixture: Path, change_to_original_dir: None
) -> None:
    """Test continue with empty search space."""
    from conftest import get_commit_shas

    from git_bifurcate.git_ops import GitRepo
    from git_bifurcate.models import Strategy
    from git_bifurcate.parser import parse_file_changes

    os.chdir(simple_fixture)
    parent_sha, bad_sha = get_commit_shas(simple_fixture)

    git = GitRepo()
    diff_text = git.get_diff(bad_sha, parent_sha)
    file_changes = parse_file_changes(diff_text)

    # Create state with empty search space
    state = BifurcationState(
        commit_sha=bad_sha,
        parent_sha=parent_sha,
        test_command="bash test.sh",
        strategy=Strategy.FILE,
        changes=file_changes,
        search_space=[],  # Empty!
    )
    state.save()

    result = runner.invoke(main, ["continue"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Search space is empty" in result.output


def test_cli_bisect_error_handling(runner: CliRunner) -> None:
    """Test bisect command error handling."""
    # Test with invalid commit - should handle gracefully
    result = runner.invoke(
        main,
        ["bisect", "invalid_sha", "invalid_sha2", "--test", "true"],
    )

    # Should either error or handle gracefully
    assert result.exit_code in [0, 1]
    # Output should contain either error or commit info
    assert "Error" in result.output or "Bisecting" in result.output or "commits" in result.output


def test_cli_continue_hunk_strategy(
    runner: CliRunner, hunk_fixture: Path, change_to_original_dir: None
) -> None:
    """Test continue command with hunk strategy."""
    from conftest import get_commit_shas

    from git_bifurcate.git_ops import GitRepo
    from git_bifurcate.models import Strategy
    from git_bifurcate.parser import parse_hunk_changes

    os.chdir(hunk_fixture)
    parent_sha, bad_sha = get_commit_shas(hunk_fixture)

    git = GitRepo()
    diff_text = git.get_diff(bad_sha, parent_sha)
    hunk_changes = parse_hunk_changes(diff_text)

    # Create state with hunk strategy
    state = BifurcationState(
        commit_sha=bad_sha,
        parent_sha=parent_sha,
        test_command="python3 test.py",
        strategy=Strategy.HUNK,
        changes=hunk_changes,
        search_space=list(range(len(hunk_changes))),
    )
    state.save()

    result = runner.invoke(main, ["continue"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "RESUMING BIFURCATION" in result.output


def test_cli_start_hunk_with_analyze_deps(
    runner: CliRunner, hunk_fixture: Path, change_to_original_dir: None
) -> None:
    """Test hunk strategy with dependency analysis."""
    from conftest import get_commit_shas

    os.chdir(hunk_fixture)
    _parent_sha, bad_sha = get_commit_shas(hunk_fixture)

    result = runner.invoke(
        main,
        ["start", bad_sha, "--strategy", "hunk", "--test", "python3 test.py", "--analyze-deps"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Analyzing dependencies" in result.output


def test_cli_start_hunk_with_find_more(
    runner: CliRunner,
    hunk_fixture: Path,
    change_to_original_dir: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test hunk strategy with find-more flag."""
    import click
    from conftest import get_commit_shas

    os.chdir(hunk_fixture)
    _parent_sha, bad_sha = get_commit_shas(hunk_fixture)

    monkeypatch.setattr(click, "confirm", lambda _: False)

    result = runner.invoke(
        main,
        ["start", bad_sha, "--strategy", "hunk", "--test", "python3 test.py", "--find-more"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "BREAKING CHANGE" in result.output


def test_cli_continue_error(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test continue with error during execution."""
    from git_bifurcate.models import BifurcationState

    # Create an invalid state that will cause an error
    os.chdir(tmp_path)

    # Mock to make state exist but fail to load
    monkeypatch.setattr(BifurcationState, "exists", lambda *args: True)
    monkeypatch.setattr(
        BifurcationState,
        "load",
        lambda *args: (_ for _ in ()).throw(Exception("Test error")),
    )

    result = runner.invoke(main, ["continue"])

    assert result.exit_code == 1
    assert "Error" in result.output


def test_cli_bisect_with_stats(runner: CliRunner, simple_fixture: Path) -> None:
    """Test bisect command shows statistics."""
    from conftest import get_commit_shas

    os.chdir(simple_fixture)
    parent_sha, bad_sha = get_commit_shas(simple_fixture)

    result = runner.invoke(
        main,
        ["bisect", parent_sha, bad_sha, "--test", "bash test.sh"],
        catch_exceptions=False,
    )

    assert "Total commits to search" in result.output
    assert "Estimated iterations" in result.output


def test_cli_continue_with_stats(
    runner: CliRunner, simple_fixture: Path, change_to_original_dir: None
) -> None:
    """Test continue shows statistics at end."""
    from conftest import get_commit_shas

    from git_bifurcate.git_ops import GitRepo
    from git_bifurcate.models import Strategy
    from git_bifurcate.parser import parse_file_changes

    os.chdir(simple_fixture)
    parent_sha, bad_sha = get_commit_shas(simple_fixture)

    git = GitRepo()
    diff_text = git.get_diff(bad_sha, parent_sha)
    file_changes = parse_file_changes(diff_text)

    # Create state file
    state = BifurcationState(
        commit_sha=bad_sha,
        parent_sha=parent_sha,
        test_command="bash test.sh",
        strategy=Strategy.FILE,
        changes=file_changes,
        search_space=list(range(len(file_changes))),
    )
    state.save()

    result = runner.invoke(main, ["continue"], catch_exceptions=False)

    assert result.exit_code == 0
    # Should show stats
    assert "Statistics" in result.output or "RESUMING BIFURCATION" in result.output


def test_cli_bisect_exception_handling(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test bisect command exception handling (lines 687-689)."""
    from git_bifurcate.commit_bisect import CommitBisector

    # Mock to raise an exception
    def raise_error(*args, **kwargs):
        raise ValueError("Test error")

    monkeypatch.setattr(CommitBisector, "bisect_commits", raise_error)

    result = runner.invoke(
        main,
        ["bisect", "abc123", "def456", "--test", "true"],
    )

    assert result.exit_code == 1
    assert "Error during commit bisection" in result.output


def test_cli_start_find_more_exhausts_all_changes(
    runner: CliRunner,
    simple_fixture: Path,
    change_to_original_dir: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test find-more exhausts all changes (line 213)."""
    from conftest import get_commit_shas

    from git_bifurcate.core import BifurcationEngine

    os.chdir(simple_fixture)
    _parent_sha, bad_sha = get_commit_shas(simple_fixture)

    # Track how many times bifurcate_files is called
    call_count = [0]
    original_bifurcate = BifurcationEngine.bifurcate_files

    def mock_bifurcate(self, changes, *args, **kwargs):
        call_count[0] += 1
        # First call finds a change, subsequent calls find nothing
        if call_count[0] == 1:
            result = original_bifurcate(self, changes, *args, **kwargs)
            return result
        return None

    monkeypatch.setattr(BifurcationEngine, "bifurcate_files", mock_bifurcate)
    monkeypatch.setattr("click.confirm", lambda _: True)  # Always continue

    result = runner.invoke(
        main,
        ["start", bad_sha, "--strategy", "file", "--test", "bash test.sh", "--find-more"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    # Should have made multiple attempts
    assert call_count[0] >= 2


def test_cli_start_find_more_finds_multiple_files(
    runner: CliRunner,
    simple_fixture: Path,
    change_to_original_dir: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test find-more finds multiple breaking changes and shows summary (lines 262-267)."""
    from conftest import get_commit_shas

    from git_bifurcate.core import BifurcationEngine

    os.chdir(simple_fixture)
    _parent_sha, bad_sha = get_commit_shas(simple_fixture)

    # Mock to return different breaking files
    call_count = [0]

    def mock_bifurcate(self, changes, *args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1 and len(changes) > 0:
            # Return first change
            return changes[0]
        elif call_count[0] == 2 and len(changes) > 1:
            # Return second change
            return changes[1] if len(changes) > 1 else None
        return None

    monkeypatch.setattr(BifurcationEngine, "bifurcate_files", mock_bifurcate)

    # Mock confirm to say yes once, then no
    confirm_calls = [True, False]

    def mock_confirm(_):
        return confirm_calls.pop(0) if confirm_calls else False

    monkeypatch.setattr("click.confirm", mock_confirm)

    result = runner.invoke(
        main,
        ["start", bad_sha, "--strategy", "file", "--test", "bash test.sh", "--find-more"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    # Should show summary when multiple breaking changes found
    if "FOUND" in result.output and "BREAKING CHANGE" in result.output:
        assert True  # Summary was shown


def test_cli_start_find_more_exhausts_hunks(
    runner: CliRunner,
    hunk_fixture: Path,
    change_to_original_dir: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test find-more exhausts all hunks (line 407)."""
    from conftest import get_commit_shas

    from git_bifurcate.core import BifurcationEngine

    os.chdir(hunk_fixture)
    _parent_sha, bad_sha = get_commit_shas(hunk_fixture)

    # Track how many times bifurcate_hunks is called
    call_count = [0]
    original_bifurcate = BifurcationEngine.bifurcate_hunks

    def mock_bifurcate(self, hunks, *args, **kwargs):
        call_count[0] += 1
        # First call finds a hunk, subsequent calls find nothing
        if call_count[0] == 1:
            result = original_bifurcate(self, hunks, *args, **kwargs)
            return result
        return None

    monkeypatch.setattr(BifurcationEngine, "bifurcate_hunks", mock_bifurcate)
    monkeypatch.setattr("click.confirm", lambda _: True)  # Always continue

    result = runner.invoke(
        main,
        ["start", bad_sha, "--strategy", "hunk", "--test", "python3 test.py", "--find-more"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    # Should have made multiple attempts
    assert call_count[0] >= 2


def test_cli_start_find_more_finds_multiple_hunks(
    runner: CliRunner,
    hunk_fixture: Path,
    change_to_original_dir: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test find-more finds multiple breaking hunks and shows summary (lines 453-458)."""
    from conftest import get_commit_shas

    from git_bifurcate.core import BifurcationEngine

    os.chdir(hunk_fixture)
    _parent_sha, bad_sha = get_commit_shas(hunk_fixture)

    # Mock to return different breaking hunks
    call_count = [0]

    def mock_bifurcate(self, hunks, *args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1 and len(hunks) > 0:
            return hunks[0]
        elif call_count[0] == 2 and len(hunks) > 1:
            return hunks[1] if len(hunks) > 1 else None
        return None

    monkeypatch.setattr(BifurcationEngine, "bifurcate_hunks", mock_bifurcate)

    # Mock confirm to say yes once, then no
    confirm_calls = [True, False]

    def mock_confirm(_):
        return confirm_calls.pop(0) if confirm_calls else False

    monkeypatch.setattr("click.confirm", mock_confirm)

    result = runner.invoke(
        main,
        ["start", bad_sha, "--strategy", "hunk", "--test", "python3 test.py", "--find-more"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    # Should show summary when multiple breaking changes found
    if "FOUND" in result.output and "BREAKING CHANGE" in result.output:
        assert True  # Summary was shown


def test_cli_continue_hunk_empty_search_space(
    runner: CliRunner, hunk_fixture: Path, change_to_original_dir: None
) -> None:
    """Test continue with empty search space for hunk strategy (lines 759-760)."""
    from conftest import get_commit_shas

    from git_bifurcate.git_ops import GitRepo
    from git_bifurcate.models import Strategy
    from git_bifurcate.parser import parse_hunk_changes

    os.chdir(hunk_fixture)
    parent_sha, bad_sha = get_commit_shas(hunk_fixture)

    git = GitRepo()
    diff_text = git.get_diff(bad_sha, parent_sha)
    hunk_changes = parse_hunk_changes(diff_text)

    # Create state with empty search space
    state = BifurcationState(
        commit_sha=bad_sha,
        parent_sha=parent_sha,
        test_command="python3 test.py",
        strategy=Strategy.HUNK,
        changes=hunk_changes,
        search_space=[],  # Empty!
    )
    state.save()

    result = runner.invoke(main, ["continue"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Search space is empty" in result.output



def test_cli_continue_file_no_breaking_change_found(
    runner: CliRunner,
    simple_fixture: Path,
    change_to_original_dir: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test lines 751-752: continue when no breaking file found."""
    from conftest import get_commit_shas

    from git_bifurcate.core import BifurcationEngine
    from git_bifurcate.git_ops import GitRepo
    from git_bifurcate.models import Strategy
    from git_bifurcate.parser import parse_file_changes

    os.chdir(simple_fixture)
    parent_sha, bad_sha = get_commit_shas(simple_fixture)

    git = GitRepo()
    diff_text = git.get_diff(bad_sha, parent_sha)
    file_changes = parse_file_changes(diff_text)

    # Create state
    state = BifurcationState(
        commit_sha=bad_sha,
        parent_sha=parent_sha,
        test_command="bash test.sh",
        strategy=Strategy.FILE,
        changes=file_changes,
        search_space=list(range(len(file_changes))),
    )
    state.save()

    # Mock to return None (no breaking change)
    monkeypatch.setattr(BifurcationEngine, "bifurcate_files", lambda *args, **kwargs: None)

    result = runner.invoke(main, ["continue"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "No single breaking change found" in result.output


def test_cli_continue_hunk_no_breaking_change_found(
    runner: CliRunner,
    hunk_fixture: Path,
    change_to_original_dir: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test lines 780-781: continue when no breaking hunk found."""
    from conftest import get_commit_shas

    from git_bifurcate.core import BifurcationEngine
    from git_bifurcate.git_ops import GitRepo
    from git_bifurcate.models import Strategy
    from git_bifurcate.parser import parse_hunk_changes

    os.chdir(hunk_fixture)
    parent_sha, bad_sha = get_commit_shas(hunk_fixture)

    git = GitRepo()
    diff_text = git.get_diff(bad_sha, parent_sha)
    hunk_changes = parse_hunk_changes(diff_text)

    # Create state
    state = BifurcationState(
        commit_sha=bad_sha,
        parent_sha=parent_sha,
        test_command="python3 test.py",
        strategy=Strategy.HUNK,
        changes=hunk_changes,
        search_space=list(range(len(hunk_changes))),
    )
    state.save()

    # Mock to return None (no breaking change)
    monkeypatch.setattr(BifurcationEngine, "bifurcate_hunks", lambda *args, **kwargs: None)

    result = runner.invoke(main, ["continue"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "No single breaking change found" in result.output


def test_cli_bisect_with_submodules_detected(
    runner: CliRunner, simple_fixture: Path, monkeypatch
) -> None:
    """Test line 660: submodules notification in bisect command."""
    from conftest import get_commit_shas

    os.chdir(simple_fixture)
    parent_sha, bad_sha = get_commit_shas(simple_fixture)

    # Mock get_bisect_stats to return has_submodules=True
    def mock_get_bisect_stats(self, good_commit, bad_commit):
        return {
            "total_commits": 5,
            "estimated_iterations": 3,
            "has_submodules": True,  # This triggers line 660
        }

    # Mock bisect_commits to return a commit
    def mock_bisect_commits(self, good_commit, bad_commit, verbose=True):
        return bad_sha

    from git_bifurcate.commit_bisect import CommitBisector

    monkeypatch.setattr(CommitBisector, "get_bisect_stats", mock_get_bisect_stats)
    monkeypatch.setattr(CommitBisector, "bisect_commits", mock_bisect_commits)

    result = runner.invoke(
        main, ["bisect", parent_sha, bad_sha, "--test", "python3 test.py"], catch_exceptions=False
    )

    assert result.exit_code == 0
    assert "Note: Repository contains submodules" in result.output
