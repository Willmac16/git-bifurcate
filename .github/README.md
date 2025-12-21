# GitHub Configuration

This directory contains GitHub-specific configuration files for CI/CD, issue templates, and repository automation.

## Workflows

### 🧪 [test.yml](workflows/test.yml)
**Runs on:** Push to main/master/claude/* branches, pull requests

Tests the codebase across multiple Python versions:
- Python 3.12 and 3.13
- Runs full test suite with pytest
- Generates coverage reports
- Uploads coverage to Codecov (requires `CODECOV_TOKEN` secret)
- Uploads HTML coverage report as artifact

**Status Badge:**
```markdown
![Tests](https://github.com/Willmac16/git-bifurcate/actions/workflows/test.yml/badge.svg)
```

### 🎨 [lint.yml](workflows/lint.yml)
**Runs on:** Push to main/master/claude/* branches, pull requests

Code quality checks:
- **Ruff linter** - Fast Python linter (checks code quality)
- **Ruff formatter** - Code formatting checks
- **Mypy** - Static type checking (currently non-blocking)

**Status Badge:**
```markdown
![Lint](https://github.com/Willmac16/git-bifurcate/actions/workflows/lint.yml/badge.svg)
```

### 📦 [build.yml](workflows/build.yml)
**Runs on:** Push to main/master, pull requests, version tags

Build and installation testing:
- Builds Python wheel and sdist using `uv build`
- Tests installation on multiple platforms (Ubuntu, macOS, Windows)
- Tests across Python 3.12 and 3.13
- Verifies CLI is accessible after installation
- Uploads build artifacts

**Status Badge:**
```markdown
![Build](https://github.com/Willmac16/git-bifurcate/actions/workflows/build.yml/badge.svg)
```

### 🚀 [release.yml](workflows/release.yml)
**Runs on:** Version tags (e.g., v1.0.0)

Automated release process:
- Builds the package
- Publishes to PyPI (requires `PYPI_API_TOKEN` secret)
- Creates GitHub release with auto-generated notes
- Attaches distribution files to release

**Creating a release:**
```bash
git tag v0.1.0
git push origin v0.1.0
```

## Dependabot

[dependabot.yml](dependabot.yml) configures automatic dependency updates:
- **Python dependencies** - Weekly updates for pyproject.toml
- **GitHub Actions** - Weekly updates for workflow dependencies

## Issue Templates

- **Bug Report** ([bug_report.yml](ISSUE_TEMPLATE/bug_report.yml)) - Structured bug reporting
- **Feature Request** ([feature_request.yml](ISSUE_TEMPLATE/feature_request.yml)) - Feature suggestions with phase alignment
- **Config** ([config.yml](ISSUE_TEMPLATE/config.yml)) - Links to discussions and docs

## Pull Request Template

[pull_request_template.md](pull_request_template.md) provides a checklist for contributors:
- Description and type of change
- Testing checklist
- Code quality verification
- Documentation updates

## Required Secrets

To enable all workflows, add these secrets in repository settings:

### Optional (for full functionality)
- `CODECOV_TOKEN` - For uploading coverage reports to Codecov
  - Get from: https://codecov.io/
  - Used in: test.yml

### Required for releases
- `PYPI_API_TOKEN` - For publishing to PyPI
  - Get from: https://pypi.org/manage/account/token/
  - Used in: release.yml
  - Scope: Project-specific token for git-bifurcate

## Badge Setup

Add these badges to your README.md:

```markdown
[![Tests](https://github.com/Willmac16/git-bifurcate/actions/workflows/test.yml/badge.svg)](https://github.com/Willmac16/git-bifurcate/actions/workflows/test.yml)
[![Lint](https://github.com/Willmac16/git-bifurcate/actions/workflows/lint.yml/badge.svg)](https://github.com/Willmac16/git-bifurcate/actions/workflows/lint.yml)
[![Build](https://github.com/Willmac16/git-bifurcate/actions/workflows/build.yml/badge.svg)](https://github.com/Willmac16/git-bifurcate/actions/workflows/build.yml)
[![codecov](https://codecov.io/gh/Willmac16/git-bifurcate/branch/main/graph/badge.svg)](https://codecov.io/gh/Willmac16/git-bifurcate)
[![PyPI version](https://badge.fury.io/py/git-bifurcate.svg)](https://badge.fury.io/py/git-bifurcate)
```

## Enabling GitHub Actions

GitHub Actions should be automatically enabled for this repository. If workflows don't run:

1. Go to repository Settings → Actions → General
2. Under "Actions permissions", select "Allow all actions and reusable workflows"
3. Under "Workflow permissions", ensure "Read and write permissions" is selected
4. Enable "Allow GitHub Actions to create and approve pull requests" for Dependabot

## Local Development

Run the same checks locally before pushing:

```bash
# Run tests with coverage
uv run pytest

# Run linter
uv run ruff check src tests

# Run formatter
uv run ruff format src tests

# Run type checker
uv run mypy src

# Build package
uv build
```

## Troubleshooting

### Workflow fails on Python 3.13
- Check if all dependencies support Python 3.13
- May need to add `continue-on-error: true` temporarily

### Coverage upload fails
- Ensure `CODECOV_TOKEN` secret is set
- The workflow continues even if Codecov upload fails

### Release workflow fails
- Verify `PYPI_API_TOKEN` is set and valid
- Ensure version in pyproject.toml matches the tag
- Check that version doesn't already exist on PyPI
