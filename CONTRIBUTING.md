# Contributing to kenso

Thanks for your interest in contributing to kenso! This guide will help you get started.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/fvena/kenso.git
cd kenso

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev,yaml]"

# Install pre-commit hooks
pre-commit install --hook-type commit-msg
```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=kenso --cov-report=term-missing

# Run linter
ruff check src/ tests/
```

## Code Style

- **Linter**: [Ruff](https://docs.astral.sh/ruff/) handles linting and import sorting
- **Line length**: 99 characters
- **Target**: Python 3.11+
- **Type hints**: use `from __future__ import annotations` in all modules

Run `ruff check src/ tests/` before committing. The CI pipeline will catch any issues.

## Commit Messages

This project uses [Conventional Commits](https://www.conventionalcommits.org/) to automate versioning and changelog generation.

Format: `<type>(<scope>): <description>`

| Type | When to use |
|------|-------------|
| `feat` | New feature (triggers minor version bump) |
| `fix` | Bug fix (triggers patch version bump) |
| `perf` | Performance improvement (triggers patch bump) |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `docs` | Documentation only |
| `test` | Adding or updating tests |
| `ci` | CI/CD changes |
| `chore` | Maintenance tasks |

Examples:

```
feat(search): add prefix matching for single-word queries
fix(ingest): handle empty frontmatter blocks without crashing
docs: add editor integration examples for VS Code
test(backend): add unit tests for deduplication logic
```

A pre-commit hook validates your commit message format automatically.

## Pull Request Process

1. **Fork** the repository and create a feature branch from `main`
2. **Write tests** for any new functionality
3. **Ensure all tests pass** (`pytest`) and linting is clean (`ruff check src/ tests/`)
4. **Keep commits atomic** — one logical change per commit
5. **Write a clear PR description** explaining what and why

### PR Checklist

- [ ] Tests added/updated for changes
- [ ] All tests pass locally
- [ ] Ruff linting passes
- [ ] Commit messages follow Conventional Commits
- [ ] Documentation updated if needed

## Project Structure

```
src/kenso/
├── __init__.py      # Version
├── __main__.py      # python -m kenso entry point
├── backend.py       # SQLite FTS5 backend, search, CRUD
├── cli.py           # Command-line interface
├── config.py        # Environment-based configuration
├── ingest.py        # Markdown parsing, chunking, ingestion
├── schema.py        # SQLite DDL
└── server.py        # FastMCP server and tool definitions

tests/
├── test_config.py   # Configuration tests
├── test_backend.py  # Backend search and CRUD tests
├── test_ingest.py   # Parsing and chunking tests
└── eval/            # Search quality benchmarks
```

## Reporting Bugs

Open an issue with:

- kenso version (`kenso --version`)
- Python version
- Steps to reproduce
- Expected vs. actual behavior

## Questions?

Open a [Discussion](https://github.com/fvena/kenso/discussions) or an issue labeled `question`.
