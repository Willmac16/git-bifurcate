# Architecture & Implementation Details

**Language:** Python 3.12+
**Test Coverage:** 99.9%
**Lines of Code:** ~3,900 (src) + ~9,100 (tests)

## System Architecture (As Implemented)

```
┌─────────────────────────────────────────────────────────────┐
│                  CLI Interface Layer (cli.py)                │
│         Click framework - command routing, progress          │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│              Core Bifurcation Engine (core.py)               │
│  - BifurcationEngine class                                   │
│  - Binary search for files and hunks                         │
│  - Test result caching                                       │
│  - Statistics and time estimation                            │
└──────┬────────────────┬────────────────────┬────────────────┘
       │                │                    │
       │                │                    │
┌──────▼────────┐ ┌─────▼──────────┐ ┌──────▼────────────────┐
│ Dependency    │ │   Commit       │ │   Change Management   │
│ Analysis      │ │   Bisection    │ │   (parser.py,         │
│ - dependency_ │ │   (commit_     │ │    models.py)         │
│   analyzer.py │ │    bisect.py)  │ │   - FileChange        │
│ - dependency_ │ │   - Bisect     │ │   - HunkChange        │
│   graph.py    │ │     commits    │ │   - Diff parsing      │
│ - Multi-lang  │ │   - Integrate  │ │                       │
│   static      │ │     with       │ │                       │
│   analysis    │ │     bifurcate  │ │                       │
└───────────────┘ └────────────────┘ └───────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│           Git Operations Layer (git_ops.py)                  │
│  - GitRepo class (wraps GitPython)                           │
│  - Patch application, commit operations                      │
│  - Submodule support                                         │
│  - Temporary branch management                               │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│           Test Execution Layer (test_runner.py)              │
│  - CommandRunner class                                       │
│  - Subprocess execution with timeout                         │
└──────────────────────────────────────────────────────────────┘
```

## Core Data Models (Python)

### FileChange and HunkChange

Represents individual changes:

```python
@dataclass
class FileChange:
    """Represents a file-level change"""
    file_path: str
    change_type: str  # 'added', 'modified', 'deleted'
    diff: str
    is_submodule: bool = False
    submodule_commits: tuple[str, str] | None = None

@dataclass
class HunkChange:
    """Represents a hunk-level change"""
    file_path: str
    hunk_index: int
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]
    header: str
```

### BifurcationState

Persistent state for resuming bifurcation:

```python
@dataclass
class BifurcationState:
    """Persistent bifurcation session state"""
    commit_sha: str
    parent_sha: str
    strategy: Strategy
    test_command: str

    # For file-level bifurcation
    file_changes: list[FileChange]
    # For hunk-level bifurcation
    hunk_changes: list[HunkChange] | None

    # Search state
    search_space: list[int]  # Indices still being tested
    tested_combinations: dict[str, CommandResult]
    found_breaking_indices: list[int]

    # Metadata
    working_dir: str
    created_at: str
    analyze_deps: bool

    def to_json(self) -> str: ...
    @classmethod
    def from_json(cls, json_str: str) -> BifurcationState: ...

class Strategy(Enum):
    FILE = "file"
    HUNK = "hunk"
    HYBRID = "hybrid"  # Not yet implemented

class CommandResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
```

## Key Algorithms

### 1. Diff Parsing Algorithm (Actual Implementation)

Parse git diff output into structured changes:

```python
def parse_file_changes(repo: GitRepo, commit_sha: str, parent_sha: str,
                      restrict_paths: list[str] | None = None) -> list[FileChange]:
    """Parse commit diff into file-level changes (parser.py)"""
    diff = repo.get_commit_diff(commit_sha, parent_sha)

    file_changes = []
    for diff_item in diff:
        # Check if path matches restriction
        if restrict_paths and not matches_any_path(diff_item.a_path, restrict_paths):
            continue

        # Handle submodule changes
        if diff_item.a_blob and diff_item.a_blob.mode == 0o160000:
            file_changes.append(FileChange(
                file_path=diff_item.a_path,
                change_type="modified",
                diff=str(diff_item),
                is_submodule=True,
                submodule_commits=(diff_item.a_blob.hexsha, diff_item.b_blob.hexsha)
            ))
        else:
            file_changes.append(FileChange(
                file_path=diff_item.a_path or diff_item.b_path,
                change_type=get_change_type(diff_item),
                diff=str(diff_item),
                is_submodule=False
            ))

    return file_changes

def parse_hunk_changes(file_changes: list[FileChange]) -> list[HunkChange]:
    """Parse file diffs into individual hunks (parser.py)"""
    hunk_changes = []

    for file_change in file_changes:
        hunks = extract_hunks_from_diff(file_change.diff)

        for idx, hunk in enumerate(hunks):
            hunk_changes.append(HunkChange(
                file_path=file_change.file_path,
                hunk_index=idx,
                old_start=hunk.old_start,
                old_count=hunk.old_count,
                new_start=hunk.new_start,
                new_count=hunk.new_count,
                lines=hunk.lines,
                header=hunk.header
            ))

    return hunk_changes
```

