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
- `file`: Binary search across files only (default, implemented ✅)
- `hunk`: Binary search across individual hunks (implemented ✅)
- `hybrid`: File-level first, then drill down to hunk-level (planned, not implemented ❌)

**State**: Persistent bifurcation state saved to `.git/bifurcate-state.json` for resumption

### Key Data Models (Python)

```python
@dataclass
class FileChange:
    file_path: str
    change_type: str  # 'added', 'modified', 'deleted'
    diff: str
    is_submodule: bool = False
    submodule_commits: tuple[str, str] | None = None

@dataclass
class HunkChange:
    file_path: str
    hunk_index: int
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]
    header: str

@dataclass
class BifurcationState:
    commit_sha: str
    parent_sha: str
    strategy: Strategy
    test_command: str
    file_changes: list[FileChange]
    hunk_changes: list[HunkChange] | None
    search_space: list[int]  # Indices still being tested
    tested_combinations: dict[str, CommandResult]
    found_breaking_indices: list[int]
    working_dir: str
    created_at: str
    analyze_deps: bool
```

## Key Algorithms

### Binary Search with Dependencies

The core algorithm performs binary search but must handle dependencies between changes (e.g., import statements depend on function definitions):

1. Split search space in half
2. Expand each half to include all dependencies
3. Test each half
4. Narrow search space based on results
5. Handle special case: both halves pass but together they fail (interaction)

### Dependency Detection (Implemented ✅)

Multi-language static analysis implemented in `dependency_analyzer.py` and `dependency_graph.py`:
1. **Static Analysis** (Implemented):
   - **Python**: AST-based parsing for functions, classes, imports
   - **C/C++, Rust, Go, Swift, Zig, Verilog**: Regex-based symbol extraction
   - Detects definitions vs references
   - Builds dependency graph with transitive closure
2. **Contextual Dependencies**: Hunks within 5 lines marked as potentially dependent
3. **Graph Algorithms**: Topological sort, independent sets, minimal testable subsets

Enabled with `--analyze-deps` flag.

### Change Application Strategies

- **Temporary Commits** (recommended): Create temp branch, commit changes, test, reset
- **Patch Application**: Use `git apply` to apply/revert without commits
- **Worktrees**: Create separate worktrees for parallel testing

## Implementation Status

**✅ Phase 1 - MVP**: File-level bifurcation, automated mode, state persistence - COMPLETE

**✅ Phase 2 - Hunk Level**: Parse hunks, hunk-level bifurcation - COMPLETE
- ❌ Hybrid strategy - NOT YET IMPLEMENTED

**✅ Phase 3 - Robustness**: Multi-language dependency detection, skip problematic combinations - COMPLETE
- ❌ Manual mode - NOT YET IMPLEMENTED

**✅ Phase 4 - Advanced Features**: Multiple breaking changes (--find-more), commit bisection, path filtering, submodule support - COMPLETE
- ❌ Parallel testing - NOT YET IMPLEMENTED
- ❌ GUI/TUI - NOT YET IMPLEMENTED

**✅ Phase 5 - Production Quality**: 99.9% test coverage, CI/CD, linting, type checking - COMPLETE

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

**Language:** Python 3.12+
**Package Manager:** uv (modern Python package manager)

```bash
# Setup development environment
uv venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows
uv pip install -e .

# Run all checks (linting + tests + coverage)
./test

# Run only linting and type checks
./test --lint-only

# Run only tests with coverage (HTML and XML reports)
./test --test-only

# Run specific test file
uv run pytest tests/test_core.py

# Run specific test function
uv run pytest tests/test_core.py::test_bifurcate_files -v

# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Fix auto-fixable lint issues
uv run ruff check --fix .

# Type check
uv run ty check src/

# Install pre-commit hooks (runs on every commit)
uv run pre-commit install

# Run pre-commit on all files
uv run pre-commit run --all-files

# Build package
uv build
```

## File Structure (Actual Implementation)

