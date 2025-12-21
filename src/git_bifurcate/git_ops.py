"""Git operations wrapper using GitPython."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import git

if TYPE_CHECKING:
    from git_bifurcate.models import FileChange, HunkChange


class GitOperationError(Exception):
    """Raised when a git operation fails."""


class GitRepo:
    """Wrapper around GitPython for git-bifurcate operations."""

    def __init__(self, repo_path: Path | str = ".") -> None:
        """Initialize git repository wrapper.

        Args:
            repo_path: Path to git repository. Defaults to current directory.

        Raises:
            GitOperationError: If not a valid git repository.
        """
        try:
            self.repo = git.Repo(repo_path, search_parent_directories=True)
            # Resolve the repository path to eliminate any symlink prefixes (e.g., /private on macOS)
            self.repo_path = Path(self.repo.working_dir).resolve()
        except git.InvalidGitRepositoryError as e:
            msg = f"Not a git repository: {repo_path}"
            raise GitOperationError(msg) from e

    def get_commit(self, sha: str) -> git.Commit:
        """Get commit object by SHA.

        Args:
            sha: Commit SHA (can be short or full).

        Returns:
            Commit object.

        Raises:
            GitOperationError: If commit not found.
        """
        try:
            return self.repo.commit(sha)
        except (git.BadName, ValueError) as e:
            msg = f"Commit not found: {sha}"
            raise GitOperationError(msg) from e

    def get_parent_commit(self, sha: str) -> str:
        """Get parent commit SHA.

        Args:
            sha: Commit SHA.

        Returns:
            Parent commit SHA.

        Raises:
            GitOperationError: If commit has no parent or multiple parents.
        """
        commit = self.get_commit(sha)

        if not commit.parents:
            msg = f"Commit {sha} has no parent (initial commit)"
            raise GitOperationError(msg)

        if len(commit.parents) > 1:
            msg = f"Commit {sha} is a merge commit with multiple parents"
            raise GitOperationError(msg)

        return commit.parents[0].hexsha

    def get_diff(self, commit_sha: str, parent_sha: str | None = None) -> str:
        """Get diff between commit and parent.

        Args:
            commit_sha: Commit SHA to diff.
            parent_sha: Parent commit SHA. If None, uses commit's parent.

        Returns:
            Diff as string in unified format.

        Raises:
            GitOperationError: If diff fails.
        """
        try:
            if parent_sha is None:
                parent_sha = self.get_parent_commit(commit_sha)

            # Get diff using git command for consistent format
            result = subprocess.run(
                ["git", "diff", parent_sha, commit_sha],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout

        except subprocess.CalledProcessError as e:
            msg = f"Failed to get diff: {e.stderr}"
            raise GitOperationError(msg) from e

    def checkout(self, ref: str) -> None:
        """Checkout a ref (commit, branch, tag).

        Args:
            ref: Git reference to checkout.

        Raises:
            GitOperationError: If checkout fails.
        """
        try:
            self.repo.git.checkout(ref)
        except git.GitCommandError as e:
            msg = f"Failed to checkout {ref}: {e}"
            raise GitOperationError(msg) from e

    def create_temp_branch(self, name: str, base_commit: str) -> None:
        """Create a temporary branch at base commit.

        Args:
            name: Branch name.
            base_commit: Commit SHA to branch from.

        Raises:
            GitOperationError: If branch creation fails.
        """
        try:
            self.repo.create_head(name, base_commit, force=True)
            self.checkout(name)
        except git.GitCommandError as e:
            msg = f"Failed to create branch {name}: {e}"
            raise GitOperationError(msg) from e

    def delete_branch(self, name: str) -> None:
        """Delete a branch.

        Args:
            name: Branch name to delete.

        Raises:
            GitOperationError: If deletion fails.
        """
        try:
            self.repo.delete_head(name, force=True)
        except git.GitCommandError as e:
            msg = f"Failed to delete branch {name}: {e}"
            raise GitOperationError(msg) from e

    def apply_patch(self, patch: str) -> bool:
        """Apply a patch to working directory.

        Args:
            patch: Patch content in unified diff format.

        Returns:
            True if patch applied successfully, False otherwise.
        """
        try:
            # Ensure patch ends with newline (git requires it)
            if not patch.endswith("\n"):
                patch = patch + "\n"

            # Use git apply with --index to stage changes
            result = subprocess.run(
                ["git", "apply", "--index"],
                input=patch,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    def reset_hard(self, ref: str) -> None:
        """Hard reset to a ref.

        Args:
            ref: Git reference to reset to.

        Raises:
            GitOperationError: If reset fails.
        """
        try:
            self.repo.head.reset(ref, index=True, working_tree=True)
        except git.GitCommandError as e:
            msg = f"Failed to reset to {ref}: {e}"
            raise GitOperationError(msg) from e

    def commit(self, message: str) -> None:
        """Create a commit with staged changes.

        Args:
            message: Commit message.

        Raises:
            GitOperationError: If commit fails.
        """
        try:
            self.repo.index.commit(message)
        except git.GitCommandError as e:
            msg = f"Failed to commit: {e}"
            raise GitOperationError(msg) from e

    def apply_changes(
        self, changes: list[FileChange], base_commit: str, use_temp_branch: bool = True
    ) -> bool:
        """Apply a subset of file changes.

        Args:
            changes: List of FileChange objects to apply.
            base_commit: Commit SHA to apply changes on top of.
            use_temp_branch: Whether to use temporary branch (safer).

        Returns:
            True if changes applied successfully, False otherwise.
        """
        if not changes:
            return True

        original_ref = None
        if use_temp_branch:
            # Save current branch or HEAD to restore on failure
            try:
                original_ref = self.repo.head.ref.name
            except TypeError:
                # Detached HEAD - save commit SHA
                original_ref = self.repo.head.commit.hexsha

            # Create temp branch
            import uuid

            branch_name = f"bifurcate-temp-{uuid.uuid4().hex[:8]}"
            try:
                self.create_temp_branch(branch_name, base_commit)
            except GitOperationError:
                return False
        else:
            try:
                self.reset_hard(base_commit)
            except GitOperationError:
                return False

        # Separate submodule changes from regular file patches
        submodule_changes: list[FileChange] = [c for c in changes if c.change_type == "submodule"]
        regular_changes: list[FileChange] = [c for c in changes if c.change_type != "submodule"]

        # Combine patches
        combined_patch = "\n".join(
            change.diff_content for change in regular_changes if change.diff_content
        )

        # Try to apply
        success = True
        if combined_patch.strip():
            success = self.apply_patch(combined_patch)

        if success:
            for change in submodule_changes:
                success = self._apply_submodule_change(change)
                if not success:
                    break

        if not success:
            if use_temp_branch:
                # Clean up failed temp branch
                try:
                    # Force checkout to discard any failed patch changes
                    self.repo.git.checkout(original_ref, force=True)
                    self.delete_branch(branch_name)
                except git.GitCommandError:
                    pass
            else:
                try:
                    self.reset_hard(base_commit)
                except GitOperationError:
                    pass

        return success

    def apply_hunk_changes(
        self,
        hunks: list[HunkChange],
        base_commit: str,
        bad_commit: str,
        use_temp_branch: bool = True,
    ) -> bool:
        """Apply a subset of hunk changes.

        Args:
            hunks: List of HunkChange objects to apply.
            base_commit: Commit SHA to apply changes on top of.
            bad_commit: Commit SHA where hunks came from (for header reconstruction).
            use_temp_branch: Whether to use temporary branch (safer).

        Returns:
            True if changes applied successfully, False otherwise.
        """
        if not hunks:
            return True

        original_ref = None
        if use_temp_branch:
            # Save current branch or HEAD to restore on failure
            try:
                original_ref = self.repo.head.ref.name
            except TypeError:
                # Detached HEAD - save commit SHA
                original_ref = self.repo.head.commit.hexsha

            # Create temp branch
            import uuid

            branch_name = f"bifurcate-temp-{uuid.uuid4().hex[:8]}"
            try:
                self.create_temp_branch(branch_name, base_commit)
            except GitOperationError:
                return False
        else:
            try:
                self.reset_hard(base_commit)
            except GitOperationError:
                return False

        # Group hunks by file
        from collections import defaultdict

        hunks_by_file: dict[str, list[HunkChange]] = defaultdict(list)
        for hunk in hunks:
            hunks_by_file[hunk.file_path].append(hunk)

        # Get full diff to extract headers
        full_diff = self.get_diff(bad_commit, base_commit)

        # Build patch with headers for each file
        patch_parts = []
        for file_path, file_hunks in hunks_by_file.items():
            # Extract file headers from full diff
            file_header = self._extract_file_header(full_diff, file_path)
            if not file_header:
                # Can't reconstruct patch without headers
                if use_temp_branch:
                    try:
                        # Force checkout to discard any changes
                        self.repo.git.checkout(original_ref, force=True)
                        self.delete_branch(branch_name)
                    except git.GitCommandError:
                        pass
                return False

            patch_parts.append(file_header)
            # Add selected hunks
            for hunk in file_hunks:
                patch_parts.append(hunk.diff_content)

        combined_patch = "\n".join(patch_parts)

        # Try to apply
        success = self.apply_patch(combined_patch)

        if not success and use_temp_branch:
            # Clean up failed temp branch
            try:
                # Force checkout to discard any failed patch changes
                self.repo.git.checkout(original_ref, force=True)
                self.delete_branch(branch_name)
            except git.GitCommandError:
                pass

        return success

    def _extract_file_header(self, full_diff: str, file_path: str) -> str | None:
        """Extract file header lines from a diff.

        Args:
            full_diff: Complete diff text.
            file_path: Path to file to extract header for.

        Returns:
            Header lines (diff --git, index, ---, +++) or None if not found.
        """
        lines = full_diff.split("\n")
        header_lines = []
        in_file = False

        for line in lines:
            if line.startswith("diff --git") and file_path in line:
                in_file = True
                header_lines = [line]
            elif in_file:
                if line.startswith("@@"):
                    # Found start of hunks, header is complete
                    return "\n".join(header_lines)
                elif line.startswith("diff --git"):
                    # Moved to next file without finding hunks
                    return None
                else:
                    header_lines.append(line)

        return None

    def _apply_submodule_change(self, change: FileChange) -> bool:
        """Apply a submodule pointer change.

        Args:
            change: FileChange describing the submodule gitlink update.

        Returns:
            True if the gitlink and working tree were updated, False otherwise.
        """
        target_commit = self._get_submodule_commit(change, "new_commit")
        if not target_commit:
            return False

        submodule_path = self.repo_path / change.file_path

        try:
            # Ensure the submodule exists locally and is initialized
            subprocess.run(
                ["git", "submodule", "update", "--init", "--recursive", "--", change.file_path],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True,
            )

            # Checkout the desired commit inside the submodule
            subprocess.run(
                ["git", "checkout", target_commit],
                cwd=submodule_path,
                check=True,
                capture_output=True,
                text=True,
            )

            # Stage the gitlink update in the parent repository
            subprocess.run(
                ["git", "add", change.file_path],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def _get_submodule_commit(self, change: FileChange, key: str) -> str | None:
        """Extract a submodule commit from metadata or diff content."""
        metadata_value = change.metadata.get(key)
        if isinstance(metadata_value, str):
            return metadata_value

        search_token = "+Subproject commit" if key == "new_commit" else "-Subproject commit"
        for line in change.diff_content.split("\n"):
            if line.strip().startswith(search_token):
                parts = line.strip().split()
                if len(parts) == 3:
                    return parts[-1]
        return None