### 2. Binary Search Algorithm (Actual Implementation in core.py)

```python
class BifurcationEngine:
    """Core bifurcation engine implementing binary search"""

    def bifurcate_files(self, file_changes: list[FileChange]) -> FileChange | None:
        """Binary search through file-level changes"""
        search_space = list(range(len(file_changes)))

        while len(search_space) > 1:
            mid = len(search_space) // 2
            lower_half = search_space[:mid]
            upper_half = search_space[mid:]

            # Test lower half
            result = self._test_file_subset(lower_half, file_changes)

            if result == CommandResult.FAIL:
                search_space = lower_half
            elif result == CommandResult.PASS:
                search_space = upper_half
            else:  # SKIP
                # Try upper half if lower fails to build
                result_upper = self._test_file_subset(upper_half, file_changes)
                if result_upper == CommandResult.FAIL:
                    search_space = upper_half
                else:
                    # Both halves have issues - may need interaction detection
                    return self._handle_interaction(lower_half, upper_half, file_changes)

        # Found single breaking change
        if search_space:
            return file_changes[search_space[0]]
        return None

    def bifurcate_hunks(self, hunk_changes: list[HunkChange]) -> HunkChange | None:
        """Binary search through hunk-level changes (similar algorithm)"""
        # Similar binary search but reconstructs patches for hunks
        ...

    def _test_file_subset(self, indices: list[int],
                         file_changes: list[FileChange]) -> CommandResult:
        """Test with a subset of file changes"""
        # Check cache first
        cache_key = tuple(sorted(indices))
        if cache_key in self.tested_combinations:
            return self.tested_combinations[cache_key]

        # Apply changes and run test
        selected_changes = [file_changes[i] for i in indices]
        self.git_repo.apply_changes(selected_changes, self.parent_sha)

        result = self.test_runner.run(self.test_command)

        # Cache result
        self.tested_combinations[cache_key] = result
        self.stats.tests_run += 1

        return result
```

### 3. Interaction Detection (Actual Implementation)

When both halves pass individually but fail together:

```python
def _handle_interaction(self, lower_indices: list[int], upper_indices: list[int],
                       changes: list) -> None:
    """Handle cases where changes interact to cause failure (core.py)"""

    # Budget-limited search to avoid exponential complexity
    MAX_COMBINATIONS = 64
    tested = 0

    # Try dependent pairs first (optimization when deps are known)
    if self.dep_graph:
        for i in lower_indices:
            for j in upper_indices:
                if self.dep_graph.are_dependent(i, j):
                    if self._test_subset([i, j], changes) == CommandResult.FAIL:
                        return [changes[i], changes[j]]
                    tested += 1
                    if tested >= MAX_COMBINATIONS:
                        break

    # Try all size-2 combinations
    for i in lower_indices:
        for j in upper_indices:
            if tested >= MAX_COMBINATIONS:
                break
            if self._test_subset([i, j], changes) == CommandResult.FAIL:
                return [changes[i], changes[j]]
            tested += 1

    # If still not found, try size-3, size-4, etc.
    # (with combinatorial budget limits)

    # Give up and report all possibilities
    click.echo("Could not isolate to a single change or simple interaction.")
    click.echo(f"Possible breaking changes: {lower_indices + upper_indices}")
    return None
```

### 4. Change Application

Apply a subset of changes to the working directory:

