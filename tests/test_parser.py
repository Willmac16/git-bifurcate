"""Tests for diff parsing functionality."""

from __future__ import annotations

from git_bifurcate.models import ChangeStatus
from git_bifurcate.parser import (
    get_file_hunks,
    parse_file_changes,
    parse_hunk_changes,
)


def test_parse_file_changes_basic(sample_diff: str) -> None:
    """Test parsing basic file changes from diff."""
    changes = parse_file_changes(sample_diff)

    assert len(changes) == 3
    assert changes[0].file_path == "file1.py"
    assert changes[0].change_type == "modified"
    assert changes[0].status == ChangeStatus.UNKNOWN

    assert changes[1].file_path == "file2.py"
    assert changes[1].change_type == "added"

    assert changes[2].file_path == "file3.py"
    assert changes[2].change_type == "deleted"


def test_parse_file_changes_ids(sample_diff: str) -> None:
    """Test that file changes have unique sequential IDs."""
    changes = parse_file_changes(sample_diff)

    assert changes[0].id == "0"
    assert changes[1].id == "1"
    assert changes[2].id == "2"


def test_parse_file_changes_diff_content(sample_diff: str) -> None:
    """Test that diff content is preserved."""
    changes = parse_file_changes(sample_diff)

    # Check that diff content starts with the diff header
    assert changes[0].diff_content.startswith("diff --git a/file1.py")
    assert "Hello World" in changes[0].diff_content
    assert "New line" in changes[0].diff_content

    assert changes[1].diff_content.startswith("diff --git a/file2.py")
    assert "new_function" in changes[1].diff_content


def test_parse_file_changes_empty() -> None:
    """Test parsing empty diff."""
    changes = parse_file_changes("")
    assert len(changes) == 0


def test_parse_hunk_changes_basic(sample_hunk_diff: str) -> None:
    """Test parsing hunk changes from diff."""
    hunks = parse_hunk_changes(sample_hunk_diff)

    assert len(hunks) == 2
    assert hunks[0].file_path == "module.py"
    assert hunks[1].file_path == "module.py"


def test_parse_hunk_changes_line_numbers(sample_hunk_diff: str) -> None:
    """Test that hunk line numbers are correctly parsed."""
    hunks = parse_hunk_changes(sample_hunk_diff)

    # First hunk: @@ -5,7 +5,8 @@
    assert hunks[0].original_start == 5
    assert hunks[0].original_length == 7
    assert hunks[0].new_start == 5
    assert hunks[0].new_length == 8
    assert hunks[0].start_line == 5
    assert hunks[0].end_line == 12  # 5 + 8 - 1

    # Second hunk: @@ -20,3 +21,5 @@
    assert hunks[1].original_start == 20
    assert hunks[1].original_length == 3
    assert hunks[1].new_start == 21
    assert hunks[1].new_length == 5
    assert hunks[1].start_line == 21
    assert hunks[1].end_line == 25  # 21 + 5 - 1


def test_parse_hunk_changes_ids(sample_hunk_diff: str) -> None:
    """Test that hunks have unique sequential IDs."""
    hunks = parse_hunk_changes(sample_hunk_diff)

    assert hunks[0].id == "0"
    assert hunks[1].id == "1"


def test_parse_hunk_changes_diff_content(sample_hunk_diff: str) -> None:
    """Test that hunk diff content is preserved."""
    hunks = parse_hunk_changes(sample_hunk_diff)

    # Check that diff content includes the hunk header
    assert hunks[0].diff_content.startswith("@@ -5,7 +5,8 @@")
    assert "New version" in hunks[0].diff_content
    assert "Extra line" in hunks[0].diff_content

    assert hunks[1].diff_content.startswith("@@ -20,3 +21,5 @@")
    assert "New comment" in hunks[1].diff_content


def test_parse_hunk_changes_empty() -> None:
    """Test parsing empty diff for hunks."""
    hunks = parse_hunk_changes("")
    assert len(hunks) == 0


def test_get_file_hunks(sample_hunk_diff: str) -> None:
    """Test extracting hunks for a specific file."""
    # Add another file to the diff
    multi_file_diff = (
        sample_hunk_diff
        + """
diff --git a/other.py b/other.py
index 1111111..2222222 100644
--- a/other.py
+++ b/other.py
@@ -1,2 +1,3 @@ def other():
     pass
+    return None
"""
    )

    # Get hunks for module.py only
    module_hunks = get_file_hunks("module.py", multi_file_diff)
    assert len(module_hunks) == 2
    assert all(h.file_path == "module.py" for h in module_hunks)

    # Get hunks for other.py
    other_hunks = get_file_hunks("other.py", multi_file_diff)
    assert len(other_hunks) == 1
    assert other_hunks[0].file_path == "other.py"

    # Get hunks for non-existent file
    no_hunks = get_file_hunks("nonexistent.py", multi_file_diff)
    assert len(no_hunks) == 0


def test_parse_single_line_hunk() -> None:
    """Test parsing hunk with single line change."""
    single_line_diff = """diff --git a/test.py b/test.py
index 1234567..abcdefg 100644
--- a/test.py
+++ b/test.py
@@ -10 +10 @@ def func():
-    old
+    new
"""

    hunks = parse_hunk_changes(single_line_diff)
    assert len(hunks) == 1
    assert hunks[0].original_start == 10
    assert hunks[0].original_length == 1
    assert hunks[0].new_start == 10
    assert hunks[0].new_length == 1


def test_parse_renamed_file() -> None:
    """Test parsing renamed file."""
    rename_diff = """diff --git a/old_name.py b/new_name.py
similarity index 100%
rename from old_name.py
rename to new_name.py
index 1234567..abcdefg 100644
--- a/old_name.py
+++ b/new_name.py
@@ -1,2 +1,2 @@
 def function():
-    old
+    new
"""

    changes = parse_file_changes(rename_diff)
    assert len(changes) == 1
    assert changes[0].file_path == "new_name.py"
    assert changes[0].change_type == "renamed"


def test_parse_file_changes_status() -> None:
    """Test that all parsed changes start with UNKNOWN status."""
    diff = """diff --git a/file.py b/file.py
index 1234567..abcdefg 100644
--- a/file.py
+++ b/file.py
@@ -1,2 +1,2 @@
-old
+new
"""

    changes = parse_file_changes(diff)
    assert all(c.status == ChangeStatus.UNKNOWN for c in changes)

    hunks = parse_hunk_changes(diff)
    assert all(h.status == ChangeStatus.UNKNOWN for h in hunks)


def test_parse_complex_diff() -> None:
    """Test parsing diff with multiple files and various change types."""
    complex_diff = """diff --git a/added.py b/added.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/added.py
@@ -0,0 +1,3 @@
+def new():
+    pass
+
diff --git a/modified.py b/modified.py
index abcdefg..9876543 100644
--- a/modified.py
+++ b/modified.py
@@ -5,3 +5,4 @@ def func():
     x = 1
     y = 2
+    z = 3

diff --git a/deleted.py b/deleted.py
deleted file mode 100644
index 1111111..0000000
--- a/deleted.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def old():
-    pass
"""

    changes = parse_file_changes(complex_diff)
    assert len(changes) == 3

    # Check change types
    assert changes[0].change_type == "added"
    assert changes[0].file_path == "added.py"

    assert changes[1].change_type == "modified"
    assert changes[1].file_path == "modified.py"

    assert changes[2].change_type == "deleted"
    assert changes[2].file_path == "deleted.py"
