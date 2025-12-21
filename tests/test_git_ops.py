"""Tests for git operations wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from git_bifurcate.git_ops import GitOperationError, GitRepo
from git_bifurcate.models import ChangeStatus, FileChange
from git_bifurcate.parser import parse_file_changes


def create_commit(repo_path: Path, filename: str, content: str, message: str) -> str:
    """Helper to create a commit in test repo."""
    file_path = repo_path / filename
    file_path.write_text(content)

    subprocess.run(["git", "add", filename], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo_path, check=True, capture_output=True)

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_path, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def test_git_repo_init(git_repo: Path) -> None:
    """Test GitRepo initialization."""
    repo = GitRepo(git_repo)

    assert repo.repo_path == git_repo.resolve()
    assert repo.repo is not None


def test_git_repo_init_non_repo(temp_dir: Path) -> None:
    """Test GitRepo initialization with non-git directory."""
    non_repo = temp_dir / "not_a_repo"
    non_repo.mkdir()

    with pytest.raises(GitOperationError, match="Not a git repository"):
        GitRepo(non_repo)


def test_git_repo_init_current_dir(git_repo: Path, change_to_original_dir: None) -> None:
    """Test GitRepo can be initialized from current directory."""
    import os

    os.chdir(git_repo)

    repo = GitRepo()
    assert repo.repo_path == git_repo.resolve()


def test_get_commit(git_repo: Path) -> None:
    """Test getting commit by SHA."""
    # Create a commit
    sha = create_commit(git_repo, "test.txt", "content", "Initial commit")

    repo = GitRepo(git_repo)
    commit = repo.get_commit(sha)

    assert commit.hexsha == sha
    assert commit.message.strip() == "Initial commit"


def test_get_commit_short_sha(git_repo: Path) -> None:
    """Test getting commit by short SHA."""
    sha = create_commit(git_repo, "test.txt", "content", "Test commit")

    repo = GitRepo(git_repo)
    short_sha = sha[:7]
    commit = repo.get_commit(short_sha)

    assert commit.hexsha == sha


def test_get_commit_head(git_repo: Path) -> None:
    """Test getting HEAD commit."""
    sha = create_commit(git_repo, "test.txt", "content", "Test commit")

    repo = GitRepo(git_repo)
    commit = repo.get_commit("HEAD")

    assert commit.hexsha == sha


def test_get_commit_invalid(git_repo: Path) -> None:
    """Test getting invalid commit raises error."""
    create_commit(git_repo, "test.txt", "content", "Test commit")

    repo = GitRepo(git_repo)

    with pytest.raises(GitOperationError, match="Commit not found"):
        repo.get_commit("nonexistent")


def test_get_parent_commit(git_repo: Path) -> None:
    """Test getting parent commit."""
    parent_sha = create_commit(git_repo, "file1.txt", "content1", "Parent commit")
    child_sha = create_commit(git_repo, "file2.txt", "content2", "Child commit")

    repo = GitRepo(git_repo)
    result = repo.get_parent_commit(child_sha)

    assert result == parent_sha


def test_get_parent_commit_initial(git_repo: Path) -> None:
    """Test getting parent of initial commit raises error."""
    sha = create_commit(git_repo, "test.txt", "content", "Initial commit")

    repo = GitRepo(git_repo)

    with pytest.raises(GitOperationError, match="has no parent"):
        repo.get_parent_commit(sha)


def test_get_diff(git_repo: Path) -> None:
    """Test getting diff between commits."""
    parent_sha = create_commit(git_repo, "test.txt", "old content", "Parent")
    child_sha = create_commit(git_repo, "test.txt", "new content", "Child")

    repo = GitRepo(git_repo)
    diff = repo.get_diff(child_sha, parent_sha)

    assert "diff --git" in diff
    assert "test.txt" in diff
    assert "-old content" in diff
    assert "+new content" in diff


def test_get_diff_auto_parent(git_repo: Path) -> None:
    """Test getting diff with automatic parent detection."""
    create_commit(git_repo, "test.txt", "old content", "Parent")
    child_sha = create_commit(git_repo, "test.txt", "new content", "Child")

    repo = GitRepo(git_repo)
    diff = repo.get_diff(child_sha)

    assert "test.txt" in diff
    assert "-old content" in diff
    assert "+new content" in diff


def test_get_diff_multiple_files(git_repo: Path) -> None:
    """Test getting diff with multiple file changes."""
    parent_sha = create_commit(git_repo, "file1.txt", "content1", "Parent")

    # Modify file1 and add file2
    (git_repo / "file1.txt").write_text("modified1")
    (git_repo / "file2.txt").write_text("content2")
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Child"], cwd=git_repo, check=True, capture_output=True)

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, check=True, capture_output=True, text=True
    )
    child_sha = result.stdout.strip()

    repo = GitRepo(git_repo)
    diff = repo.get_diff(child_sha, parent_sha)

    assert "file1.txt" in diff
    assert "file2.txt" in diff
    assert "-content1" in diff
    assert "+modified1" in diff
    assert "+content2" in diff


def test_checkout(git_repo: Path) -> None:
    """Test checking out a commit."""
    sha1 = create_commit(git_repo, "test.txt", "v1", "Commit 1")
    sha2 = create_commit(git_repo, "test.txt", "v2", "Commit 2")

    repo = GitRepo(git_repo)

    # Checkout first commit
    repo.checkout(sha1)

    content = (git_repo / "test.txt").read_text()
    assert content == "v1"

    # Checkout second commit
    repo.checkout(sha2)

    content = (git_repo / "test.txt").read_text()
    assert content == "v2"


def test_create_temp_branch(git_repo: Path) -> None:
    """Test creating temporary branch."""
    sha = create_commit(git_repo, "test.txt", "content", "Commit")

    repo = GitRepo(git_repo)
    repo.create_temp_branch("temp-branch", sha)

    # Verify branch exists and points to correct commit
    result = subprocess.run(
        ["git", "rev-parse", "temp-branch"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == sha

    # Verify we're on the branch
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "temp-branch"


def test_delete_branch(git_repo: Path) -> None:
    """Test deleting a branch."""
    sha = create_commit(git_repo, "test.txt", "content", "Commit")

    repo = GitRepo(git_repo)
    repo.create_temp_branch("temp-branch", sha)

    # Switch away from branch before deleting
    repo.checkout(sha)

    # Delete branch
    repo.delete_branch("temp-branch")

    # Verify branch is gone
    result = subprocess.run(
        ["git", "branch", "--list", "temp-branch"],
        cwd=git_repo,
        capture_output=True,
        text=True,
    )
    assert "temp-branch" not in result.stdout


def test_apply_patch(git_repo: Path) -> None:
    """Test applying a patch."""
    create_commit(git_repo, "test.txt", "line1\nline2\n", "Initial")

    patch = """diff --git a/test.txt b/test.txt