```python
def apply_changes(changes, base_commit, strategy='temp-commit'):
    """
    Apply selected changes starting from base_commit
    """
    if strategy == 'temp-commit':
        # Create temporary branch
        temp_branch = f"bifurcate-temp-{random_id()}"
        run_git(['checkout', '-b', temp_branch, base_commit])

        # Create patch for selected changes
        patch = create_patch_from_changes(changes)

        # Apply patch
        try:
            run_git(['apply', '--index'], input=patch)
            run_git(['commit', '-m', 'Bifurcate temporary commit'])
            return Success()
        except GitApplyError as e:
            # Conflicts or dependencies missing
            run_git(['checkout', 'HEAD~'])  # Go back
            run_git(['branch', '-D', temp_branch])
            return Failure(reason='conflicts')

    elif strategy == 'patch':
        # Reset to base
        run_git(['reset', '--hard', base_commit])

        # Apply patch without committing
        patch = create_patch_from_changes(changes)
        try:
            run_git(['apply'], input=patch)
            return Success()
        except GitApplyError:
            return Failure(reason='conflicts')
```

## Dependency Detection (Actual Multi-Language Implementation)

### Static Analysis Approach (dependency_analyzer.py)

**Supports:** Python (AST-based), C/C++, Rust, Go, Swift, Zig, Verilog (regex-based)

```python
class DependencyAnalyzer:
    """Multi-language static dependency analysis"""

    def analyze_dependencies(self, changes: list[FileChange | HunkChange],
                           repo_path: str) -> DependencyGraph:
        """Build dependency graph from changes"""
        graph = DependencyGraph()

        # Extract symbols from each change
        symbols_by_change = {}
        for idx, change in enumerate(changes):
            symbols_by_change[idx] = self._extract_symbols(change, repo_path)

        # Detect dependencies between changes
        for i, symbols_i in symbols_by_change.items():
            for j, symbols_j in symbols_by_change.items():
                if i == j:
                    continue

                # Check if j references anything defined in i
                if symbols_j.references & symbols_i.definitions:
                    graph.add_dependency(j, i)  # j depends on i

                # Contextual dependency (proximity in same file)
                if self._are_contextually_dependent(changes[i], changes[j]):
                    graph.add_dependency(j, i)

        return graph

    def _extract_symbols(self, change: FileChange, repo_path: str) -> SymbolInfo:
        """Extract definitions and references from a change"""
        file_ext = Path(change.file_path).suffix

        if file_ext == '.py':
            return self._extract_python_symbols(change)
        elif file_ext in {'.c', '.cpp', '.cc', '.h', '.hpp'}:
            return self._extract_cpp_symbols(change)
        elif file_ext == '.rs':
            return self._extract_rust_symbols(change)
        elif file_ext == '.go':
            return self._extract_go_symbols(change)
        # ... etc for other languages

    def _extract_python_symbols(self, change: FileChange) -> SymbolInfo:
        """AST-based Python symbol extraction"""
        tree = ast.parse(change.diff)

        definitions = set()
        references = set()

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                definitions.add(node.name)
            elif isinstance(node, ast.Name):
                references.add(node.id)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    references.add(alias.name)

        return SymbolInfo(definitions, references)

    def _extract_cpp_symbols(self, change: FileChange) -> SymbolInfo:
        """Regex-based C++ symbol extraction"""
        # Extract function/class definitions
        func_pattern = r'\b(?:void|int|bool|auto|template)\s+(\w+)\s*\('
        class_pattern = r'\bclass\s+(\w+)'

        definitions = set(re.findall(func_pattern, change.diff))
        definitions.update(re.findall(class_pattern, change.diff))

        # Extract references (function calls, includes)
        call_pattern = r'\b(\w+)\s*\('
        include_pattern = r'#include\s+[<"](\w+)'

        references = set(re.findall(call_pattern, change.diff))
        references.update(re.findall(include_pattern, change.diff))

        return SymbolInfo(definitions, references)
```

### Build-Based Approach (Simpler)

Instead of complex static analysis, just track which combinations fail to build:

```python
def test_with_changes(changes, test_command):
    """
    Test with specific changes, detecting build vs test failures
    """
    apply_changes(changes)

    # First try to build
    build_result = run_command(get_build_command())

    if build_result.exit_code != 0:
        # Build failed - likely missing dependencies
        return TestResult.Skip

    # Build succeeded, run tests
    test_result = run_command(test_command)

    if test_result.exit_code == 0:
        return TestResult.Pass
    else:
        return TestResult.Fail
```

## State Persistence

### State File Format

