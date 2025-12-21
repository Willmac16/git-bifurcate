"""Shared pytest fixtures for git-bifurcate tests."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def git_repo(temp_dir: Path) -> Path:
    """Create a temporary git repository."""
    repo_path = temp_dir / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
    subprocess.run(
        ["git", "init"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Configure git
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Disable GPG and SSH signing for tests
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "gpg.format", "openpgp"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    return repo_path


@pytest.fixture
def sample_diff() -> str:
    """Sample git diff output for testing."""
    return """diff --git a/file1.py b/file1.py
index 1234567..abcdefg 100644
--- a/file1.py
+++ b/file1.py
@@ -1,5 +1,6 @@
 def hello():
-    print("Hello")
+    print("Hello World")
+    print("New line")
     return True

 def goodbye():
diff --git a/file2.py b/file2.py
new file mode 100644
index 0000000..9876543
--- /dev/null
+++ b/file2.py
@@ -0,0 +1,3 @@
+def new_function():
+    print("This is new")
+    return 42
diff --git a/file3.py b/file3.py
deleted file mode 100644
index abcdefg..0000000
--- a/file3.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def old_function():
-    pass
"""


@pytest.fixture
def sample_hunk_diff() -> str:
    """Sample diff with multiple hunks in one file."""
    return """diff --git a/module.py b/module.py
index 1234567..abcdefg 100644
--- a/module.py
+++ b/module.py
@@ -5,7 +5,8 @@ import os
 def function1():
-    print("Old version")
+    print("New version")
+    print("Extra line")
     return True

@@ -20,3 +21,5 @@ def function2():
     result = calculate()
     return result
+
+# New comment
"""


@pytest.fixture
def change_to_original_dir() -> Generator[None, None, None]:
    """Fixture to ensure tests return to original directory."""
    original_dir = os.getcwd()
    yield
    os.chdir(original_dir)