index 0000000..1111111 100644
--- a/test.txt
+++ b/test.txt
@@ -1,2 +1,3 @@
 line1
 line2
+line3
"""

    repo = GitRepo(git_repo)
    success = repo.apply_patch(patch)

    assert success
    content = (git_repo / "test.txt").read_text()
    assert content == "line1\nline2\nline3\n"


def test_apply_patch_invalid(git_repo: Path) -> None:
    """Test applying invalid patch returns False."""
    create_commit(git_repo, "test.txt", "content", "Initial")

    invalid_patch = """diff --git a/nonexistent.txt b/nonexistent.txt
index 0000000..1111111 100644
--- a/nonexistent.txt
+++ b/nonexistent.txt
@@ -1,1 +1,2 @@
 old line
+new line
"""

    repo = GitRepo(git_repo)
    success = repo.apply_patch(invalid_patch)

    assert not success


def test_reset_hard(git_repo: Path) -> None:
    """Test hard reset to a commit."""
    sha1 = create_commit(git_repo, "test.txt", "v1", "Commit 1")
    _sha2 = create_commit(git_repo, "test.txt", "v2", "Commit 2")

    # Make uncommitted changes
    (git_repo / "test.txt").write_text("v3")

    repo = GitRepo(git_repo)
    repo.reset_hard(sha1)

    # Verify reset to sha1
    content = (git_repo / "test.txt").read_text()
    assert content == "v1"

    # Note: git reset --hard doesn't delete untracked files, only resets tracked ones


def test_commit(git_repo: Path) -> None:
    """Test creating a commit."""
    create_commit(git_repo, "test.txt", "v1", "Initial")

    # Make changes
    (git_repo / "test.txt").write_text("v2")
    subprocess.run(["git", "add", "test.txt"], cwd=git_repo, check=True, capture_output=True)

    repo = GitRepo(git_repo)
    repo.commit("Test commit message")

    # Verify commit was created
    result = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "Test commit message"


def test_apply_changes(git_repo: Path) -> None:
    """Test applying FileChanges."""
    parent_sha = create_commit(git_repo, "file1.txt", "content1\n", "Parent")

    # Create child commit with a simple modification
    (git_repo / "file1.txt").write_text("modified1\n")
    subprocess.run(["git", "add", "file1.txt"], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Child"], cwd=git_repo, check=True, capture_output=True)

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, check=True, capture_output=True, text=True
    )
    child_sha = result.stdout.strip()

    # Get diff and parse
    repo = GitRepo(git_repo)
    diff = repo.get_diff(child_sha, parent_sha)

    # Create FileChanges from diff
    from git_bifurcate.parser import parse_file_changes

    changes = parse_file_changes(diff)
    assert len(changes) == 1

    # Apply the change
    success = repo.apply_changes(changes, parent_sha)

    assert success

    # Verify change was applied
    content = (git_repo / "file1.txt").read_text()
    assert content == "modified1\n"


def test_apply_changes_multiple(git_repo: Path) -> None:
    """Test applying multiple FileChanges."""
    parent_sha = create_commit(git_repo, "file1.txt", "content1\n", "Parent")

    # Create changes
    (git_repo / "file1.txt").write_text("modified1\n")
    (git_repo / "file2.txt").write_text("content2\n")
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Child"], cwd=git_repo, check=True, capture_output=True)

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, check=True, capture_output=True, text=True
    )
    child_sha = result.stdout.strip()

    # Get diff and parse
    repo = GitRepo(git_repo)
    diff = repo.get_diff(child_sha, parent_sha)

    from git_bifurcate.parser import parse_file_changes

    changes = parse_file_changes(diff)

    # Apply all changes
    success = repo.apply_changes(changes, parent_sha)

    assert success

    # Verify all changes applied
    content1 = (git_repo / "file1.txt").read_text()
    assert content1 == "modified1\n"

    content2 = (git_repo / "file2.txt").read_text()
    assert content2 == "content2\n"


def test_apply_changes_invalid_patch(git_repo: Path) -> None:
    """Test apply_changes with invalid patch content."""
    repo = GitRepo(git_repo)
    parent_sha = create_commit(git_repo, "file.txt", "original\n", "Initial")

    # Create invalid FileChange with malformed diff
    invalid_change = FileChange(
        id="0",
        file_path="file.txt",
        change_type="modified",
        diff_content="invalid patch content",
        status=ChangeStatus.UNKNOWN,
    )

    # Should fail gracefully
    success = repo.apply_changes([invalid_change], parent_sha, use_temp_branch=False)
    assert not success

    # Get branch count before
    result = subprocess.run(
        ["git", "branch"], cwd=git_repo, capture_output=True, text=True, check=True
    )
    initial_branches = len([b for b in result.stdout.split("\n") if b.strip()])

    # Create invalid change
    invalid_change = FileChange(
        id="0",
        file_path="file.txt",
        change_type="modified",
        diff_content="invalid patch",
        status=ChangeStatus.UNKNOWN,
    )

    # Apply with temp branch should fail and clean up
    success = repo.apply_changes([invalid_change], parent_sha, use_temp_branch=True)
    assert not success

    # Check branch count after - should be same (cleanup worked)
    result = subprocess.run(
        ["git", "branch"], cwd=git_repo, capture_output=True, text=True, check=True
    )
    final_branches = len([b for b in result.stdout.split("\n") if b.strip()])
    assert final_branches == initial_branches


def test_apply_hunk_changes_basic(git_repo: Path) -> None:
    """Test applying hunk changes."""
    from git_bifurcate.parser import parse_hunk_changes

    repo = GitRepo(git_repo)

    # Create file with multiple functions
    content = """def func1():
    return 1


