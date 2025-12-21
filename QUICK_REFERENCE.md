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
# Start bifurcation
git bifurcate start <commit> --test "npm test"

# Check status
git bifurcate status

# Reset/abort
git bifurcate reset

# Manual mode
git bifurcate start <commit> --manual
git bifurcate apply-half upper
npm test
git bifurcate bad
```

## Strategies

- **file**: Search at file level only (fast, less precise)
- **hunk**: Search at hunk level (slow, very precise)
- **hybrid**: File first, then hunk (recommended)

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
├── src/
│   ├── cli.py          # Commands
│   ├── core.py         # Bifurcation engine
│   ├── parser.py       # Diff parsing
│   ├── git_ops.py      # Git wrapper
│   └── models.py       # Data models
├── tests/
│   └── fixtures/       # Test repos
├── DESIGN.md           # High-level design
├── ARCHITECTURE.md     # Implementation details
└── IMPLEMENTATION_ROADMAP.md  # Step-by-step guide
```

## Example Session

```bash
# After git bisect finds bad commit abc123
$ git bifurcate start abc123 --test "pytest tests/test_auth.py"

Bifurcating commit abc123
Found 12 file changes
Strategy: hybrid

Testing files...
[==========] Test [1-6]: PASS
[==========] Test [7-12]: FAIL
[=====     ] Test [7-9]: FAIL
[===       ] Test [7-8]: PASS
[=         ] Test [9]: FAIL

Breaking file: src/auth/login.py

Testing hunks in src/auth/login.py...
Found 5 hunks
[====      ] Test hunks [1-3]: PASS
[======    ] Test hunks [4-5]: FAIL
[=======   ] Test hunk [4]: FAIL

Found breaking change:
  File: src/auth/login.py
  Lines: 45-52
  Hunk: Modified validatePassword function

  @@ -45,7 +45,8 @@
   function validatePassword(password) {
  -  return password.length >= 8;
  +  const minLength = 8;
  +  return password.length > minLength;  # BUG: should be >=
   }

Tests performed: 7
Time saved: ~90% vs manual review
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

## Implementation Phases

**Phase 1**: File-level, automated mode, basic state
**Phase 2**: Hunk-level, hybrid strategy
**Phase 3**: Manual mode, skip handling, robustness
**Phase 4**: Parallel testing, multiple breaks, GUI

## Performance

- **Best case**: O(log n) for n independent changes
- **Worst case**: O(n log n) with many dependencies
- **Typical**: 5-10 tests for commits with 20-50 changes

## Language Choice

**MVP**: Python (fast prototyping, GitPython library)
**Production**: Consider Rust (performance, single binary)

## Key Insights

1. **Complexity is in dependencies**, not binary search
2. **State persistence essential** for resumption
3. **User guidance critical** when automation struggles
4. **Testing is expensive** - minimize iterations
5. **Multiple breaks common** in large commits

## Next Steps

1. Read DESIGN.md for full design
2. Read ARCHITECTURE.md for implementation details
3. Read IMPLEMENTATION_ROADMAP.md for step-by-step guide
4. Start with Phase 1 MVP
5. Test on real repositories
6. Iterate based on feedback
