"""Tests for git operations wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import git
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


def test_get_parent_commit_merge_commit(git_repo: Path) -> None:
    """Ensure merge commits raise an error when asking for a single parent."""
    base = create_commit(git_repo, "base.txt", "base", "base")

    subprocess.run(
        ["git", "checkout", "-b", "feature"], cwd=git_repo, check=True, capture_output=True
    )
    create_commit(git_repo, "feature.txt", "feature", "feature change")

    subprocess.run(["git", "checkout", "master"], cwd=git_repo, check=True, capture_output=True)
    _master_change = create_commit(git_repo, "master.txt", "master", "master change")

    subprocess.run(
        ["git", "merge", "--no-ff", "feature", "-m", "Merge feature"],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )
    merge_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_repo, check=True, capture_output=True, text=True
    ).stdout.strip()

    repo = GitRepo(git_repo)
    with pytest.raises(GitOperationError, match="merge commit"):
        repo.get_parent_commit(merge_sha)
    assert base  # silence unused variable lints


def test_get_diff_failure(monkeypatch: pytest.MonkeyPatch, git_repo: Path) -> None:
    """get_diff surfaces subprocess failures as GitOperationError."""
    repo = GitRepo(git_repo)

    def bad_run(*args, **kwargs):
        raise subprocess.CalledProcessError(returncode=1, cmd=args[0], stderr="boom")

    monkeypatch.setattr(subprocess, "run", bad_run)

    with pytest.raises(GitOperationError, match="Failed to get diff"):
        repo.get_diff("child", "parent")


def test_checkout_best_effort_submodules(monkeypatch: pytest.MonkeyPatch, git_repo: Path) -> None:
    """Checkout should ignore submodule update failures but still succeed."""
    first_sha = create_commit(git_repo, "file.txt", "one", "first")
    second_sha = create_commit(git_repo, "file.txt", "two", "second")

    repo = GitRepo(git_repo)
    (git_repo / ".gitmodules").write_text('[submodule "lib"]\n\tpath = lib\n\turl = url\n')

    def fake_submodule(*args, **kwargs):
        raise git.GitCommandError("submodule", 1, "failure")

    monkeypatch.setattr(type(repo.repo.git), "submodule", fake_submodule, raising=False)

    repo.checkout(first_sha)
    assert (git_repo / "file.txt").read_text() == "one"

    repo.checkout(second_sha)
    assert (git_repo / "file.txt").read_text() == "two"


def test_checkout_failure(monkeypatch: pytest.MonkeyPatch, git_repo: Path) -> None:
    """Checkout errors are wrapped in GitOperationError."""
    create_commit(git_repo, "file.txt", "content", "msg")
    repo = GitRepo(git_repo)

    def bad_checkout(*args, **kwargs):
        raise git.GitCommandError("checkout", 1, "fail")

    monkeypatch.setattr(type(repo.repo.git), "checkout", bad_checkout, raising=False)

    with pytest.raises(GitOperationError):
        repo.checkout("HEAD")


def test_create_temp_branch_failure(monkeypatch: pytest.MonkeyPatch, git_repo: Path) -> None:
    """Branch creation errors propagate as GitOperationError."""
    head_sha = create_commit(git_repo, "file.txt", "data", "message")
    repo = GitRepo(git_repo)

    def bad_create_head(*args, **kwargs):
        raise git.GitCommandError("create", 1, "nope")

    monkeypatch.setattr(repo.repo, "create_head", bad_create_head)

    with pytest.raises(GitOperationError):
        repo.create_temp_branch("temp", head_sha)


def test_delete_branch_failure(monkeypatch: pytest.MonkeyPatch, git_repo: Path) -> None:
    """Branch deletion errors propagate as GitOperationError."""
    sha = create_commit(git_repo, "file.txt", "data", "message")
    repo = GitRepo(git_repo)
    repo.create_temp_branch("todelete", sha)
    repo.checkout(sha)

    def bad_delete_head(*args, **kwargs):
        raise git.GitCommandError("delete", 1, "oops")

    monkeypatch.setattr(repo.repo, "delete_head", bad_delete_head)

    with pytest.raises(GitOperationError):
        repo.delete_branch("todelete")


def test_apply_patch_exception(monkeypatch: pytest.MonkeyPatch, git_repo: Path) -> None:
    """Unexpected subprocess errors return False."""
    repo = GitRepo(git_repo)

    def explode(*args, **kwargs):
        raise ValueError("kaboom")

    monkeypatch.setattr(subprocess, "run", explode)
    assert not repo.apply_patch("diff --git a/file b/file")


def test_apply_changes_failed_patch_cleanup_error(
    monkeypatch: pytest.MonkeyPatch, git_repo: Path
) -> None:
    """Failed patch applications handle cleanup errors gracefully."""
    base = create_commit(git_repo, "file.txt", "v1\n", "msg")
    repo = GitRepo(git_repo)

    change = FileChange("1", "file.txt", "modified", "diff", status=ChangeStatus.UNKNOWN)
    monkeypatch.setattr(repo, "apply_patch", lambda patch: False)
    monkeypatch.setattr(repo, "create_temp_branch", lambda name, base_commit: None)

    def bad_checkout(*args, **kwargs):
        raise git.GitCommandError("checkout", 1, "fail")

    monkeypatch.setattr(type(repo.repo.git), "checkout", bad_checkout, raising=False)

    assert not repo.apply_changes([change], base, use_temp_branch=True)


def test_reset_hard_failure(monkeypatch: pytest.MonkeyPatch, git_repo: Path) -> None:
    """Hard reset failures raise GitOperationError."""
    create_commit(git_repo, "file.txt", "data", "message")
    repo = GitRepo(git_repo)

    def bad_reset(*args, **kwargs):
        raise git.GitCommandError("reset", 1, "fail")

    fake_repo = SimpleNamespace(head=SimpleNamespace(reset=bad_reset))
    monkeypatch.setattr(repo, "repo", fake_repo)

    with pytest.raises(GitOperationError):
        repo.reset_hard("HEAD")


def test_commit_failure(monkeypatch: pytest.MonkeyPatch, git_repo: Path) -> None:
    """Index commit failures raise GitOperationError."""
    create_commit(git_repo, "file.txt", "data", "message")
    (git_repo / "file.txt").write_text("changed")
    subprocess.run(["git", "add", "file.txt"], cwd=git_repo, check=True, capture_output=True)

    repo = GitRepo(git_repo)

    def bad_commit(*args, **kwargs):
        raise git.GitCommandError("commit", 1, "nope")

    monkeypatch.setattr(repo, "repo", SimpleNamespace(index=SimpleNamespace(commit=bad_commit)))

    with pytest.raises(GitOperationError):
        repo.commit("msg")


def test_apply_changes_detached_head(monkeypatch: pytest.MonkeyPatch, git_repo: Path) -> None:
    """apply_changes records detached HEAD hexsha when ref.name fails."""
    base = create_commit(git_repo, "file.txt", "data", "message")
    repo = GitRepo(git_repo)

    class FakeHead:
        def __init__(self, hexsha: str) -> None:
            self.commit = SimpleNamespace(hexsha=hexsha)

        @property
        def ref(self) -> str:  # pragma: no cover - property intentionally raises
            raise TypeError("detached")

    monkeypatch.setattr(repo, "repo", SimpleNamespace(head=FakeHead(base)))
    monkeypatch.setattr(repo, "create_temp_branch", lambda name, base_commit: None)

    success = repo.apply_changes([], base, use_temp_branch=True)
    assert success


def test_apply_changes_temp_branch_failure(monkeypatch: pytest.MonkeyPatch, git_repo: Path) -> None:
    """apply_changes returns False when temp branch cannot be created."""
    base = create_commit(git_repo, "file.txt", "data", "message")
    repo = GitRepo(git_repo)

    def bad_create(*args, **kwargs):
        raise GitOperationError("no branch")

    monkeypatch.setattr(repo, "create_temp_branch", bad_create)

    assert not repo.apply_changes([], base, use_temp_branch=True)


def test_apply_changes_reset_failure_without_temp(
    monkeypatch: pytest.MonkeyPatch, git_repo: Path
) -> None:
    """Reset failures when not using temp branches return False."""
    base = create_commit(git_repo, "file.txt", "data", "message")
    repo = GitRepo(git_repo)

    def bad_reset(*args, **kwargs):
        raise GitOperationError("nope")

    monkeypatch.setattr(repo, "reset_hard", bad_reset)
    assert not repo.apply_changes([], base, use_temp_branch=False)


def test_apply_changes_submodule_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch, git_repo: Path
) -> None:
    """Submodule failures while using temp branches attempt cleanup."""
    base = create_commit(git_repo, "file.txt", "data", "message")
    repo = GitRepo(git_repo)

    change = FileChange(
        id="1",
        file_path="submodule/path",
        change_type="submodule",
        diff_content="+Subproject commit deadbeef",
        status=ChangeStatus.UNKNOWN,
    )

    monkeypatch.setattr(repo, "_apply_submodule_changes", lambda changes: False)
    monkeypatch.setattr(
        type(repo.repo.git), "checkout", lambda *args, **kwargs: None, raising=False
    )
    monkeypatch.setattr(repo, "create_temp_branch", lambda name, base_commit: None)
    deleted = {"called": False}
    monkeypatch.setattr(repo, "delete_branch", lambda name: deleted.__setitem__("called", True))

    assert not repo.apply_changes([change], base, use_temp_branch=True)
    assert deleted["called"]


def test_apply_changes_submodule_cleanup_checkout_error(
    monkeypatch: pytest.MonkeyPatch, git_repo: Path
) -> None:
    """Cleanup ignores checkout errors when submodule application fails."""
    base = create_commit(git_repo, "file.txt", "data", "message")
    repo = GitRepo(git_repo)

    change = FileChange(
        id="1",
        file_path="submodule/path",
        change_type="submodule",
        diff_content="+Subproject commit deadbeef",
        status=ChangeStatus.UNKNOWN,
    )

    monkeypatch.setattr(repo, "_apply_submodule_changes", lambda changes: False)

    def bad_checkout(*args, **kwargs):
        raise git.GitCommandError("checkout", 1, "fail")

    monkeypatch.setattr(type(repo.repo.git), "checkout", bad_checkout, raising=False)
    monkeypatch.setattr(repo, "create_temp_branch", lambda name, base_commit: None)

    assert not repo.apply_changes([change], base, use_temp_branch=True)


def test_apply_submodule_changes_missing_commit(git_repo: Path) -> None:
    """Missing gitlink commit returns False and stops processing."""
    repo = GitRepo(git_repo)
    change = FileChange(
        id="1",
        file_path="sub",
        change_type="submodule",
        diff_content="diff --git a/sub b/sub",
        status=ChangeStatus.UNKNOWN,
    )

    assert not repo._apply_submodule_changes([change])
    assert repo._extract_submodule_commit(change.diff_content) is None


def test_apply_submodule_changes_init_failure(
    monkeypatch: pytest.MonkeyPatch, git_repo: Path
) -> None:
    """Failing submodule init short-circuits processing."""
    repo = GitRepo(git_repo)
    change = FileChange(
        id="1",
        file_path="sub",
        change_type="submodule",
        diff_content="+Subproject commit cafe",
        status=ChangeStatus.UNKNOWN,
    )

    class Dummy:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode
            self.stdout = ""
            self.stderr = ""

    def fake_run(*args, **kwargs):
        return Dummy(1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert not repo._apply_submodule_changes([change])


def test_apply_submodule_changes_checkout_and_add_failures(
    monkeypatch: pytest.MonkeyPatch, git_repo: Path
) -> None:
    """Submodule checkout or add failures are reported."""
    repo = GitRepo(git_repo)
    change = FileChange(
        id="1",
        file_path="sub",
        change_type="submodule",
        diff_content="+Subproject commit cafe",
        status=ChangeStatus.UNKNOWN,
    )

    class Dummy:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode
            self.stdout = ""
            self.stderr = ""

    def fail_on_checkout(*args, **kwargs):
        cmd = args[0]
        checkout_prefix = ["git", "-C", str(repo.repo_path / "sub"), "checkout"]
        if cmd[:2] == ["git", "submodule"]:
            return Dummy(0)
        if cmd[:4] == checkout_prefix:
            return Dummy(1)
        if cmd[:2] == ["git", "add"]:
            return Dummy(0)
        return Dummy(0)

    monkeypatch.setattr(subprocess, "run", fail_on_checkout)
    assert not repo._apply_submodule_changes([change])

    call_state = {"step": 0}

    def fail_on_add(*args, **kwargs):
        call_state["step"] += 1
        if call_state["step"] == 1:
            return Dummy(0)
        if call_state["step"] == 2:
            return Dummy(0)
        if call_state["step"] == 3:
            return Dummy(0)
        return Dummy(1)

    monkeypatch.setattr(subprocess, "run", fail_on_add)
    assert not repo._apply_submodule_changes([change])


def test_apply_hunk_changes_reset_failure(monkeypatch: pytest.MonkeyPatch, git_repo: Path) -> None:
    """Reset failures with empty hunks return False."""
    repo = GitRepo(git_repo)
    create_commit(git_repo, "file.txt", "content\n", "msg")

    def bad_reset(*args, **kwargs):
        raise GitOperationError("cannot reset")

    monkeypatch.setattr(repo, "reset_hard", bad_reset)
    assert not repo.apply_hunk_changes([], "HEAD", "HEAD", use_temp_branch=False)


def test_apply_hunk_changes_temp_branch_missing_header(
    monkeypatch: pytest.MonkeyPatch, git_repo: Path
) -> None:
    """Missing file headers trigger cleanup when using temp branches."""
    repo = GitRepo(git_repo)
    base = create_commit(git_repo, "file.txt", "one\n", "msg")
    from git_bifurcate.models import HunkChange

    sample_hunk = HunkChange(
        id="1",
        file_path="file.txt",
        start_line=1,
        end_line=1,
        original_start=1,
        original_length=1,
        new_start=1,
        new_length=1,
        diff_content="@@ -1 +1 @@\n-one\n+two\n",
        status=ChangeStatus.UNKNOWN,
    )

    monkeypatch.setattr(repo, "get_diff", lambda bad, base_commit: "diff --git a/x b/x")
    monkeypatch.setattr(repo, "_extract_file_header", lambda full, path: None)

    def bad_checkout(*args, **kwargs):
        raise git.GitCommandError("checkout", 1, "fail")

    monkeypatch.setattr(type(repo.repo.git), "checkout", bad_checkout, raising=False)
    monkeypatch.setattr(repo, "create_temp_branch", lambda name, commit: None)

    assert not repo.apply_hunk_changes([sample_hunk], base, base, use_temp_branch=True)


def test_apply_hunk_changes_detached_head(monkeypatch: pytest.MonkeyPatch, git_repo: Path) -> None:
    """Detached HEAD path stores commit hexsha."""
    base = create_commit(git_repo, "file.txt", "one\n", "msg")
    repo = GitRepo(git_repo)
    from git_bifurcate.models import HunkChange

    class FakeHead:
        def __init__(self, hexsha: str) -> None:
            self.commit = SimpleNamespace(hexsha=hexsha)

        @property
        def ref(self) -> str:  # pragma: no cover - intentionally raises
            raise TypeError("detached")

    diff_text = """diff --git a/file.txt b/file.txt
