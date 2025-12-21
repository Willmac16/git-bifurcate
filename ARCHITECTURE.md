# Architecture & Implementation Details

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CLI Interface Layer                      │
│  (Argument parsing, command routing, user interaction)       │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│                   Core Bifurcation Engine                    │
├──────────────────────────────────────────────────────────────┤
│  ┌────────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ State Manager  │  │ Bisect Logic │  │  Test Runner    │  │
│  │ - Save state   │  │ - Binary     │  │  - Run command  │  │
│  │ - Load state   │  │   search     │  │  - Capture exit │  │
│  │ - Resume       │  │ - Strategy   │  │  - Timeout      │  │
│  └────────────────┘  └──────────────┘  └─────────────────┘  │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│                  Change Management Layer                     │
├──────────────────────────────────────────────────────────────┤
│  ┌────────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │  Diff Parser   │  │ Change Graph │  │ Change Applier  │  │
│  │  - Parse diff  │  │ - Dependencies│ │ - Apply patches │ │
│  │  - Extract     │  │ - Grouping   │  │ - Create commits│ │
│  │    hunks       │  │ - Conflicts  │  │ - Revert        │  │
│  └────────────────┘  └──────────────┘  └─────────────────┘  │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│                      Git Operations Layer                    │
│  (git diff, git apply, git commit, git reset, worktree)     │
└──────────────────────────────────────────────────────────────┘
```

## Core Data Models

### Change

Represents a single atomic change (file or hunk):

```rust
struct Change {
    id: String,              // Unique identifier
    change_type: ChangeType, // File or Hunk
    file_path: String,       // Path to file
    start_line: Option<usize>, // For hunks
    end_line: Option<usize>,   // For hunks
    diff_content: String,    // The actual diff
    dependencies: Vec<String>, // IDs of changes this depends on
    status: ChangeStatus,    // Unknown, Good, Bad, Skip
}

enum ChangeType {
    File,
    Hunk,
}

enum ChangeStatus {
    Unknown,
    Good,    // Test passes with this change
    Bad,     // Test fails with this change
    Skip,    // Couldn't test (e.g., won't build)
}
```

### BifurcationState

Persistent state for resuming bifurcation:

```rust
struct BifurcationState {
    commit_sha: String,
    parent_sha: String,
    strategy: Strategy,
    test_command: String,
    working_dir: Option<PathBuf>,

    changes: Vec<Change>,
    search_space: Vec<usize>,        // Indices of changes still being tested
    tested_combinations: HashMap<Vec<usize>, TestResult>,
    found_breaking: Vec<usize>,      // Indices of identified breaking changes

    current_iteration: usize,
    total_iterations: usize,
}

enum Strategy {
    File,
    Hunk,
    Hybrid,
}

enum TestResult {
    Pass,
    Fail,
    Skip,
    Error(String),
}
```

## Key Algorithms

### 1. Diff Parsing Algorithm

Parse git diff output into structured changes:

```python
def parse_diff(commit_sha, parent_sha):
    """
    Parse diff between commit and parent into Change objects
    """
    diff_output = run_git(['diff', parent_sha, commit_sha])

    changes = []
    current_file = None
    current_hunk = None

    for line in diff_output.split('\n'):
        if line.startswith('diff --git'):
            # New file
            if current_file:
                changes.append(current_file)
            current_file = parse_file_header(line)

        elif line.startswith('@@'):
            # New hunk
            if current_hunk:
                current_file.add_hunk(current_hunk)
            current_hunk = parse_hunk_header(line)

        elif current_hunk:
            current_hunk.add_line(line)

    # Don't forget last file
    if current_file:
        changes.append(current_file)

    return changes
```

### 2. Binary Search with Dependency Handling

```python
def bifurcate_with_dependencies(changes, test_fn, dependency_graph):
    """
    Binary search accounting for dependencies between changes
    """
    search_space = list(range(len(changes)))

    while len(search_space) > 1:
        mid = len(search_space) // 2
        lower_indices = search_space[:mid]
        upper_indices = search_space[mid:]

        # Expand to include dependencies
        lower_with_deps = expand_with_dependencies(lower_indices, dependency_graph)

        result = test_with_changes(lower_with_deps, test_fn)

        if result == TestResult.Fail:
            # Problem is in lower half
            search_space = lower_indices
        elif result == TestResult.Pass:
            # Problem is in upper half
            search_space = upper_indices
        else:
            # Skip or error - try different split
            search_space = handle_skip(search_space, lower_indices, upper_indices)

    return search_space[0]

def expand_with_dependencies(indices, dependency_graph):
    """
    Add all dependencies of selected changes
    """
    expanded = set(indices)
    queue = list(indices)

    while queue:
        idx = queue.pop(0)
        for dep_idx in dependency_graph.get_dependencies(idx):
            if dep_idx not in expanded:
                expanded.add(dep_idx)
                queue.append(dep_idx)

    return sorted(expanded)
```

### 3. Interaction Detection

When both halves pass individually but fail together:

```python
def find_interaction(lower_changes, upper_changes, test_fn):
    """
    Find specific changes that interact to cause failure
    """
    # Try each change from lower with all of upper
    for i, lower_change in enumerate(lower_changes):
        if test_with_changes([lower_change] + upper_changes) == Fail:
            # Found a change in lower that's part of the interaction
            # Now bisect upper to find what it interacts with
            upper_culprit = bifurcate(upper_changes,
                                     lambda changes: test_with_changes([lower_change] + changes))
            return InteractionResult([lower_change, upper_culprit])

    # Try each change from upper with all of lower
    for upper_change in upper_changes:
        if test_with_changes(lower_changes + [upper_change]) == Fail:
            lower_culprit = bifurcate(lower_changes,
                                     lambda changes: test_with_changes(changes + [upper_change]))
            return InteractionResult([upper_change, lower_culprit])

    # Complex interaction - fall back to exhaustive search or user guidance
    return find_complex_interaction(lower_changes, upper_changes, test_fn)
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

## Dependency Detection

### Static Analysis Approach

```python
def detect_dependencies(changes):
    """
    Analyze changes to detect dependencies between them
    """
    dependency_graph = DependencyGraph()

    for i, change_a in enumerate(changes):
        for j, change_b in enumerate(changes):
            if i == j:
                continue

            # Check various dependency types
            if has_import_dependency(change_a, change_b):
                dependency_graph.add_edge(j, i)  # b depends on a

            if has_reference_dependency(change_a, change_b):
                dependency_graph.add_edge(j, i)

            if has_order_dependency(change_a, change_b):
                dependency_graph.add_edge(j, i)

    return dependency_graph

def has_import_dependency(change_a, change_b):
    """
    Check if change_b imports something defined in change_a
    """
    # Extract definitions from change_a
    definitions = extract_definitions(change_a)  # Functions, classes, variables

    # Extract imports/references from change_b
    references = extract_references(change_b)

    return bool(definitions & references)
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

## Testing Strategy

### Unit Tests

- Diff parser with various diff formats
- Binary search algorithm with different inputs
- Dependency detection
- Change application and reversion

### Integration Tests

- Full bifurcation runs on test repositories
- State persistence and resumption
- Error handling (build failures, test errors)

### Test Repository Structure

Create test repos with known breaking changes:

```
test-repo-1/
  - 10 commits, commit 5 is bad
  - Commit 5 has 3 files changed
  - File B, hunk 2 is the breaking change

test-repo-2/
  - Single commit with 2 independent breaking changes

test-repo-3/
  - Interacting changes (both needed to break)

test-repo-4/
  - Changes with dependencies (imports, references)
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
