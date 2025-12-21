# Implementation Roadmap

Step-by-step guide for implementing git-bifurcate.

## Phase 1: MVP (Minimum Viable Product)

**Goal**: Working file-level bifurcation with automated testing.

**Target**: A user can run `git bifurcate start <commit> --test "npm test"` and find which file contains the breaking change.

### Step 1.1: Project Setup

**Choose Language**: Recommend Python for MVP (fast iteration, good git libraries)

```bash
# Initialize project
mkdir -p src/git_bifurcate
touch src/git_bifurcate/__init__.py
touch src/git_bifurcate/cli.py
touch src/git_bifurcate/core.py
touch src/git_bifurcate/git_ops.py
touch setup.py
touch requirements.txt

# Dependencies
# - GitPython (git operations)
# - click or argparse (CLI)
# - pytest (testing)
```

**Files to create:**
- `src/git_bifurcate/cli.py` - CLI entry point
- `src/git_bifurcate/core.py` - Bifurcation engine
- `src/git_bifurcate/git_ops.py` - Git operations wrapper
- `src/git_bifurcate/models.py` - Data models (Change, State)
- `setup.py` - Package installation
- `requirements.txt` - Dependencies

### Step 1.2: Git Operations Layer

Implement basic git operations:

```python
# git_ops.py

def get_commit_diff(commit_sha: str, parent_sha: str) -> str:
    """Get diff between commit and parent"""
    pass

def get_parent_commit(commit_sha: str) -> str:
    """Get parent of commit"""
    pass

def checkout_commit(commit_sha: str):
    """Checkout specific commit"""
    pass

def create_temp_branch(name: str, base_commit: str):
    """Create temporary branch"""
    pass

def apply_patch(patch: str) -> bool:
    """Apply patch to working directory. Returns True if successful."""
    pass

def reset_hard(commit: str):
    """Reset to commit"""
    pass
```

**Test**: Write unit tests using a test git repository.

### Step 1.3: File-Level Diff Parser

Parse diff output to extract changed files:

```python
# parser.py

def parse_diff_files(diff_text: str) -> List[FileChange]:
    """
    Parse git diff output to extract file-level changes

    Returns list of FileChange objects, one per file
    """
    files = []
    current_file = None

    for line in diff_text.split('\n'):
        if line.startswith('diff --git'):
            if current_file:
                files.append(current_file)
            current_file = FileChange.from_diff_header(line)
        elif current_file:
            current_file.add_diff_line(line)

    if current_file:
        files.append(current_file)

    return files
```

**Test**: Parse various diff formats (new files, deleted files, renamed files, modified files).

### Step 1.4: Data Models

```python
# models.py

@dataclass
class FileChange:
    id: str
    file_path: str
    change_type: str  # 'modified', 'added', 'deleted', 'renamed'
    diff_content: str
    status: str = 'unknown'  # 'unknown', 'good', 'bad', 'skip'

    def to_dict(self) -> dict:
        pass

    @classmethod
    def from_dict(cls, data: dict) -> 'FileChange':
        pass

@dataclass
class BifurcationState:
    commit_sha: str
    parent_sha: str
    test_command: str
    changes: List[FileChange]
    search_space: List[int]  # Indices of changes being tested
    tested_combinations: Dict[str, str]  # "1,2,3" -> "pass"/"fail"/"skip"
    found_breaking: List[int]

    def save(self, filepath: str = '.git/bifurcate-state.json'):
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, filepath: str = '.git/bifurcate-state.json') -> 'BifurcationState':
        with open(filepath) as f:
            return cls.from_dict(json.load(f))
```

### Step 1.5: Change Application

Apply subset of file changes:

```python
# change_applier.py

def apply_file_changes(changes: List[FileChange], base_commit: str) -> bool:
    """
    Apply selected file changes starting from base_commit

    Returns True if successful, False if conflicts/errors
    """
    # Create temporary branch
    branch_name = f"bifurcate-temp-{uuid.uuid4().hex[:8]}"
    create_temp_branch(branch_name, base_commit)

    # Create combined patch
    combined_patch = '\n'.join(change.diff_content for change in changes)

    # Try to apply
    success = apply_patch(combined_patch)

    if not success:
        # Revert
        checkout_commit(base_commit)
        delete_branch(branch_name)
        return False

    return True
```

### Step 1.6: Test Runner

