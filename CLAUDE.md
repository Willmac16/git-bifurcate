# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**git-bifurcate** is a tool that extends `git bisect` to find bugs at the file and hunk level within a single commit. It uses binary search to isolate the exact change that broke tests, rather than just identifying the commit.

**Core Workflow:**
1. User runs `git bisect` to find the bad commit
2. User runs `git bifurcate` on that commit with a test command
3. Tool binary searches through files and hunks to find the breaking change
4. Reports the exact lines that caused the test failure

## Architecture

### System Layers

1. **CLI Layer**: Command parsing, user interaction, progress reporting
2. **Bifurcation Engine**: Binary search logic, state management, test execution
3. **Change Management**: Diff parsing, change application/reversion, dependency detection
4. **Git Operations**: Low-level git commands (diff, apply, commit, reset, worktree)

### Core Concepts

**Change**: An atomic unit of modification - either a file or a hunk within a file

**Search Space**: The set of changes currently being bisected

**Strategy**: Granularity level for search:
- `file`: Binary search across files only
- `hunk`: Binary search across individual hunks
- `hybrid`: File-level first, then drill down to hunk-level

**State**: Persistent bifurcation state saved to `.git/bifurcate-state.json` for resumption

### Key Data Models

```rust
Change {
    id: String,
    change_type: File | Hunk,
    file_path: String,
    start_line: Option<usize>,
    end_line: Option<usize>,
    diff_content: String,
    dependencies: Vec<String>,  // Other changes this depends on
    status: Unknown | Good | Bad | Skip
}

BifurcationState {
    commit_sha: String,
    parent_sha: String,
    strategy: Strategy,
    test_command: String,
    changes: Vec<Change>,
    search_space: Vec<usize>,  // Indices still being tested
    tested_combinations: HashMap<Vec<usize>, TestResult>,
    found_breaking: Vec<usize>
}
```

## Key Algorithms

### Binary Search with Dependencies

The core algorithm performs binary search but must handle dependencies between changes (e.g., import statements depend on function definitions):

1. Split search space in half
2. Expand each half to include all dependencies
3. Test each half
4. Narrow search space based on results
5. Handle special case: both halves pass but together they fail (interaction)

### Dependency Detection

Two approaches:
1. **Static Analysis** (complex): Parse code to find imports, references, definitions
2. **Build-Based** (simpler): Track which combinations fail to compile → mark as dependencies

### Change Application Strategies

- **Temporary Commits** (recommended): Create temp branch, commit changes, test, reset
- **Patch Application**: Use `git apply` to apply/revert without commits
- **Worktrees**: Create separate worktrees for parallel testing

## Implementation Phases

**Phase 1 - MVP**: File-level only, automated mode, basic state persistence

**Phase 2 - Hunk Level**: Parse hunks, hunk-level bifurcation, hybrid strategy

**Phase 3 - Robustness**: Dependency handling, skip problematic combinations, manual mode

**Phase 4 - Advanced**: Parallel testing, multiple breaking changes, GUI/TUI

## Critical Design Decisions

### Why Binary Search?

Linear search would take O(n) tests for n changes. Binary search takes O(log n) tests. For a commit with 32 changes, this is 5-7 tests instead of up to 32.

### Why Both File and Hunk Level?

- File-level is faster but less precise
- Hunk-level is precise but slower (more changes to search)
- Hybrid gives best of both: fast initial narrowing, then precision

### Why Temporary Commits vs Patches?

Temporary commits are cleaner and work with any git operation. Patches are faster but can have conflicts. We default to commits for reliability.

### How to Handle Interdependent Changes?

Three strategies:
1. **Detect and skip**: If a combination won't build, mark as "skip" and try different split
2. **Dependency graph**: Track dependencies and keep dependent changes together
3. **Fallback**: If too many skips, switch to file-level or manual mode

### How to Handle Multiple Breaking Changes?

After finding one break:
1. Remove it from search space
2. Continue bifurcating on remaining changes
3. Report all breaking changes found

Or test all changes individually in parallel, then test combinations.

## Development Commands