```json
{
  "version": "1.0",
  "commit": "abc123",
  "parent": "def456",
  "strategy": "hybrid",
  "test_command": "npm test",
  "working_dir": null,

  "changes": [
    {
      "id": "0",
      "type": "hunk",
      "file": "src/auth.js",
      "start_line": 45,
      "end_line": 52,
      "diff": "--- a/src/auth.js\n+++ b/src/auth.js\n...",
      "status": "unknown"
    }
  ],

  "search_state": {
    "search_space": [3, 4, 5, 6],
    "tested_combinations": {
      "0,1,2,3,4,5,6,7": "fail",
      "0,1,2,3": "pass",
      "4,5,6,7": "fail",
      "4,5,6": "skip"
    },
    "found_breaking": []
  },

  "metadata": {
    "created_at": "2025-12-20T10:00:00Z",
    "last_updated": "2025-12-20T10:15:00Z",
    "iterations": 12
  }
}
```

### State Management

```python
class StateManager:
    def __init__(self, state_file='.git/bifurcate-state.json'):
        self.state_file = state_file

    def save(self, state: BifurcationState):
        with open(self.state_file, 'w') as f:
            json.dump(state.to_dict(), f, indent=2)

    def load(self) -> BifurcationState:
        if not os.path.exists(self.state_file):
            raise NoStateError()

        with open(self.state_file) as f:
            data = json.load(f)

        return BifurcationState.from_dict(data)

    def clear(self):
        if os.path.exists(self.state_file):
            os.remove(self.state_file)
```

## Testing Infrastructure (Production Quality)

### Test Coverage: 99.9%

**215 test functions** across 13 test files, **9,061 lines of test code**

### Test Organization

```
tests/
├── test_cli.py (1,860 lines)              # CLI interface tests
├── test_git_ops.py (1,716 lines)          # Git operations tests
├── test_core.py (964 lines)               # Core engine tests
├── test_multi_language_dependencies.py    # Multi-language dep tests
├── test_dependency_detection.py           # Dependency detection tests
├── test_dependency_analyzer.py            # Static analysis tests
├── test_models.py                         # Data model tests
├── test_commit_bisect.py                  # Commit bisection tests
├── test_dependency_graph.py               # Graph algorithm tests
├── test_parser.py                         # Diff parser tests
├── test_integration.py                    # End-to-end tests
├── test_test_runner.py                    # Test runner tests
└── conftest.py                            # Shared fixtures
```

### Test Categories

1. **Unit Tests**: Test individual functions and classes in isolation
2. **Integration Tests**: Test full workflows with temporary git repos
3. **Multi-Language Tests**: Verify dependency detection for 7 languages
4. **Edge Case Tests**: Error handling, corrupt state, submodules

### CI/CD Pipeline (GitHub Actions)

**Workflows:**
- `test.yml` - Run tests with 99.9% coverage requirement (Python 3.12, 3.13)
- `lint.yml` - Ruff formatting and linting + type checking
- `build.yml` - Verify package builds correctly
- `release.yml` - Automated releases

**Pre-commit Hooks:**
- Ruff formatter check
- Ruff linter
- Type checker (ty)
- Pytest with coverage check

### Local Testing

```bash
./test                # Run everything (lint + tests + coverage)
./test --lint-only    # Only linting and type checks
./test --test-only    # Only tests with coverage
```

## Performance Optimizations

### 1. Caching Test Results

```python
class TestCache:
    def __init__(self):
        self.cache = {}

    def get(self, change_set):
        key = frozenset(change_set)
        return self.cache.get(key)

    def set(self, change_set, result):
        key = frozenset(change_set)
        self.cache[key] = result
```

### 2. Parallel Testing with Worktrees

```python
def parallel_test(change_sets, test_command):
    """
    Test multiple change sets in parallel using worktrees
    """
    results = {}
    worktrees = []

    for i, change_set in enumerate(change_sets):
        # Create worktree
        worktree_path = f".git/bifurcate-worktree-{i}"
        run_git(['worktree', 'add', worktree_path, base_commit])
        worktrees.append(worktree_path)

        # Apply changes in worktree
        with WorkingDirectory(worktree_path):
            apply_changes(change_set)

    # Run tests in parallel
    with ThreadPoolExecutor(max_workers=cpu_count()) as executor:
        futures = {}
        for i, change_set in enumerate(change_sets):
            future = executor.submit(run_test, worktrees[i], test_command)
            futures[future] = change_set

        for future in as_completed(futures):
            change_set = futures[future]
            results[change_set] = future.result()

    # Cleanup worktrees
    for worktree in worktrees:
        run_git(['worktree', 'remove', worktree])

    return results
```