```python
# test_runner.py

def run_test(command: str, timeout: int = 300) -> TestResult:
    """
    Run test command and return result
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            timeout=timeout,
            text=True
        )

        if result.returncode == 0:
            return TestResult.PASS
        else:
            return TestResult.FAIL

    except subprocess.TimeoutExpired:
        return TestResult.ERROR
    except Exception as e:
        return TestResult.ERROR

class TestResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"
```

### Step 1.7: Binary Search Engine

```python
# bisect_engine.py

def bifurcate_files(
    changes: List[FileChange],
    test_command: str,
    base_commit: str
) -> Optional[FileChange]:
    """
    Binary search through file changes to find breaking change
    """
    search_space = list(range(len(changes)))

    while len(search_space) > 1:
        mid = len(search_space) // 2
        lower_half = search_space[:mid]
        upper_half = search_space[mid:]

        # Test lower half
        lower_changes = [changes[i] for i in lower_half]
        result = test_changes(lower_changes, test_command, base_commit)

        if result == TestResult.FAIL:
            search_space = lower_half
        elif result == TestResult.PASS:
            # Problem is in upper half
            search_space = upper_half
        else:
            # Skip - try different approach
            # For MVP, just try upper half
            search_space = upper_half

    if len(search_space) == 1:
        return changes[search_space[0]]

    return None

def test_changes(
    changes: List[FileChange],
    test_command: str,
    base_commit: str
) -> TestResult:
    """Apply changes and run test"""
    if not apply_file_changes(changes, base_commit):
        return TestResult.SKIP

    return run_test(test_command)
```

### Step 1.8: CLI Interface

```python
# cli.py

import click

@click.group()
def cli():
    """git-bifurcate: Find breaking changes within a commit"""
    pass

@cli.command()
@click.argument('commit')
@click.option('--test', '-t', required=True, help='Test command to run')
def start(commit: str, test: str):
    """Start bifurcating a commit"""

    # Get commit info
    parent = get_parent_commit(commit)
    diff = get_commit_diff(commit, parent)

    # Parse changes
    changes = parse_diff_files(diff)

    print(f"Bifurcating commit {commit[:7]}")
    print(f"Found {len(changes)} file changes")

    # Create initial state
    state = BifurcationState(
        commit_sha=commit,
        parent_sha=parent,
        test_command=test,
        changes=changes,
        search_space=list(range(len(changes))),
        tested_combinations={},
        found_breaking=[]
    )

    # Save state
    state.save()

    # Run bifurcation
    print("\nStarting automated bifurcation...")
    result = bifurcate_files(changes, test, parent)

    if result:
        print(f"\nFound breaking change:")
        print(f"  File: {result.file_path}")
        print(f"  Type: {result.change_type}")
    else:
        print("\nCould not isolate single breaking change")

@cli.command()
def status():
    """Show bifurcation status"""
    state = BifurcationState.load()

    print(f"Commit: {state.commit_sha[:7]}")
    print(f"Files: {len(state.changes)}")
    print(f"Search space: {len(state.search_space)}")
    print(f"Tests run: {len(state.tested_combinations)}")

@cli.command()
def reset():
    """Abort bifurcation and clean up"""
    # Delete state file
    # Cleanup temp branches
    print("Bifurcation reset")

if __name__ == '__main__':
    cli()
```

### Step 1.9: Installation

```python
# setup.py

from setuptools import setup, find_packages

setup(
    name='git-bifurcate',
    version='0.1.0',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    install_requires=[
        'GitPython>=3.1.0',
        'click>=8.0.0',
    ],
    entry_points={
        'console_scripts': [
            'git-bifurcate=git_bifurcate.cli:cli',
        ],
    },
)
```

### Step 1.10: Testing the MVP

Create test repositories:

```bash
# Create test repo
mkdir test-repo-1
cd test-repo-1
git init

# Create initial working state
echo "def add(a, b): return a + b" > math.py
echo "def sub(a, b): return a - b" > math.py
echo "def mul(a, b): return a * b" > math.py
git add math.py
git commit -m "Initial commit"

# Create test file
echo "from math import *\nassert add(1,2)==3" > test.py
git add test.py
git commit -m "Add test"

# Create bad commit with multiple file changes
echo "def add(a, b): return a - b" > math.py  # BUG HERE
echo "def div(a, b): return a / b" > math2.py
echo "# comment" > utils.py
git add .
git commit -m "Bad commit"

# Now test bifurcate
cd ..
git-bifurcate start HEAD --test "python test.py"

# Expected: Should find math.py as breaking file
```

