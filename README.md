# git-bifurcate

**Find the exact change that broke your tests.**

`git-bifurcate` extends `git bisect` to locate bugs at the file and hunk level within a single commit. When `git bisect` tells you which commit introduced a bug, `git-bifurcate` tells you which specific change in that commit caused it.

## The Problem

You run `git bisect` and find the commit that broke your tests:

```bash
$ git bisect good
Bisecting: 0 revisions left to test
[abc123] Refactor authentication and add password validation
```

Great! But now you look at the commit:

```
15 files changed, 347 insertions(+), 89 deletions(-)
```

Which change actually broke the test? Manual review could take hours.

## The Solution

```bash
$ git bifurcate start abc123 --test "npm test"

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

  @@ -45,7 +45,8 @@
   function validatePassword(password) {
  -  return password.length >= 8;
  +  const minLength = 8;
  +  return password.length > minLength;
   }
```

**Problem found in 7 iterations** instead of manually reviewing 32 changes.

## Quick Start

### Installation

```bash
# Install from source (Python)
git clone https://github.com/yourusername/git-bifurcate
cd git-bifurcate
pip install -e .
```

### Basic Usage

```bash
# After git bisect identifies the bad commit
$ git bisect good
[abc123] The bad commit

# Start automated bifurcation
$ git bifurcate start abc123 --test "npm test"

# Or use manual mode
$ git bifurcate start abc123 --manual
$ git bifurcate apply-half upper
$ npm test
$ git bifurcate bad
# Continue marking good/bad...
```

## Features

- **Automated Testing**: Binary search through changes with your test command
- **Multiple Granularities**: File-level, hunk-level, or hybrid strategies
- **Smart Handling**: Detects dependencies between changes
- **Resume Support**: Interrupt and resume bifurcation sessions
- **Multiple Breaking Changes**: Find all breaking changes in a commit
- **Manual Mode**: Step through manually for complex cases

## How It Works

1. **Extract Changes**: Parse the commit diff into individual files and hunks
2. **Binary Search**: Apply binary search to find breaking change(s)
3. **Test**: Run your test command against each combination
4. **Isolate**: Narrow down to the specific breaking change

### Strategies

- **File-level**: Fast, finds which file contains the break
- **Hunk-level**: Precise, finds the exact lines that break
- **Hybrid** (default): File-level first, then hunk-level for the problematic file

## Examples

### Example 1: Simple Automated Run

```bash
$ git bifurcate start abc123 --test "pytest tests/"

Bifurcating commit abc123
Strategy: hybrid
Changes: 8 files, 23 hunks

Testing files...
Found breaking file: src/utils.py

Testing hunks in src/utils.py...
Found breaking hunk: lines 156-163

Breaking change identified in 6 tests.
```

### Example 2: Multiple Breaking Changes

```bash
$ git bifurcate start abc123 --test "cargo test" --find-more

Found breaking change: src/parser.rs:45-52

Continue searching? [Y/n] y

Found breaking change: src/validator.rs:89-95

Continue searching? [Y/n] n

Found 2 breaking changes total.
```

### Example 3: Manual Mode

```bash
$ git bifurcate start abc123 --manual

Bifurcating commit abc123
8 files changed, 23 hunks total

$ git bifurcate apply-half upper
Applied changes [1-12] of 23
Run your tests, then: git bifurcate good/bad

$ npm test
# Tests fail

$ git bifurcate bad
Changes [1-12] marked as bad

$ git bifurcate apply-half upper
Applied changes [1-6] of 12
# Continue...
```

## Command Reference

### `git bifurcate start <commit> [options]`

Start a bifurcation session.

**Options:**
- `--strategy=<file|hunk|hybrid>` - Search strategy (default: hybrid)
- `--manual` - Use manual mode instead of automated
- `--test=<command>` - Test command for automated mode
- `--dir=<path>` - Working directory for tests

### `git bifurcate test <command>`

Run automated bifurcation with a test command.

### `git bifurcate good/bad/skip`

Mark current changes as good, bad, or skip (manual mode).

### `git bifurcate apply-half <upper|lower>`

Apply half of the remaining changes (manual mode).

### `git bifurcate status`

Show current bifurcation state and progress.

### `git bifurcate reset`

Abort bifurcation and clean up.

### `git bifurcate continue`

Resume an interrupted bifurcation session.

## Advanced Usage

### Finding Multiple Breaks

```bash
$ git bifurcate start abc123 --test "npm test" --find-more
```

After finding one breaking change, continues searching for more.

### Custom Working Directory

```bash
$ git bifurcate start abc123 --test "make test" --dir=./build
```

Useful if tests need to run in a specific directory.

### Parallel Testing (Experimental)

```bash
$ git bifurcate start abc123 --test "npm test" --parallel
```

Uses git worktrees to test multiple combinations in parallel.

## Tips

- **Use Specific Tests**: Instead of running your entire test suite, run only the failing test for faster iteration
- **Manual Mode for Complex Cases**: If automated mode struggles with dependencies, switch to manual
- **Hybrid Strategy**: Usually the best balance of speed and precision
- **Resume Sessions**: Use `git bifurcate continue` if you need to interrupt

## Integration with git bisect

Seamless workflow:

```bash
# Run bisect to find bad commit
$ git bisect start
$ git bisect bad HEAD
$ git bisect good v1.0.0
$ git bisect run npm test

# Bisect found the commit, now find the exact change
$ git bifurcate start $(git rev-parse HEAD) --test "npm test"
```

## Limitations

- **Dependent Changes**: Changes that depend on each other may cause build failures during bifurcation
- **Complex Interactions**: Some bugs only appear when multiple changes are present together
- **Test Determinism**: Requires tests to be deterministic and reliable

## Contributing

See [DESIGN.md](DESIGN.md) for architecture details and [ARCHITECTURE.md](ARCHITECTURE.md) for implementation details.

## License

MIT License - see LICENSE file

## Inspiration

- `git bisect` - Binary search for commits
- `git blame` - Find when lines changed
- Various debugging tools that use binary search

## Roadmap

- [ ] Phase 1: MVP with file-level bifurcation
- [ ] Phase 2: Hunk-level support
- [ ] Phase 3: Dependency detection
- [ ] Phase 4: TUI/GUI interface
- [ ] Phase 5: CI/CD integration

## Support

- **Issues**: https://github.com/yourusername/git-bifurcate/issues
- **Discussions**: https://github.com/yourusername/git-bifurcate/discussions
- **Documentation**: https://github.com/yourusername/git-bifurcate/wiki