### 3. Smart Ordering

Test most likely breaking changes first:

```python
def order_changes_by_suspiciousness(changes):
    """
    Heuristics for which changes are more likely to break tests
    """
    scored_changes = []

    for change in changes:
        score = 0

        # Test files are less likely to break production code tests
        if 'test' in change.file_path:
            score -= 10

        # Larger changes more likely to have bugs
        score += len(change.diff_content.split('\n'))

        # Changes to core files
        if 'core' in change.file_path or 'engine' in change.file_path:
            score += 5

        # Changes with keywords
        if 'error' in change.diff_content.lower():
            score += 3
        if 'null' in change.diff_content.lower():
            score += 2

        scored_changes.append((score, change))

    # Sort by score descending
    scored_changes.sort(reverse=True, key=lambda x: x[0])

    return [change for score, change in scored_changes]
```

## Error Recovery

### Handling Stuck States

If bifurcation gets stuck (too many skip results):

```python
def handle_stuck_bifurcation(state):
    """
    Recovery strategies when too many combinations fail to build
    """
    skip_rate = count_skips(state) / state.total_iterations

    if skip_rate > 0.5:
        # More than 50% of tests are skipped

        # Strategy 1: Switch to coarser granularity
        if state.strategy == Strategy.Hunk:
            print("Too many build failures at hunk level.")
            print("Switching to file-level bifurcation...")
            return switch_to_file_level(state)

        # Strategy 2: Manual mode
        print("Automated bifurcation struggling due to dependencies.")
        print("Switch to manual mode? (y/n)")
        if input().lower() == 'y':
            return switch_to_manual_mode(state)

        # Strategy 3: Report best effort
        print("Cannot isolate single change.")
        print("Possible breaking changes:")
        return report_candidates(state)
```

## CLI Implementation

### Command Structure

```python
class CLI:
    def __init__(self):
        self.parser = argparse.ArgumentParser(
            prog='git-bifurcate',
            description='Find breaking changes within a commit'
        )
        self.subparsers = self.parser.add_subparsers(dest='command')

        # git bifurcate start
        start_parser = self.subparsers.add_parser('start')
        start_parser.add_argument('commit', help='Commit to bifurcate')
        start_parser.add_argument('--strategy', choices=['file', 'hunk', 'hybrid'])
        start_parser.add_argument('--manual', action='store_true')

        # git bifurcate test
        test_parser = self.subparsers.add_parser('test')
        test_parser.add_argument('command', help='Test command to run')
        test_parser.add_argument('--dir', help='Working directory')

        # Other commands...

    def run(self, args):
        parsed = self.parser.parse_args(args)

        if parsed.command == 'start':
            return self.cmd_start(parsed)
        elif parsed.command == 'test':
            return self.cmd_test(parsed)
        # ...
```

### Progress Reporting

```python
def report_progress(state):
    """
    Show user-friendly progress
    """
    total_changes = len(state.changes)
    search_space_size = len(state.search_space)

    print(f"\nBifurcation Progress")
    print(f"{'=' * 50}")
    print(f"Total changes: {total_changes}")
    print(f"Search space: {search_space_size}")
    print(f"Iterations: {state.current_iteration}")
    print(f"Tests run: {len(state.tested_combinations)}")

    # Progress bar
    progress = 1 - (search_space_size / total_changes)
    bar_length = 30
    filled = int(bar_length * progress)
    bar = '█' * filled + '░' * (bar_length - filled)
    print(f"\n[{bar}] {progress*100:.1f}%")

    if state.found_breaking:
        print(f"\nFound breaking changes: {len(state.found_breaking)}")
```

## Security Considerations

1. **Command Injection**: Sanitize test commands
2. **Path Traversal**: Validate file paths from diffs
3. **Resource Limits**: Timeout for tests, limit worktrees
4. **State File**: Validate state file before loading

```python
def sanitize_test_command(command):
    """
    Validate test command to prevent injection
    """
    # Don't allow shell metacharacters unless explicitly quoted
    dangerous_chars = [';', '&', '|', '>', '<', '`', '$']

    if any(char in command for char in dangerous_chars):
        raise SecurityError(
            f"Test command contains potentially dangerous characters. "
            f"Please quote properly or use --allow-dangerous flag."
        )

    return command
```
