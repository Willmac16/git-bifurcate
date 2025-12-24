# git-bifurcate

[![Tests](https://github.com/Willmac16/git-bifurcate/actions/workflows/test.yml/badge.svg)](https://github.com/Willmac16/git-bifurcate/actions/workflows/test.yml)
[![Lint](https://github.com/Willmac16/git-bifurcate/actions/workflows/lint.yml/badge.svg)](https://github.com/Willmac16/git-bifurcate/actions/workflows/lint.yml)
[![Build](https://github.com/Willmac16/git-bifurcate/actions/workflows/build.yml/badge.svg)](https://github.com/Willmac16/git-bifurcate/actions/workflows/build.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![codecov](https://codecov.io/gh/Willmac16/git-bifurcate/branch/main/graph/badge.svg)](https://codecov.io/gh/Willmac16/git-bifurcate)
[![PyPI version](https://badge.fury.io/py/git-bifurcate.svg)](https://badge.fury.io/py/git-bifurcate)

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
# Install from PyPI
pip install git-bifurcate

# Or install from source
git clone https://github.com/Willmac16/git-bifurcate
cd git-bifurcate
uv venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows
uv pip install -e .
```

**Requirements:** Python 3.12 or higher

### Basic Usage

```bash
# After git bisect identifies the bad commit
$ git bisect good
[abc123] The bad commit

# Start automated bifurcation
$ git bifurcate start abc123 --test "npm test"

# Or start on the current commit (HEAD)
$ git bifurcate start --test "pytest tests/test_feature.py"
```

## Features

- **Automated Testing**: Binary search through changes with your test command
- **Multiple Granularities**: File-level and hunk-level bifurcation strategies
- **Dependency Analysis**: Multi-language static analysis for 7+ languages (Python, C/C++, Rust, Go, Swift, Zig, Verilog)
- **Commit Bisection**: Find the bad commit, then drill down to the exact change
- **Resume Support**: Interrupt and resume bifurcation sessions with persistent state
- **Multiple Breaking Changes**: Find all breaking changes in a commit with `--find-more`
- **Path Filtering**: Restrict search to specific files or directories
- **Submodule Support**: Detect and analyze changes in git submodules
- **High Test Coverage**: 99.9% test coverage with 215+ test cases

## How It Works

1. **Extract Changes**: Parse the commit diff into individual files and hunks
2. **Binary Search**: Apply binary search to find breaking change(s)
3. **Test**: Run your test command against each combination
4. **Isolate**: Narrow down to the specific breaking change

### Strategies

- **File-level** (default): Fast, finds which file contains the break
- **Hunk-level**: Precise, finds the exact lines that break
  Use with `--strategy hunk` for maximum precision

## Examples

### Example 1: File-Level Bifurcation

```bash
$ git bifurcate start abc123 --test "pytest tests/"

Bifurcating commit abc123 (8 file changes)
Strategy: file
Parent: def456

Iteration 1/3: Testing changes [1-4] of 8... FAIL
Iteration 2/3: Testing changes [1-2] of 4... PASS
Iteration 3/3: Testing changes [3-4] of 4... FAIL
Iteration 4/4: Testing change [3] of 2... FAIL

Breaking change found:
  src/utils.py

Completed in 4 iterations (8 tests run: 4 passed, 4 failed)
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

### Example 3: Commit Bisection

```bash
# Find the bad commit and the exact breaking change
$ git bifurcate bisect v1.0.0 HEAD --test "npm test"

Bisecting commits between v1.0.0 and HEAD...
Found bad commit: abc123

Now bifurcating commit abc123...
Breaking change found: src/auth/login.js

Complete: Identified breaking change in commit abc123, file src/auth/login.js
```

### Example 4: Path Filtering

```bash
# Only search for changes in specific paths
$ git bifurcate start abc123 --test "pytest" -- src/auth/ tests/test_auth.py

Bifurcating commit abc123
Restricted to paths: src/auth/, tests/test_auth.py
Strategy: file
Changes: 3 files (filtered from 8)

Breaking change found: src/auth/validator.py
```

## Development

Run the same checks locally that CI executes:

```bash
# Linting and type checking
./test --lint-only

# Test suite with coverage (includes HTML and XML reports)
./test --test-only
```

Or run everything together:

```bash
./test
```

Optional: install pre-commit hooks to run these checks automatically before each commit:

```bash
uv run pre-commit install
```

## Command Reference

### `git bifurcate start [COMMIT] [PATHS...] [OPTIONS]`

Start a bifurcation session on a specific commit.

**Arguments:**
- `COMMIT` - Commit SHA to bifurcate (optional, defaults to HEAD)
- `PATHS` - Files or directories to restrict search to (optional)

**Options:**
- `--test, -t <command>` - **Required.** Test command to run (e.g., "pytest tests/")
- `--strategy, -s <file|hunk>` - Search strategy (default: file)
- `--parent, -p <sha>` - Parent commit SHA (defaults to COMMIT^)
- `--analyze-deps, -d` - Enable multi-language dependency analysis
- `--find-more, -m` - Continue searching for more breaking changes after finding one

**Examples:**
```bash
git bifurcate start abc123 --test "npm test"
git bifurcate start --test "pytest" --strategy hunk
git bifurcate start abc123 --test "cargo test" -- src/
```

### `git bifurcate bisect <GOOD_COMMIT> <BAD_COMMIT> --test <command>`

Bisect commits to find the first bad commit, then bifurcate it.

**Arguments:**
- `GOOD_COMMIT` - Known good commit SHA or ref
- `BAD_COMMIT` - Known bad commit SHA or ref

**Options:**
- `--test, -t <command>` - **Required.** Test command to run

**Example:**
```bash
git bifurcate bisect v1.0.0 HEAD --test "npm test"
```

### `git bifurcate status`

Show current bifurcation state and progress.

### `git bifurcate reset [OPTIONS]`

Abort bifurcation and clean up state.

**Options:**
- `--force, -f` - Force reset even if state file is corrupted

### `git bifurcate continue`

Resume an interrupted bifurcation session.

### `git bifurcate --version`

Show version information.

## Advanced Usage

### Finding Multiple Breaks

```bash
$ git bifurcate start abc123 --test "npm test" --find-more
```

After finding one breaking change, prompts to continue searching for more.

### Dependency Analysis

```bash
$ git bifurcate start abc123 --test "pytest" --analyze-deps
```

Enables static dependency analysis across multiple languages (Python, C/C++, Rust, Go, Swift, Zig, Verilog). Helps avoid testing invalid combinations that won't compile.

### Hunk-Level Precision

```bash
$ git bifurcate start abc123 --test "cargo test" --strategy hunk
```

Searches at the hunk (code block) level instead of file level for maximum precision.

## Tips

- **Use Specific Tests**: Instead of running your entire test suite, run only the failing test for faster iteration
- **Enable Dependency Analysis**: Use `--analyze-deps` for codebases with complex dependencies between changes
- **Start with File-Level**: Use the default file-level strategy first, then drill down with `--strategy hunk` if needed
- **Resume Sessions**: Use `git bifurcate continue` if you need to interrupt - state is automatically saved
- **Combine with git bisect**: Use `git bifurcate bisect` to find both the bad commit and the exact breaking change in one command

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

- [x] **Phase 1: MVP** - File-level bifurcation ✅
- [x] **Phase 2: Hunk-Level** - Hunk-level support and strategies ✅
- [x] **Phase 3: Dependency Detection** - Multi-language static analysis ✅
- [x] **Phase 4: Commit Bisection** - Integrated commit and change-level bisection ✅
- [x] **Phase 5: Production Ready** - 99.9% test coverage, CI/CD ✅
- [ ] **Phase 6: TUI/GUI Interface** - Visual interface for bifurcation
- [ ] **Phase 7: Advanced Features** - Hybrid strategy, parallel testing

## Support

- **Issues**: https://github.com/Willmac16/git-bifurcate/issues
- **Discussions**: https://github.com/Willmac16/git-bifurcate/discussions