index 1..2 100644
--- a/file.txt
+++ b/file.txt
@@ -1 +1 @@
-one
+two"""

    sample_hunk = HunkChange(
        id="1",
        file_path="file.txt",
        start_line=1,
        end_line=1,
        original_start=1,
        original_length=1,
        new_start=1,
        new_length=1,
        diff_content="@@ -1 +1 @@\n-one\n+two\n",
        status=ChangeStatus.UNKNOWN,
    )

    monkeypatch.setattr(repo, "create_temp_branch", lambda name, commit: None)
    monkeypatch.setattr(repo, "get_diff", lambda bad, base_commit: diff_text)
    monkeypatch.setattr(repo, "apply_patch", lambda patch: True)
    monkeypatch.setattr(
        repo,
        "repo",
        SimpleNamespace(
            head=FakeHead(base), git=SimpleNamespace(checkout=lambda *args, **kwargs: None)
        ),
    )

    assert repo.apply_hunk_changes([sample_hunk], base, base, use_temp_branch=True)


def test_apply_hunk_changes_create_branch_failure(
    monkeypatch: pytest.MonkeyPatch, git_repo: Path
) -> None:
    """Branch creation failure bubbles up as False."""
    base = create_commit(git_repo, "file.txt", "one\n", "msg")
    repo = GitRepo(git_repo)
    from git_bifurcate.models import HunkChange

    sample_hunk = HunkChange(
        id="1",
        file_path="file.txt",
        start_line=1,
        end_line=1,
        original_start=1,
        original_length=1,
        new_start=1,
        new_length=1,
        diff_content="@@ -1 +1 @@\n-one\n+two\n",
        status=ChangeStatus.UNKNOWN,
    )

    monkeypatch.setattr(
        repo,
        "create_temp_branch",
        lambda name, commit: (_ for _ in ()).throw(GitOperationError("no branch")),
    )
    assert not repo.apply_hunk_changes([sample_hunk], base, base, use_temp_branch=True)


def test_apply_hunk_changes_header_cleanup_calls_delete(
    monkeypatch: pytest.MonkeyPatch, git_repo: Path
) -> None:
    """Cleanup when headers are missing calls delete_branch."""
    base = create_commit(git_repo, "file.txt", "one\n", "msg")
    repo = GitRepo(git_repo)
    from git_bifurcate.models import HunkChange

    sample_hunk = HunkChange(
        id="1",
        file_path="file.txt",
        start_line=1,
        end_line=1,
        original_start=1,
        original_length=1,
        new_start=1,
        new_length=1,
        diff_content="@@ -1 +1 @@\n-one\n+two\n",
        status=ChangeStatus.UNKNOWN,
    )

    monkeypatch.setattr(repo, "get_diff", lambda bad, base_commit: "diff --git a/x b/x")
    monkeypatch.setattr(repo, "_extract_file_header", lambda full, path: None)
    monkeypatch.setattr(repo, "create_temp_branch", lambda name, commit: None)
    deleted = {"called": False}
    monkeypatch.setattr(repo, "delete_branch", lambda name: deleted.__setitem__("called", True))

    assert not repo.apply_hunk_changes([sample_hunk], base, base, use_temp_branch=True)
    assert deleted["called"]


def test_apply_hunk_changes_apply_patch_cleanup_error(
    monkeypatch: pytest.MonkeyPatch, git_repo: Path
) -> None:
    """Cleanup handles checkout failures when patch application fails."""
    base = create_commit(git_repo, "file.txt", "one\n", "msg")
    repo = GitRepo(git_repo)
    from git_bifurcate.models import HunkChange

    sample_hunk = HunkChange(
        id="1",
        file_path="file.txt",
        start_line=1,
        end_line=1,
        original_start=1,
        original_length=1,
        new_start=1,
        new_length=1,
        diff_content="@@ -1 +1 @@\n-one\n+two\n",
        status=ChangeStatus.UNKNOWN,
    )

    diff_text = """diff --git a/file.txt b/file.txt
