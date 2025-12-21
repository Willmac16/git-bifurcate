"""Data models for git-bifurcate."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ChangeStatus(str, Enum):
    """Status of a change during bifurcation."""

    UNKNOWN = "unknown"
    GOOD = "good"
    BAD = "bad"
    SKIP = "skip"


class CommandResult(str, Enum):
    """Result of running a test command."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


class Strategy(str, Enum):
    """Bifurcation strategy."""

    FILE = "file"
    HUNK = "hunk"
    HYBRID = "hybrid"


@dataclass
class FileChange:
    """Represents a file-level change in a commit."""

    id: str
    file_path: str
    change_type: str  # 'modified', 'added', 'deleted', 'renamed'
    diff_content: str
    status: ChangeStatus = ChangeStatus.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "file_path": self.file_path,
            "change_type": self.change_type,
            "diff_content": self.diff_content,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileChange:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            file_path=data["file_path"],
            change_type=data["change_type"],
            diff_content=data["diff_content"],
            status=ChangeStatus(data["status"]),
        )


@dataclass
class HunkChange:
    """Represents a hunk-level change within a file."""

    id: str
    file_path: str
    start_line: int
    end_line: int
    original_start: int
    original_length: int
    new_start: int
    new_length: int
    diff_content: str
    status: ChangeStatus = ChangeStatus.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "original_start": self.original_start,
            "original_length": self.original_length,
            "new_start": self.new_start,
            "new_length": self.new_length,
            "diff_content": self.diff_content,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HunkChange:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            file_path=data["file_path"],
            start_line=data["start_line"],
            end_line=data["end_line"],
            original_start=data["original_start"],
            original_length=data["original_length"],
            new_start=data["new_start"],
            new_length=data["new_length"],
            diff_content=data["diff_content"],
            status=ChangeStatus(data["status"]),
        )


@dataclass
class BifurcationState:
    """Persistent state for a bifurcation session."""

    commit_sha: str
    parent_sha: str
    test_command: str
    strategy: Strategy
    changes: list[FileChange | HunkChange]
    search_space: list[int]
    tested_combinations: dict[str, str] = field(default_factory=dict)
    found_breaking: list[int] = field(default_factory=list)
    current_iteration: int = 0

    def save(self, filepath: Path | str = ".git/bifurcate-state.json") -> None:
        """Save state to JSON file."""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "commit_sha": self.commit_sha,
            "parent_sha": self.parent_sha,
            "test_command": self.test_command,
            "strategy": self.strategy.value,
            "changes": [change.to_dict() for change in self.changes],
            "search_space": self.search_space,
            "tested_combinations": self.tested_combinations,
            "found_breaking": self.found_breaking,
            "current_iteration": self.current_iteration,
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, filepath: Path | str = ".git/bifurcate-state.json") -> BifurcationState:
        """Load state from JSON file."""
        filepath = Path(filepath)

        if not filepath.exists():
            msg = f"State file not found: {filepath}"
            raise FileNotFoundError(msg)

        with open(filepath) as f:
            data = json.load(f)

        # Reconstruct changes (they could be FileChange or HunkChange)
        changes: list[FileChange | HunkChange] = []
        for change_data in data["changes"]:
            if "start_line" in change_data:
                changes.append(HunkChange.from_dict(change_data))
            else:
                changes.append(FileChange.from_dict(change_data))

        return cls(
            commit_sha=data["commit_sha"],
            parent_sha=data["parent_sha"],
            test_command=data["test_command"],
            strategy=Strategy(data["strategy"]),
            changes=changes,
            search_space=data["search_space"],
            tested_combinations=data["tested_combinations"],
            found_breaking=data.get("found_breaking", []),
            current_iteration=data.get("current_iteration", 0),
        )

    @classmethod
    def exists(cls, filepath: Path | str = ".git/bifurcate-state.json") -> bool:
        """Check if state file exists."""
        return Path(filepath).exists()

    @staticmethod
    def delete(filepath: Path | str = ".git/bifurcate-state.json") -> None:
        """Delete state file."""
        filepath = Path(filepath)
        if filepath.exists():
            filepath.unlink()