def func2():
    return 2


def func3():
    return 3
"""
    parent_sha = create_commit(git_repo, "code.py", content, "Initial")

    # Modify all functions
    modified = """def func1():
    # Modified
    return 10


def func2():
    # Modified
    return 20


def func3():
    # Modified
    return 30
"""
    bad_sha = create_commit(git_repo, "code.py", modified, "Modify all")

    # Parse hunks
    diff = repo.get_diff(bad_sha, parent_sha)
    hunks = parse_hunk_changes(diff)

    assert len(hunks) >= 1

    # Apply all hunks
    success = repo.apply_hunk_changes(hunks, parent_sha, bad_sha, use_temp_branch=False)
    assert success


def test_apply_hunk_changes_empty_list(git_repo: Path) -> None:
    """Test applying empty hunk list."""
    repo = GitRepo(git_repo)
    parent_sha = create_commit(git_repo, "file.txt", "content\n", "Initial")

    # Empty list should succeed (no-op)
    success = repo.apply_hunk_changes([], parent_sha, parent_sha, use_temp_branch=False)
    assert success


def test_apply_hunk_changes_missing_file_header(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test apply_hunk_changes when file header extraction fails."""
    from git_bifurcate.models import HunkChange

    repo = GitRepo(git_repo)
    parent_sha = create_commit(git_repo, "file.txt", "content\n", "Initial")

    # Create a hunk change
    hunk = HunkChange(
        id="0",
        file_path="file.txt",
        start_line=1,
        end_line=2,
        original_start=1,
        original_length=1,
        new_start=1,
        new_length=2,
        diff_content="@@ -1 +1,2 @@\n content\n+more",
        status=ChangeStatus.UNKNOWN,
    )

    # Mock _extract_file_header to return None (simulating failure)
    def mock_extract(self, full_diff: str, file_path: str) -> str | None:
        return None

    monkeypatch.setattr(GitRepo, "_extract_file_header", mock_extract)

    # Should fail gracefully
    success = repo.apply_hunk_changes([hunk], parent_sha, parent_sha, use_temp_branch=False)
    assert not success


