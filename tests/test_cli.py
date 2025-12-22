"""Tests for CLI interface."""

from __future__ import annotations

import os
import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
from click.testing import CliRunner

from git_bifurcate.cli import main
from git_bifurcate.models import BifurcationState, ChangeStatus, FileChange, HunkChange, Strategy
from git_bifurcate.models import CommandResult  # type: ignore  # re-export convenience


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


def test_cli_start_defaults_and_parent_option(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
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


def test_cli_start_all_changes_should_fail(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
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


def test_cli_start_no_breaking_file_found(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
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
    monkeypatch.setattr(BifurcationState, "save", lambda self, filepath=".git/bifurcate-state.json": None)
    monkeypatch.setattr(BifurcationState, "delete", staticmethod(lambda filepath=".git/bifurcate-state.json": None))
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
        diff_content="@@" ,
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


def test_cli_start_hunk_parent_should_pass(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
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
        diff_content="@@" ,
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


def test_cli_start_hunk_no_breaking_change(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
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
        diff_content="@@" ,
        status=ChangeStatus.UNKNOWN,
    )

    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: False))
    monkeypatch.setattr(BifurcationState, "save", lambda self, filepath=".git/bifurcate-state.json": None)
    monkeypatch.setattr(BifurcationState, "delete", staticmethod(lambda filepath=".git/bifurcate-state.json": None))
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
    monkeypatch.setattr(BifurcationState, "load", classmethod(lambda cls: SimpleNamespace(commit_sha="abc123")))
    monkeypatch.setattr(BifurcationState, "delete", staticmethod(lambda filepath=".git/bifurcate-state.json": None))
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
                diff_content="@@" ,
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
    monkeypatch.setattr(BifurcationState, "load", classmethod(lambda cls: (_ for _ in ()).throw(ValueError("bad"))))

    result = runner.invoke(main, ["status"])
    assert result.exit_code == 1
    assert "Error loading state" in result.output


def test_cli_reset_missing_state(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    """Reset handles missing state with and without force."""
    monkeypatch.setattr(BifurcationState, "exists", classmethod(lambda cls: True))
    monkeypatch.setattr(BifurcationState, "load", classmethod(lambda cls: (_ for _ in ()).throw(FileNotFoundError())))

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
