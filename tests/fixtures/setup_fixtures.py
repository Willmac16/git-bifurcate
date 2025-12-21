#!/usr/bin/env python3
"""Setup script to create test fixture repositories.

Each fixture is a real git repository with a known breaking change
that git-bifurcate should be able to find.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def run_git(cmd: list[str], cwd: Path) -> None:
    """Run git command in directory."""
    subprocess.run(["git"] + cmd, cwd=cwd, check=True, capture_output=True)


def setup_simple_file_fixture(fixtures_dir: Path) -> None:
    """Create simple fixture: 4 files modified, file 2 breaks tests.

    This tests basic file-level bifurcation.
    """
    repo_path = fixtures_dir / "simple-file-break"
    if repo_path.exists():
        shutil.rmtree(repo_path)
    repo_path.mkdir(parents=True)

    # Initialize repo
    run_git(["init"], repo_path)
    run_git(["config", "user.name", "Test User"], repo_path)
    run_git(["config", "user.email", "test@example.com"], repo_path)
    run_git(["config", "commit.gpgsign", "false"], repo_path)

    # Create initial files - one file per value
    (repo_path / "test.sh").write_text("""#!/bin/bash
set -e

python3 -c "from module1 import value1; assert value1 >= 1"
python3 -c "from module2 import value2; assert value2 == 2"
python3 -c "from module3 import value3; assert value3 >= 3"
python3 -c "from module4 import value4; assert value4 >= 4"

echo "All tests passed!"
""")
    (repo_path / "test.sh").chmod(0o755)

    (repo_path / "module1.py").write_text("value1 = 1\n")
    (repo_path / "module2.py").write_text("value2 = 2\n")
    (repo_path / "module3.py").write_text("value3 = 3\n")
    (repo_path / "module4.py").write_text("value4 = 4\n")

    run_git(["add", "."], repo_path)
    run_git(["commit", "-m", "Initial working version"], repo_path)

    # Store parent SHA
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    parent_sha = result.stdout.strip()

    # Modify all 4 files, but only module2 breaks
    (repo_path / "module1.py").write_text("# Updated\nvalue1 = 10\n")
    (repo_path / "module2.py").write_text("# BROKEN\nvalue2 = 99\n")
    (repo_path / "module3.py").write_text("# Updated\nvalue3 = 30\n")
    (repo_path / "module4.py").write_text("# Updated\nvalue4 = 40\n")

    run_git(["add", "."], repo_path)
    run_git(["commit", "-m", "Modify all 4 files (module2 breaks tests)"], repo_path)

    # Get bad commit SHA
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    bad_sha = result.stdout.strip()

    # Write metadata file
    (repo_path / "FIXTURE_INFO.md").write_text(f"""# Simple File Break Fixture

## Description
Four files (module1-4.py) are modified. Only module2.py breaks the test.

## Expected Result
File-level bifurcation should identify `module2.py` as the breaking file.

## Commits
- Parent (good): {parent_sha}
- Bad commit: {bad_sha}

## Test Command
```bash
bash test.sh
```

## Breaking Change
File: `module2.py`
Line: `value2 = 99`
Expected: `value2 = 2`
""")

    # Commit the metadata file
    run_git(["add", "FIXTURE_INFO.md"], repo_path)
    run_git(["commit", "-m", "Add fixture metadata"], repo_path)

    # Tag the metadata commit for easy reset
    run_git(["tag", "-f", "fixture-head"], repo_path)


def setup_multiple_files_fixture(fixtures_dir: Path) -> None:
    """Create fixture: 5 files modified, file 3 breaks tests.

    Tests binary search efficiency with more files.
    """
    repo_path = fixtures_dir / "multiple-files-break"
    if repo_path.exists():
        shutil.rmtree(repo_path)
    repo_path.mkdir(parents=True)

    # Initialize repo
    run_git(["init"], repo_path)
    run_git(["config", "user.name", "Test User"], repo_path)
    run_git(["config", "user.email", "test@example.com"], repo_path)
    run_git(["config", "commit.gpgsign", "false"], repo_path)

    # Create initial files
    (repo_path / "test.sh").write_text("""#!/bin/bash
set -e

python3 -c "from file1 import func1; assert func1() == 'file1', 'file1 failed'"
python3 -c "from file2 import func2; assert func2() == 'file2', 'file2 failed'"
python3 -c "from file3 import func3; assert func3() == 'file3', 'file3 failed'"
python3 -c "from file4 import func4; assert func4() == 'file4', 'file4 failed'"
python3 -c "from file5 import func5; assert func5() == 'file5', 'file5 failed'"

echo "All tests passed!"
""")
    (repo_path / "test.sh").chmod(0o755)

    for i in range(1, 6):
        (repo_path / f"file{i}.py").write_text(f'def func{i}():\n    return "file{i}"\n')

    run_git(["add", "."], repo_path)
    run_git(["commit", "-m", "Initial version"], repo_path)

    parent_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    parent_sha = parent_result.stdout.strip()

    # Modify all files, but file3 breaks
    for i in range(1, 6):
        if i == 3:
            (repo_path / f"file{i}.py").write_text(f'def func{i}():\n    return "BROKEN"\n')
        else:
            (repo_path / f"file{i}.py").write_text(
                f'def func{i}():\n    # Modified\n    return "file{i}"\n'
            )

    run_git(["add", "."], repo_path)
    run_git(["commit", "-m", "Modify all files (file3 breaks)"], repo_path)

    bad_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    bad_sha = bad_result.stdout.strip()

    (repo_path / "FIXTURE_INFO.md").write_text(f"""# Multiple Files Break Fixture

