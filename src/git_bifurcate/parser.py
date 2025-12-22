"""Parse git diff output into structured changes."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from git_bifurcate.models import FileChange, HunkChange

from git_bifurcate.models import ChangeStatus


def parse_file_changes(diff_text: str) -> list[FileChange]:
    """Parse git diff output to extract file-level changes.

    Args:
        diff_text: Output from git diff command.

    Returns:
        List of FileChange objects.
    """
    from git_bifurcate.models import FileChange

    changes: list[FileChange] = []
    current_file: list[str] = []
    current_path: str | None = None
    current_type = "modified"
    file_counter = 0

    for line in diff_text.split("\n"):
        if line.startswith("diff --git"):
            # Save previous file if exists
            if current_path and current_file:
                detected_type = _detect_change_type(current_type, current_file)
                metadata: dict[str, str] | None = None

                if detected_type == "submodule":
                    metadata = _extract_submodule_commits(current_file)

                changes.append(
                    FileChange(
                        id=str(file_counter),
                        file_path=current_path,
                        change_type=detected_type,
                        diff_content="\n".join(current_file),
                        status=ChangeStatus.UNKNOWN,
                        metadata=metadata or {},
                    )
                )
                file_counter += 1

            # Start new file
            current_file = [line]
            # Extract file path: diff --git a/path/to/file b/path/to/file
            match = re.search(r"b/(.+)$", line)
            current_path = match.group(1) if match else "unknown"
            current_type = "modified"

        elif line.startswith("new file"):
            current_type = "added"
            current_file.append(line)
        elif line.startswith("deleted file"):
            current_type = "deleted"
            current_file.append(line)
        elif line.startswith("rename"):
            current_type = "renamed"
            current_file.append(line)
        elif current_file:
            current_file.append(line)

    # Don't forget last file
    if current_path and current_file:
        detected_type = _detect_change_type(current_type, current_file)
        metadata: dict[str, str] | None = None

        if detected_type == "submodule":
            metadata = _extract_submodule_commits(current_file)

        changes.append(
            FileChange(
                id=str(file_counter),
                file_path=current_path,
                change_type=detected_type,
                diff_content="\n".join(current_file),
                status=ChangeStatus.UNKNOWN,
                metadata=metadata or {},
            )
        )

    return changes


def parse_hunk_changes(diff_text: str) -> list[HunkChange]:
    """Parse git diff output to extract hunk-level changes.

    Args:
        diff_text: Output from git diff command.

    Returns:
        List of HunkChange objects.
    """
    from git_bifurcate.models import HunkChange

    hunks: list[HunkChange] = []
    current_file: str | None = None
    current_hunk: list[str] = []
    hunk_header: tuple[int, int, int, int] | None = None
    hunk_counter = 0

    for line in diff_text.split("\n"):
        if line.startswith("diff --git"):
            # Save previous hunk before changing files
            if current_file and current_hunk and hunk_header:
                orig_start, orig_len, new_start, new_len = hunk_header
                hunks.append(
                    HunkChange(
                        id=str(hunk_counter),
                        file_path=current_file,
                        start_line=new_start,
                        end_line=new_start + new_len - 1,
                        original_start=orig_start,
                        original_length=orig_len,
                        new_start=new_start,
                        new_length=new_len,
                        diff_content="\n".join(current_hunk),
                        status=ChangeStatus.UNKNOWN,
                    )
                )
                hunk_counter += 1
                current_hunk = []
                hunk_header = None

            # Extract file path
            match = re.search(r"b/(.+)$", line)
            current_file = match.group(1) if match else "unknown"

        elif line.startswith("@@"):
            # Save previous hunk if exists
            if current_file and current_hunk and hunk_header:
                orig_start, orig_len, new_start, new_len = hunk_header
                hunks.append(
                    HunkChange(
                        id=str(hunk_counter),
                        file_path=current_file,
                        start_line=new_start,
                        end_line=new_start + new_len - 1,
                        original_start=orig_start,
                        original_length=orig_len,
                        new_start=new_start,
                        new_length=new_len,
                        diff_content="\n".join(current_hunk),
                        status=ChangeStatus.UNKNOWN,
                    )
                )
                hunk_counter += 1

            # Parse hunk header: @@ -45,7 +45,8 @@
            match = re.search(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@", line)
            if match:
                hunk_header = (
                    int(match.group(1)),  # original start
                    int(match.group(2)),  # original length
                    int(match.group(3)),  # new start
                    int(match.group(4)),  # new length
                )
                current_hunk = [line]
            else:
                # Hunk header without length (single line)
                match = re.search(r"@@ -(\d+) \+(\d+) @@", line)
                if match:
                    hunk_header = (
                        int(match.group(1)),
                        1,
                        int(match.group(2)),
                        1,
                    )
                    current_hunk = [line]

        elif current_hunk:
            current_hunk.append(line)

    # Don't forget last hunk
    if current_file and current_hunk and hunk_header:
        orig_start, orig_len, new_start, new_len = hunk_header
        hunks.append(
            HunkChange(
                id=str(hunk_counter),
                file_path=current_file,
                start_line=new_start,
                end_line=new_start + new_len - 1,
                original_start=orig_start,
                original_length=orig_len,
                new_start=new_start,
                new_length=new_len,
                diff_content="\n".join(current_hunk),
                status=ChangeStatus.UNKNOWN,
            )
        )

    return hunks


def get_file_hunks(file_path: str, diff_text: str) -> list[HunkChange]:
    """Get all hunks for a specific file from diff.

    Args:
        file_path: Path of file to extract hunks for.
        diff_text: Full diff text.

    Returns:
        List of HunkChange objects for the specified file.
    """
    all_hunks = parse_hunk_changes(diff_text)
    return [hunk for hunk in all_hunks if hunk.file_path == file_path]


def _detect_change_type(current_type: str, diff_lines: list[str]) -> str:
    """Infer the change type, including submodule updates."""

    if any("Subproject commit" in line for line in diff_lines) or any(
        re.search(r"160000", line) for line in diff_lines if line.startswith("index")
    ):
        return "submodule"

    return current_type


def _extract_submodule_commits(diff_lines: list[str]) -> dict[str, str]:
    """Extract old and new submodule commits from a gitlink diff."""

    old_sha: str | None = None
    new_sha: str | None = None

    for line in diff_lines:
        if line.startswith("-Subproject commit "):
            old_sha = line.replace("-Subproject commit ", "").strip()
        if line.startswith("+Subproject commit "):
            new_sha = line.replace("+Subproject commit ", "").strip()

    metadata: dict[str, str] = {}
    if old_sha:
        metadata["old_sha"] = old_sha
    if new_sha:
        metadata["new_sha"] = new_sha
    return metadata
