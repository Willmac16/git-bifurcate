# git bifurcate - Design Document

## Overview

`git bifurcate` is a tool that extends `git bisect` to locate bugs at the file and hunk level within a single commit. While `git bisect` finds which commit introduced a bug, `git bifurcate` finds which specific change(s) within that commit caused the failure.

## Problem Statement

When `git bisect` identifies a bad commit, developers face a new problem: the commit might contain dozens of files and hundreds of lines of changes. Manually reviewing each change to find the culprit is time-consuming and error-prone.

`git bifurcate` automates this process using binary search at a finer granularity than commits.

## Core Concept

**Binary Search on Changes**: Just as `git bisect` performs binary search across commits, `git bifurcate` performs binary search across individual changes (files and hunks) within a commit.

**Granularity Levels**:
1. **File-level**: Test with subsets of changed files
2. **Hunk-level**: Test with subsets of hunks within files
3. **Hybrid**: File-level first, then drill down to hunk-level in the problematic file(s)

## User Workflow

### Basic Usage

```bash
# After git bisect finds the bad commit
$ git bisect good
Bisecting: 0 revisions left to test after this
[abc123] Bad commit message

# Start bifurcating the bad commit
$ git bifurcate start abc123
$ git bifurcate test "npm test"

# Automated mode: runs automatically
Bifurcating commit abc123...
Testing changes [1-16] of 32... FAIL
Testing changes [1-8] of 16... PASS
Testing changes [9-16] of 16... FAIL
Testing changes [9-12] of 8... FAIL
Testing changes [9-10] of 4... PASS
Testing changes [11-12] of 4... FAIL
Testing changes [11] of 2... FAIL

Found breaking change:
  File: src/auth/login.js
  Lines: 45-52
  Hunk: Modified validatePassword function
```

### Manual Mode

```bash
$ git bifurcate start abc123 --manual
$ git bifurcate apply-half upper  # Apply first half of changes
$ npm test                         # Run test manually
$ git bifurcate bad                # Mark as bad
$ git bifurcate apply-half upper  # Continue bisecting
$ npm test
$ git bifurcate good
...
```

### Advanced Options

```bash
# Start at file level, then drill down
$ git bifurcate start abc123 --strategy=hybrid

# Hunk-level only
$ git bifurcate start abc123 --strategy=hunk

# File-level only
$ git bifurcate start abc123 --strategy=file

# Specify working directory for test
$ git bifurcate test --command="npm test" --dir=/path/to/project

# Resume after interruption
$ git bifurcate continue

# Skip problematic change combinations
$ git bifurcate skip
```

## Technical Architecture

### Components

1. **Diff Parser**: Extract and parse changes from commit
2. **Change Manager**: Track and apply subsets of changes
3. **Test Runner**: Execute test command and capture results
4. **Bisection Engine**: Implement binary search algorithm
5. **State Manager**: Persist bifurcation state for resumption

### Change Representation

```
Commit: abc123
├── File: src/auth/login.js
│   ├── Hunk 1: Lines 12-15 (import statements)
│   ├── Hunk 2: Lines 45-52 (validatePassword function)
│   └── Hunk 3: Lines 78-80 (error handling)
├── File: src/auth/register.js
│   ├── Hunk 1: Lines 23-30 (validation logic)
│   └── Hunk 2: Lines 56-60 (database call)
└── File: tests/auth.test.js
    └── Hunk 1: Lines 100-120 (new test cases)
```

### Change Application Strategies

#### Strategy 1: Temporary Commits (Recommended)

- Create a temporary branch from the parent commit
- Apply subsets of changes as temporary commits
- Run tests
- Reset and try different combinations
- Advantages: Clean, reversible, works with all git operations
- Disadvantages: More git operations

#### Strategy 2: Patch Application

- Use `git apply` to apply patches from the parent commit
- Run tests
- Use `git reset --hard` to revert
- Advantages: Faster, fewer git objects
- Disadvantages: Harder to debug, may have conflicts