index 1..2 100644
--- a/file.txt
+++ b/file.txt
@@ -1 +1 @@
-one
+two"""

    monkeypatch.setattr(repo, "get_diff", lambda bad, base_commit: diff_text)
    monkeypatch.setattr(repo, "apply_patch", lambda patch: False)
    monkeypatch.setattr(repo, "create_temp_branch", lambda name, commit: None)

    def bad_checkout(*args, **kwargs):
        raise git.GitCommandError("checkout", 1, "fail")

    monkeypatch.setattr(type(repo.repo.git), "checkout", bad_checkout, raising=False)
    monkeypatch.setattr(repo, "delete_branch", lambda name: None)

    assert not repo.apply_hunk_changes([sample_hunk], base, base, use_temp_branch=True)


def test_apply_hunk_changes_apply_patch_failure(
    monkeypatch: pytest.MonkeyPatch, git_repo: Path
) -> None:
    """Failed patch application cleans up temp branch."""
    repo = GitRepo(git_repo)
    base = create_commit(git_repo, "file.txt", "one\n", "msg")
    from git_bifurcate.models import HunkChange

    sample_hunk = HunkChange(
        id="1",
        file_path="file.txt",
        start_line=1,
        end_line=1,
        original_start=1,
        original_length=1,
        new_start=1,
        new_length=1,
        diff_content="@@ -1 +1 @@\n-one\n+two\n",
        status=ChangeStatus.UNKNOWN,
    )

    diff_text = """diff --git a/file.txt b/file.txt
