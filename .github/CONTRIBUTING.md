# Contributing to git-bifurcate

Thank you for considering contributing to git-bifurcate! This document provides guidelines and instructions for contributing.

## Getting Started

### Prerequisites

- Python 3.12 or higher
- Git
- [uv](https://docs.astral.sh/uv/) package manager

### Development Setup

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/YOUR-USERNAME/git-bifurcate.git
   cd git-bifurcate
   ```

2. **Install dependencies**
   ```bash
   uv sync --all-extras --dev
   ```

3. **(Optional) Install pre-commit hooks**
   ```bash
   uv run pre-commit install
   ```

4. **Run tests to verify setup**
   ```bash
   ./test --test-only
   ```

## Development Workflow

### Making Changes

1. **Create a branch**
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bug-fix
   ```

2. **Make your changes**
   - Write code following the project's style (see Code Style below)
   - Add tests for new functionality
   - Update documentation as needed

3. **Run quality checks**
   ```bash
   # Full CI-equivalent suite
   ./test

   # Linting and type checks only
   ./test --lint-only

   # Tests with coverage only
   ./test --test-only
   ```

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "Brief description of changes"
   ```

   Use clear, descriptive commit messages. Follow conventional commits format:
   - `feat:` for new features
   - `fix:` for bug fixes
   - `docs:` for documentation changes
   - `test:` for test changes
   - `refactor:` for code refactoring

5. **Push and create a pull request**
   ```bash
   git push origin feature/your-feature-name
   ```
   Then open a pull request on GitHub.

## Code Style

This project uses:
- **Ruff** for linting and formatting (configured in pyproject.toml)
- **Mypy** for static type checking
- Line length: 100 characters
- Python 3.12+ features encouraged

### Type Hints

All functions should include type hints:

```python
def bifurcate_files(
    self, changes: list[FileChange], base_commit: str, verbose: bool = True
) -> FileChange | None:
    """Binary search through file changes."""
    # implementation
```

### Docstrings

Use Google-style docstrings:

```python
def function_name(param1: str, param2: int) -> bool:
    """Brief description of function.

    Longer description if needed, explaining the purpose
    and behavior of the function.

    Args:
        param1: Description of param1.
        param2: Description of param2.

    Returns:
        Description of return value.

    Raises:
        GitOperationError: When git operation fails.
    """
```

## Testing

### Writing Tests

- Place tests in the `tests/` directory
- Name test files as `test_*.py`
- Use pytest fixtures for common setup
- Aim for >80% code coverage

Example test structure:

```python
def test_bifurcate_finds_breaking_change(git_repo: Path) -> None:
    """Test that bifurcation finds the breaking change."""
    # Arrange
    repo = GitRepo(git_repo)
    changes = create_test_changes()

    # Act
    result = engine.bifurcate_files(changes, "base_sha")

    # Assert
    assert result is not None
    assert result.file_path == "expected.py"
```

### Running Tests

```bash
# Full CI-equivalent suite (lint, type check, tests with coverage)
./test

# Linting and type checks only
./test --lint-only

# Test suite only (with coverage reports)
./test --test-only

# Run specific test file
uv run pytest tests/test_core.py

# Run specific test
uv run pytest tests/test_core.py::test_bifurcate_finds_breaking_change

# Run verbose
uv run pytest -v
```

## Architecture Guidelines

Refer to these documents for design guidance:
- **DESIGN.md** - High-level concepts and user-facing behavior
- **ARCHITECTURE.md** - Implementation details and algorithms
- **CLAUDE.md** - Development patterns and common challenges

### Phase Alignment

The project is developed in phases:
- **Phase 1** - MVP (File-level bifurcation) ✅ Complete
- **Phase 2** - Hunk-level bifurcation ✅ Complete
- **Phase 3** - Robustness (Multi-language dependencies, skip logic) ✅ Complete
- **Phase 4** - Advanced (Multiple breaking changes, commit bisection, path filtering, submodules) ✅ Complete
- **Phase 5** - Production Quality (99.9% coverage, CI/CD) ✅ Complete
- **Phase 6** - Future (Hybrid strategy, manual mode, parallel testing, TUI) 🚧 Planned

When adding features, consider which phase they belong to and the project's current focus on stability and usability improvements.

## Pull Request Process

1. **Ensure CI passes**
   - All tests pass
   - Linting passes
   - Type checking passes
   - Code coverage maintained or improved

2. **Update documentation**
   - Update README.md if adding user-facing features
   - Add docstrings to new functions
   - Update ARCHITECTURE.md for architectural changes

3. **Describe your changes**
   - Use the pull request template
   - Link related issues
   - Explain the "why" behind changes

4. **Respond to feedback**
   - Address review comments
   - Push updates to the same branch
   - Mark conversations as resolved

5. **Squash commits** (if requested)
   - Maintainers may ask you to squash commits before merging

## Code Review

All submissions require review. We use GitHub pull requests for this purpose.

Reviewers will check:
- Code quality and style
- Test coverage
- Documentation completeness
- Alignment with project architecture
- Performance implications

## Reporting Bugs

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.yml) and include:
- Clear description of the bug
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version, git-bifurcate version)
- Relevant logs or error messages

## Suggesting Features

Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.yml) and include:
- Problem you're trying to solve
- Proposed solution
- Use cases and examples
- Which implementation phase this relates to

## Questions?

- Open a [Discussion](https://github.com/Willmac16/git-bifurcate/discussions)
- Check existing issues and pull requests
- Read the documentation in README.md, DESIGN.md, and ARCHITECTURE.md

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