```
git-bifurcate/
├── DESIGN.md                    # High-level design document
├── ARCHITECTURE.md              # Implementation details and algorithms
├── README.md                    # User documentation
├── CLAUDE.md                    # This file
├── LICENSE                      # MIT License
├── pyproject.toml               # Python package configuration
├── .github/workflows/           # CI/CD pipelines
│   ├── test.yml                # Test workflow (99.9% coverage requirement)
│   ├── lint.yml                # Linting and type checking
│   ├── build.yml               # Build verification
│   └── release.yml             # Automated releases
├── src/git_bifurcate/          # Source code (3,871 LOC)
│   ├── __init__.py             # Package initialization
│   ├── cli.py                  # CLI interface (Click framework)
│   ├── core.py                 # Bifurcation engine (binary search)
│   ├── git_ops.py              # Git operations (GitPython wrapper)
│   ├── parser.py               # Diff parsing
│   ├── models.py               # Data models (FileChange, HunkChange, State)
│   ├── dependency_analyzer.py  # Multi-language static analysis
│   ├── dependency_graph.py     # Dependency graph algorithms
│   ├── commit_bisect.py        # Commit-level bisection
│   └── test_runner.py          # Test execution with timeout
├── tests/                      # Test suite (9,061 LOC, 215 tests)
│   ├── conftest.py             # Shared fixtures
│   ├── test_cli.py             # CLI tests (1,860 lines)
│   ├── test_git_ops.py         # Git operations tests (1,716 lines)
│   ├── test_core.py            # Core engine tests (964 lines)
│   ├── test_multi_language_dependencies.py
│   ├── test_dependency_detection.py
│   ├── test_dependency_analyzer.py
│   ├── test_models.py
│   ├── test_commit_bisect.py
│   ├── test_dependency_graph.py
│   ├── test_parser.py
│   ├── test_integration.py
│   └── test_test_runner.py
├── benchmarks/                 # Performance benchmarks
│   └── benchmark_suite.py
└── test                        # Test runner script
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

## Testing Infrastructure (Production Quality)

**Coverage:** 99.9% (enforced by CI/CD)
**Tests:** 215 test functions across 13 test files
**Test Code:** 9,061 lines (2.3x more than source code)

### Test Categories

1. **Unit Tests**: Test individual functions and classes in isolation
   - Core bifurcation engine (`test_core.py`)
   - Git operations (`test_git_ops.py`)
   - Dependency analysis (`test_dependency_analyzer.py`, `test_dependency_graph.py`)
   - Diff parsing (`test_parser.py`)
   - Data models (`test_models.py`)

2. **Integration Tests**: End-to-end workflows with temporary git repositories
   - Full bifurcation sessions
   - State persistence and resumption
   - CLI command tests (`test_cli.py`)

3. **Multi-Language Tests**: Verify dependency detection for 7 languages
   - Python (AST-based)
   - C/C++, Rust, Go, Swift, Zig, Verilog (regex-based)

4. **Edge Case Tests**:
   - Error handling (build failures, test errors)
   - Corrupt state files
   - Submodule changes
   - Interaction detection

### CI/CD (GitHub Actions)

- **test.yml**: Run tests on Python 3.12 and 3.13 with 99.9% coverage requirement
- **lint.yml**: Ruff formatting and linting + type checking with ty
- **build.yml**: Verify package builds
- **release.yml**: Automated releases to PyPI

### Pre-commit Hooks

Automatically run on every commit:
- Ruff formatter check
- Ruff linter
- Type checker (ty)
- Pytest with coverage check

## When Adding New Features

1. **Check Design Docs First**: DESIGN.md and ARCHITECTURE.md define the intended behavior
2. **Maintain State Compatibility**: Ensure new features don't break state file loading
3. **Add Tests**: Create test repository fixtures that exercise the feature
4. **Update Progress Reporting**: Keep user informed of what's happening
5. **Handle Errors Gracefully**: Provide recovery strategies when things go wrong

## Language Choice

**Python 3.12+** (Decided and Implemented ✅)

**Why Python:**
- Fast development and prototyping
- Excellent git library (GitPython)
- Easy string/regex parsing for multi-language analysis
- AST parsing built-in for Python symbol extraction
- Great testing ecosystem (pytest)
- Type hints with Python 3.12+ syntax (PEP 695)
- Modern tooling (uv, ruff, ty)

**Key Dependencies:**
- `gitpython >= 3.1.0` - Git operations
- `click >= 8.1.0` - CLI framework

**Development Tools:**
- `pytest >= 8.0.0` - Testing
- `ruff >= 0.6.0` - Linting and formatting
- `ty >= 0.0.5` - Type checking
- `uv` - Package management

## Git Integration (Implemented ✅)

The tool feels like a native git command:
- ✅ Installed as `git-bifurcate` (can be invoked as `git bifurcate`)
- ✅ Follows git conventions (state in `.git/bifurcate-state.json`, similar CLI to `git bisect`)
- ✅ Worktree-aware state file location
- ✅ Uses GitPython for all git operations
- ✅ Submodule support with automatic initialization
- ✅ Temporary branch management for testing
- ✅ Clean state management (reset cleans up properly)

## Key Insights from Design Phase

1. **Complexity is in Dependencies**: The hard part isn't binary search—it's handling interdependent changes
2. **User Guidance is Critical**: When automated mode struggles, provide clear guidance on switching to manual
3. **State Persistence is Essential**: Users will interrupt; bifurcation must be resumable
4. **Testing is Expensive**: Each iteration runs the test suite; minimize iterations
5. **Multiple Breaking Changes are Common**: Large commits often have multiple bugs; support finding all of them