index 111..222 100644
--- a/file.txt
+++ b/file.txt
@@ -1 +1 @@
-one
+two"""

    monkeypatch.setattr(repo, "get_diff", lambda bad, base_commit: diff_text)
    monkeypatch.setattr(repo, "apply_patch", lambda patch: False)
    monkeypatch.setattr(repo, "create_temp_branch", lambda name, commit: None)
    monkeypatch.setattr(repo, "delete_branch", lambda name: None)

    assert not repo.apply_hunk_changes([sample_hunk], base, base, use_temp_branch=True)


def test_apply_hunk_changes_reset_failure_non_temp(
    monkeypatch: pytest.MonkeyPatch, git_repo: Path
) -> None:
    """Reset failures without temp branch return False."""
    repo = GitRepo(git_repo)
    create_commit(git_repo, "file.txt", "one\n", "msg")
    from git_bifurcate.models import HunkChange

    sample_hunk = HunkChange(
        id="1",
        file_path="file.txt",
        start_line=1,
        end_line=1,
        original_start=1,
        original_length=1,
        new_start=1,
        new_length=1,
        diff_content="@@ -1 +1 @@\n-one\n+two\n",
        status=ChangeStatus.UNKNOWN,
    )

    def bad_reset(*args, **kwargs):
        raise GitOperationError("reset")

    monkeypatch.setattr(repo, "reset_hard", bad_reset)
    assert not repo.apply_hunk_changes([sample_hunk], "HEAD", "HEAD", use_temp_branch=False)


def test_extract_file_header_without_hunks() -> None:
    """If the diff moves to the next file without hunks, None is returned."""
    repo = GitRepo()
    diff = """diff --git a/a.txt b/a.txt
index 1..2 100644
--- a/a.txt
+++ b/a.txt
diff --git a/b.txt b/b.txt
@@ -1 +1 @@
-x
+y"""

    assert repo._extract_file_header(diff, "a.txt") is None