**Note**: Not yet implemented. When implementation begins, add:

```bash
# Build
[language-specific build command]

# Run tests
[test command]

# Run single test
[single test command]

# Install dependencies
[dependency installation]

# Format code
[formatter]

# Lint
[linter]
```

## File Structure

```
git-bifurcate/
├── DESIGN.md           # High-level design and user-facing concepts
├── ARCHITECTURE.md     # Implementation details, algorithms, data structures
├── README.md           # User documentation
├── CLAUDE.md          # This file
├── src/               # Source code (future)
│   ├── cli/          # Command-line interface
│   ├── core/         # Bifurcation engine
│   ├── git/          # Git operations wrapper
│   └── parser/       # Diff parsing
└── tests/            # Test suite (future)
    └── fixtures/     # Test repositories with known breaks
```

## Important Patterns

### State Management

Always save state after each iteration to allow resumption:
```python
state = load_state()
result = run_test(changes)
state.update(result)
save_state(state)
```

### Error Handling

Distinguish between:
- **Test Failure**: Test ran but failed (this is what we're looking for)
- **Test Error**: Test command errored (bad test command or unbuildable state)
- **Build Failure**: Code won't compile (missing dependencies)

### User Experience

- Show clear progress: "Testing changes [1-8] of 16..."
- Report estimated iterations remaining
- Allow interruption and resumption
- Provide helpful errors when stuck

## Common Challenges

### Challenge: Complex Dependencies

**Problem**: Changes A and B individually won't compile, only together

**Solution**: Track build failures, mark those combinations as "must stay together", treat as atomic unit

### Challenge: Interaction Effects

**Problem**: Changes A and B individually pass tests, but together fail

**Solution**: Detect this case, then bisect to find minimal interacting set using specialized algorithm (see `find_interaction` in ARCHITECTURE.md)

### Challenge: Nondeterministic Tests

**Problem**: Tests sometimes pass, sometimes fail

**Solution**: Run tests multiple times, require consistent results, or warn user

### Challenge: Slow Tests

**Problem**: Each test takes minutes, making bifurcation too slow

**Solution**:
- Encourage users to run only failing test, not full suite
- Implement parallel testing with worktrees
- Cache test results aggressively

## Testing Strategy

Create test repositories with known breaking changes:

```
test-repo-simple/
  - Single commit, 5 files changed
  - File 3, hunk 2 breaks tests
  - Expected: 7 iterations to find

test-repo-dependencies/
  - Changes with import dependencies
  - Should handle without false positives

test-repo-interaction/
  - Two changes that only break together
  - Should detect interaction

test-repo-multiple-breaks/
  - Three independent breaking changes
  - Should find all three with --find-more
```

## When Adding New Features

1. **Check Design Docs First**: DESIGN.md and ARCHITECTURE.md define the intended behavior
2. **Maintain State Compatibility**: Ensure new features don't break state file loading
3. **Add Tests**: Create test repository fixtures that exercise the feature
4. **Update Progress Reporting**: Keep user informed of what's happening
5. **Handle Errors Gracefully**: Provide recovery strategies when things go wrong

## Language Choice

**Not Yet Decided**. Candidates:

- **Python**: Fast prototyping, good git libraries, easier string/parsing
- **Rust**: Performance, safety, single binary distribution
- **Go**: Good balance, easy distribution, reasonable git libraries

## Git Integration

The tool should feel like a native git command:
- Installed as `git-bifurcate` (git will find it as `git bifurcate`)
- Follows git conventions (state in `.git/`, similar CLI to `git bisect`)
- Works with git hooks and configurations
- Respects `.gitignore` and git attributes

## Key Insights from Design Phase

1. **Complexity is in Dependencies**: The hard part isn't binary search—it's handling interdependent changes
2. **User Guidance is Critical**: When automated mode struggles, provide clear guidance on switching to manual
3. **State Persistence is Essential**: Users will interrupt; bifurcation must be resumable
4. **Testing is Expensive**: Each iteration runs the test suite; minimize iterations
5. **Multiple Breaking Changes are Common**: Large commits often have multiple bugs; support finding all of them
