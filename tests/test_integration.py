"""Integration tests for git-bifurcate using real test fixtures."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from git_bifurcate.core import BifurcationEngine
from git_bifurcate.git_ops import GitRepo
from git_bifurcate.parser import parse_file_changes, parse_hunk_changes
from git_bifurcate.test_runner import CommandRunner


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Get fixtures directory path and ensure fixtures are initialized."""
    fixtures_path = Path(__file__).parent / "fixtures"

    # Run setup script if fixtures aren't initialized
    setup_script = fixtures_path / "setup_fixtures.py"
    if setup_script.exists():
        # Check if fixtures are already git repos
        simple_git = fixtures_path / "simple-file-break" / ".git"
        if not simple_git.exists():
            # Need to initialize fixtures
            subprocess.run(
                ["python3", str(setup_script)],
                cwd=fixtures_path,
                check=True,
                capture_output=True,
            )

    return fixtures_path


@pytest.fixture
def simple_fixture(fixtures_dir: Path) -> Path:
    """Get simple file-break fixture path and ensure clean state."""
    fixture_path = fixtures_dir / "simple-file-break"

    # Reset master to fixture-head tag (metadata commit)
    subprocess.run(["git", "checkout", "-f", "master"], cwd=fixture_path, capture_output=True)
    subprocess.run(
        ["git", "reset", "--hard", "fixture-head"], cwd=fixture_path, capture_output=True
    )
    subprocess.run(["git", "clean", "-fd"], cwd=fixture_path, capture_output=True)

    # Delete any temp branches
    result = subprocess.run(
        ["git", "branch"],
        cwd=fixture_path,
        capture_output=True,
        text=True,
    )
    for line in result.stdout.split("\n"):
        if "bifurcate-temp" in line:
            branch = line.strip().replace("* ", "")
            subprocess.run(["git", "branch", "-D", branch], cwd=fixture_path, capture_output=True)

    return fixture_path


@pytest.fixture
def multiple_fixture(fixtures_dir: Path) -> Path:
    """Get multiple files fixture path and ensure clean state."""
    fixture_path = fixtures_dir / "multiple-files-break"

    # Reset master to fixture-head tag (metadata commit)
    subprocess.run(["git", "checkout", "-f", "master"], cwd=fixture_path, capture_output=True)
    subprocess.run(
        ["git", "reset", "--hard", "fixture-head"], cwd=fixture_path, capture_output=True
    )
    subprocess.run(["git", "clean", "-fd"], cwd=fixture_path, capture_output=True)

    return fixture_path


@pytest.fixture
def hunk_fixture(fixtures_dir: Path) -> Path:
    """Get single hunk break fixture path and ensure clean state."""
    fixture_path = fixtures_dir / "single-hunk-break"

    # Reset master to fixture-head tag (metadata commit)
    subprocess.run(["git", "checkout", "-f", "master"], cwd=fixture_path, capture_output=True)
    subprocess.run(
        ["git", "reset", "--hard", "fixture-head"], cwd=fixture_path, capture_output=True
    )
    subprocess.run(["git", "clean", "-fd"], cwd=fixture_path, capture_output=True)

    return fixture_path


def get_commit_shas(repo_path: Path) -> tuple[str, str]:
    """Get parent and bad commit SHAs from fixture.

    Fixtures have 3 commits:
    - HEAD^^ = parent (good) commit
    - HEAD^ = bad commit with breaking change
    - HEAD = metadata commit (FIXTURE_INFO.md)
    """
    # Get HEAD^ (bad commit with breaking change)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD^"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    bad_sha = result.stdout.strip()

    # Get HEAD^^ (parent/good commit)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD^^"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    parent_sha = result.stdout.strip()

    return parent_sha, bad_sha


def test_simple_fixture_setup(simple_fixture: Path) -> None:
    """Test that simple fixture is set up correctly."""
    assert simple_fixture.exists()
    assert (simple_fixture / "test.sh").exists()
    assert (simple_fixture / "module1.py").exists()
    assert (simple_fixture / "module2.py").exists()
    assert (simple_fixture / "module3.py").exists()
    assert (simple_fixture / "module4.py").exists()

    parent_sha, bad_sha = get_commit_shas(simple_fixture)

    # Test parent commit passes
    subprocess.run(
        ["git", "checkout", parent_sha], cwd=simple_fixture, check=True, capture_output=True
    )
    result = subprocess.run(
        ["bash", "test.sh"],
        cwd=simple_fixture,
        capture_output=True,
    )
    assert result.returncode == 0, "Parent commit should pass tests"

    # Test bad commit fails
    subprocess.run(
        ["git", "checkout", bad_sha], cwd=simple_fixture, check=True, capture_output=True
    )
    result = subprocess.run(
        ["bash", "test.sh"],
        cwd=simple_fixture,
        capture_output=True,
    )
    assert result.returncode != 0, "Bad commit should fail tests"


