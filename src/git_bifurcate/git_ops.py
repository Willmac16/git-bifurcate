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
            self.git_dir = Path(self.repo.git_dir).resolve()
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

        return str(commit.parents[0].hexsha)

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
            # Keep submodules in sync with checked out ref when present
            gitmodules = self.repo_path / ".gitmodules"
            if gitmodules.exists():
                try:
                    self.repo.git.submodule("update", "--init", "--recursive", "--checkout")
                except git.GitCommandError:
                    # Best-effort: submodule update failures should not crash checkout
                    pass
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

        # Separate submodule changes so we can update gitlinks explicitly
        submodule_changes = [c for c in changes if c.change_type == "submodule"]
        normal_changes = [c for c in changes if c.change_type != "submodule"]
        nested_submodule_changes = [c for c in normal_changes if c.metadata.get("submodule_path")]
        root_changes = [c for c in normal_changes if not c.metadata.get("submodule_path")]

        # Apply submodule updates first (they don't participate in textual patching)
        if submodule_changes:
            submodule_success = self._apply_submodule_changes(submodule_changes)
            if not submodule_success:
                if use_temp_branch:
                    try:
                        self.repo.git.checkout(original_ref, force=True)
                        self.delete_branch(branch_name)
                    except git.GitCommandError:
                        pass
                return False

        # Combine patches for non-submodule changes
        combined_patch = "\n".join(change.diff_content for change in root_changes)

        # Try to apply
        success = True
        if combined_patch.strip():
            success = self.apply_patch(combined_patch)

        # Apply nested submodule patches grouped per submodule
        if success and nested_submodule_changes:
            from collections import defaultdict

            grouped: dict[str, list[FileChange]] = defaultdict(list)
            for change in nested_submodule_changes:
                sub_path = change.metadata.get("submodule_path")
                if sub_path:
                    grouped[sub_path].append(change)

            for submodule_path, sub_changes in grouped.items():
                if not self._ensure_submodule_available(submodule_path):
                    success = False
                    break

                target_sha = sub_changes[0].metadata.get("submodule_old_sha")
                if target_sha:
                    checkout_cmd = subprocess.run(
                        ["git", "-C", str(self.repo_path / submodule_path), "checkout", target_sha],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if checkout_cmd.returncode != 0:
                        success = False
                        break

                combined_sub_patch = "\n".join(change.diff_content for change in sub_changes)
                if combined_sub_patch.strip():
                    success = self._apply_patch_in_submodule(submodule_path, combined_sub_patch)

                if not success:
                    break

        if not success and use_temp_branch:
            # Clean up failed temp branch
            try:
                # Force checkout to discard any failed patch changes
                self.repo.git.checkout(original_ref, force=True)
                self.delete_branch(branch_name)
            except git.GitCommandError:
                pass

        return success

    def get_submodule_changes(self, submodule_change: FileChange) -> list[FileChange]:
        """Return parsed changes within a submodule update for deeper analysis."""

        if submodule_change.change_type != "submodule":
            return []

        from git_bifurcate.parser import parse_file_changes

        submodule_path = submodule_change.file_path
        old_sha = submodule_change.metadata.get("old_sha")
        new_sha = submodule_change.metadata.get("new_sha") or self._extract_submodule_commit(
            submodule_change.diff_content
        )

        if not old_sha or not new_sha:
            return []

        if not self._ensure_submodule_available(submodule_path):
            return []

        diff_cmd = subprocess.run(
            ["git", "-C", str(self.repo_path / submodule_path), "diff", old_sha, new_sha],
            capture_output=True,
            text=True,
            check=False,
        )
        if diff_cmd.returncode != 0:
            return []

        inner_changes = parse_file_changes(diff_cmd.stdout)
        for change in inner_changes:
            change.file_path = f"{submodule_path}/{change.file_path}"
            change.metadata = {
                "submodule_path": submodule_path,
                "submodule_old_sha": old_sha,
                "submodule_new_sha": new_sha,
            }

        return inner_changes

    def _apply_submodule_changes(self, submodule_changes: list[FileChange]) -> bool:
        """Apply submodule gitlink updates.

        Args:
            submodule_changes: Changes that represent submodule gitlinks.

        Returns:
            True if all submodule updates were applied and staged.
        """
        for change in submodule_changes:
            new_sha = change.metadata.get("new_sha") or self._extract_submodule_commit(
                change.diff_content
            )
            if not new_sha:
                return False

            submodule_path = self.repo_path / change.file_path

            # Ensure submodule exists
            init_cmd = subprocess.run(
                ["git", "submodule", "update", "--init", "--recursive", "--", change.file_path],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False,
            )
            if init_cmd.returncode != 0:
                return False

            # Fetch best-effort; ignore failures to keep offline compatibility
            subprocess.run(
                ["git", "-C", str(submodule_path), "fetch", "--all"],
                capture_output=True,
                text=True,
                check=False,
            )

            checkout_cmd = subprocess.run(
                ["git", "-C", str(submodule_path), "checkout", new_sha],
                capture_output=True,
                text=True,
                check=False,
            )
            if checkout_cmd.returncode != 0:
                return False

            add_cmd = subprocess.run(
                ["git", "add", change.file_path],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False,
            )
            if add_cmd.returncode != 0:
                return False

        return True

    def _ensure_submodule_available(self, path: str) -> bool:
        """Ensure a submodule exists and is initialized."""

        init_cmd = subprocess.run(
            ["git", "submodule", "update", "--init", "--recursive", "--", path],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        return init_cmd.returncode == 0

    def _apply_patch_in_submodule(self, submodule_path: str, patch: str) -> bool:
        """Apply a patch inside a submodule working tree."""

        try:
            if not patch.endswith("\n"):
                patch = patch + "\n"

            result = subprocess.run(
                ["git", "apply", "--index"],
                input=patch,
                cwd=self.repo_path / submodule_path,
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _extract_submodule_commit(diff_content: str) -> str | None:
        """Extract the new submodule commit SHA from diff content."""

        for line in diff_content.split("\n"):
            if line.startswith("+Subproject commit "):
                return line.replace("+Subproject commit ", "").strip()

        return None

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
            # Ensure repository is on the base commit before running tests
            try:
                self.reset_hard(base_commit)
            except GitOperationError:
                return False
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