### Step 1.11: MVP Completion Checklist

- [ ] Can parse file-level changes from commit
- [ ] Can apply subset of changes
- [ ] Can run test command and capture result
- [ ] Binary search finds breaking file
- [ ] State persists to .git/bifurcate-state.json
- [ ] CLI is usable
- [ ] Works on test repository
- [ ] Handles errors gracefully (bad commit sha, bad test command, etc.)

## Phase 2: Hunk-Level Support

**Goal**: Drill down to specific hunks within files.

### Step 2.1: Hunk Parser

Extend diff parser to extract hunks:

```python
# parser.py

def parse_diff_hunks(diff_text: str) -> List[HunkChange]:
    """
    Parse git diff to extract individual hunks
    """
    hunks = []
    current_file = None
    current_hunk = None

    for line in diff_text.split('\n'):
        if line.startswith('diff --git'):
            current_file = extract_filename(line)

        elif line.startswith('@@'):
            if current_hunk:
                hunks.append(current_hunk)

            # Parse hunk header: @@ -45,7 +45,8 @@
            current_hunk = HunkChange.from_header(line, current_file)

        elif current_hunk:
            current_hunk.add_line(line)

    if current_hunk:
        hunks.append(current_hunk)

    return hunks
```

### Step 2.2: Hunk Change Model

```python
@dataclass
class HunkChange:
    id: str
    file_path: str
    start_line: int
    end_line: int
    original_start: int
    original_length: int
    new_start: int
    new_length: int
    diff_content: str
    status: str = 'unknown'
```

### Step 2.3: Hunk Application

Applying subset of hunks is trickier than files:

```python
def apply_hunks(hunks: List[HunkChange], base_commit: str) -> bool:
    """
    Apply selected hunks

    Challenge: Line numbers shift when you apply earlier hunks
    Solution: Apply hunks in order, track line number shifts
    """
    # Group hunks by file
    hunks_by_file = group_by_file(hunks)

    for file_path, file_hunks in hunks_by_file.items():
        # Sort hunks by line number
        file_hunks.sort(key=lambda h: h.start_line)

        # Apply hunks with line number adjustment
        apply_hunks_to_file(file_path, file_hunks)
```

### Step 2.4: Hybrid Strategy

```python
def bifurcate_hybrid(changes, test_command, base_commit):
    """
    File-level first, then hunk-level
    """
    # Parse files
    files = parse_diff_files(get_diff())

    # Find breaking file
    breaking_file = bifurcate_files(files, test_command, base_commit)

    if not breaking_file:
        return None

    print(f"Breaking change is in {breaking_file.file_path}")
    print("Drilling down to hunk level...")

    # Parse hunks for that file
    hunks = parse_hunks_for_file(breaking_file.file_path, get_diff())

    # Find breaking hunk
    breaking_hunk = bifurcate_hunks(hunks, test_command, base_commit)

    return breaking_hunk
```

## Phase 3: Robustness

### Step 3.1: Better Error Handling

