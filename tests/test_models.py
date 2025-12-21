"""Tests for data models and serialization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from git_bifurcate.models import (
    BifurcationState,
    ChangeStatus,
    CommandResult,
    FileChange,
    HunkChange,
    Strategy,
)


def test_change_status_enum() -> None:
    """Test ChangeStatus enum values."""
    assert ChangeStatus.UNKNOWN.value == "unknown"
    assert ChangeStatus.GOOD.value == "good"
    assert ChangeStatus.BAD.value == "bad"
    assert ChangeStatus.SKIP.value == "skip"


def test_test_result_enum() -> None:
    """Test CommandResult enum values."""
    assert CommandResult.PASS.value == "pass"
    assert CommandResult.FAIL.value == "fail"
    assert CommandResult.SKIP.value == "skip"
    assert CommandResult.ERROR.value == "error"


def test_strategy_enum() -> None:
    """Test Strategy enum values."""
    assert Strategy.FILE.value == "file"
    assert Strategy.HUNK.value == "hunk"
    assert Strategy.HYBRID.value == "hybrid"


def test_file_change_creation() -> None:
    """Test creating FileChange object."""
    change = FileChange(
        id="0",
        file_path="test.py",
        change_type="modified",
        diff_content="diff content",
        status=ChangeStatus.UNKNOWN,
    )

    assert change.id == "0"
    assert change.file_path == "test.py"
    assert change.change_type == "modified"
    assert change.diff_content == "diff content"
    assert change.status == ChangeStatus.UNKNOWN


def test_file_change_to_dict() -> None:
    """Test FileChange serialization to dict."""
    change = FileChange(
        id="1",
        file_path="module.py",
        change_type="added",
        diff_content="some diff",
        status=ChangeStatus.GOOD,
    )

    data = change.to_dict()

    assert data["id"] == "1"
    assert data["file_path"] == "module.py"
    assert data["change_type"] == "added"
    assert data["diff_content"] == "some diff"
    assert data["status"] == "good"


def test_file_change_from_dict() -> None:
    """Test FileChange deserialization from dict."""
    data = {
        "id": "2",
        "file_path": "utils.py",
        "change_type": "deleted",
        "diff_content": "diff data",
        "status": "bad",
    }

    change = FileChange.from_dict(data)

    assert change.id == "2"
    assert change.file_path == "utils.py"
    assert change.change_type == "deleted"
    assert change.diff_content == "diff data"
    assert change.status == ChangeStatus.BAD


def test_file_change_roundtrip() -> None:
    """Test FileChange serialization roundtrip."""
    original = FileChange(
        id="3",
        file_path="test.py",
        change_type="modified",
        diff_content="test diff",
        status=ChangeStatus.SKIP,
    )

    data = original.to_dict()
    restored = FileChange.from_dict(data)

    assert restored.id == original.id
    assert restored.file_path == original.file_path
    assert restored.change_type == original.change_type
    assert restored.diff_content == original.diff_content
    assert restored.status == original.status


def test_hunk_change_creation() -> None:
    """Test creating HunkChange object."""
    hunk = HunkChange(
        id="0",
        file_path="test.py",
        start_line=10,
        end_line=15,
        original_start=10,
        original_length=5,
        new_start=10,
        new_length=6,
        diff_content="hunk diff",
        status=ChangeStatus.UNKNOWN,
    )

    assert hunk.id == "0"
    assert hunk.file_path == "test.py"
    assert hunk.start_line == 10
    assert hunk.end_line == 15
    assert hunk.original_start == 10
    assert hunk.original_length == 5
    assert hunk.new_start == 10
    assert hunk.new_length == 6
    assert hunk.diff_content == "hunk diff"
    assert hunk.status == ChangeStatus.UNKNOWN


def test_hunk_change_to_dict() -> None:
    """Test HunkChange serialization to dict."""
    hunk = HunkChange(
        id="1",
        file_path="module.py",
        start_line=20,
        end_line=25,
        original_start=20,
        original_length=5,
        new_start=20,
        new_length=6,
        diff_content="some hunk",
        status=ChangeStatus.GOOD,
    )

    data = hunk.to_dict()

    assert data["id"] == "1"
    assert data["file_path"] == "module.py"
    assert data["start_line"] == 20
    assert data["end_line"] == 25
    assert data["original_start"] == 20
    assert data["original_length"] == 5
    assert data["new_start"] == 20
    assert data["new_length"] == 6
    assert data["diff_content"] == "some hunk"
    assert data["status"] == "good"


def test_hunk_change_from_dict() -> None:
    """Test HunkChange deserialization from dict."""
    data = {
        "id": "2",
        "file_path": "utils.py",
        "start_line": 30,
        "end_line": 35,
        "original_start": 30,
        "original_length": 5,
        "new_start": 30,
        "new_length": 6,
        "diff_content": "hunk data",
        "status": "bad",
    }

    hunk = HunkChange.from_dict(data)

    assert hunk.id == "2"
    assert hunk.file_path == "utils.py"
    assert hunk.start_line == 30
    assert hunk.end_line == 35
    assert hunk.status == ChangeStatus.BAD


def test_hunk_change_roundtrip() -> None:
    """Test HunkChange serialization roundtrip."""
    original = HunkChange(
        id="3",
        file_path="test.py",
        start_line=40,
        end_line=45,
        original_start=40,
        original_length=5,
        new_start=40,
        new_length=6,
        diff_content="test hunk",
        status=ChangeStatus.SKIP,
    )

    data = original.to_dict()
    restored = HunkChange.from_dict(data)

    assert restored.id == original.id
    assert restored.file_path == original.file_path
    assert restored.start_line == original.start_line
    assert restored.end_line == original.end_line
    assert restored.original_start == original.original_start
    assert restored.original_length == original.original_length
    assert restored.new_start == original.new_start
    assert restored.new_length == original.new_length
    assert restored.diff_content == original.diff_content
    assert restored.status == original.status


def test_bifurcation_state_creation() -> None:
    """Test creating BifurcationState object."""
    changes = [
        FileChange("0", "file1.py", "modified", "diff1", ChangeStatus.UNKNOWN),
        FileChange("1", "file2.py", "added", "diff2", ChangeStatus.UNKNOWN),
    ]

    state = BifurcationState(
        commit_sha="abc123",
        parent_sha="def456",
        test_command="pytest",
        strategy=Strategy.FILE,
        changes=changes,
        search_space=[0, 1],
    )

    assert state.commit_sha == "abc123"
    assert state.parent_sha == "def456"
    assert state.test_command == "pytest"
    assert state.strategy == Strategy.FILE
    assert len(state.changes) == 2
    assert state.search_space == [0, 1]
    assert state.current_iteration == 0
    assert len(state.tested_combinations) == 0
    assert len(state.found_breaking) == 0


def test_bifurcation_state_save_load(temp_dir: Path) -> None:
    """Test saving and loading BifurcationState."""
    state_file = temp_dir / "state.json"

    changes = [
        FileChange("0", "file1.py", "modified", "diff1", ChangeStatus.GOOD),
        FileChange("1", "file2.py", "added", "diff2", ChangeStatus.BAD),
    ]

    original = BifurcationState(
        commit_sha="abc123",
        parent_sha="def456",
        test_command="pytest tests/",
        strategy=Strategy.FILE,
        changes=changes,
        search_space=[0, 1],
        tested_combinations={"0,1": "fail"},
        found_breaking=[1],
        current_iteration=5,
    )

    # Save
    original.save(state_file)

    # Verify file exists
    assert state_file.exists()

    # Load
    loaded = BifurcationState.load(state_file)

    # Verify all fields match
    assert loaded.commit_sha == original.commit_sha
    assert loaded.parent_sha == original.parent_sha
    assert loaded.test_command == original.test_command
    assert loaded.strategy == original.strategy
    assert len(loaded.changes) == len(original.changes)
    assert loaded.search_space == original.search_space
    assert loaded.tested_combinations == original.tested_combinations
    assert loaded.found_breaking == original.found_breaking
    assert loaded.current_iteration == original.current_iteration

    # Verify changes
    assert loaded.changes[0].id == "0"
    assert loaded.changes[0].file_path == "file1.py"
    assert loaded.changes[0].status == ChangeStatus.GOOD

    assert loaded.changes[1].id == "1"
    assert loaded.changes[1].file_path == "file2.py"
    assert loaded.changes[1].status == ChangeStatus.BAD


def test_bifurcation_state_save_load_hunks(temp_dir: Path) -> None:
    """Test saving and loading BifurcationState with HunkChanges."""
    state_file = temp_dir / "state.json"

    changes: list[FileChange | HunkChange] = [
        HunkChange(
            "0",
            "file.py",
            10,
            15,
            10,
            5,
            10,
            6,
            "hunk1",
            ChangeStatus.UNKNOWN,
        ),
        HunkChange(
            "1",
            "file.py",
            20,
            25,
            20,
            5,
            20,
            6,
            "hunk2",
            ChangeStatus.UNKNOWN,
        ),
    ]

    original = BifurcationState(
        commit_sha="xyz789",
        parent_sha="uvw012",
        test_command="make test",
        strategy=Strategy.HUNK,
        changes=changes,
        search_space=[0, 1],
    )

    # Save and load
    original.save(state_file)
    loaded = BifurcationState.load(state_file)

    # Verify hunks were preserved
    assert len(loaded.changes) == 2
    assert isinstance(loaded.changes[0], HunkChange)
    assert isinstance(loaded.changes[1], HunkChange)

    hunk0 = loaded.changes[0]
    assert isinstance(hunk0, HunkChange)  # Type narrowing for mypy
    assert hunk0.start_line == 10
    assert hunk0.end_line == 15


def test_bifurcation_state_mixed_changes(temp_dir: Path) -> None:
    """Test BifurcationState with mixed FileChange and HunkChange."""
    state_file = temp_dir / "state.json"

    changes: list[FileChange | HunkChange] = [
        FileChange("0", "file1.py", "added", "diff1", ChangeStatus.UNKNOWN),
        HunkChange("1", "file2.py", 10, 15, 10, 5, 10, 6, "hunk1", ChangeStatus.UNKNOWN),
    ]

    original = BifurcationState(
        commit_sha="abc",
        parent_sha="def",
        test_command="test",
        strategy=Strategy.HYBRID,
        changes=changes,
        search_space=[0, 1],
    )

    original.save(state_file)
    loaded = BifurcationState.load(state_file)

    assert len(loaded.changes) == 2
    assert isinstance(loaded.changes[0], FileChange)
    assert isinstance(loaded.changes[1], HunkChange)


def test_bifurcation_state_exists(temp_dir: Path) -> None:
    """Test BifurcationState.exists() method."""
    state_file = temp_dir / "state.json"

    assert not BifurcationState.exists(state_file)

    changes = [FileChange("0", "file.py", "modified", "diff", ChangeStatus.UNKNOWN)]
    state = BifurcationState(
        commit_sha="abc",
        parent_sha="def",
        test_command="test",
        strategy=Strategy.FILE,
        changes=changes,
        search_space=[0],
    )

    state.save(state_file)

    assert BifurcationState.exists(state_file)


def test_bifurcation_state_delete(temp_dir: Path) -> None:
    """Test BifurcationState.delete() method."""
    state_file = temp_dir / "state.json"

    changes = [FileChange("0", "file.py", "modified", "diff", ChangeStatus.UNKNOWN)]
    state = BifurcationState(
        commit_sha="abc",
        parent_sha="def",
        test_command="test",
        strategy=Strategy.FILE,
        changes=changes,
        search_space=[0],
    )

    state.save(state_file)
    assert state_file.exists()

    BifurcationState.delete(state_file)
    assert not state_file.exists()

    # Deleting non-existent file should not raise
    BifurcationState.delete(state_file)


def test_bifurcation_state_load_nonexistent(temp_dir: Path) -> None:
    """Test loading non-existent state file raises error."""
    state_file = temp_dir / "nonexistent.json"

    with pytest.raises(FileNotFoundError, match="State file not found"):
        BifurcationState.load(state_file)


def test_bifurcation_state_json_format(temp_dir: Path) -> None:
    """Test that saved state is valid JSON with expected structure."""
    state_file = temp_dir / "state.json"

    changes = [
        FileChange("0", "file.py", "modified", "diff", ChangeStatus.GOOD),
    ]

    state = BifurcationState(
        commit_sha="abc123",
        parent_sha="def456",
        test_command="pytest",
        strategy=Strategy.FILE,
        changes=changes,
        search_space=[0],
        tested_combinations={"0": "pass"},
        found_breaking=[],
        current_iteration=3,
    )

    state.save(state_file)

    # Read and verify JSON
    with open(state_file) as f:
        data = json.load(f)

    assert data["commit_sha"] == "abc123"
    assert data["parent_sha"] == "def456"
    assert data["test_command"] == "pytest"
    assert data["strategy"] == "file"
    assert len(data["changes"]) == 1
    assert data["changes"][0]["id"] == "0"
    assert data["search_space"] == [0]
    assert data["tested_combinations"] == {"0": "pass"}
    assert data["found_breaking"] == []
    assert data["current_iteration"] == 3