def test_extract_file_header_found(git_repo: Path) -> None:
    """Test _extract_file_header successfully finds header."""
    repo = GitRepo(git_repo)

    parent_sha = create_commit(git_repo, "test.txt", "original\n", "Initial")
    bad_sha = create_commit(git_repo, "test.txt", "modified\n", "Modified")

    diff = repo.get_diff(bad_sha, parent_sha)
    header = repo._extract_file_header(diff, "test.txt")

    assert header is not None
    assert "diff --git" in header
    assert "test.txt" in header


def test_extract_file_header_not_found(git_repo: Path) -> None:
    """Test _extract_file_header when file not in diff."""
    repo = GitRepo(git_repo)

    parent_sha = create_commit(git_repo, "test.txt", "original\n", "Initial")
    bad_sha = create_commit(git_repo, "test.txt", "modified\n", "Modified")

    diff = repo.get_diff(bad_sha, parent_sha)
    header = repo._extract_file_header(diff, "nonexistent.txt")

    assert header is None


def test_apply_changes_submodule(git_repo: Path, temp_dir: Path) -> None:
    """Test applying submodule gitlink updates."""
    sub_repo = temp_dir / "sub_repo"
    sub_repo.mkdir()

    subprocess.run(["git", "init"], cwd=sub_repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=sub_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=sub_repo, check=True)

    # Initial commit
    (sub_repo / "dep.txt").write_text("v1\n")
    subprocess.run(["git", "add", "dep.txt"], cwd=sub_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial dep"], cwd=sub_repo, check=True)
    initial_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=sub_repo, check=True, capture_output=True, text=True
    ).stdout.strip()

    # Add submodule at initial commit (allow local file transport explicitly)
    subprocess.run(
        [
            "git",
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            str(sub_repo),
            "vendor/lib",
        ],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "commit", "-am", "Add submodule"], cwd=git_repo, check=True)
    parent_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, check=True, capture_output=True, text=True
    ).stdout.strip()

    # Create new commit in the submodule clone
    submodule_clone = git_repo / "vendor/lib"
    subprocess.run(
        ["git", "-C", str(submodule_clone), "config", "user.name", "Test User"], check=True
    )
    subprocess.run(
        ["git", "-C", str(submodule_clone), "config", "user.email", "test@example.com"], check=True
    )

    (submodule_clone / "dep.txt").write_text("v2\n")
    subprocess.run(
        ["git", "-C", str(submodule_clone), "add", "dep.txt"], check=True, capture_output=True
    )
    subprocess.run(["git", "-C", str(submodule_clone), "commit", "-m", "Update dep"], check=True)
    new_sha = subprocess.run(
        ["git", "-C", str(submodule_clone), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert new_sha != initial_sha

    subprocess.run(["git", "add", "vendor/lib"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "Update submodule"], cwd=git_repo, check=True)
    bad_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, check=True, capture_output=True, text=True
    ).stdout.strip()

    repo = GitRepo(git_repo)
    diff = repo.get_diff(bad_sha, parent_sha)
    changes = parse_file_changes(diff)

    assert len(changes) == 1
    assert changes[0].change_type == "submodule"

    repo.reset_hard(parent_sha)

    success = repo.apply_changes(changes, parent_sha, use_temp_branch=False)

    assert success
    current_sha = subprocess.run(
        ["git", "-C", str(submodule_clone), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert current_sha == new_sha