#### Strategy 3: Worktree

- Create separate worktrees for each test
- Apply changes in isolation
- Advantages: Parallel testing possible, original repo untouched
- Disadvantages: Disk space, complexity

### Binary Search Algorithm

```python
def bifurcate(changes, test_command, parent_commit):
    """
    Binary search through changes to find breaking change(s)
    """
    if len(changes) == 0:
        return None

    if len(changes) == 1:
        # Found the breaking change
        if test_with_changes([changes[0]]) == FAIL:
            return changes[0]
        return None

    mid = len(changes) // 2
    lower_half = changes[:mid]
    upper_half = changes[mid:]

    # Test with first half
    result = test_with_changes(lower_half)

    if result == FAIL:
        return bifurcate(lower_half, test_command, parent_commit)
    else:
        # The break is in the upper half or in combination
        result = test_with_changes(upper_half)
        if result == FAIL:
            return bifurcate(upper_half, test_command, parent_commit)
        else:
            # Both halves pass individually but fail together
            # Need to find interaction - use different strategy
            return find_interaction(lower_half, upper_half, test_command)
```

### Handling Change Dependencies

**Problem**: Changes may depend on each other. Removing one change might make code uncompilable.

**Solutions**:

1. **Compilation Check**: Before running tests, verify code compiles/builds
   - If build fails, treat as "skip" and try different combination
   - Track failed combinations to avoid retrying

2. **Dependency Analysis** (Advanced):
   - Parse code to detect dependencies between hunks
   - Keep dependent changes together as atomic units
   - Examples: import + usage, function definition + call

3. **User Hints**:
   - Allow users to mark changes as "must be together"
   - `git bifurcate group hunk1 hunk2 hunk3`

4. **Fallback Strategy**:
   - If too many combinations fail to build, switch to file-level only
   - Or switch to manual mode

### Handling Multiple Breaking Changes

If commit has multiple independent breaking changes:

1. **Sequential Discovery**:
   - Find and report first breaking change
   - Allow user to continue: `git bifurcate continue --find-more`
   - Remove found change from search space, continue bisecting

2. **Parallel Detection** (Advanced):
   - Test all individual changes in parallel
   - Identify all changes that break tests on their own
   - Then test combinations for interaction effects

## Data Structures

### State File (.git/bifurcate-state)

```json
{
  "commit": "abc123def456",
  "parent": "parent123def",
  "strategy": "hybrid",
  "test_command": "npm test",
  "current_level": "hunk",
  "changes": [
    {
      "id": "change_1",
      "type": "hunk",
      "file": "src/auth/login.js",
      "start_line": 45,
      "end_line": 52,
      "content": "diff content...",
      "status": "unknown"
    }
  ],
  "search_space": [1, 2, 3, 5, 6],
  "tested_combinations": {
    "[1,2,3]": "pass",
    "[4,5,6]": "fail",
    "[4,5]": "skip_no_build"
  },
  "found_breaking": []
}
```

## Implementation Phases

### Phase 1: MVP (Minimum Viable Product)
- File-level bifurcation only
- Automated mode with test command
- Temporary commit strategy
- Basic state persistence

### Phase 2: Hunk-Level Support
- Parse hunks from diff
- Hunk-level bifurcation
- Hybrid strategy (file then hunk)

### Phase 3: Robustness
- Handle build failures gracefully
- Skip problematic combinations
- Manual mode support
- Better error messages and progress reporting

### Phase 4: Advanced Features
- Dependency detection
- Multiple breaking change discovery
- Parallel testing with worktrees
- Integration with git bisect workflow
- GUI/TUI interface

## Command Reference

### Commands

- `git bifurcate start <commit> [options]` - Start bifurcation session
- `git bifurcate test <command>` - Run automated bifurcation
- `git bifurcate apply-half <upper|lower>` - Manual mode: apply half of changes
- `git bifurcate good` - Manual mode: mark current state as good
- `git bifurcate bad` - Manual mode: mark current state as bad
- `git bifurcate skip` - Manual mode: skip current combination
- `git bifurcate reset` - Abort bifurcation and clean up
- `git bifurcate status` - Show current bifurcation state
- `git bifurcate log` - Show history of tests performed
- `git bifurcate continue` - Resume interrupted bifurcation