- Distinguish test failures from test errors
- Handle build failures (code won't compile)
- Timeout for long-running tests
- Better error messages

### Step 3.2: Manual Mode

```python
@cli.command()
@click.option('--half', type=click.Choice(['upper', 'lower']))
def apply_half(half: str):
    """Apply half of remaining changes"""
    state = BifurcationState.load()

    mid = len(state.search_space) // 2

    if half == 'lower':
        indices = state.search_space[:mid]
    else:
        indices = state.search_space[mid:]

    changes = [state.changes[i] for i in indices]
    apply_file_changes(changes, state.parent_sha)

    # Save current selection
    state.current_selection = indices
    state.save()

    print(f"Applied changes: {indices}")
    print("Run your tests, then mark as good/bad")

@cli.command()
@click.argument('result', type=click.Choice(['good', 'bad', 'skip']))
def mark(result: str):
    """Mark current changes as good/bad/skip"""
    state = BifurcationState.load()

    if result == 'bad':
        state.search_space = state.current_selection
    else:
        # Remove current selection from search space
        state.search_space = [i for i in state.search_space
                             if i not in state.current_selection]

    state.save()
```

### Step 3.3: Skip Handling

When combination won't build:

```python
def bifurcate_with_skip(changes, test_command, base_commit):
    """
    Binary search with skip handling
    """
    search_space = list(range(len(changes)))
    max_skips = len(changes) // 2  # Don't allow too many skips
    skip_count = 0

    while len(search_space) > 1:
        # ... standard binary search ...

        result = test_changes(changes_subset, test_command, base_commit)

        if result == TestResult.SKIP:
            skip_count += 1

            if skip_count > max_skips:
                print("Too many build failures.")
                print("Possible dependency issues.")
                print("Try:")
                print("  1. Manual mode")
                print("  2. File-level only strategy")
                return None

            # Try different split
            # ... alternative strategy ...
```

## Phase 4: Advanced Features

### Step 4.1: Multiple Breaking Changes

```python
def find_all_breaking(changes, test_command, base_commit):
    """Find all breaking changes, not just first one"""
    all_breaking = []
    remaining = changes.copy()

    while remaining:
        breaking = bifurcate_files(remaining, test_command, base_commit)

        if not breaking:
            break

        all_breaking.append(breaking)

        # Remove from remaining
        remaining.remove(breaking)

        print(f"Found breaking change {len(all_breaking)}: {breaking.file_path}")

        if not click.confirm("Continue searching for more?"):
            break

    return all_breaking
```

### Step 4.2: Parallel Testing

```python
def parallel_test_with_worktrees(change_sets, test_command, base_commit):
    """Test multiple change sets in parallel using worktrees"""

    import concurrent.futures
    import tempfile

    results = {}
    worktree_paths = []

    # Create worktrees
    for i, changes in enumerate(change_sets):
        worktree_path = tempfile.mkdtemp(prefix=f'bifurcate-wt-{i}-')
        create_worktree(worktree_path, base_commit)
        worktree_paths.append(worktree_path)

        # Apply changes in worktree
        with WorkingDirectory(worktree_path):
            apply_file_changes(changes, base_commit)

    # Run tests in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}

        for i, worktree_path in enumerate(worktree_paths):
            future = executor.submit(run_test_in_dir, worktree_path, test_command)
            futures[future] = change_sets[i]

        for future in concurrent.futures.as_completed(futures):
            changes = futures[future]
            results[changes] = future.result()

    # Cleanup
    for worktree_path in worktree_paths:
        remove_worktree(worktree_path)

    return results
```

## Testing Strategy

### Unit Tests

```python
# tests/test_parser.py

def test_parse_single_file():
    diff = """
diff --git a/test.py b/test.py
index abc123..def456 100644
--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
 def foo():
-    return 1
+    return 2
"""
    files = parse_diff_files(diff)
    assert len(files) == 1
    assert files[0].file_path == 'test.py'

def test_parse_multiple_files():
    # ...

def test_parse_new_file():
    # ...

def test_parse_deleted_file():
    # ...
```

### Integration Tests

```python
# tests/test_integration.py

def test_simple_bifurcation(test_repo):
    """
    Test repo has 3 file changes, file 2 breaks tests
    Should find file 2 in ceil(log2(3)) = 2 iterations
    """
    result = run_bifurcate(test_repo, 'pytest')

    assert result.breaking_file == 'file2.py'
    assert result.iterations <= 2

def test_hunk_level_bifurcation(test_repo):
    # ...
```

### Fixture Repositories

Create in `tests/fixtures/`:

```bash
# tests/fixtures/simple/setup.sh

git init
echo "pass" > file1.py
echo "pass" > file2.py
echo "pass" > file3.py
git add .
git commit -m "Base"

# Modify all three, but only file2 breaks
echo "pass" > file1.py
echo "FAIL" > file2.py  # This breaks
echo "pass" > file3.py
git add .
git commit -m "Bad commit"
```

## Metrics and Success Criteria

### Performance Metrics

- **Iterations**: Should be O(log n) for n changes
- **Speed**: Each iteration should be fast (depends on test suite)
- **Accuracy**: Should find the actual breaking change

### Usability Metrics

- **Error Rate**: How often does automated mode fail?
- **Skip Rate**: How often are combinations unbuildable?
- **User Satisfaction**: Is the tool helpful?

## Next Steps After MVP

1. **Real-world Testing**: Use on actual codebases
2. **User Feedback**: What features are most valuable?
3. **Performance Optimization**: Caching, parallel testing
4. **Language Ports**: Consider Rust for performance/distribution
5. **IDE Integration**: VSCode extension, IntelliJ plugin
6. **CI/CD Integration**: Run automatically when tests fail
