# Quick Reference

One-page overview of git-bifurcate.

## What is it?

Extends `git bisect` to find bugs at the file/hunk level within a commit.

**git bisect**: Which commit broke? → Commit ABC
**git bifurcate**: Which change in commit ABC broke? → File X, lines 45-52

## How it Works

```
Commit ABC has 16 changes
├─ Test all 16: FAIL
├─ Test changes 1-8: PASS
├─ Test changes 9-16: FAIL
│  ├─ Test changes 9-12: FAIL
│  │  ├─ Test changes 9-10: PASS
│  │  └─ Test changes 11-12: FAIL
│  │     ├─ Test change 11: FAIL ← Found it!
```

Binary search: 16 changes → 5 tests instead of up to 16

## Core Commands

```bash
# Start bifurcation (automated)
git bifurcate start <commit> --test "npm test"

# Commit bisection + bifurcation
git bifurcate bisect <good> <bad> --test "npm test"

# Check status
git bifurcate status

# Resume interrupted session
git bifurcate continue

# Reset/abort
git bifurcate reset
```

## Strategies

- **file** (default): Search at file level only (fast, less precise)
- **hunk**: Search at hunk level (slow, very precise)
- **hybrid**: File first, then hunk (planned, not yet implemented)

## Key Concepts

### Change
Atomic unit: one file or one hunk within a file

### Search Space
Set of changes currently being bisected

### State
Saved to `.git/bifurcate-state.json` for resumption

### Test Result
- **PASS**: Test succeeded
- **FAIL**: Test failed (this is what we're looking for)
- **SKIP**: Couldn't test (e.g., won't build)
- **ERROR**: Test command itself errored

## Algorithm Pseudocode

```python
def bifurcate(changes):
    if len(changes) == 1:
        return changes[0]

    mid = len(changes) // 2
    lower = changes[:mid]
    upper = changes[mid:]

    if test(lower) == FAIL:
        return bifurcate(lower)
    else:
        return bifurcate(upper)
```

## Common Issues

### Issue: Too many SKIPs
**Cause**: Changes have dependencies (won't build separately)
**Solution**: Switch to file-level or manual mode

### Issue: Both halves PASS individually
**Cause**: Changes interact (only break together)
**Solution**: Use interaction detection algorithm

### Issue: Tests flaky
**Cause**: Nondeterministic tests
**Solution**: Run tests multiple times, require consistency

## Architecture Layers

```
CLI Layer
  ↓
Bifurcation Engine (binary search, state)
  ↓
Change Management (parsing, application)
  ↓
Git Operations (diff, apply, commit, reset)
```

## Data Flow

```
1. Parse commit diff → List of Changes
2. Binary search → Select subset of changes
3. Apply changes → Modified working directory
4. Run test → PASS/FAIL/SKIP
5. Update search space → Narrow down
6. Repeat until 1 change found
```

## File Structure

```
git-bifurcate/
├── src/git_bifurcate/
│   ├── cli.py                  # CLI commands
│   ├── core.py                 # Bifurcation engine
│   ├── parser.py               # Diff parsing
│   ├── git_ops.py              # Git operations
│   ├── models.py               # Data models
│   ├── dependency_analyzer.py  # Multi-language static analysis
│   ├── dependency_graph.py     # Dependency graph
│   ├── commit_bisect.py        # Commit bisection
│   └── test_runner.py          # Test execution
├── tests/                      # 215 tests, 99.9% coverage
├── DESIGN.md                   # High-level design
├── ARCHITECTURE.md             # Implementation details
└── CLAUDE.md                   # Development guide
```

## Example Session

```bash
# After git bisect finds bad commit abc123
$ git bifurcate start abc123 --test "pytest tests/test_auth.py"

Bifurcating commit abc123 (12 file changes)
Strategy: file
Parent: def456

Iteration 1/4: Testing changes [1-6] of 12... PASS
Iteration 2/4: Testing changes [7-12] of 12... FAIL
Iteration 3/5: Testing changes [7-9] of 6... FAIL
Iteration 4/5: Testing changes [7-8] of 4... PASS
Iteration 5/5: Testing change [9] of 2... FAIL

Breaking change found:
  src/auth/login.py

Completed in 5 iterations (10 tests run: 5 passed, 5 failed)

# For hunk-level precision, use --strategy hunk
$ git bifurcate start abc123 --test "pytest" --strategy hunk

Bifurcating commit abc123 (45 hunk changes)
Strategy: hunk
...
Breaking change found:
  src/auth/login.py:45-52
```

## State File Format

```json
{
  "commit": "abc123",
  "parent": "def456",
  "test_command": "npm test",
  "strategy": "hybrid",
  "changes": [...],
  "search_space": [4, 5, 6],
  "tested_combinations": {
    "1,2,3,4,5,6": "fail",
    "1,2,3": "pass"
  },
  "found_breaking": []
}
```

## Implementation Status

**✅ Phase 1**: File-level, automated mode, state persistence
**✅ Phase 2**: Hunk-level bifurcation
**✅ Phase 3**: Dependency analysis, skip handling, robustness
**✅ Phase 4**: Multiple breaks (--find-more), commit bisection
**✅ Phase 5**: Production quality - 99.9% test coverage, CI/CD

**Planned**: Hybrid strategy, manual mode, parallel testing, GUI

## Performance

- **Best case**: O(log n) for n independent changes
- **Worst case**: O(n log n) with many dependencies
- **Typical**: 5-10 tests for commits with 20-50 changes

## Language

**Python 3.12+** (Implemented)
- GitPython for git operations
- Click for CLI
- 99.9% test coverage with pytest
- Type checked with ty, linted with ruff

## Key Insights

1. **Complexity is in dependencies**, not binary search
2. **State persistence essential** for resumption
3. **User guidance critical** when automation struggles
4. **Testing is expensive** - minimize iterations
5. **Multiple breaks common** in large commits

## Getting Started

1. Install: `pip install git-bifurcate`
2. Read README.md for usage examples
3. Read DESIGN.md for full design
4. Read ARCHITECTURE.md for implementation details
5. Check CONTRIBUTING.md to contribute