## Description
5 files modified, file3.py contains breaking change.

## Expected Result
Binary search should find file3.py in ~3 iterations instead of 5 linear.

## Commits
- Parent (good): {parent_sha}
- Bad commit: {bad_sha}

## Test Command
```bash
bash test.sh
```

## Breaking Change
File: `file3.py`
Line: `return "BROKEN"`
Expected: `return "file3"`
""")

    # Commit the metadata file
    run_git(["add", "FIXTURE_INFO.md"], repo_path)
    run_git(["commit", "-m", "Add fixture metadata"], repo_path)

    # Tag the metadata commit for easy reset
    run_git(["tag", "-f", "fixture-head"], repo_path)


def setup_hunk_level_fixture(fixtures_dir: Path) -> None:
    """Create fixture: Single file, multiple hunks, one hunk breaks.

    Tests hunk-level bifurcation.
    """
    repo_path = fixtures_dir / "single-hunk-break"
    if repo_path.exists():
        shutil.rmtree(repo_path)
    repo_path.mkdir(parents=True)

    # Initialize repo
    run_git(["init"], repo_path)
    run_git(["config", "user.name", "Test User"], repo_path)
    run_git(["config", "user.email", "test@example.com"], repo_path)
    run_git(["config", "commit.gpgsign", "false"], repo_path)

    # Create initial file with lots of spacing to create separate hunks
    (repo_path / "calculator.py").write_text("""def add(a, b):
    return a + b


# ============================================================
# Subtraction operations
# ============================================================


def subtract(a, b):
    return a - b


# ============================================================
# Multiplication operations
# ============================================================


def multiply(a, b):
    return a * b


# ============================================================
# Division operations
# ============================================================


def divide(a, b):
    return a / b
""")

    (repo_path / "test.py").write_text("""#!/usr/bin/env python3
from calculator import add, subtract, multiply, divide

assert add(2, 3) == 5, "add failed"
assert subtract(5, 3) == 2, "subtract failed"
assert multiply(4, 3) == 12, "multiply failed"
assert divide(10, 2) == 5, "divide failed"

print("All tests passed!")
""")

    run_git(["add", "."], repo_path)
    run_git(["commit", "-m", "Initial calculator"], repo_path)

    parent_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    parent_sha = parent_result.stdout.strip()

    # Modify all functions, but multiply has bug
    (repo_path / "calculator.py").write_text("""def add(a, b):
    # Updated implementation
    result = a + b
    return result


# ============================================================
# Subtraction operations
# ============================================================


def subtract(a, b):
    # Updated implementation
    result = a - b
    return result


# ============================================================
# Multiplication operations
# ============================================================


def multiply(a, b):
    # BUGGY implementation
    result = a + b  # Oops, should be a * b
    return result


# ============================================================
# Division operations
# ============================================================


def divide(a, b):
    # Updated implementation
    if b == 0:
        raise ValueError("Cannot divide by zero")
    result = a / b
    return result
""")

    run_git(["add", "calculator.py"], repo_path)
    run_git(["commit", "-m", "Refactor all functions (multiply has bug)"], repo_path)

    bad_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    bad_sha = bad_result.stdout.strip()

    (repo_path / "FIXTURE_INFO.md").write_text(f"""# Single Hunk Break Fixture

## Description
Single file with 4 functions modified. The multiply() function has a bug.

## Expected Result
Hunk-level bifurcation should identify the specific hunk (multiply function).

## Commits
- Parent (good): {parent_sha}
- Bad commit: {bad_sha}

## Test Command
```bash
python3 test.py
```

## Breaking Change
Function: `multiply(a, b)`
Line: `result = a + b  # Oops, should be a * b`
Expected: `result = a * b`
""")

    # Commit the metadata file
    run_git(["add", "FIXTURE_INFO.md"], repo_path)
    run_git(["commit", "-m", "Add fixture metadata"], repo_path)

    # Tag the metadata commit for easy reset
    run_git(["tag", "-f", "fixture-head"], repo_path)


def main() -> None:
    """Setup all test fixtures."""
    fixtures_dir = Path(__file__).parent

    print("Creating test fixtures...")

    print("  1. simple-file-break")
    setup_simple_file_fixture(fixtures_dir)

    print("  2. multiple-files-break")
    setup_multiple_files_fixture(fixtures_dir)

    print("  3. single-hunk-break")
    setup_hunk_level_fixture(fixtures_dir)

    print("\nFixtures created successfully!")
    print(f"Location: {fixtures_dir}")

    # List created fixtures
    print("\nCreated fixtures:")
    for fixture in sorted(fixtures_dir.iterdir()):
        if fixture.is_dir() and fixture.name != "__pycache__":
            info_file = fixture / "FIXTURE_INFO.md"
            if info_file.exists():
                first_line = info_file.read_text().split("\n")[0]
                print(f"  - {fixture.name}: {first_line.replace('# ', '')}")


if __name__ == "__main__":
    main()