### Options

- `--strategy=<file|hunk|hybrid>` - Choose granularity level
- `--manual` - Use manual mode instead of automated
- `--dir=<path>` - Working directory for running tests
- `--find-more` - After finding one break, continue to find more
- `--parallel` - Use worktrees for parallel testing (advanced)

## Error Handling

### Build Failures

When a combination of changes fails to build:
1. Record combination as "unbuildable"
2. Skip and try different combination
3. If too many unbuildable (>50%), suggest file-level only or manual mode

### Test Failures vs Errors

- **Test Failure**: Test runs but fails (this is what we're looking for)
- **Test Error**: Test command itself errors out
  - Could indicate unbuildable state
  - Or incorrect test command
  - Ask user to verify test command

### Ambiguous Results

If binary search can't isolate a single change:
- Multiple independent breaking changes
- Changes only break in combination
- Report all possibilities to user

## Performance Considerations

- **Worst Case**: O(n log n) for n changes if testing is thorough
- **Best Case**: O(log n) if single breaking change
- **Optimizations**:
  - Cache test results for combinations
  - Use worktrees for parallel testing
  - Smart ordering (test most suspicious changes first)

## Examples

### Example 1: Simple Case

Commit changes 3 files, test fails. Bifurcate finds it's in file B, hunk 2.

```
Commit has 3 files: A, B, C
Test [A,B,C]: FAIL
Test [A]: PASS
Test [B,C]: FAIL
Test [B]: FAIL
  B has 3 hunks: B1, B2, B3
  Test [B1,B2,B3]: FAIL
  Test [B1,B2]: PASS
  Test [B3]: FAIL

Breaking change: File B, Hunk 3
```

### Example 2: Multiple Breaking Changes

Commit has 2 independent breaking changes.

```
Commit has 4 files: A, B, C, D
Test [A,B,C,D]: FAIL
Test [A,B]: FAIL
Test [A]: FAIL

First breaking change: File A

Continue to find more:
Test [B,C,D]: FAIL
Test [B]: PASS
Test [C,D]: FAIL
Test [C]: FAIL

Second breaking change: File C

Continue to find more:
Test [B,D]: PASS

Found 2 breaking changes: File A, File C
```

### Example 3: Interacting Changes

Two changes that only break together.

```
Commit has 2 files: A, B
Test [A,B]: FAIL
Test [A]: PASS
Test [B]: PASS

Changes interact: Both A and B needed to cause failure
Breaking combination: File A (all changes) + File B (all changes)

Drilling down to hunks...
[Further bisection to find specific interacting hunks]
```

## Integration with git bisect

Potential workflow integration:

```bash
# Traditional bisect
$ git bisect start
$ git bisect bad HEAD
$ git bisect good v1.0
$ git bisect run npm test

# Bisect finds bad commit: abc123

# Automatically transition to bifurcate
$ git bisect bifurcate
# OR manually
$ git bifurcate start abc123 --test="npm test"

# After finding specific change
$ git bisect reset
# Work on fixing the specific change
```

## Future Enhancements

1. **Machine Learning**: Learn which types of changes are more likely to break tests
2. **Semantic Analysis**: Understand code to better group related changes
3. **Visual Interface**: TUI or GUI to visualize the search process
4. **Team Features**: Share bifurcation results with team
5. **CI/CD Integration**: Run bifurcation in CI when tests fail
6. **Language-Specific Plugins**: Better parsing for specific languages
7. **Blame Integration**: Combine with git blame for better context

## Success Metrics

- **Time Saved**: Compare manual review time vs automated bifurcation
- **Accuracy**: Correctly identify breaking changes
- **Usability**: Easy to use, good error messages
- **Reliability**: Handle edge cases gracefully