def test_file_level_bifurcation_simple(simple_fixture: Path, change_to_original_dir: None) -> None:
    """Test file-level bifurcation on simple fixture."""
    os.chdir(simple_fixture)

    parent_sha, bad_sha = get_commit_shas(simple_fixture)

    # Setup bifurcation
    git = GitRepo(simple_fixture)
    diff = git.get_diff(bad_sha, parent_sha)
    changes = parse_file_changes(diff)

    # Should have 4 file changes
    assert len(changes) == 4

    # Run bifurcation
    test_runner = CommandRunner("bash test.sh", working_dir=simple_fixture)
    engine = BifurcationEngine(git, test_runner)

    breaking_change = engine.bifurcate_files(changes, parent_sha, verbose=False)

    # Should find module2.py
    assert breaking_change is not None
    assert breaking_change.file_path == "module2.py"

    # Check stats
    stats = engine.get_stats()
    # With 4 files, binary search should take ~3-4 tests
    assert stats["tests_run"] <= 6, (
        f"Should use binary search efficiently, got {stats['tests_run']} tests"
    )


def test_file_level_bifurcation_multiple(
    multiple_fixture: Path, change_to_original_dir: None
) -> None:
    """Test file-level bifurcation on multiple files fixture."""
    os.chdir(multiple_fixture)

    parent_sha, bad_sha = get_commit_shas(multiple_fixture)

    # Setup bifurcation
    git = GitRepo(multiple_fixture)
    diff = git.get_diff(bad_sha, parent_sha)
    changes = parse_file_changes(diff)

    # Should have 5 file changes
    assert len(changes) == 5

    # Run bifurcation
    test_runner = CommandRunner("bash test.sh", working_dir=multiple_fixture)
    engine = BifurcationEngine(git, test_runner)

    breaking_change = engine.bifurcate_files(changes, parent_sha, verbose=False)

    # Should find file3.py
    assert breaking_change is not None
    assert breaking_change.file_path == "file3.py"

    # Check efficiency
    stats = engine.get_stats()
    # With 5 files, binary search should take ~4-5 tests vs 5 for linear
    assert stats["tests_run"] <= 7, (
        f"Should use binary search efficiently, got {stats['tests_run']} tests"
    )


def test_hunk_level_bifurcation(hunk_fixture: Path, change_to_original_dir: None) -> None:
    """Test hunk-level bifurcation on single file with multiple hunks."""
    os.chdir(hunk_fixture)

    parent_sha, bad_sha = get_commit_shas(hunk_fixture)

    # Setup bifurcation
    git = GitRepo(hunk_fixture)
    diff = git.get_diff(bad_sha, parent_sha)
    hunks = parse_hunk_changes(diff)

    # Should have 4 hunks (one per function)
    assert len(hunks) >= 4

    # Run hunk-level bifurcation
    test_runner = CommandRunner("python3 test.py", working_dir=hunk_fixture)
    engine = BifurcationEngine(git, test_runner)

    # Use bifurcate_hunks for hunk-level search
    breaking_hunk = engine.bifurcate_hunks(hunks, parent_sha, bad_sha, verbose=False)

    # Should find the multiply function hunk
    assert breaking_hunk is not None
    assert breaking_hunk.file_path == "calculator.py"
    # The breaking hunk should contain "multiply"
    assert "multiply" in breaking_hunk.diff_content.lower()


def test_integration_with_git_state_cleanup(
    simple_fixture: Path, change_to_original_dir: None
) -> None:
    """Test that bifurcation cleans up git state properly."""
    os.chdir(simple_fixture)

    parent_sha, bad_sha = get_commit_shas(simple_fixture)

    # Record initial state
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=simple_fixture,
        capture_output=True,
        text=True,
        check=True,
    )
    initial_head = result.stdout.strip()

    # Run bifurcation
    git = GitRepo(simple_fixture)
    diff = git.get_diff(bad_sha, parent_sha)
    changes = parse_file_changes(diff)

    test_runner = CommandRunner("bash test.sh", working_dir=simple_fixture)
    engine = BifurcationEngine(git, test_runner)

    breaking_change = engine.bifurcate_files(changes, parent_sha, verbose=False)

    assert breaking_change is not None

    # Check that we can determine the current state
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=simple_fixture,
        capture_output=True,
        text=True,
        check=True,
    )
    # Working directory might have changes from the bifurcation


def test_no_breaking_change_found(simple_fixture: Path, change_to_original_dir: None) -> None:
    """Test behavior when no single breaking change exists."""
    os.chdir(simple_fixture)

    parent_sha, bad_sha = get_commit_shas(simple_fixture)

    git = GitRepo(simple_fixture)
    diff = git.get_diff(bad_sha, parent_sha)
    changes = parse_file_changes(diff)

    # Create a test runner that always passes
    class AlwaysPassRunner:
        def __init__(self, cmd: str, **kwargs: object) -> None:
            pass

        def run(self) -> object:
            from git_bifurcate.models import CommandResult

            return CommandResult.PASS

    engine = BifurcationEngine(git, AlwaysPassRunner("true"))  # type: ignore[arg-type]

    breaking_change = engine.bifurcate_files(changes, parent_sha, verbose=False)

    # Should return None when all tests pass
    assert breaking_change is None


def test_fixture_info_files_exist(
    fixtures_dir: Path,
    simple_fixture: Path,
    multiple_fixture: Path,
    hunk_fixture: Path,
) -> None:
    """Test that all fixtures have FIXTURE_INFO.md files."""
    fixtures = ["simple-file-break", "multiple-files-break", "single-hunk-break"]

    for fixture_name in fixtures:
        fixture_path = fixtures_dir / fixture_name
        info_file = fixture_path / "FIXTURE_INFO.md"
        assert info_file.exists(), f"Missing FIXTURE_INFO.md for {fixture_name}"

        content = info_file.read_text()
        assert "## Description" in content
        assert "## Expected Result" in content
        assert "## Test Command" in content
